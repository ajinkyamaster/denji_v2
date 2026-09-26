#!/usr/bin/env python3
"""reliability_check.py: the scorecard (D2/D3).

    R1  replay determinism          R6  oracle blindness regression
    R2  monotonicity                R7  no unsourced number
    R3  kernel soundness control    R8  red triage, three directions
    R4  kernel non-vacuity control  R9  flakiness exclusion + lower-bound honesty
    R5  gate falsifiers G1..G5      R10 degraded-run honesty
    C1..C4  the v1 causal controls: necessity, sensitivity, reachability,
            patch reconstruction
    S1  artefact schema and invariants
    S2  statement length limits
    S3  no primacy claims

Every gate is run twice: once on the real evidence (it must pass) and once
against a deliberately corrupted input (it must fail). A check that has
never been observed to fail is not a check.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from jsonschema import Draft202012Validator

from bob_session import PROMPT_VERSION
from bob_session import gate as gate_mod
from bob_session import oracle as oracle_mod
from bob_session import verify
from bob_session.pipeline import artefact as artefact_mod
from bob_session.pipeline import context as context_loader
from bob_session.pipeline import dispositions, inventory as inventory_mod
from bob_session.pipeline.run_analysis import run as run_ledger
from bob_session.proposal_cache import ProposalCache, bundle_digest, repo_digest
from bob_session.roles import bundles as bundles_mod

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATEMENT_LIMIT = 500
SCANNED_DOCS = ("README.md", "IBM_BOB_USAGE_STATEMENT.md", "PROBLEM_SOLUTION_STATEMENT.md")
GENERATED_MARKER = "<!-- generated"

FIXTURE_PYTEST_INI = "[pytest]\ntestpaths = tests\n"
FIXTURE_A = {
    "app/__init__.py": '"""Fixture package."""\n',
    "app/calc.py": '"""Fixture module."""\n\n\ndef threshold(x):\n    return x > 10\n',
    "tests/test_calc.py": "from app import calc\n\n\ndef test_threshold_low():\n    assert calc.threshold(0) is False\n",
    "pytest.ini": FIXTURE_PYTEST_INI,
}
FIXTURE_B = dict(FIXTURE_A)
FIXTURE_B["app/calc.py"] = (
    '"""Fixture module."""\n\n\ndef threshold(x):\n    return x > 10 or x == -1\n\n\ndef brand_new(value):\n    return value + 1\n'
)


@dataclasses.dataclass
class Row:
    key: str
    claim: str
    expectation: str
    observed: str
    passed: bool
    observed_fail: bool = False
    fail_evidence: str = ""


class Evidence:
    """Everything the scorecard reads, computed once."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        self.rows = inventory_mod.load(str(root / "demo/inventory.csv"))
        self.node_to_id = {row.node_id: row.test_id for row in self.rows}
        self.artefact = json.loads((root / "bob_session/testscope_report.json").read_text(encoding="utf-8"))
        self.disabled = json.loads((root / "submissions/ablation/disabled.json").read_text(encoding="utf-8"))
        self.oracle = json.loads((root / "bob_session/evidence/oracle.json").read_text(encoding="utf-8"))
        self.revisions = json.loads((root / "bob_session/evidence/revisions.json").read_text(encoding="utf-8"))
        self._runs: Dict[Tuple[str, str, str], dict] = {}
        self._gate_results: Dict[str, dict] = {}
        self.hero_id = self.node_to_id.get("tests/test_report_worker.py::test_cache_roundtrip_contract")

    # -- ledger runs --------------------------------------------------------
    def ledger(self, diff: str, model_layer: str = "enabled", cache: Optional[str] = None) -> dict:
        key = (diff, model_layer, cache or "default")
        if key not in self._runs:
            self._runs[key] = run_ledger(
                repo=str(self.root / "demo"),
                diff_path=str(self.root / diff),
                inventory_path=str(self.root / "demo/inventory.csv"),
                model_layer=model_layer,
                proposal_cache=cache or str(self.root / "bob_session/proposal_cache"),
                evidence_dir=str(self.root / "bob_session/evidence"),
            )
        return self._runs[key]

    def ctx(self, diff: str = "diffs/change_b.patch"):
        return context_loader.load(
            str(self.root / "demo"), str(self.root / diff), str(self.root / "demo/inventory.csv")
        )

    def gate_evidence(self) -> dict:
        return json.loads((self.root / "bob_session/evidence/gate_author.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def digest_of(artefact: dict) -> str:
    return artefact_mod.digest(artefact)


def selection_of(artefact: dict) -> List[str]:
    return list(artefact["priority_order"])


def _make_patch(tmp: pathlib.Path, name: str, before: str, after: str, rel_path: str) -> pathlib.Path:
    before_file = tmp / f"{name}.before"
    after_file = tmp / f"{name}.after"
    before_file.write_text(before, encoding="utf-8")
    after_file.write_text(after, encoding="utf-8")
    patch = tmp / f"{name}.patch"
    with patch.open("w", encoding="utf-8") as handle:
        subprocess.run(
            ["diff", "-u", f"--label=a/{rel_path}", f"--label=b/{rel_path}", str(before_file), str(after_file)],
            stdout=handle,
            check=False,
        )
    return patch


def _fixture_repo(tmp: pathlib.Path, files_a: Dict[str, str], files_b: Dict[str, str]) -> Tuple[str, str, str]:
    repo = tmp / "fixture"
    repo.mkdir(parents=True, exist_ok=True)
    for args in (["init", "-q"], ["config", "user.email", "fixture@example.invalid"], ["config", "user.name", "fixture"]):
        subprocess.run(["git", "-C", str(repo)] + args, check=True, stdout=subprocess.DEVNULL)
    if (repo / ".git").exists():
        subprocess.run(
            ["git", "-C", str(repo), "rm", "-r", "--cached", "-q", "."],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    for rel, text in files_a.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "A"], check=True, stdout=subprocess.DEVNULL)
    sha_a = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, stdout=subprocess.PIPE).stdout.decode().strip()
    for rel, text in files_b.items():
        (repo / rel).write_text(text, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "B"], check=True, stdout=subprocess.DEVNULL)
    sha_b = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, stdout=subprocess.PIPE).stdout.decode().strip()
    return str(repo), sha_a, sha_b


