#!/usr/bin/env python3
"""testscope_oracle: executed ground truth (MCP tool 3).

Runs the FULL suite at both revisions, with every marker, and computes the
outcome discriminant:

    Delta(t) = [ outcome_A(t) != outcome_B(t) ]

That is a LOWER BOUND on the truly affected set (a test can be affected and
still pass twice), so it measures recall and can never measure precision.
The oracle therefore reports its own blindness rather than hiding it:

  missing        inventory rows whose node was never collected
  unmapped       collected nodes with no inventory row
  already_red    tests that fail at BOTH revisions (not caused by the change)
  flaky          tests whose outcome is not stable across repeats
  deselected     tests pytest reported as "N deselected" (a marker filter ran)
  complete       (collected - unmapped) + missing >= inventory_total
                 AND nothing was deselected: a marker filter makes the run
                 narrower than the population, so the instrument reports its
                 own blindness instead of counting deselected rows as "missing"

Nothing here touches the input repository: each revision is exported into
its own temporary tree.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import re
import shlex
import subprocess
import sys
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from bob_session.pipeline import inventory as inventory_mod

DEFAULT_MARKERS_ALL = "-m ''"
DEFAULT_MARKERS_DEFAULT = ""  # let pytest.ini's addopts apply: the blind run


def export_revision(repo: str, rev: str, target: pathlib.Path) -> None:
    """Export one git revision into a fresh directory (input repo untouched)."""
    target.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(
        ["git", "-C", repo, "archive", rev],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    with tempfile.NamedTemporaryFile(suffix=".tar") as handle:
        handle.write(archive)
        handle.flush()
        with tarfile.open(handle.name) as tar:
            tar.extractall(target)


def _node_from_xml(classname: str, name: str) -> Optional[str]:
    if not classname:
        return None
    path = classname.replace(".", "/") + ".py"
    return f"{path}::{name}"


def run_suite(
    tree: pathlib.Path,
    *,
    python: str,
    extra_args: Sequence[str],
    junit_path: pathlib.Path,
    timeout: int = 600,
) -> Tuple[Dict[str, str], int]:
    """Run pytest in a tree; returns ({node: outcome}, deselected_count)."""
    command = [python, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={junit_path.name}"] + list(extra_args)
    result = subprocess.run(
        command,
        cwd=tree,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    summary = result.stdout.decode("utf-8", "replace")
    match = re.search(r"(\d+) deselected", summary)
    deselected = int(match.group(1)) if match else 0
    outcomes: Dict[str, str] = {}
    if not junit_path.exists():
        return outcomes, deselected
    root = ET.parse(junit_path).getroot()
    for case in root.iter("testcase"):
        node = _node_from_xml(case.get("classname", ""), case.get("name", ""))
        if node is None:
            continue
        outcome = "passed"
        for child in case:
            if child.tag in ("failure", "error"):
                outcome = "failed"
                break
            if child.tag == "skipped":
                outcome = "skipped"
                break
        outcomes[node] = outcome
    return outcomes, deselected


def run_revision(
    repo: str,
    rev: str,
    *,
    python: str,
    markers: str,
    repeats: int,
    workdir: pathlib.Path,
    timeout: int = 600,
) -> Tuple[List[Dict[str, str]], int]:
    """Export a revision and run its suite `repeats` times.

    Returns (runs, deselected): the highest deselected count observed across
    the repeats — any marker filter at all makes the run a blind one.
    """
    tree = workdir / rev[:12]
    export_revision(repo, rev, tree)
    runs: List[Dict[str, str]] = []
    deselected = 0
    for index in range(repeats):
        junit = tree / f"junit_{index}.xml"
        extra = shlex.split(markers) if markers else []
        outcomes, blind = run_suite(tree, python=python, extra_args=extra, junit_path=junit, timeout=timeout)
        runs.append(outcomes)
        deselected = max(deselected, blind)
    return runs, deselected


def analyse(
    *,
    rows: Sequence[inventory_mod.Row],
    runs_a: Sequence[Dict[str, str]],
    runs_b: Sequence[Dict[str, str]],
    strategy: str,
    deselected: int = 0,
) -> dict:
    """Compare two revisions' repeated runs into the oracle evidence."""
    nodes = sorted(set().union(*[set(run) for run in runs_a], *[set(run) for run in runs_b]))
    stable_a, stable_b = {}, {}
    flaky: List[str] = []
    for node in nodes:
        outcomes_a = {run.get(node) for run in runs_a if node in run}
        outcomes_b = {run.get(node) for run in runs_b if node in run}
        if len(outcomes_a) == 1 and len(outcomes_b) == 1:
            stable_a[node] = outcomes_a.pop()
            stable_b[node] = outcomes_b.pop()
        else:
            flaky.append(node)
    changed = sorted(node for node in stable_a if stable_a[node] != stable_b[node])
    already_red = sorted(node for node in stable_a if stable_a[node] == stable_b[node] == "failed")
    # collected = what the instrument saw at least once at revision B. Nodes
    # seen in only one of the repeats are unstable and are excluded from the
    # discriminant anyway, but they must still be counted as collected, or the
    # completeness arithmetic compares the inventory against a subset of runs.
    collected_b = sorted(set().union(*[set(run) for run in runs_b])) if runs_b else []
    collected_a = sorted(set().union(*[set(run) for run in runs_a])) if runs_a else []
    collected_ids = {row.node_id for row in rows}
    missing = sorted(row.node_id for row in rows if row.node_id not in set(collected_a) | set(collected_b))
    unmapped = sorted(node for node in collected_b if node not in collected_ids)
    collected = len(collected_b)
    inventory_total = len(rows)
    arithmetic = (collected - len(unmapped)) + len(missing) >= inventory_total
    complete = arithmetic and deselected == 0
    return {
        "strategy": strategy,
        "collected": collected,
        "inventory_total": inventory_total,
        "complete": complete,
        "deselected": deselected,
        "missing": missing,
        "unmapped": unmapped,
        "already_red": already_red,
        "flaky_excluded": sorted(flaky),
        "flaky_excluded_count": len(flaky),
        "changed": changed,
        "outcome": {
            node: {"a": stable_a[node], "b": stable_b[node]}
            for node in sorted(set(stable_a) & set(stable_b))
        },
    }


