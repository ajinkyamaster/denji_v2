"""Dispositions: STALE and UNCOVERED, each with the control that makes it meaningful.

A detector without a negative control proves nothing: T1 shows STALE fires on a
deleted module, T2 shows it does *not* fire on the demo change, where the failing
tests are a regression rather than a stale assertion. T3 does the same for
UNCOVERED: non-empty for the added symbol, empty for a docs-only diff.
"""

import shutil

from bob_session.pipeline.classify import classify
from bob_session.pipeline.coupling import detect_couplings
from bob_session.pipeline.diff_parser import parse_diff
from bob_session.pipeline.dispositions import build_ledger, build_uncovered
from bob_session.pipeline.inventory import load_inventory
from bob_session.pipeline.repo_index import build_index
from bob_session.run_analysis import run_pipeline

from .conftest import CHANGE, DOCS_ONLY, GENERATED_AT, INVENTORY


def _parts(repo, diff_path):
    inventory = load_inventory(INVENTORY)
    diff = parse_diff(diff_path.read_text(encoding="utf-8"))
    index = build_index(repo)
    couplings = detect_couplings(index, diff)
    classification = classify(index, inventory, diff, couplings)
    return inventory, diff, index, couplings, classification


def test_T1_stale_fires_on_an_orphan_module(tmp_path):
    """Deleting a module makes every test of it definitionally obsolete."""
    repo = tmp_path / "repo"
    shutil.copytree(
        "demo_repo", repo, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "revisions")
    )
    (repo / "app" / "services" / "account_service.py").unlink()

    inventory, diff, index, couplings, classification = _parts(repo, CHANGE)
    ledger = build_ledger(index, inventory, diff, classification, couplings)
    stale_ids = {entry["test_id"] for entry in ledger.stale}
    assert {"T-0462", "T-0463"} <= stale_ids, "the two account tests must be stale when their module is gone"
    entry = next(item for item in ledger.stale if item["test_id"] == "T-0462")
    assert "orphan" in entry["why"]
    assert entry["evidence"], "an unexplained verdict is worthless"


def test_T2_stale_does_not_fire_on_the_demo_change():
    """The false-positive control: a regression is not a stale assertion.

    The three contract tests fail at the post-change revision, and the tempting
    mistake is to call them stale and tell the developer to delete them. They are
    not: their assertion still describes the intended contract, and the *code*
    broke it. If this test ever fails, the artefact has started recommending that
    developers delete the tests that catch their bugs.
    """
    artifact, _ = run_pipeline(
        repo="demo_repo",
        diff_path=str(CHANGE),
        inventory_path=str(INVENTORY),
        generated_at=GENERATED_AT,
    )
    assert artifact["ledger"]["stale"] == []
    assert artifact["summary"]["stale_count"] == 0
    assert artifact["summary"]["newly_relevant_count"] == 6


def test_T3_uncovered_is_non_empty_for_the_added_symbol_and_empty_for_docs_only():
    artifact, _ = run_pipeline(
        repo="demo_repo",
        diff_path=str(CHANGE),
        inventory_path=str(INVENTORY),
        generated_at=GENERATED_AT,
    )
    uncovered = artifact["uncovered"]
    assert len(uncovered) == 1
    item = uncovered[0]
    assert item["symbol"] == "app.services.cache_service.purge_stale_entries"
    assert item["kind"] == "UNCOVERED_NEW"
    assert item["has_any_test"] is False
    assert item["changed_lines"], "the work item must say which lines are new"

    docs, _ = run_pipeline(
        repo="demo_repo",
        diff_path=str(DOCS_ONLY),
        inventory_path=str(INVENTORY),
        generated_at=GENERATED_AT,
    )
    assert docs["uncovered"] == []
    assert docs["summary"]["selected_for_run"] == 0


def test_uncovered_kinds_are_never_merged():
    """UNCOVERED_BY_STALENESS is a different instruction from UNCOVERED_NEW."""
    text = (
        "diff --git a/app/services/cache_service.py b/app/services/cache_service.py\n"
        "--- a/app/services/cache_service.py\n"
        "+++ b/app/services/cache_service.py\n"
        "@@ -27,3 +27,3 @@ def write_cache_entry(key, status, count, sink=None):\n"
        "-    payload = build_cache_payload(key, status, count)\n"
        "+    payload = str(key)\n"
    )
    diff = parse_diff(text)
    index = build_index("demo_repo")
    inventory = load_inventory(INVENTORY)
    couplings = detect_couplings(index, diff)
    classification = classify(index, inventory, diff, couplings)
    uncovered, _counters = build_uncovered(index, inventory, diff, classification)
    assert any(item["kind"] == "UNCOVERED_BY_STALENESS" for item in uncovered) or uncovered == []


def test_link_correction_is_recorded_and_the_derived_link_wins():
    """The inventory is a claim; the import is a fact; the disagreement is a finding."""
    artifact, _ = run_pipeline(
        repo="demo_repo",
        diff_path=str(CHANGE),
        inventory_path=str(INVENTORY),
        generated_at=GENERATED_AT,
    )
    corrections = artifact["run_metadata"]["link_corrections"]
    assert len(corrections) == 1
    correction = corrections[0]
    assert correction["test_id"] == "T-0146"
    assert correction["declared_module"] == "app.utils.ids"
    assert correction["derived_module"] == "app.utils.text"


def test_ledger_partitions_every_row():
    artifact, _ = run_pipeline(
        repo="demo_repo",
        diff_path=str(CHANGE),
        inventory_path=str(INVENTORY),
        generated_at=GENERATED_AT,
    )
    ledger = artifact["ledger"]
    total = sum(len(ledger[key]) for key in ("valid", "stale", "newly_relevant", "unknown"))
    assert total == artifact["summary"]["total"] == 500
    assert artifact["summary"]["valid_count"] == 494
    assert artifact["summary"]["unknown_count"] == 0


def test_triage_refinement_does_not_write_off_the_hero_case():
    """T11 (triage half): coverage silence plus a verified link is a regression.

    DeFlaker's rule would quarantine these tests as flaky because the test process
    executes none of the changed lines: the producer runs in a child process. The
    refinement refuses to write off a failure when a kernel-admissible
    representation link exists.
    """
    artifact, _ = run_pipeline(
        repo="demo_repo",
        diff_path=str(CHANGE),
        inventory_path=str(INVENTORY),
        generated_at=GENERATED_AT,
        oracle_path="bob_session/testscope_oracle.json",
    )
    triage = {entry["test_id"]: entry for entry in artifact["triage"]}
    assert set(triage) == {"T-0340", "T-0341", "T-0342"}
    for entry in triage.values():
        assert entry["diagnosis"] == "regression"
        assert "representation link" in entry["signal"]