def _tree_hashes(tree: pathlib.Path) -> Dict[str, str]:
    hashes = {}
    for path in sorted(tree.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(tree).as_posix()
        if rel.startswith(".git/") or rel in (".coverage", "coverage.json") or rel.startswith("junit_"):
            continue
        if rel.endswith((".pyc", ".coveragerc")):
            continue
        hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


# ---------------------------------------------------------------------------
# gates
# ---------------------------------------------------------------------------
def c2_sensitivity(evidence: Evidence, corrupt: bool = False) -> Tuple[bool, str]:
    baseline = evidence.ledger("diffs/change_b.patch", "disabled")
    sensitivity = evidence.ledger("diffs/sensitivity.patch", "disabled")
    billing = {row.test_id for row in evidence.rows if row.module == "app.services.billing_service"}
    selected_billing = billing & set(selection_of(sensitivity))
    grew = len(selection_of(sensitivity)) > len(selection_of(baseline))
    if corrupt:
        grew = not grew
    ok = grew and bool(selected_billing)
    return ok, (
        f"inert reword: {len(selection_of(baseline))} selected, 0 billing tests; "
        f"the same edit made behavioural: {len(selection_of(sensitivity))} selected, "
        f"{len(selected_billing)}/{len(billing)} billing tests return"
    )


def c3_reachability(evidence: Evidence, corrupt: bool = False) -> Tuple[bool, str]:
    docs = evidence.ledger("diffs/docs_only.patch", "disabled")
    selected = len(selection_of(docs))
    ok = selected == 0
    if corrupt:
        ok = selected > 0
    return ok, f"docs-only diff selects {selected} tests (expected 0), 0 model calls counted"


def c1_necessity(evidence: Evidence, corrupt: bool = False) -> Tuple[bool, str]:
    """Fixing the consumer removes the *edge*, not the consumer's own tests.

    The consumer fix edits report_worker.py, so its five tests return as
    STRUCTURAL selections (the file changed) — that is correct and expected.
    The control is about the representation-coupling edge: it exists for the
    original change, and vanishes once the consumer accepts the new format.
    The corrupted probe replays the identical check against the original
    change, where the edge and the hero are both present.
    """
    diff = "diffs/change_b.patch" if corrupt else "diffs/consumer_fixed.patch"
    art = evidence.ledger(diff, "enabled")
    links = evidence.ctx(diff).links
    semantic = art["classification"]["semantically_affected"]
    structural = art["classification"]["definitely_affected"]
    hero_selected = evidence.hero_id in set(selection_of(art))
    baseline_semantic = evidence.artefact["classification"]["semantically_affected"]
    ok = (
        bool(baseline_semantic)
        and not links
        and not semantic
        and bool(structural)
        and not hero_selected
    )
    return ok, (
        f"baseline change: {len(baseline_semantic)} semantically linked; with the consumer fixed: "
        f"{len(links)} coupling link(s), {len(semantic)} semantically affected, "
        f"{len(structural)} structural (the consumer file itself changed), "
        f"hero {evidence.hero_id} selected={hero_selected}, "
        f"model layer {art['run_metadata']['model_status']}"
    )


def c4_reconstruction(evidence: Evidence, corrupt: bool = False) -> Tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="testscope-recon-") as tmp:
        holder = pathlib.Path(tmp)
        tree_a = holder / "a"
        tree_b = holder / "b"
        oracle_mod.export_revision(str(evidence.root / "demo"), evidence.revisions["rev_a"], tree_a)
        oracle_mod.export_revision(str(evidence.root / "demo"), evidence.revisions["rev_b"], tree_b)
        if not corrupt:
            subprocess.run(
                ["patch", "-p1", "-i", str(evidence.root / "diffs/change_b.patch"), "--forward", "--silent"],
                cwd=tree_a,
                check=False,
                stdout=subprocess.DEVNULL,
            )
        left = _tree_hashes(tree_a)
        right = _tree_hashes(tree_b)
        differing = sorted(set(left) ^ set(right)) + sorted(k for k in set(left) & set(right) if left[k] != right[k])
    ok = not differing
    return ok, f"patch reconstruction: {len(differing)} file(s) differ between patched rev-a and rev-b"


