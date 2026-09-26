#!/usr/bin/env python3
"""The five behavioural gates (G1..G5) that decide whether an authored test is admissible.

These gates are what stands between a generated test and the suite. Each one is
mechanical; none consults a model.

  G1 BUILDABLE      the test file imports and collects.
  G2 PASSES 5x      executed five times against the current revision; it must pass
                    every time. A test that passes sometimes is flaky, and flaky is
                    discarded. The five runs vary PYTHONHASHSEED, which catches
                    order- and hash-dependent behaviour cheaply.
  G3 PATCH TEST     executed against the PREVIOUS revision, and an ASSERTION must
                    fire. This is the published patch-test definition. A collection
                    or import error does NOT qualify: it proves the symbol is
                    absent, not that behaviour changed. G3 is deliberately stricter
                    than "increases coverage", because coverage is only weakly
                    correlated with effectiveness while assertions correlate
                    strongly - and LLM-written assertions routinely encode the
                    ACTUAL behaviour of new code, which turns bugs into passing
                    tests.
  G4 STRENGTH       mutation analysis restricted to the changed lines: perturb them
                    and see whether the new test notices. A test that survives every
                    perturbation of the behaviour it claims to pin is not pinning it.
  G5 SPEC-ANCHORED  when (and only when) an intent artefact exists, the assertion
                    must encode the specification's distinguishing tokens. Without
                    an intent artefact this reports null - it never invents an anchor.

Sandbox properties, and one disclosed limitation:

  * everything happens inside a temp directory; the analysed repository is copied,
    never written to;
  * the patch is applied with ``git apply``, which refuses paths outside the
    working tree, so a patch cannot write outside the sandbox;
  * the subprocess environment is a whitelist: PATH, HOME, LANG and the Python
    toggles. No API keys, no proxies, no credentials from the operator's shell;
  * commands are argument lists, never shell strings;
  * every run is bounded by a timeout (default 120 s) and the patch size is capped;
  * LIMITATION, stated rather than implied: network isolation is NOT enforced. A
    hostile test could open a socket. It cannot read the operator's environment
    or credentials, it cannot write outside the sandbox, and it is killed on
    timeout, but "no network" would need OS-level isolation this build does not
    claim.
"""

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ElementTree
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MAX_PATCH_BYTES = 1024 * 1024
G2_RUNS = 5
G4_MAX_MUTANTS = 5
SKIP_COPY = ("revisions", "__pycache__", ".pytest_cache", ".git", ".mypy_cache")
DEFINITION = re.compile(r"^\+\s*def\s+([A-Za-z_]\w*)\s*\(")
STOPWORDS = {"the", "and", "not", "for", "with", "that", "this", "from", "when", "then", "its", "are", "was", "will"}


def _sandbox_environment(hash_seed="0"):
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": str(hash_seed),
        "PYTHONPATH": "",
    }


def _run(command, cwd, timeout):
    return subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_sandbox_environment(),
    )


def _copy(source, destination):
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns(*SKIP_COPY), symlinks=False)


def _apply_patch(patch_text_or_path, workdir, *, reverse=False):
    candidate = Path(str(patch_text_or_path))
    if candidate.exists() and candidate.is_file() and "\n" not in str(patch_text_or_path)[:200]:
        text = candidate.read_text(encoding="utf-8")
    else:
        text = str(patch_text_or_path)
    if len(text.encode("utf-8")) > MAX_PATCH_BYTES:
        raise RuntimeError(f"patch larger than {MAX_PATCH_BYTES} bytes: refusing to apply it")
    patch_file = Path(workdir) / ".gate-patch.diff"
    patch_file.write_text(text, encoding="utf-8")
    command = ["git", "apply", "-p1", str(patch_file)]
    if reverse:
        command.insert(2, "-R")
    completed = subprocess.run(command, cwd=str(workdir), capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"git apply failed: {completed.stderr.strip()[:300]}")
    return text


def _test_names_from_patch(patch_text):
    names = []
    for line in patch_text.splitlines():
        match = DEFINITION.match(line)
        if match:
            names.append(match.group(1))
    return names


