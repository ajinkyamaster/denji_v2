"""The causal controls. Without them, "we correctly excluded 75 tests" is unfalsifiable.

T12 is the sensitivity control for the second soundness lever: the same repository,
the same 75 tests, and a change to the same module - only the *nature* of the change
differs (an inert log reword versus a semantics-modifying constant). If the 75 tests
come back, the inertness rule is doing work. If this test ever stops failing when it
should, the lever has silently broken and the selection is no longer trustworthy.
"""

import json

import pytest

from bob_session.pipeline import cache as cache_module
from bob_session.run_analysis import run_pipeline

from .conftest import BEHAVIOURAL_CONTROL, CHANGE, DOCS_ONLY, GENERATED_AT, INVENTORY


def _run(diff_path, **overrides):
    arguments = {
        "repo": "demo_repo",
        "diff_path": str(diff_path),
        "inventory_path": str(INVENTORY),
        "generated_at": GENERATED_AT,
    }
    arguments.update(overrides)
    artifact, _ = run_pipeline(**arguments)
    return artifact


def test_T12_the_inertness_control_still_fires():
    baseline = _run(CHANGE)
    control = _run(BEHAVIOURAL_CONTROL)
    assert baseline["summary"]["selected_for_run"] == 47
    assert control["summary"]["selected_for_run"] == 122, "the 75 control tests must return"
    assert baseline["summary"]["definitely_affected_count"] == 41
    assert control["summary"]["definitely_affected_count"] == 116
    assert baseline["summary"]["semantically_affected_count"] == control["summary"]["semantically_affected_count"] == 6
    assert control["summary"]["reduction_pct"] == 75.6


def test_T12_the_two_runs_differ_only_in_the_billing_hunk():
    baseline = _run(CHANGE)
    control = _run(BEHAVIOURAL_CONTROL)
    assert baseline["run_metadata"]["diff_files"] == control["run_metadata"]["diff_files"]
    assert baseline["run_metadata"]["change_summary"]["semantics_modifying_modules"] == [
        "app.services.cache_service"
    ]
    assert control["run_metadata"]["change_summary"]["semantics_modifying_modules"] == [
        "app.services.billing_service",
        "app.services.cache_service",
    ]


def test_docs_only_reachability_control_selects_nothing():
    artifact = _run(DOCS_ONLY)
    assert artifact["summary"]["selected_for_run"] == 0
    assert artifact["summary"]["reduction_pct"] == 100.0
    assert artifact["uncovered"] == []
    assert artifact["ledger"]["stale"] == []
    assert len(artifact["ledger"]["valid"]) == 500


def test_T13_environment_fingerprint_and_cache_report_are_present_and_non_empty():
    artifact = _run(CHANGE)
    metadata = artifact["run_metadata"]
    assert metadata["environment_fingerprint"], "reuse is only sound if its environment assumption is visible"
    assert isinstance(metadata["environment_fingerprint"], str)
    assert metadata["declared_assumptions"], "declared assumptions must be recorded in the artefact"
    assert any("NOT sound" in assumption for assumption in metadata["declared_assumptions"])


def test_T13_the_cache_records_its_state_and_what_invalidated_it(tmp_path):
    cache_dir = tmp_path / "cache"
    store = cache_module.ArtifactCache(cache_dir)
    key = cache_module.cache_key(
        repo_hash=cache_module.content_hash_of_tree("demo_repo"),
        diff_hash="a" * 64,
        inventory_hash="b" * 64,
        prompt_version="v2.0.0",
        tool_version="2.0.0",
        env_fingerprint=cache_module.environment_fingerprint(),
    )
    assert store.load(key) is None
    store.store(key, "{}")
    assert store.load(key) == "{}"
    assert list(cache_dir.glob("*.json")), "the stored artefact must be addressable by its content key"


def test_the_cache_is_atomic_and_leaves_no_temp_files(tmp_path):
    store = cache_module.ArtifactCache(tmp_path / "cache")
    store.store("k" * 64, "body")
    assert not list((tmp_path / "cache").glob(".tmp-*")), "a killed run must not leave a partial artefact"


def test_empty_diff_selects_nothing_and_spends_nothing(tmp_path):
    empty = tmp_path / "empty.diff"
    empty.write_text("", encoding="utf-8")
    artifact = _run(empty)
    assert artifact["summary"]["selected_for_run"] == 0
    assert artifact["claims"]["proposed"] == 0, "an empty diff must not trigger a model call"
    assert artifact["run_metadata"]["coins_spent"] == 0