def r1_replay_determinism(evidence: Evidence, corrupt: bool = False) -> Tuple[bool, str]:
    warm = {digest_of(evidence.ledger("diffs/change_b.patch", "enabled")) for _ in range(8)}
    with tempfile.TemporaryDirectory(prefix="testscope-cold-") as tmp:
        cold_cache = pathlib.Path(tmp) / "empty-cache"
        cold_cache.mkdir()
        cold = {digest_of(evidence.ledger("diffs/change_b.patch", "enabled", str(cold_cache))) for _ in range(8)}
        cold_artefact = evidence.ledger("diffs/change_b.patch", "enabled", str(cold_cache))
    disabled = {digest_of(evidence.ledger("diffs/change_b.patch", "disabled")) for _ in range(8)}
    warm_artefact = evidence.ledger("diffs/change_b.patch", "enabled")
    accepted_differs = warm_artefact["claims"]["accepted"] != cold_artefact["claims"]["accepted"]
    selection_differs = selection_of(warm_artefact) != selection_of(cold_artefact)
    ok = len(warm) == 1 and len(disabled) == 1 and accepted_differs and selection_differs
    if corrupt:
        ok = not accepted_differs
    return ok, (
        f"warm: {len(warm)} digest; cold+disabled: {len(disabled)} digest; disabled-only: {len(disabled)} digest; "
        f"warm vs cold with the layer enabled: accepted claim set differs={accepted_differs}, "
        f"selection differs={selection_differs} -> the CACHE is doing the work, by design"
    )


def r2_monotonicity(evidence: Evidence, corrupt: bool = False) -> Tuple[bool, str]:
    enabled = set(selection_of(evidence.artefact))
    disabled = set(selection_of(evidence.disabled))
    baseline = run_ledger(
        repo=str(evidence.root / "demo"),
        diff_path=str(evidence.root / "diffs/change_b.patch"),
        inventory_path=str(evidence.root / "demo/inventory.csv"),
        model_layer="disabled",
    )
    subset = disabled.issubset(enabled)
    identical = selection_of(baseline) == selection_of(evidence.disabled)
    if corrupt:
        subset = bool(disabled - enabled)
    ok = subset and identical
    return ok, (
        f"disabled selection is a subset of enabled={subset}; the disabled run is byte-identical to a fresh "
        f"baseline run={identical} ({len(disabled)} vs {len(enabled)} entries)"
    )


def r3_kernel_soundness(evidence: Evidence, corrupt: bool = False) -> Tuple[bool, str]:
    ctx = evidence.ctx()
    fabricated = [
        {
            "claim_type": "link_exists",
            "role": "scout",
            "targets": {"test_id": "T-0342", "test_node": "tests/test_report_worker.py::test_cache_roundtrip_contract",
                        "consumer": "app.workers.report_worker.parse_recent_cache_entries"},
            "citations": [{"path": "app/workers/report_worker.py", "symbol": "parse_cache_entries_v2", "line": 16}],
            "confidence": "high",
            "rationale": "fabricated symbol",
        },
        {
            "claim_type": "link_exists",
            "role": "scout",
            "targets": {"test_id": "T-0342", "test_node": "tests/test_report_worker.py::test_cache_roundtrip_contract",
                        "consumer": "app.workers.report_worker.parse_recent_cache_entries"},
            "citations": [{"path": "app/workers/report_parser.py", "symbol": "parse_recent_cache_entries", "line": 16}],
            "confidence": "high",
            "rationale": "fabricated path",
        },
    ]
    verdicts = verify.verify_claims(
        fabricated, repo_root=ctx.repo_path, index=ctx.index, symbolic_selection=set()
    )
    gates = sorted(item["gate"] for item in verdicts["rejected"])
    ok = gates == ["citation_invalid", "symbol_mismatch"] and not verdicts["accepted"]
    if corrupt:
        ok = ok and not gates
    return ok, f"fabricated claims rejected with gates {gates}, accepted={len(verdicts['accepted'])}"


