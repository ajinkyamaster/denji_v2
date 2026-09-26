#!/usr/bin/env python3
"""testscope_gate: the five-gate filtration for authored tests (MCP tool 4).

    G1 buildable            the test file imports and collects
    G2 passes at B, 5x      a test that does not pass repeatedly is flaky
    G3 assertion fires at A the failure must be an ASSERTION, never an import
                            or collection error (C14 qualification)
    G4 mutation strength    mutants restricted to the changed lines must be
                            killed, or the assertion is weak
    G5 spec anchor          conditional: when an intent artefact exists, the
                            assertion must match it; otherwise the test PINS
                            and does not SPECIFY

This is the only tool that writes test files, and it writes them inside a
sandbox copy: the input repository is never mutated.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

PASSES = 5
MUTATION_THRESHOLD = 0.5

MUTATORS: List[Tuple[str, "re.Pattern[str]", str]] = [
    ("literal_swap", re.compile(r'"([^"]{1,24})"'), '"\1_MUT"'),
    ("or_to_and", re.compile(r"\bor\b"), "and"),
    ("equality_flip", re.compile(r"=="), "!="),
]


@dataclasses.dataclass
class GateInput:
    tree_a: pathlib.Path
    tree_b: pathlib.Path
    test_node: str
    symbol: str
    added_lines: List[Tuple[str, int]] = dataclasses.field(default_factory=list)
    intent_quote: Optional[str] = None
    intent_path: Optional[str] = None


def _run(tree: pathlib.Path, args: Sequence[str], python: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        [python, "-m", "pytest", "-q", "-p", "no:cacheprovider"] + list(args),
        cwd=tree,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )


def apply_patch(tree: pathlib.Path, patch_path: pathlib.Path) -> Tuple[bool, str]:
    """Apply a unified diff inside a sandbox tree."""
    result = subprocess.run(
        ["patch", "-p1", "-i", str(patch_path), "--forward", "--silent"],
        cwd=tree,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return result.returncode == 0, result.stdout.decode("utf-8", "replace")


def failure_origin(output: str) -> str:
    """Classify a failure: assertion, collection error, or other error."""
    if "error during collection" in output or "ERROR collecting" in output:
        return "collection"
    if re.search(r"^\s*E\s+(ImportError|ModuleNotFoundError|SyntaxError)", output, re.M):
        return "collection"
    if re.search(r"^\s*E\s+(AttributeError|TypeError|KeyError|IndexError|ValueError|NameError)", output, re.M):
        return "error"
    if "AssertionError" in output or re.search(r"^\s*E\s+assert\b", output, re.M):
        return "assertion"
    return "unknown"


def _outcome(result: subprocess.CompletedProcess) -> bool:
    return result.returncode == 0


def collect(tree: pathlib.Path, python: str) -> Tuple[bool, str]:
    result = _run(tree, ["--collect-only", "-q", "-m", ""], python)
    return _outcome(result), result.stdout.decode("utf-8", "replace")


def run_node(tree: pathlib.Path, node: str, python: str) -> Tuple[bool, str]:
    result = _run(tree, [node, "-m", ""], python)
    return _outcome(result), result.stdout.decode("utf-8", "replace")


def mutant_lines(lines: Sequence[Tuple[str, int]]) -> List[Tuple[str, int, str]]:
    """Textual mutants restricted to the changed lines of the target symbol.

    Every applicable operator on every changed line, not only the first: a
    weak assertion often survives one mutation while dying on another, and
    restricting the mutation budget to the changed lines keeps this cheap.
    """
    out: List[Tuple[str, int, str]] = []
    seen = set()
    for text, number in lines:
        stripped = text.strip()
        if not stripped or stripped.startswith(("#", "@", '"""')):
            continue
        candidates: List[Tuple[str, str]] = []
        for name, pattern, replacement in MUTATORS:
            mutated = pattern.sub(replacement, text, count=1)
            if mutated != text:
                candidates.append((name, mutated))
        mutated_all = re.sub(r'"([A-Za-z_][^"]*)"', '"\\1_MUT"', text)
        if mutated_all != text:
            candidates.append(("literal_swap_all", mutated_all))
        for name, mutated in candidates:
            marker = (number, mutated)
            if marker in seen:
                continue
            seen.add(marker)
            out.append((f"{name}:{number}", number, mutated))
    return out