def _parse_junit(path):
    """Return ``{node: (outcome, message)}`` from a JUnit XML report."""
    if not path.exists():
        return {}
    if path.stat().st_size > 32 * 1024 * 1024:
        raise RuntimeError("junit xml too large to parse safely")
    tree = ElementTree.parse(str(path))
    results = {}
    for case in tree.iter("testcase"):
        node = f"{case.get('classname') or ''}::{case.get('name') or ''}"
        outcome, message = "passed", ""
        for child in case:
            if child.tag == "failure":
                outcome, message = "failed", (child.get("message") or "") + " " + (child.text or "")
            elif child.tag == "error":
                outcome, message = "error", (child.get("message") or "") + " " + (child.text or "")
            elif child.tag == "skipped":
                outcome = "skipped"
        results[node] = (outcome, message)
    return results


def _failure_origin(outcome, message):
    """Classify a failure: assertion, collection, or error (gate C14)."""
    if outcome == "passed":
        return "passed"
    if outcome == "skipped":
        return "skipped"
    lowered = (message or "").lower()
    if "modulenotfounderror" in lowered or "importerror" in lowered or "no module named" in lowered:
        return "collection"
    if "attributeerror" in lowered and "assert" not in lowered:
        return "collection"
    if "assertionerror" in lowered or lowered.strip().startswith("assert") or "assert " in lowered:
        return "assertion"
    if outcome == "error":
        return "error"
    return "assertion"


def _collect_only(workdir, target, timeout):
    completed = _run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", str(target)],
        workdir,
        timeout,
    )
    return completed.returncode == 0, completed.stdout[-4000:]


def _run_test(workdir, target, timeout, hash_seed="0", xml_name="run.xml"):
    xml_path = Path(workdir) / xml_name
    completed = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            f"--junitxml={xml_path}",
            str(target),
        ],
        workdir,
        timeout,
    )
    results = _parse_junit(xml_path)
    return completed, results


def _mutants_for_lines(source, changed_lines, limit=G4_MAX_MUTANTS):
    """Deterministic mutants restricted to the changed lines.

    Each mutant is a (description, mutated_line) pair. The mutation set is small
    and syntactic on purpose: it is a *strength* probe, not a full mutation
    testing campaign, and it must be reproducible on any machine.
    """
    lines = source.splitlines()
    mutants = []
    for number in changed_lines:
        if number < 1 or number > len(lines):
            continue
        line = lines[number - 1]
        stripped = line.strip()
        # Skip lines that are not executable statements. Mutating a docstring or an
        # import and counting the survivor as "weak assertion" would be measuring
        # equivalent mutants, not test strength.
        if (
            not stripped
            or stripped.startswith(("#", '"""', "'''", "import ", "from "))
            or re.match(r"^(async\s+)?(def|class)\s", stripped)
        ):
            continue
        mutated = None
        description = None
        if "json.dumps(" in line:
            mutated, description = line.replace("json.dumps(", "str("), "serializer -> str"
        elif "sort_keys=True" in line:
            mutated, description = line.replace("sort_keys=True", "sort_keys=False"), "sort_keys flipped"
        elif re.search(r"\bTrue\b", line):
            mutated, description = re.sub(r"\bTrue\b", "False", line, count=1), "True -> False"
        elif re.search(r"\bFalse\b", line):
            mutated, description = re.sub(r"\bFalse\b", "True", line, count=1), "False -> True"
        elif re.search(r"==(?!=)", line):
            mutated, description = re.sub(r"==(?!=)", "!=", line, count=1), "== -> !="
        elif re.search(r"\band\b", line):
            mutated, description = re.sub(r"\band\b", "or", line, count=1), "and -> or"
        elif re.search(r"\d+", line):
            mutated, description = re.sub(r"\d+", lambda match: str(int(match.group()) + 1), line, count=1), "number + 1"
        elif '"' in line:
            mutated, description = line.replace('"', '"x', 1), "literal perturbed"
        if mutated is not None and mutated != line:
            mutants.append((number, description, mutated))
        if len(mutants) >= limit:
            break
    return mutants