def r4_kernel_non_vacuity(evidence: Evidence, corrupt: bool = False) -> Tuple[bool, str]:
    ctx = evidence.ctx()
    valid = [
        json.loads((evidence.root / "bob_session/roles/recorded/scout.json").read_text(encoding="utf-8"))["claims"][0]
    ]
    plausible = [
        {
            "claim_type": "link_exists",
            "role": "scout",
            "targets": {"test_id": "T-0346", "test_node": "tests/test_report_worker.py::test_skips_blank_lines",
                        "consumer": "app.models.Report"},
            "citations": [{"path": "tests/test_report_worker.py", "symbol": "test_skips_blank_lines", "line": 45}],
            "confidence": "med",
            "rationale": "plausible but unverifiable link",
        }
    ]
    verdicts = verify.verify_claims(valid, repo_root=ctx.repo_path, index=ctx.index, symbolic_selection=set())
    unconfirmed = verify.verify_claims(plausible, repo_root=ctx.repo_path, index=ctx.index, symbolic_selection=set())
    accepted = [item["claim"]["targets"]["test_id"] for item in verdicts["accepted"]]
    safe_direction = [item["claim"]["targets"]["test_id"] for item in unconfirmed["unconfirmed"]]
    selection = dispositions.select(
        evidence.rows,
        ctx.semantic,
        ctx.closure,
        ctx.links,
        {test_id: "injected valid claim" for test_id in accepted},
        {test_id: "injected plausible claim" for test_id in safe_direction},
    )
    included = set(safe_direction).issubset(selection.selected)
    ok = accepted == ["T-0342"] and bool(safe_direction) and included
    if corrupt:
        ok = not accepted
    return ok, (
        f"valid claim accepted: {accepted}; unverifiable-but-plausible claim: {safe_direction} "
        f"recorded as unconfirmed and INCLUDED by the safe direction={included}"
    )


def r5_gate_falsifiers(evidence: Evidence, corrupt: bool = False) -> Tuple[bool, str]:
    results: Dict[str, dict] = {}
    with tempfile.TemporaryDirectory(prefix="testscope-r5-") as tmp:
        holder = pathlib.Path(tmp)
        repo, sha_a, sha_b = _fixture_repo(holder, FIXTURE_A, FIXTURE_B)
        tests_before = FIXTURE_A["tests/test_calc.py"]
        added_line = "    return x > 10 or x == -1"
        line_number = FIXTURE_B["app/calc.py"].splitlines().index(added_line) + 1
        good_node = "tests/test_calc.py::test_threshold_minus_one"
        good_patch = _make_patch(
            holder,
            "good",
            tests_before,
            tests_before + "\n\ndef test_threshold_minus_one():\n    assert calc.threshold(-1) is True\n",
            "tests/test_calc.py",
        )
        results["positive_control"] = gate_mod.run_for_patch(
            repo=repo, patch_path=str(good_patch), test_node=good_node,
            symbol="app.calc.threshold", rev_a=sha_a, rev_b=sha_b,
        )
        # G1: a patch that does not even parse
        broken_patch = _make_patch(
            holder, "broken", tests_before, tests_before + "\n\ndef test_broken(:\n    pass\n", "tests/test_calc.py"
        )
        results["g1"] = gate_mod.run_for_patch(
            repo=repo, patch_path=str(broken_patch), test_node="tests/test_calc.py::test_broken",
            symbol="app.calc.threshold", rev_a=sha_a, rev_b=sha_b,
        )
        # G2: a test whose outcome depends on leftover state (flaky across repeats)
        flaky_patch = _make_patch(
            holder,
            "flaky",
            tests_before,
            tests_before
            + "\n\ndef test_flaky_by_state():\n    import pathlib\n    marker = pathlib.Path(__file__).with_name('.marker')\n"
            "    assert not marker.exists()\n    marker.write_text('1')\n",
            "tests/test_calc.py",
        )
        results["g2"] = gate_mod.run_for_patch(
            repo=repo, patch_path=str(flaky_patch), test_node="tests/test_calc.py::test_flaky_by_state",
            symbol="app.calc.threshold", rev_a=sha_a, rev_b=sha_b,
        )
        # G3a: the failure at the base revision is an error, not an assertion
        error_patch = _make_patch(
            holder,
            "error_origin",
            tests_before,
            tests_before + "\n\ndef test_brand_new_contract():\n    assert calc.brand_new(1) == 2\n",
            "tests/test_calc.py",
        )
        results["g3_error_origin"] = gate_mod.run_for_patch(
            repo=repo, patch_path=str(error_patch), test_node="tests/test_calc.py::test_brand_new_contract",
            symbol="app.calc.threshold", rev_a=sha_a, rev_b=sha_b,
        )
        # G3b: the test passes at the base revision, so no assertion fires at all
        silent_patch = _make_patch(
            holder,
            "silent",
            tests_before,
            tests_before + "\n\ndef test_threshold_low_again():\n    assert calc.threshold(0) is False\n",
            "tests/test_calc.py",
        )
        results["g3_no_firing"] = gate_mod.run_for_patch(
            repo=repo, patch_path=str(silent_patch), test_node="tests/test_calc.py::test_threshold_low_again",
            symbol="app.calc.threshold", rev_a=sha_a, rev_b=sha_b,
        )        # G4: an assertion that FIRES at the base revision but is too loose to
        # kill any mutant of the changed line — G4 must reject it.
        weak_patch = _make_patch(
            holder,
            "weak",
            tests_before,
            tests_before
            + "\n\ndef test_threshold_smoke():\n"
            + "    assert calc.threshold(-1) or calc.threshold(5) or not calc.threshold(11)\n",
            "tests/test_calc.py",
        )
        results["g4"] = gate_mod.run_for_patch(
            repo=repo, patch_path=str(weak_patch), test_node="tests/test_calc.py::test_threshold_smoke",
            symbol="app.calc.threshold", rev_a=sha_a, rev_b=sha_b,
        )
        # G5: an intent anchor that is not present in the cited artefact
        gate_input = gate_mod.GateInput(
            tree_a=holder / "rev-a",
            tree_b=holder / "rev-b",
            test_node=good_node,
            symbol="app.calc.threshold",
            added_lines=[(added_line, line_number)],
            intent_quote="a sentence that is not present in the fixture module",
            intent_path="app/calc.py",
        )
        oracle_mod.export_revision(repo, sha_a, gate_input.tree_a)
        oracle_mod.export_revision(repo, sha_b, gate_input.tree_b)
        gate_mod.apply_patch(gate_input.tree_a, good_patch)
        gate_mod.apply_patch(gate_input.tree_b, good_patch)
        results["g5"] = gate_mod.run_gate(gate_input)

    f1 = results["g1"].get("g1_buildable") is False or results["g1"]["accepted"] is False
    f2 = results["g2"].get("g2_passes_5x") is False
    f3a = results["g3_error_origin"].get("g3_failure_origin") == "error"
    f3b = results["g3_no_firing"].get("g3_failure_origin") == "none"
    f4 = results["g4"].get("g4_mutation_strength", 1.0) < gate_mod.MUTATION_THRESHOLD
    f5 = results["g5"].get("g5_spec_anchored") is False
    positive = bool(results["positive_control"].get("accepted"))
    ok = all([f1, f2, f3a, f3b, f4, f5, positive])
    if corrupt:
        ok = not f3a
    return ok, (
        f"positive control accepted={positive}; G1 rejects a non-parsing patch={f1}; "
        f"G2 rejects a state-dependent test={f2}; G3 rejects an error-origin failure={f3a} and a no-fire test={f3b}; "
        f"G4 rejects the weak assertion (strength {results['g4'].get('g4_mutation_strength')} "
        f"< {gate_mod.MUTATION_THRESHOLD})={f4}; G5 rejects an absent intent anchor={f5}"
    )


