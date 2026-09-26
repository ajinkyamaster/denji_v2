"""The repository index and the representation-coupling detector.

These tests pin the numbers the demo publishes, so a fixture edit that changes
them fails here rather than silently changing the story: 11 application modules in
the closure, depth histogram {0:1, 1:8, 2:1, 3:1}, 41 inventory rows, 18 direct and
23 transitive.
"""

import ast

import pytest

from bob_session.pipeline.coupling import detect_couplings
from bob_session.pipeline.diff_parser import parse_diff
from bob_session.pipeline.repo_index import build_index, references

from .conftest import CHANGE, DEMO


@pytest.fixture(scope="module")
def index():
    return build_index(DEMO)


@pytest.fixture(scope="module")
def parsed_change():
    return parse_diff(CHANGE.read_text(encoding="utf-8"))


def test_index_finds_every_module(index):
    assert index.unparseable == []
    assert index.module_named("app.services.cache_service") is not None
    assert index.module_named("app.workers.report_worker") is not None
    assert index.module_named("tests.test_report_worker").is_test is True


def test_reverse_closure_matches_the_documented_histogram(index, parsed_change, inventory_rows):
    closure = index.reverse_closure(parsed_change.changed_modules, include_tests=False)
    app = {name: depth for name, depth in closure.items() if index.module_named(name).path.startswith("app/")}
    histogram = {}
    for depth in app.values():
        histogram[depth] = histogram.get(depth, 0) + 1
    assert len(app) == 11
    assert histogram == {0: 1, 1: 8, 2: 1, 3: 1}
    rows = [row for row in inventory_rows if row.module in app]
    direct = sum(1 for row in rows if app[row.module] <= 1)
    transitive = sum(1 for row in rows if app[row.module] >= 2)
    assert len(rows) == 41
    assert (direct, transitive) == (18, 23)


def test_consumer_is_absent_from_the_producer_closure(index):
    """The counterexample: report_worker cannot reach cache_service by imports."""
    closure = index.forward_closure("app.workers.report_worker")
    assert "app.services.cache_service" not in closure
    assert "app.services.account_service" not in closure


def test_the_job_still_depends_on_the_change(index, parsed_change):
    """The operator script is a dependent too; it is reported, not hidden."""
    closure = index.reverse_closure(parsed_change.changed_modules, include_tests=False)
    assert "scripts.build_cache" in closure
    assert index.module_named("scripts.build_cache").path.startswith("scripts/")


def test_coupling_is_detected_with_evidence(index, parsed_change):
    couplings = detect_couplings(index, parsed_change)
    assert len(couplings) == 1
    coupling = couplings[0]
    assert coupling.producer_module == "app.services.cache_service"
    assert coupling.producer_symbol == "write_cache_entry", "pre-change attribution, not post-change"
    assert coupling.consumer_module == "app.workers.report_worker"
    assert coupling.consumer_symbol == "parse_recent_cache_entries"
    assert coupling.separator == "|"
    assert any("no import edge" in line for line in coupling.evidence)


def test_coupling_fires_only_when_the_change_touches_the_format(index):
    """Negative control: an unrelated change must produce no coupling at all."""
    headline = (
        "diff --git a/app/utils/text.py b/app/utils/text.py\n"
        "--- a/app/utils/text.py\n"
        "+++ b/app/utils/text.py\n"
        "@@ -20,3 +20,3 @@ def word_count(text):\n"
        "-    return len(text.split())\n"
        "+    return len(text.split(' '))\n"
    )
    diff = parse_diff(headline)
    assert detect_couplings(index, diff) == []


def test_intra_module_closure_respects_depth(index):
    assert "build_cache_payload" in index.intra_module_closure("app.services.cache_service", "write_cache_entry")
    assert "purge_stale_entries" not in index.intra_module_closure("app.services.cache_service", "write_cache_entry")


def test_references_finds_names_and_attribute_chains(index):
    module = index.module_named("tests.test_report_worker")
    names = references(ast.parse(module.source))
    assert "parse_recent_cache_entries" in names
    assert "read_cache_file" in names


def test_unparseable_module_is_skipped_and_recorded(tmp_path):
    broken = tmp_path / "repo"
    (broken / "pkg").mkdir(parents=True)
    (broken / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (broken / "pkg" / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    (broken / "pkg" / "good.py").write_text("VALUE = 1\n", encoding="utf-8")
    index = build_index(broken)
    assert "pkg.good" in index.modules
    assert index.unparseable_paths() == {"pkg/bad.py"}