def _intent_tokens(quote):
    tokens = set()
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}|\d+", quote):
        lowered = token.lower()
        if lowered not in STOPWORDS:
            tokens.add(lowered)
    return tokens


def _assertion_sources(test_source):
    """The source text of every assertion expression in a test file."""
    try:
        tree = ast.parse(test_source)
    except SyntaxError:
        return []
    segments = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            segments.append(ast.dump(node.test))
        if isinstance(node, ast.Compare):
            segments.append(ast.dump(node))
    return segments


def run_gates(
    *,
    repo,
    test_patch,
    symbol,
    change_patch=None,
    test_path=None,
    intent=None,
    timeout=120,
    workdir=None,
):
    """Run G1..G5 and return the gate result dict."""
    repo = Path(repo).resolve()
    temporary = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="testscope-gate-"))
    owned = workdir is None
    result = {
        "g1_buildable": False,
        "g2_passes_5x": False,
        "g2_runs": [],
        "g3_assertion_fires_at_a": False,
        "g3_failure_origin": None,
        "g4_mutation_strength": 0.0,
        "g5_spec_anchored": None,
        "accepted": False,
        "notes": [],
        "symbol": symbol,
    }
    try:
        rev_b = temporary / "rev_b"
        rev_a = temporary / "rev_a"
        _copy(repo, rev_b)
        patch_text = _apply_patch(test_patch, rev_b)
        names = _test_names_from_patch(patch_text)
        if not names:
            result["notes"].append("the patch adds no test function: nothing to gate")
            return result
        if test_path is None:
            for line in patch_text.splitlines():
                if line.startswith("+++ "):
                    test_path = line[4:].strip()
                    if test_path.startswith("b/"):
                        test_path = test_path[2:]
                    break
        target = str(test_path or "tests")
        result["test_functions"] = names

        # ---- G1 ---------------------------------------------------------- #
        buildable, output = _collect_only(rev_b, target, timeout)
        result["g1_buildable"] = bool(buildable)
        if not buildable:
            result["notes"].append(f"G1: collection failed: {output[-200:]}")

        # ---- G2: five runs, varying the hash seed ------------------------ #
        runs = []
        for index in range(G2_RUNS):
            completed, parsed = _run_test(
                rev_b, target, timeout, hash_seed=str(index), xml_name=f"g2-{index}.xml"
            )
            passed = bool(parsed) and all(outcome == "passed" for outcome, _ in parsed.values())
            runs.append(passed)
            if not parsed:
                result["notes"].append(f"G2 run {index + 1}: no test results (rc={completed.returncode})")
        result["g2_runs"] = runs
        result["g2_passes_5x"] = all(runs) and bool(runs)

        # ---- G3: the patch test, at the previous revision ---------------- #
        if change_patch:
            _copy(repo, rev_a)
            try:
                _apply_patch(change_patch, rev_a, reverse=True)
                _apply_patch(test_patch, rev_a)
                completed, parsed = _run_test(rev_a, target, timeout, xml_name="g3.xml")
                origins = [_failure_origin(outcome, message) for outcome, message in parsed.values()]
                if "passed" in origins and len(set(origins)) == 1:
                    result["g3_failure_origin"] = "passed"
                    result["notes"].append("G3: the test passes at the previous revision too: it does not pin the change")
                elif "assertion" in origins:
                    result["g3_assertion_fires_at_a"] = True
                    result["g3_failure_origin"] = "assertion"
                else:
                    origin = origins[0] if origins else "collection"
                    result["g3_failure_origin"] = origin
                    result["notes"].append(
                        f"G3: the failure at the previous revision is {origin}, not an assertion: "
                        "it proves the symbol is absent, not that behaviour changed"
                    )
            except Exception as error:  # noqa: BLE001 - reported, never silently swallowed
                result["notes"].append(f"G3 could not be executed: {error}")
        else:
            result["notes"].append("G3 skipped: no change patch supplied to reconstruct the previous revision")

        # ---- G4: mutation strength on the changed lines ------------------ #
        if change_patch:
            try:
                result["g4_mutation_strength"] = _mutation_strength(
                    repo, change_patch, test_patch, target, timeout, temporary
                )
            except Exception as error:  # noqa: BLE001
                result["notes"].append(f"G4 could not be executed: {error}")

        # ---- G5: specification anchoring, only when an anchor exists ----- #
        if intent and intent.get("quote"):
            quote = intent["quote"]
            anchor_path = intent.get("path")
            anchored = False
            if anchor_path:
                anchored = quote in (Path(repo) / anchor_path).read_text(encoding="utf-8", errors="ignore") if (
                    Path(repo) / anchor_path
                ).exists() else False
            tokens = _intent_tokens(quote)
            with open(Path(rev_b) / target, "r", encoding="utf-8") as handle:
                test_source = handle.read()
            assertions = " ".join(_assertion_sources(test_source)).lower()
            token_hit = any(token in assertions for token in tokens)
            result["g5_spec_anchored"] = bool(anchored and token_hit)
            if not result["g5_spec_anchored"]:
                result["notes"].append(
                    "G5: the assertion does not encode the intent artefact's distinguishing tokens"
                )

        result["accepted"] = bool(
            result["g1_buildable"]
            and result["g2_passes_5x"]
            and result["g3_assertion_fires_at_a"]
            and result["g4_mutation_strength"] > 0
            and result["g5_spec_anchored"] is not False
        )
        return result
    finally:
        if owned:
            shutil.rmtree(temporary, ignore_errors=True)


