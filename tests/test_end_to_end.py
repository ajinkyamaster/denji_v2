"""End to end: the artefact is a function of the inputs and the kernel."""
import json
import pathlib
import tempfile

import pytest
from jsonschema import Draft202012Validator

from bob_session.pipeline import artefact as artefact_mod
from bob_session.pipeline.run_analysis import run as run_ledger

ROOT = pathlib.Path(__file__).resolve().parents[1]
ARTEFACT = json.loads((ROOT / "bob_session/testscope_report.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fresh():
    return run_ledger(
        repo=str(ROOT / "demo"),
        diff_path=str(ROOT / "diffs/change_b.patch"),
        inventory_path=str(ROOT / "demo/inventory.csv"),
        model_layer="enabled",
        proposal_cache=str(ROOT / "bob_session/proposal_cache"),
        evidence_dir=str(ROOT / "bob_session/evidence"),
        ablation_baseline=str(ROOT / "submissions/ablation/disabled.json"),
    )


def test_the_committed_artefact_is_reproducible(fresh):
    assert artefact_mod.digest(fresh) == artefact_mod.digest(ARTEFACT)


def test_the_artefact_is_a_function_of_its_inputs(fresh):
    again = run_ledger(
        repo=str(ROOT / "demo"),
        diff_path=str(ROOT / "diffs/change_b.patch"),
        inventory_path=str(ROOT / "demo/inventory.csv"),
        model_layer="enabled",
        proposal_cache=str(ROOT / "bob_session/proposal_cache"),
        evidence_dir=str(ROOT / "bob_session/evidence"),
        ablation_baseline=str(ROOT / "submissions/ablation/disabled.json"),
    )
    assert artefact_mod.dumps(again) == artefact_mod.dumps(fresh)


def test_the_numbers_the_documents_publish(fresh):
    summary = fresh["summary"]
    assert summary["total"] == 500
    assert summary["selected_for_run"] == 48
    assert summary["definitely_affected_count"] == 41
    assert summary["semantically_affected_count"] == 7
    assert summary["stale_count"] == 3
    assert summary["newly_relevant_count"] == 4
    assert summary["uncovered_count"] == 2
    assert summary["reduction_pct"] == 90.4


def test_the_hero_is_selected_first(fresh):
    assert fresh["priority_order"][0] == "T-0342"


def test_the_hero_is_not_structurally_reachable(fresh):
    structural = {row["test_id"] for row in fresh["classification"]["definitely_affected"]}
    assert "T-0342" not in structural
    semantic = {row["test_id"] for row in fresh["classification"]["semantically_affected"]}
    assert "T-0342" in semantic


def test_already_red_tests_are_not_attributed_to_the_change(fresh):
    already_red = fresh["measurement"]["oracle"]["already_red"]
    assert already_red == ["tests/test_metrics_dashboard.py::test_histogram_buckets_match_expected"]
    triage_ids = {row["test_id"] for row in fresh["triage"]}
    assert all(test_id.startswith("T-") for test_id in triage_ids)


def test_the_three_contract_failures_are_diagnosed_as_regressions(fresh):
    assert [row["diagnosis"] for row in fresh["triage"]] == ["regression", "regression", "regression"]


def test_claims_are_either_accepted_or_explained(fresh):
    assert fresh["claims"]["proposed"] == 7
    assert fresh["claims"]["accepted"] == 4
    assert fresh["claims"]["rejected"] == 3
    assert len(fresh["rejection_ledger"]) == fresh["claims"]["rejected"]
    gates = {entry["gate"] for entry in fresh["rejection_ledger"]}
    assert gates == {"citation_invalid", "symbol_mismatch", "contradicts_symbolic"}


def test_the_invariants_hold(fresh):
    assert fresh["invariants"]["violations"] == []


def test_the_measurement_block_is_honest(fresh):
    measurement = fresh["measurement"]
    assert measurement["oracle"]["complete"] is True
    assert measurement["truth_size"] == 3
    assert measurement["recall"] == 1.0
    assert measurement["missed"] == []
    assert measurement["price_of_safety"] == measurement["selected"] - measurement["structurally_reachable"] == 7
    assert measurement["oracle"]["flaky_excluded_count"] == 0


def test_the_artefact_validates_against_the_schema(fresh):
    schema = json.loads((ROOT / "schemas/testscope_report.schema.json").read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(fresh)) == []


def test_model_layer_disabled_is_the_deterministic_baseline():
    disabled = run_ledger(
        repo=str(ROOT / "demo"),
        diff_path=str(ROOT / "diffs/change_b.patch"),
        inventory_path=str(ROOT / "demo/inventory.csv"),
        model_layer="disabled",
    )
    assert disabled["summary"]["selected_for_run"] == 46
    assert disabled["run_metadata"]["model_layer"] == "disabled"
    assert disabled["claims"]["proposed"] == 0
    assert set(disabled["priority_order"]).issubset(set(ARTEFACT["priority_order"]))


def test_a_cold_cache_degrades_to_the_baseline_and_says_so():
    with tempfile.TemporaryDirectory(prefix="testscope-cold-") as tmp:
        degraded = run_ledger(
            repo=str(ROOT / "demo"),
            diff_path=str(ROOT / "diffs/change_b.patch"),
            inventory_path=str(ROOT / "demo/inventory.csv"),
            model_layer="enabled",
            proposal_cache=tmp,
        )
    baseline = run_ledger(
        repo=str(ROOT / "demo"),
        diff_path=str(ROOT / "diffs/change_b.patch"),
        inventory_path=str(ROOT / "demo/inventory.csv"),
        model_layer="disabled",
    )
    assert degraded["priority_order"] == baseline["priority_order"]
    assert degraded["run_metadata"]["model_coverage"] == 0.0
    assert degraded["run_metadata"]["model_status"] == "model-unavailable"
    assert degraded["invariants"]["violations"] == []


def test_the_docs_only_diff_selects_nothing():
    docs = run_ledger(
        repo=str(ROOT / "demo"),
        diff_path=str(ROOT / "diffs/docs_only.patch"),
        inventory_path=str(ROOT / "demo/inventory.csv"),
        model_layer="enabled",
    )
    assert docs["summary"]["selected_for_run"] == 0


def test_the_sensitivity_control_returns_billing_tests():
    sensitivity = run_ledger(
        repo=str(ROOT / "demo"),
        diff_path=str(ROOT / "diffs/sensitivity.patch"),
        inventory_path=str(ROOT / "demo/inventory.csv"),
        model_layer="disabled",
    )
    selected = set(sensitivity["priority_order"])
    billing = {
        row["test_id"]
        for row in sensitivity["classification"]["definitely_affected"]
        if row["module"] == "app.services.billing_service"
    }
    assert billing and billing.issubset(selected)
    assert sensitivity["summary"]["selected_for_run"] > 46


def test_the_necessity_control_removes_the_hero():
    fixed = run_ledger(
        repo=str(ROOT / "demo"),
        diff_path=str(ROOT / "diffs/consumer_fixed.patch"),
        inventory_path=str(ROOT / "demo/inventory.csv"),
        model_layer="enabled",
    )
    assert fixed["summary"]["semantically_affected_count"] == 0
    assert "T-0342" not in set(fixed["priority_order"])