def coverage_map(
    *,
    repo: str,
    rev: str,
    rows: Sequence[inventory_mod.Row],
    workdir: pathlib.Path,
    python: str,
    run_cmd: Sequence[str],
    timeout: int = 900,
) -> dict:
    """Per-test executed lines at one revision, as a positive-witness map.

    Coverage is the admissible witness in one direction only: if a test
    executed a line, it executed it. Nothing here is used to *exclude* a
    test from the run list.
    """
    tree = workdir / f"cov-{rev[:12]}"
    export_revision(repo, rev, tree)
    (tree / ".coveragerc").write_text(
        "[run]\ndynamic_context = test_function\n\n[report]\ninclude = app/*\n", encoding="utf-8"
    )
    data_file = tree / ".coverage"
    command = [python, "-m", "coverage", "run", "--data-file", str(data_file), "-m", "pytest", "-q", "-p", "no:cacheprovider"] + list(run_cmd)
    subprocess.run(command, cwd=tree, check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    json_out = tree / "coverage.json"
    subprocess.run(
        [python, "-m", "coverage", "json", "--data-file", str(data_file), "-o", str(json_out), "--show-contexts"],
        cwd=tree,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
    )
    # coverage names a test context ``<module>.<function>``; the inventory's
    # node ids are ``tests/<module>.py::<function>``. Both spellings resolve.
    context_to_id: Dict[str, str] = {}
    for row in rows:
        rel_path, _, name = row.node_id.partition("::")
        context_to_id[f"{pathlib.Path(rel_path).stem}.{name}"] = row.test_id
        context_to_id[row.node_id] = row.test_id
    tests: Dict[str, dict] = {}
    if json_out.exists():
        report = json.loads(json_out.read_text(encoding="utf-8"))
        for path, payload in report.get("files", {}).items():
            for line_text, names in (payload.get("contexts") or {}).items():
                for name in names:
                    test_id = context_to_id.get(name)
                    if test_id is None:
                        continue
                    entry = tests.setdefault(test_id, {"node": None, "lines": {}})
                    entry["lines"].setdefault(path, []).append(int(line_text))
        for row in rows:
            if row.test_id in tests:
                tests[row.test_id]["node"] = row.node_id
        for entry in tests.values():
            for path in entry["lines"]:
                entry["lines"][path] = sorted(set(entry["lines"][path]))
    return {"revision": rev, "tests": tests}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="demo")
    parser.add_argument("--inventory", default="demo/inventory.csv")
    parser.add_argument("--rev-a", default=None)
    parser.add_argument("--rev-b", default=None)
    parser.add_argument("--revisions", default="bob_session/evidence/revisions.json")
    parser.add_argument("--out", default="bob_session/evidence/oracle.json")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--markers", default=DEFAULT_MARKERS_ALL, help="pytest -m argument; '' means: use pytest.ini's addopts")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--coverage-out", default="bob_session/evidence/coverage_b.json")
    parser.add_argument("--no-coverage", action="store_true")
    parser.add_argument("--label", default="dual-revision outcome discriminant")
    args = parser.parse_args(argv)

    revisions = json.loads(pathlib.Path(args.revisions).read_text(encoding="utf-8"))
    rev_a = args.rev_a or revisions["rev_a"]
    rev_b = args.rev_b or revisions["rev_b"]
    rows = inventory_mod.load(args.inventory)

    with tempfile.TemporaryDirectory(prefix="testscope-oracle-") as tmp:
        workdir = pathlib.Path(tmp)
        runs_a, deselected_a = run_revision(args.repo, rev_a, python=args.python, markers=args.markers, repeats=args.repeats, workdir=workdir)
        runs_b, deselected_b = run_revision(args.repo, rev_b, python=args.python, markers=args.markers, repeats=args.repeats, workdir=workdir)
        if not args.no_coverage:
            run_cmd = shlex.split(args.markers) if args.markers else []
            coverage = coverage_map(
                repo=args.repo,
                rev=rev_b,
                rows=rows,
                workdir=workdir,
                python=args.python,
                run_cmd=run_cmd,
            )
            out = pathlib.Path(args.coverage_out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(coverage, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    evidence = analyse(
        rows=rows,
        runs_a=runs_a,
        runs_b=runs_b,
        strategy=args.label,
        deselected=max(deselected_a, deselected_b),
    )
    evidence["revisions"] = {"rev_a": rev_a, "rev_b": rev_b}
    evidence["repeats"] = args.repeats
    evidence["markers"] = args.markers or "pytest.ini default"
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"oracle: collected {evidence['collected']}/{evidence['inventory_total']} "
          f"(complete={evidence['complete']}, deselected={evidence['deselected']}) -> {out}")
    print(f"  changed {len(evidence['changed'])}, already_red {len(evidence['already_red'])}, "
          f"flaky_excluded {evidence['flaky_excluded_count']}, missing {len(evidence['missing'])}, "
          f"unmapped {len(evidence['unmapped'])}")
    for node in evidence["changed"]:
        print(f"  changed: {node}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