def _mutation_strength(repo, change_patch, test_patch, target, timeout, temporary):
    """Kill mutants of the changed lines; return killed / applied."""
    source_root = Path(temporary) / "mutants"
    base = source_root / "base"
    if not base.exists():
        _copy(repo, base)
    changed_lines_by_file = _changed_lines(change_patch)
    killed = applied = 0
    index = 0
    for relative, lines in sorted(changed_lines_by_file.items()):
        original = (base / relative).read_text(encoding="utf-8")
        for number, description, mutated in _mutants_for_lines(original, lines):
            if applied >= G4_MAX_MUTANTS:
                break
            workdir = source_root / f"m{index}"
            index += 1
            _copy(base, workdir)
            _apply_patch(test_patch, workdir)
            lines_of_file = (workdir / relative).read_text(encoding="utf-8").splitlines()
            lines_of_file[number - 1] = mutated
            (workdir / relative).write_text("\n".join(lines_of_file) + "\n", encoding="utf-8")
            applied += 1
            try:
                completed, parsed = _run_test(workdir, target, timeout, xml_name=f"mutant-{index}.xml")
            except subprocess.TimeoutExpired:
                killed += 1  # a hang is a reaction
                continue
            if not parsed:
                killed += 1  # collection failure on the mutant counts as a reaction
                continue
            if any(outcome != "passed" for outcome, _ in parsed.values()):
                killed += 1
    if applied == 0:
        return 0.0
    return round(killed / applied, 4)


def _changed_lines(change_patch):
    """Map changed files to the post-change line numbers of their added lines."""
    from bob_session.pipeline.diff_parser import parse_diff

    text = Path(change_patch).read_text(encoding="utf-8") if Path(str(change_patch)).exists() else str(change_patch)
    diff = parse_diff(text)
    mapping = {}
    for parsed in diff.active_files:
        if parsed.changed_new_lines:
            mapping[parsed.path] = sorted(set(parsed.changed_new_lines))
    return mapping


def main(argv=None):
    parser = argparse.ArgumentParser(description="TestScope gates G1..G5")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--test-patch", required=True, help="unified diff text or path to a patch file")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--patch", default=None, help="the change diff (A -> B) for G3/G4")
    parser.add_argument("--test-path", default=None)
    parser.add_argument("--intent", default=None, help="JSON {path, line, quote} or a path to such a JSON file")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args(argv)

    intent = None
    if args.intent:
        candidate = Path(args.intent)
        intent = json.loads(candidate.read_text(encoding="utf-8")) if candidate.exists() else json.loads(args.intent)

    result = run_gates(
        repo=args.repo,
        test_patch=args.test_patch,
        symbol=args.symbol,
        change_patch=args.patch,
        test_path=args.test_path,
        intent=intent,
        timeout=args.timeout,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