def kill_mutants(
    tree_b: pathlib.Path,
    *,
    test_node: str,
    added_lines: Sequence[Tuple[str, int]],
    python: str,
    patch_path: Optional[pathlib.Path] = None,
) -> Tuple[int, int, List[str]]:
    """Apply each mutant to the sandbox and check whether the test kills it."""
    killed = 0
    survivors: List[str] = []
    mutants = mutant_lines(added_lines)
    original = {number: text for text, number in added_lines}
    for name, number, mutated in mutants:
        source_lines = tree_b.joinpath().resolve()
        target = _find_file_containing(tree_b, original[number])
        if target is None:
            continue
        backup = target.read_text(encoding="utf-8")
        text_lines = backup.splitlines()
        if number - 1 >= len(text_lines):
            continue
        text_lines[number - 1] = mutated
        target.write_text("\n".join(text_lines) + ("\n" if backup.endswith("\n") else ""), encoding="utf-8")
        try:
            passed, _ = run_node(tree_b, test_node, python)
            if not passed:
                killed += 1
            else:
                survivors.append(name)
        finally:
            target.write_text(backup, encoding="utf-8")
    return killed, len(mutants), survivors


def _find_file_containing(tree: pathlib.Path, needle: str) -> Optional[pathlib.Path]:
    for path in sorted(tree.rglob("*.py")):
        try:
            if needle in path.read_text(encoding="utf-8"):
                return path
        except OSError:
            continue
    return None


def run_gate(
    gate_input: GateInput,
    *,
    python: str = sys.executable,
    passes: int = PASSES,
    threshold: float = MUTATION_THRESHOLD,
) -> dict:
    """Execute G1..G5 and return the gate evidence."""
    g2_runs: List[bool] = []
    for _ in range(passes):
        passed, output = run_node(gate_input.tree_b, gate_input.test_node, python)
        g2_runs.append(passed)
    g2_passes = all(g2_runs)

    failed_a, output_a = run_node(gate_input.tree_a, gate_input.test_node, python)
    origin = failure_origin(output_a) if not failed_a else "none"
    g3_fires = (not failed_a) and origin == "assertion"

    killed, total, survivors = kill_mutants(
        gate_input.tree_b,
        test_node=gate_input.test_node,
        added_lines=gate_input.added_lines,
        python=python,
    )
    strength = (killed / total) if total else 0.0
    g4_ok = bool(total) and strength >= threshold

    g5: Optional[bool] = None
    if gate_input.intent_quote:
        path = gate_input.tree_b / (gate_input.intent_path or "")
        present = path.exists() and gate_input.intent_quote in path.read_text(encoding="utf-8", errors="replace")
        g5 = bool(present)

    accepted = g2_passes and g3_fires and g4_ok and (g5 is not False)
    detail = "all gates passed"
    if not g2_passes:
        detail = f"G2 failed: the test did not pass on every one of {passes} executions"
    elif not g3_fires:
        detail = f"G3 failed: at the base revision the test failed with origin={origin!r} (an assertion must fire)"
    elif not g4_ok:
        detail = f"G4 failed: mutation strength {strength:.2f} below threshold {threshold} (survivors: {survivors})"
    elif g5 is False:
        detail = "G5 failed: the asserted behaviour does not match the cited intent artefact"

    return {
        "symbol": gate_input.symbol,
        "test_node": gate_input.test_node,
        "accepted": accepted,
        "g1_buildable": True,
        "g2_passes_5x": g2_passes,
        "g2_runs": g2_runs,
        "g3_assertion_fires_at_a": g3_fires,
        "g3_failure_origin": origin,
        "g4_mutation_strength": round(strength, 4),
        "g4_mutants_killed": killed,
        "g4_mutants_total": total,
        "g5_spec_anchored": g5,
        "capability": "SPECIFIES" if g5 else "PINS",
        "detail": detail,
    }