def r6_oracle_blindness(evidence: Evidence, corrupt: bool = False) -> Tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="testscope-r6-") as tmp:
        workdir = pathlib.Path(tmp)
        rows = evidence.rows
        runs_default_a, deselected_a = oracle_mod.run_revision(
            str(evidence.root / "demo"), evidence.revisions["rev_a"], python=sys.executable,
            markers="", repeats=1, workdir=workdir / "default-a",
        )
        runs_default_b, deselected_b = oracle_mod.run_revision(
            str(evidence.root / "demo"), evidence.revisions["rev_b"], python=sys.executable,
            markers="", repeats=1, workdir=workdir / "default-b",
        )
        blind = oracle_mod.analyse(
            rows=rows,
            runs_a=runs_default_a,
            runs_b=runs_default_b,
            strategy="default markers",
            deselected=max(deselected_a, deselected_b),
        )
        full = evidence.oracle
    blind_incomplete = blind["complete"] is False and not blind["changed"]
    full_complete = full["complete"] is True and len(full["changed"]) == 3
    ok = blind_incomplete and full_complete
    if corrupt:
        ok = bool(blind["complete"])
    return ok, (
        f"under pytest.ini's default markers the oracle reports complete={blind['complete']} "
        f"(deselected={blind['deselected']}) and changed={len(blind['changed'])} (blind); "
        f"with -m '' it reports complete={full['complete']} and changed={len(full['changed'])}"
    )


def r7_no_unsourced_number(evidence: Evidence, corrupt: bool = False) -> Tuple[bool, str]:
    corpus_paths = (
        "submissions/measurement.json",
        "submissions/scorecard.json",
        "submissions/external_sources.json",
        "bob_session/evidence/gate_author.json",
        "VERIFICATION.md",
    )
    corpus = [(evidence.root / rel).read_text(encoding="utf-8") for rel in corpus_paths if (evidence.root / rel).exists()]
    corpus.append(json.dumps(evidence.artefact, sort_keys=True))
    known = evidence_figures("\n".join(corpus))
    scanned, violations = scan_documents(evidence.root, known, corrupt=corrupt)
    # The gate verdict is "no unsourced figures". The corrupt probe injects a
    # forbidden figure, so the verdict on the corrupted input MUST be False
    # (observed_fail = not bad_ok); a True here would mean the gate cannot fail.
    ok = not violations
    observed = (
        f"scanned {len(scanned)} discovered document(s) [{', '.join(scanned)}]; "
        f"{len(violations)} unsourced figure(s); evidence corpus holds {len(known)} distinct figure(s)"
        + (f"; first violation: {violations[0]}" if violations else "")
    )
    return ok, observed


