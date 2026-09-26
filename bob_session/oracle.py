#!/usr/bin/env python3
"""The oracle: executed ground truth, with its own blindness reported.

It computes the outcome discriminant

    Delta(t) = [ outcome_A(t) != outcome_B(t) ]

by running the **full** suite at both revisions. Delta is a LOWER BOUND on the
affected set - a test can be affected and still pass twice - so it can measure
recall and can never measure precision. That is stated rather than hidden.

Invariant O1: the oracle must select the full population and must assert that it
did. This is not defensive programming, it is a bug that already happened: the
demo repository's ``pytest.ini`` carries ``addopts = -m "not contract"``, so a
default run silently drops the three contract tests - the only tests that
discriminate the change - and the first version of this instrument reported
"no regression" with complete confidence. A recall measurement from a partial
instrument is worse than no measurement, because it looks like evidence.

So the run uses ``-m ""``, asserts ``collected >= inventory_total``, and also
records what a *default* run would have collected, so the blind spot itself is
visible in the output.

Safety properties:
  * the input repository is never mutated: both revisions are materialised into a
    temp directory (``git clone`` for SHAs, a copy plus reverse-applied patch
    otherwise);
  * JUnit XML is parsed rather than stdout, because stdout formats drift between
    pytest versions and a parsing change would silently change ground truth;
  * the XML file size is capped before parsing, and parsing uses the standard
    library only.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ElementTree
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MAX_XML_BYTES = 64 * 1024 * 1024
SKIP_COPY = ("revisions", "__pycache__", ".pytest_cache", ".git", ".mypy_cache")
DEFAULT_RUN_CMD = ["-m", "pytest", "-q", "-p", "no:cacheprovider", "-m", ""]


def _copy_repo(source, destination):
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns(*SKIP_COPY),
        symlinks=False,
    )


def _run(command, cwd, timeout):
    """Run a command list (never a shell string) with a hard timeout."""
    return subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_clean_environment(),
    )


def _clean_environment():
    """A minimal environment: no secrets, no proxy configuration, no network hints.

    The oracle executes the analysed repository's test suite, so it must not
    inherit the operator's API keys or credentials.
    """
    import os

    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
    }
    return environment


def _parse_junit(path):
    """Parse a JUnit XML report into ``{node_id: outcome}`` (sorted by node id)."""
    size = path.stat().st_size
    if size > MAX_XML_BYTES:
        raise RuntimeError(f"junit xml too large to parse safely: {size} bytes")
    tree = ElementTree.parse(str(path))
    outcomes = {}
    for case in tree.iter("testcase"):
        classname = case.get("classname") or ""
        name = case.get("name") or ""
        node = f"{classname}::{name}" if classname else name
        outcome = "passed"
        for child in case:
            tag = child.tag
            if tag == "failure":
                outcome = "failed"
            elif tag == "error":
                outcome = "error"
            elif tag == "skipped":
                outcome = "skipped"
        outcomes[node] = outcome
    return {node: outcomes[node] for node in sorted(outcomes)}


def _collect_only_count(workdir, timeout):
    """How many tests a *default* run would collect (the blind-spot control)."""
    try:
        completed = _run([sys.executable, "-m", "pytest", "--collect-only", "-q"], workdir, timeout)
    except subprocess.TimeoutExpired:
        return None
    text = completed.stdout
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if "test" in stripped and ("collected" in stripped or "selected" in stripped):
            digits = "".join(char if char.isdigit() else " " for char in stripped).split()
            if digits:
                return int(digits[0])
    return len([line for line in text.splitlines() if "::" in line])


def _materialise_revisions(repo, *, patch, rev_a, rev_b, temporary):
    """Return ``(dir_a, dir_b)`` for the two revisions, inside ``temporary``."""
    repo = Path(repo).resolve()
    dir_b = Path(temporary) / "rev_b"
    dir_a = Path(temporary) / "rev_a"
    if rev_a and rev_b:
        for target, revision in ((dir_b, rev_b), (dir_a, rev_a)):
            completed = subprocess.run(
                ["git", "clone", "--quiet", "--no-hardlinks", str(repo), str(target)],
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                raise RuntimeError(f"git clone failed: {completed.stderr.strip()[:200]}")
            checked = subprocess.run(
                ["git", "-C", str(target), "checkout", "--quiet", revision],
                capture_output=True,
                text=True,
            )
            if checked.returncode != 0:
                raise RuntimeError(f"git checkout {revision} failed: {checked.stderr.strip()[:200]}")
        return dir_a, dir_b, "git-shas"
    if not patch:
        raise RuntimeError("either rev_a/rev_b or a patch is required to reconstruct the previous revision")
    _copy_repo(repo, dir_b)
    _copy_repo(repo, dir_a)
    completed = subprocess.run(
        ["git", "apply", "-R", str(Path(patch).resolve())],
        cwd=str(dir_a),
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "could not reconstruct the pre-change revision: the patch does not reverse-apply "
            f"({completed.stderr.strip()[:200]})"
        )
    return dir_a, dir_b, "patch"


def run_oracle(
    *,
    repo,
    patch=None,
    rev_a=None,
    rev_b=None,
    inventory_total=None,
    run_cmd=None,
    timeout=900,
    repeat=1,
):
    """Execute the suite at both revisions and return the oracle result dict."""
    command = list(run_cmd) if run_cmd else list(DEFAULT_RUN_CMD)
    if isinstance(command, str):
        command = command.split()
    temporary = tempfile.mkdtemp(prefix="testscope-oracle-")
    try:
        dir_a, dir_b, mode = _materialise_revisions(
            repo, patch=patch, rev_a=rev_a, rev_b=rev_b, temporary=temporary
        )
        results = {}
        for label, workdir in (("a", dir_a), ("b", dir_b)):
            runs = []
            for attempt in range(max(1, repeat)):
                xml_path = Path(temporary) / f"{label}-{attempt}.xml"
                completed = _run(
                    [sys.executable, *command, f"--junitxml={xml_path}"],
                    workdir,
                    timeout,
                )
                if not xml_path.exists():
                    raise RuntimeError(
                        f"revision {label}: pytest produced no junit xml (rc={completed.returncode}): "
                        f"{completed.stderr.strip()[:300]}"
                    )
                runs.append(_parse_junit(xml_path))
            results[label] = runs

        runs_a, runs_b = results["a"], results["b"]
        collected_a = len(runs_a[0])
        collected_b = len(runs_b[0])
        flaky = set()
        if repeat > 1:
            for runs in (runs_a, runs_b):
                for node in runs[0]:
                    outcomes = {run.get(node) for run in runs}
                    if len(outcomes) > 1:
                        flaky.add(node)
        outcome = {}
        changed = []
        already_red = []
        for node in sorted(set(runs_a[0]) | set(runs_b[0])):
            first_a = runs_a[0].get(node, "missing")
            first_b = runs_b[0].get(node, "missing")
            outcome[node] = {"a": first_a, "b": first_b}
            if node in flaky:
                continue
            if first_a == "passed" and first_b in ("failed", "error"):
                changed.append(node)
            elif first_a in ("failed", "error") and first_b in ("failed", "error"):
                already_red.append(node)
        complete = bool(collected_a == collected_b and inventory_total is not None and collected_a >= inventory_total)
        note_parts = []
        if inventory_total is None:
            note_parts.append("inventory_total not supplied: completeness cannot be asserted (invariant O1)")
        elif collected_a < inventory_total:
            note_parts.append(
                f"VOID: collected {collected_a} < inventory {inventory_total}: the instrument is narrower "
                "than the population it measures"
            )
        if collected_a != collected_b:
            note_parts.append(f"collected differs between revisions ({collected_a} vs {collected_b})")
        if repeat == 1:
            note_parts.append("flakiness detection requires repeat>1; flaky_excluded is empty by construction")
        default_collected = None
        try:
            default_collected = _collect_only_count(dir_b, timeout)
        except Exception as error:  # pragma: no cover - control only
            note_parts.append(f"default-marker collect-only failed: {type(error).__name__}")
        return {
            "collected": collected_a,
            "collected_a": collected_a,
            "collected_b": collected_b,
            "inventory_total": inventory_total,
            "complete": complete,
            "changed": sorted(changed),
            "flaky_excluded": sorted(flaky),
            "already_red": sorted(already_red),
            "outcome": outcome,
            "run_cmd": " ".join(["python", *command]),
            "rev_a": rev_a,
            "rev_b": rev_b,
            "mode": mode,
            "repeat": repeat,
            "default_marker_collected": default_collected,
            "note": "; ".join(note_parts) if note_parts else "full-marker run collected the full inventory",
        }
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="TestScope oracle: executed ground truth")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--patch", default=None, help="diff (A -> B) reverse-applied in a temp copy to get A")
    parser.add_argument("--rev-a", default=None, help="git SHA of the pre-change revision")
    parser.add_argument("--rev-b", default=None, help="git SHA of the post-change revision")
    parser.add_argument("--inventory", default=None, help="inventory file, for the completeness assertion")
    parser.add_argument("--inventory-total", type=int, default=None)
    parser.add_argument("--run-cmd", default=None, help='pytest command, e.g. \'-q -m ""\'')
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--repeat", type=int, default=1, help="runs per revision; >1 enables flakiness detection")
    parser.add_argument("--out", default=None)
    parser.add_argument("--compact", action="store_true", help="omit the per-node outcome map")
    args = parser.parse_args(argv)

    total = args.inventory_total
    if total is None and args.inventory:
        from bob_session.pipeline.inventory import load_inventory

        total = len(load_inventory(Path(args.inventory)))

    result = run_oracle(
        repo=args.repo,
        patch=args.patch,
        rev_a=args.rev_a,
        rev_b=args.rev_b,
        inventory_total=total,
        run_cmd=args.run_cmd.split() if args.run_cmd else None,
        timeout=args.timeout,
        repeat=args.repeat,
    )
    if args.compact:
        result = {key: value for key, value in result.items() if key != "outcome"}
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