def run_for_patch(
    *,
    repo: str,
    patch_path: str,
    test_node: str,
    symbol: str,
    rev_a: str,
    rev_b: str,
    python: str = sys.executable,
    workdir: Optional[str] = None,
) -> dict:
    """Export both revisions, apply the author's patch, run G1..G5."""
    from bob_session.oracle import export_revision

    holder = pathlib.Path(workdir) if workdir else pathlib.Path(tempfile.mkdtemp(prefix="testscope-gate-"))
    tree_a = holder / "rev-a"
    tree_b = holder / "rev-b"
    export_revision(repo, rev_a, tree_a)
    export_revision(repo, rev_b, tree_b)
    patch = pathlib.Path(patch_path).resolve()
    ok_a, out_a = apply_patch(tree_a, patch)
    ok_b, out_b = apply_patch(tree_b, patch)
    if not (ok_a and ok_b):
        return {
            "symbol": symbol,
            "test_node": test_node,
            "accepted": False,
            "g1_buildable": False,
            "detail": f"the patch does not apply: {out_a.strip() or out_b.strip()}",
        }
    buildable_a, output = collect(tree_a, python)
    buildable_b, output_b = collect(tree_b, python)
    evidence = run_gate(
        GateInput(
            tree_a=tree_a,
            tree_b=tree_b,
            test_node=test_node,
            symbol=symbol,
            added_lines=_added_lines_for(repo, rev_a, rev_b, symbol),
        ),
        python=python,
    )
    evidence["g1_buildable"] = buildable_a and buildable_b
    evidence["accepted"] = bool(evidence["accepted"] and evidence["g1_buildable"])
    if not evidence["g1_buildable"]:
        evidence["detail"] = "G1 failed: the patched tree does not collect"
    return evidence


def _added_lines_for(repo: str, rev_a: str, rev_b: str, symbol: str) -> List[Tuple[str, int]]:
    """The changed lines of a symbol, from the diff between two revisions."""
    import subprocess

    from bob_session.pipeline import diffparse
    from bob_session.pipeline.index import RepoIndex

    diff_text = subprocess.run(
        ["git", "-C", repo, "diff", rev_a, rev_b],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout.decode("utf-8", "replace")
    file_changes = diffparse.parse_diff(diff_text)
    index = RepoIndex(pathlib.Path(repo))
    for file_change in file_changes:
        if not file_change.is_python:
            continue
        module = index.module_of_path(file_change.path) or file_change.path
        post_text = (index.root / file_change.path).read_text(encoding="utf-8")
        for change in diffparse.attribute(file_change, post_text, module):
            if change.symbol == symbol.rsplit(".", 1)[-1]:
                return list(change.added)
    return []


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="demo")
    parser.add_argument("--patch", default="bob_session/roles/patches/author_should_drop.patch")
    parser.add_argument("--test-node", default="tests/test_cache_service.py::test_evict_expired_drops_status_expired")
    parser.add_argument("--symbol", default="app.services.cache_service._should_drop")
    parser.add_argument("--revisions", default="bob_session/evidence/revisions.json")
    parser.add_argument("--out", default="bob_session/evidence/gate_author.json")
    args = parser.parse_args(argv)

    revisions = json.loads(pathlib.Path(args.revisions).read_text(encoding="utf-8"))
    evidence = run_for_patch(
        repo=args.repo,
        patch_path=args.patch,
        test_node=args.test_node,
        symbol=args.symbol,
        rev_a=revisions["rev_a"],
        rev_b=revisions["rev_b"],
    )
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"gate: {args.test_node} for {args.symbol}")
    print(f"  G1 {evidence.get('g1_buildable')} G2 {evidence.get('g2_passes_5x')} "
          f"G3 {evidence.get('g3_assertion_fires_at_a')} ({evidence.get('g3_failure_origin')}) "
          f"G4 {evidence.get('g4_mutation_strength')} G5 {evidence.get('g5_spec_anchored')}")
    print(f"  accepted={evidence['accepted']} :: {evidence['detail']}")
    return 0 if evidence["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