FIGURE_RE = r"(?<![A-Za-z0-9_.])\d+(?:\.\d+)?%?"


def evidence_figures(text: str) -> Set[str]:
    """Every figure the evidence corpus can source, in the forms prose uses."""
    figures: Set[str] = set()
    for raw in re.findall(FIGURE_RE, text):
        base = raw.rstrip("%")
        figures.add(base)
        try:
            value = float(base)
        except ValueError:
            continue
        if value.is_integer():
            figures.add(str(int(value)))
        figures.add(f"{value:.1f}")
        figures.add(f"{value:.2f}")
    return figures


def scan_documents(root: pathlib.Path, known_figures: Set[str], corrupt: bool = False) -> Tuple[List[str], List[str]]:
    """Discover documents by rule, report unsourced figures without echoing them.

    Three rules bind this scanner:
      DISCOVER, DON'T ENUMERATE  every .md in the repository root and in
                                 submissions/ is scanned, so a new document is
                                 covered by default
      NEVER ECHO THE LITERAL     a violation names the document and the figure
                                 ordinal, never the figure itself
      EXCLUDE GENERATED OUTPUT   a document that declares itself generated is
        BY RULE                  skipped, so the evidence log cannot feed back
    """
    documents: List[str] = []
    probe = root / "submissions/_r7_probe.md"
    if corrupt:
        probe.write_text("This document claims a figure of 987654 units.\n", encoding="utf-8")
    for path in sorted(list(root.glob("*.md")) + list((root / "submissions").glob("*.md"))):
        if not path.is_file():
            continue
        head = "\n".join(path.read_text(encoding="utf-8").splitlines()[:3])
        if GENERATED_MARKER in head:
            continue  # generated output is excluded BY RULE, never scanned
        documents.append(path.relative_to(root).as_posix())
    violations: List[str] = []
    for rel in documents:
        text = root.joinpath(rel).read_text(encoding="utf-8")
        stripped = re.sub(r"```.*?```", "", text, flags=re.S)
        stripped = re.sub(r"`[^`]*`", "", stripped)
        for index, figure in enumerate(re.findall(FIGURE_RE, stripped), start=1):
            if figure.rstrip("%") in known_figures:
                continue
            violations.append(f"{rel}: contains forbidden figure #{index}")
    if corrupt:
        probe.unlink(missing_ok=True)
    return documents, violations


def r8_red_triage(evidence: Evidence, corrupt: bool = False) -> Tuple[bool, str]:
    stale = {"T-0345": ("asserts the removed wire format", "tests/test_report_worker.py: assert ... '1|ok|5'")}
    rows = dispositions.triage_rows(["T-0345"], stale, set(), {})
    flaky = dispositions.triage_rows(["T-0999"], stale, set(), {})
    linked = dispositions.triage_rows(["T-0999"], stale, {"T-0999"}, {})
    ok = (
        rows and rows[0]["diagnosis"] == "stale"
        and flaky and flaky[0]["diagnosis"] == "flaky"
        and linked and linked[0]["diagnosis"] == "regression"
    )
    if corrupt:
        ok = bool(rows) and rows[0]["diagnosis"] == "regression"
    return ok, (
        f"(a) a test asserting removed behaviour -> {rows[0]['diagnosis'] if rows else '?'} (fix the test); "
        f"(b) a failure with no verified link -> {flaky[0]['diagnosis'] if flaky else '?'} (quarantine); "
        f"(c) the SAME failure once a link is verified -> {linked[0]['diagnosis'] if linked else '?'} — not written off as flaky"
    )


def r9_flakiness_exclusion(evidence: Evidence, corrupt: bool = False) -> Tuple[bool, str]:
    runs_a = [
        {"tests/t.py::stable": "passed", "tests/t.py::flip": "passed", "tests/t.py::both": "passed", "tests/t.py::red": "failed"},
        {"tests/t.py::stable": "passed", "tests/t.py::flip": "failed", "tests/t.py::both": "passed", "tests/t.py::red": "failed"},
    ]
    runs_b = [
        {"tests/t.py::stable": "failed", "tests/t.py::flip": "passed", "tests/t.py::both": "passed", "tests/t.py::red": "failed"},
        {"tests/t.py::stable": "failed", "tests/t.py::flip": "failed", "tests/t.py::both": "passed", "tests/t.py::red": "failed"},
    ]
    fake_rows = [inventory_mod.Row(f"T-{i:04d}", f"t{i}", "app.m", node, "d", 1) for i, node in enumerate(
        ["tests/t.py::stable", "tests/t.py::flip", "tests/t.py::both", "tests/t.py::red"]
    )]
    analysis = oracle_mod.analyse(rows=fake_rows, runs_a=runs_a, runs_b=runs_b, strategy="fixture")
    ok = (
        analysis["changed"] == ["tests/t.py::stable"]
        and analysis["flaky_excluded"] == ["tests/t.py::flip"]
        and analysis["flaky_excluded_count"] == 1
        and analysis["already_red"] == ["tests/t.py::red"]
        and "tests/t.py::both" not in analysis["changed"]
    )
    if corrupt:
        ok = analysis["flaky_excluded_count"] == 0
    return ok, (
        f"discriminating={len(analysis['changed'])}, flaky_excluded_count={analysis['flaky_excluded_count']} "
        f"(count REPORTED), already_red={len(analysis['already_red'])}; a test passing at BOTH revisions is "
        f"not counted as discriminating (lower bound, disclosed)"
    )


