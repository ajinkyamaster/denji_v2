"""Shared fixtures.

Every fixture here is a *path* or a pure function of the checked-in fixture, never
a mutable global: the tests must be able to run in any order and in parallel
without agreeing on shared state. That is the same discipline the product claims
(Rule 3: never let two units write the same thing).
"""

import json
import pathlib
import shutil

import pytest

PROJECT = pathlib.Path(__file__).resolve().parents[2]
DEMO = PROJECT / "demo_repo"
INVENTORY = PROJECT / "inventory.csv"
INVENTORY_XLSX = PROJECT / "inventory.xlsx"
CHANGE = DEMO / "revisions" / "post_change.diff"
BEHAVIOURAL_CONTROL = DEMO / "revisions" / "post_change_behavioural_billing.diff"
DOCS_ONLY = DEMO / "revisions" / "docs_only.diff"
AUTHORED_PATCH = DEMO / "revisions" / "authored_cache_test.diff"
ORACLE_RESULT = PROJECT / "bob_session" / "testscope_oracle.json"
GENERATED_AT = "2026-09-27T04:12:00Z"


@pytest.fixture(scope="session")
def project():
    return PROJECT


@pytest.fixture(scope="session")
def demo_repo():
    return DEMO


@pytest.fixture(scope="session")
def inventory_path():
    return INVENTORY


@pytest.fixture(scope="session")
def change_diff():
    return CHANGE


@pytest.fixture()
def analyse():
    """Run the deterministic pipeline with the demo fixture, overriding as needed."""

    def _analyse(**overrides):
        from bob_session.run_analysis import run_pipeline

        arguments = {
            "repo": str(DEMO),
            "diff_path": str(CHANGE),
            "inventory_path": str(INVENTORY),
            "generated_at": GENERATED_AT,
            "model_layer": "disabled",
        }
        arguments.update(overrides)
        artifact, inventory_ids = run_pipeline(**arguments)
        return artifact, inventory_ids

    return _analyse


@pytest.fixture()
def scratch_repo(tmp_path):
    """A disposable copy of the demo repository (never mutate the fixture itself)."""
    target = tmp_path / "repo"
    shutil.copytree(DEMO, target, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "revisions"))
    return target


@pytest.fixture()
def inventory_rows():
    from bob_session.pipeline.inventory import load_inventory

    return load_inventory(INVENTORY)


@pytest.fixture()
def oracle_result():
    return json.loads(ORACLE_RESULT.read_text(encoding="utf-8"))
