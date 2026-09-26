"""The artefact's invariants, checked by recomputation and proved by sabotage.

Every invariant gets a sabotage case: a check that has never been observed to fail
is not a check. Each sabotage makes exactly one lie and asserts that ``validate``
names it.
"""

import copy
import json

import pytest

from bob_session.pipeline.report import validate
from bob_session.tools_spec import TOOL_NAMES

from .conftest import CHANGE, GENERATED_AT, INVENTORY, ORACLE_RESULT


@pytest.fixture()
def artifact(analyse):
    value, _ = analyse(oracle_path=str(ORACLE_RESULT))
    return value


@pytest.fixture()
def inventory_ids():
    from bob_session.pipeline.inventory import load_inventory

    return [row.test_id for row in load_inventory(INVENTORY)]


def test_the_real_artefact_validates(artifact, inventory_ids):
    assert validate(artifact, inventory_ids=inventory_ids) == []


def test_I1_a_row_missing_from_every_bucket_is_caught(artifact, inventory_ids):
    broken = copy.deepcopy(artifact)
    broken["classification"]["not_affected"].pop()
    problems = validate(broken, inventory_ids=inventory_ids)
    assert any("I1" in problem for problem in problems)


def test_I1_a_row_in_two_buckets_is_caught(artifact, inventory_ids):
    broken = copy.deepcopy(artifact)
    duplicate = copy.deepcopy(broken["classification"]["not_affected"][0])
    broken["classification"]["definitely_affected"].append(duplicate)
    problems = validate(broken, inventory_ids=inventory_ids)
    assert any("appears in both" in problem for problem in problems)


def test_I2_a_reason_from_the_wrong_bucket_is_caught(artifact, inventory_ids):
    broken = copy.deepcopy(artifact)
    broken["classification"]["definitely_affected"][0]["reason"] = "no_import_path_to_changed_module"
    problems = validate(broken, inventory_ids=inventory_ids)
    assert any("I2" in problem for problem in problems)


def test_I13_a_ledger_entry_moved_out_of_the_partition_is_caught(artifact, inventory_ids):
    broken = copy.deepcopy(artifact)
    broken["ledger"]["valid"] = broken["ledger"]["valid"][:-1]
    problems = validate(broken, inventory_ids=inventory_ids)
    assert any("I13" in problem for problem in problems)


def test_I13_a_stale_test_in_the_run_list_is_caught(artifact, inventory_ids):
    broken = copy.deepcopy(artifact)
    broken["ledger"]["stale"].append({"test_id": broken["priority_order"][0], "why": "x", "removed_behaviour": "y", "evidence": ["z"]})
    problems = validate(broken, inventory_ids=inventory_ids)
    assert any("stale test is in the run list" in problem for problem in problems)


def test_I13_priority_order_must_be_exactly_the_run_list(artifact, inventory_ids):
    broken = copy.deepcopy(artifact)
    broken["priority_order"] = broken["priority_order"][1:]
    problems = validate(broken, inventory_ids=inventory_ids)
    assert any("priority_order" in problem for problem in problems)


def test_I14_completeness_is_recomputed_not_trusted(artifact, inventory_ids):
    broken = copy.deepcopy(artifact)
    broken["measurement"]["oracle"]["complete"] = False
    problems = validate(broken, inventory_ids=inventory_ids)
    assert any("I14" in problem for problem in problems)


def test_I14_an_incomplete_oracle_cannot_report_recall(artifact, inventory_ids):
    broken = copy.deepcopy(artifact)
    broken["measurement"]["oracle"]["complete"] = False
    problems = validate(broken, inventory_ids=inventory_ids)
    assert any("recall is reported from an incomplete oracle" in problem for problem in problems)


def test_I15_an_accepted_claim_without_a_ledger_verdict_is_caught(artifact, inventory_ids):
    broken = copy.deepcopy(artifact)
    broken["accepted_claims"] = [
        {"claim_type": "link_exists", "role": "scout", "targets": {"test_id": "T-9999"}, "citations": [], "confidence": "high", "rationale": "x"}
    ]
    problems = validate(broken, inventory_ids=inventory_ids)
    assert any("I15" in problem for problem in problems)


def test_I16_rejection_count_must_match_the_rejection_ledger(artifact, inventory_ids):
    broken = copy.deepcopy(artifact)
    broken["rejection_ledger"].append({"role": "scout", "gate": "citation_invalid", "detail": "x", "claim_ref": "y"})
    problems = validate(broken, inventory_ids=inventory_ids)
    assert any("I16" in problem for problem in problems)


def test_I17_schema_version_and_the_tool_surface_must_agree(artifact, inventory_ids):
    broken = copy.deepcopy(artifact)
    broken["run_metadata"]["schema_version"] = "1.0"
    problems = validate(broken, inventory_ids=inventory_ids)
    assert any("I17" in problem for problem in problems)


def test_I17_the_routing_ring_fails_when_a_tool_is_missing(artifact, inventory_ids):
    problems = validate(artifact, inventory_ids=inventory_ids, tool_names=("testscope_ledger",))
    assert any("is not exposed" in problem for problem in problems)


def test_recall_must_be_null_when_there_is_no_ground_truth(artifact, inventory_ids):
    broken = copy.deepcopy(artifact)
    broken["measurement"]["truth_size"] = 0
    problems = validate(broken, inventory_ids=inventory_ids)
    assert any("recall must be null" in problem for problem in problems)


def test_declared_assumptions_must_be_visible(artifact, inventory_ids):
    broken = copy.deepcopy(artifact)
    broken["declared_assumptions"] = []
    problems = validate(broken, inventory_ids=inventory_ids)
    assert any("declared assumptions are absent" in problem for problem in problems)


def test_uncovered_items_must_carry_their_work_item_fields(artifact, inventory_ids):
    broken = copy.deepcopy(artifact)
    broken["uncovered"][0].pop("kind")
    problems = validate(broken, inventory_ids=inventory_ids)
    assert any("kind" in problem for problem in problems)


def test_summary_counts_match_the_classification(artifact):
    summary = artifact["summary"]
    assert summary["definitely_affected_count"] == len(artifact["classification"]["definitely_affected"])
    assert summary["semantically_affected_count"] == len(artifact["classification"]["semantically_affected"])
    assert summary["selected_for_run"] == summary["definitely_affected_count"] + summary["semantically_affected_count"]
    assert summary["reduction_pct"] == 90.6
    assert artifact["measurement"]["price_of_safety"] == 6
    assert artifact["measurement"]["recall"] == 1.0
    assert artifact["measurement"]["missed"] == []


def test_the_four_canonical_tools_are_declared_once():
    assert TOOL_NAMES == ("testscope_ledger", "testscope_verify", "testscope_oracle", "testscope_gate")


def test_serialisation_is_canonical(artifact):
    from bob_session.pipeline.report import serialize

    text = serialize(artifact)
    assert text.endswith("\n")
    assert json.loads(text) == artifact
    assert text == serialize(json.loads(text)), "serialisation must be idempotent and key-sorted"