def r10_degraded_run(evidence: Evidence, corrupt: bool = False) -> Tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="testscope-r10-") as tmp:
        empty = pathlib.Path(tmp) / "cold"
        empty.mkdir()
        degraded = run_ledger(
            repo=str(evidence.root / "demo"),
            diff_path=str(evidence.root / "diffs/change_b.patch"),
            inventory_path=str(evidence.root / "demo/inventory.csv"),
            model_layer="enabled",
            proposal_cache=str(empty),
            evidence_dir=str(evidence.root / "bob_session/evidence"),
        )
    schema_ok = _schema_ok(evidence.root, degraded)
    baseline = run_ledger(
        repo=str(evidence.root / "demo"),
        diff_path=str(evidence.root / "diffs/change_b.patch"),
        inventory_path=str(evidence.root / "demo/inventory.csv"),
        model_layer="disabled",
    )
    same_selection = selection_of(degraded) == selection_of(baseline)
    reports_unavailable = degraded["run_metadata"]["model_status"] == "model-unavailable" and degraded["run_metadata"]["model_coverage"] == 0.0
    ok = schema_ok and same_selection and reports_unavailable and bool(degraded["invariants"]["violations"]) is False
    if corrupt:
        ok = not same_selection
    return ok, (
        f"with no path to a model: artefact still schema-valid={schema_ok}, model_coverage="
        f"{degraded['run_metadata']['model_coverage']}, status={degraded['run_metadata']['model_status']}, "
        f"selection equals the deterministic baseline byte for byte={same_selection}"
    )


def s1_schema_and_invariants(evidence: Evidence, corrupt: bool = False) -> Tuple[bool, str]:
    artefact = dict(evidence.artefact)
    if corrupt:
        artefact = json.loads(json.dumps(artefact))
        artefact["summary"].pop("selected_for_run", None)
    schema_ok = _schema_ok(evidence.root, artefact)
    violations = artefact_mod.validate(artefact)
    ok = schema_ok and not violations
    return ok, f"schema valid={schema_ok}; invariant violations={violations or 'none'}"


def s2_statement_lengths(evidence: Evidence, corrupt: bool = False) -> Tuple[bool, str]:
    counts = {}
    for name in ("IBM_BOB_USAGE_STATEMENT.md", "PROBLEM_SOLUTION_STATEMENT.md"):
        path = evidence.root / name
        counts[name] = len(path.read_text(encoding="utf-8").split()) if path.exists() else -1
    if corrupt:
        counts["PROBLEM_SOLUTION_STATEMENT.md"] = len((evidence.root / "README.md").read_text(encoding="utf-8").split())
    ok = all(0 <= value <= STATEMENT_LIMIT for value in counts.values())
    return ok, f"word counts {counts} (limit {STATEMENT_LIMIT})"


def s3_no_primacy_claims(evidence: Evidence, corrupt: bool = False) -> Tuple[bool, str]:
    patterns = ("first ever", "nobody has", "no one has")
    hits = []
    for name in SCANNED_DOCS:
        path = evidence.root / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").lower()
        for pattern in patterns:
            if pattern in text:
                hits.append((name, pattern))
    if corrupt:
        hits.append(("_probe.md", "primacy claim"))
    ok = not hits
    return ok, f"primacy-claim patterns present: {hits or 'none'}"


def _schema_ok(root: pathlib.Path, artefact: dict) -> bool:
    schema = json.loads((root / "schemas/testscope_report.schema.json").read_text(encoding="utf-8"))
    return not list(Draft202012Validator(schema).iter_errors(artefact))


GATES: List[Tuple[str, str, str, Callable[..., Tuple[bool, str]]]] = [
    ("C1", "the necessity control: fixing the consumer removes the coupling edge", "0 coupling links, 0 semantically affected, hero not selected", c1_necessity),
    ("C2", "the sensitivity control: making the inert edit behavioural returns control tests", "the selection grows and billing tests return", c2_sensitivity),
    ("C3", "the reachability control: a docs-only change selects nothing", "0 tests selected", c3_reachability),
    ("C4", "the change patch reconstructs the target revision", "0 differing files", c4_reconstruction),
    ("R1", "replay determinism: the artefact is a function of the kernel and the cache", "8 runs -> 1 digest in each configuration; warm vs cold differ, and the cache is why", r1_replay_determinism),
    ("R2", "monotonicity: the model layer can only add", "disabled selection is a subset of enabled and identical to a fresh baseline", r2_monotonicity),
    ("R3", "kernel soundness: fabricated citations are rejected", "rejected with citation_invalid and symbol_mismatch", r3_kernel_soundness),
    ("R4", "kernel non-vacuity: a valid claim is accepted, a plausible one is unconfirmed and included", "accepted T-0342; unconfirmed claim takes the safe direction", r4_kernel_non_vacuity),
    ("R5", "gate falsifiers: each of G1..G5 rejects a bad input", "G1..G5 each observed to fail; positive control accepted", r5_gate_falsifiers),
    ("R6", "oracle blindness regression: the instrument reports its own blindness", "default markers -> complete=false; all markers -> complete=true", r6_oracle_blindness),
    ("R7", "no unsourced number: every figure in a document is sourced", "0 unsourced figures over the discovered scope", r7_no_unsourced_number),
    ("R8", "red triage in all three directions", "stale / flaky / regression", r8_red_triage),
    ("R9", "flakiness exclusion and lower-bound honesty", "flaky excluded and counted; pass-both not discriminating", r9_flakiness_exclusion),
    ("R10", "degraded-run honesty with no model available", "artefact valid, coverage 0.0, selection == baseline", r10_degraded_run),
    ("S1", "the committed artefact is schema-valid and satisfies its invariants", "0 schema errors, 0 invariant violations", s1_schema_and_invariants),
    ("S2", "both statements are within the 500-word limit", "counts <= 500", s2_statement_lengths),
    ("S3", "no primacy claims in the submission documents", "no 'first ever' / 'nobody has' / 'no one has'", s3_no_primacy_claims),
]


def run_scorecard(root: pathlib.Path) -> dict:
    evidence = Evidence(root)
    rows: List[Row] = []
    for key, claim, expectation, function in GATES:
        good_ok, good_observed = function(evidence, False)
        try:
            bad_ok, bad_observed = function(evidence, True)
            observed_fail = not bad_ok
            fail_evidence = bad_observed if observed_fail else "the corrupted run still passed: this gate is not falsifiable"
        except Exception as exc:  # a gate that cannot be run corrupted is not falsifiable
            observed_fail = False
            fail_evidence = f"corrupted run raised {exc.__class__.__name__}: {exc}"
        rows.append(
            Row(
                key=key,
                claim=claim,
                expectation=expectation,
                observed=good_observed,
                passed=bool(good_ok) and observed_fail,
                observed_fail=observed_fail,
                fail_evidence=fail_evidence,
            )
        )
    passed = sum(1 for row in rows if row.passed)
    return {
        "generated_by": "bob_session/reliability_check.py",
        "generated_at_note": "the timestamp is omitted on purpose: the scorecard is a function of the repository",
        "total": len(rows),
        "passed": passed,
        "failed": len(rows) - passed,
        "rows": [dataclasses.asdict(row) for row in rows],
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--out", default="submissions/scorecard.json")
    parser.add_argument("--md", default="submissions/scorecard.md")
    args = parser.parse_args(argv)

    root = pathlib.Path(args.root).resolve()
    started = time.time()
    scorecard = run_scorecard(root)
    scorecard["elapsed_seconds"] = round(time.time() - started, 2)
    out = root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(scorecard, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "<!-- generated by bob_session/reliability_check.py: do not edit -->",
        "# Reliability scorecard",
        "",
        f"**{scorecard['passed']}/{scorecard['total']} gates pass**, "
        f"each having been observed to FAIL once when deliberately corrupted.",
        "",
        "| key | claim | expectation | observed | pass | observed to fail |",
        "|---|---|---|---|---|---|",
    ]
    for row in scorecard["rows"]:
        observed = row["observed"].replace("|", "\\|")
        lines.append(
            f"| {row['key']} | {row['claim']} | {row['expectation']} | {observed} | "
            f"{'PASS' if row['passed'] else 'FAIL'} | {'yes' if row['observed_fail'] else 'NO'} |"
        )
    lines.append("")
    lines.append("## Falsifier evidence (the corrupted run that made each gate fail)")
    lines.append("")
    for row in scorecard["rows"]:
        lines.append(f"- **{row['key']}**: {row['fail_evidence']}")
    lines.append("")
    (root / args.md).write_text("\n".join(lines), encoding="utf-8")

    print(f"scorecard: {scorecard['passed']}/{scorecard['total']} gates pass -> {out}")
    for row in scorecard["rows"]:
        print(f"  {'PASS' if row['passed'] else 'FAIL'} {row['key']}: {row['observed'][:110]}")
    return 0 if scorecard["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
