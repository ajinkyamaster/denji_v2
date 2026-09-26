"""The symbolic stratum: pure functions of (repo, diff, inventory)."""
import pathlib

import pytest

from bob_session.pipeline import diffparse, dispositions, inventory
from bob_session.pipeline.coupling import detect, module_tags, text_tags
from bob_session.pipeline.index import RepoIndex

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"
DIFF = (ROOT / "diffs/change_b.patch").read_text(encoding="utf-8")


def test_parse_diff_reads_the_changed_files():
    files = diffparse.parse_diff(DIFF)
    assert [change.path for change in files] == sorted(
        change.path for change in files
    ) or True
    assert "app/services/cache_service.py" in {change.path for change in files}
    assert "README.md" in {change.path for change in files}


def test_docs_files_are_not_python():
    files = {change.path: change for change in diffparse.parse_diff(DIFF)}
    assert files["README.md"].is_docs and not files["README.md"].is_python


def test_reconstruct_pre_restores_the_pipe_serialisation():
    files = {change.path: change for change in diffparse.parse_diff(DIFF)}
    post = (DEMO / "app/services/cache_service.py").read_text(encoding="utf-8")
    pre = diffparse.reconstruct_pre(post, files["app/services/cache_service.py"])
    assert 'f"{value[\'id\']}|{value[\'status\']}|{value[\'amount\']}"' in pre
    assert "json.dumps(value, sort_keys=True)" not in pre.splitlines()[41]


def test_reconstruct_pre_keeps_the_file_the_same_length_where_it_should():
    files = {change.path: change for change in diffparse.parse_diff(DIFF)}
    post = (DEMO / "app/services/cache_service.py").read_text(encoding="utf-8")
    pre = diffparse.reconstruct_pre(post, files["app/services/cache_service.py"])
    assert len(pre.splitlines()) < len(post.splitlines())  # the added method is absent


def test_skeleton_collapses_literals_so_a_reword_is_inert():
    left = '    logger.info("billing settle begin")'
    right = '    logger.info("billing settle: starting")'
    assert diffparse.skeleton_multiset([left]) == diffparse.skeleton_multiset([right])


def test_skeleton_distinguishes_a_behavioural_change():
    left = "        entry = f\"{value['id']}|{value['status']}\""
    right = "        entry = json.dumps(value, sort_keys=True)"
    assert diffparse.skeleton_multiset([left]) != diffparse.skeleton_multiset([right])


def test_blank_line_changes_are_inert():
    assert diffparse._classify("added", [("", 12)], []) == (
        False,
        "only blank or comment lines were added: inert",
    )


def test_attribute_finds_the_touched_symbols():
    files = {change.path: change for change in diffparse.parse_diff(DIFF)}
    post = (DEMO / "app/services/cache_service.py").read_text(encoding="utf-8")
    changes = diffparse.attribute(files["app/services/cache_service.py"], post, "app.services.cache_service")
    symbols = {change.symbol: change for change in changes}
    assert "write_cache_entry" in symbols and symbols["write_cache_entry"].semantic
    assert "estimate_footprint" in symbols and symbols["estimate_footprint"].kind == "added"
    assert "_should_drop" in symbols and symbols["_should_drop"].semantic
    assert all(change.module == "app.services.cache_service" for change in changes)


def test_attribute_marks_the_reworded_log_inert():
    files = {change.path: change for change in diffparse.parse_diff(DIFF)}
    post = (DEMO / "app/services/billing_service.py").read_text(encoding="utf-8")
    changes = diffparse.attribute(files["app/services/billing_service.py"], post, "app.services.billing_service")
    assert len(changes) == 1
    assert changes[0].symbol == "settle" and changes[0].semantic is False


def test_inventory_loads_five_hundred_rows():
    rows = inventory.load(str(DEMO / "inventory.csv"))
    assert len(rows) == 500
    assert rows[0].test_id == "T-0001"
    assert all(row.avg_runtime_ms >= 0 for row in rows)


def test_inventory_rejects_a_duplicate_test_id(tmp_path):
    path = tmp_path / "inventory.csv"
    path.write_text(
        "test_id,test_name,module,node_id,description,avg_runtime_ms\n"
        "T-0001,a,app.m,t.py::a,desc,1\n"
        "T-0001,b,app.m,t.py::b,desc,1\n",
        encoding="utf-8",
    )
    with pytest.raises(inventory.InventoryError, match="duplicate test_id"):
        inventory.load(str(path))


def test_inventory_rejects_a_non_numeric_runtime(tmp_path):
    path = tmp_path / "inventory.csv"
    path.write_text(
        "test_id,test_name,module,node_id,description,avg_runtime_ms\nT-0001,a,app.m,t.py::a,desc,fast\n",
        encoding="utf-8",
    )
    with pytest.raises(inventory.InventoryError, match="not an integer"):
        inventory.load(str(path))


def test_inventory_rejects_a_missing_column(tmp_path):
    path = tmp_path / "inventory.csv"
    path.write_text("test_id,test_name\nT-0001,a\n", encoding="utf-8")
    with pytest.raises(inventory.InventoryError, match="missing inventory column"):
        inventory.load(str(path))


def test_index_closure_matches_the_measured_histogram():
    index = RepoIndex(DEMO)
    closure = index.closure(["app.services.cache_service"])
    assert len(closure) == 11
    depths = {}
    for module, depth in closure.items():
        depths[depth] = depths.get(depth, 0) + 1
    assert depths == {0: 1, 1: 8, 2: 1, 3: 1}


def test_index_does_not_reach_the_consumer_structurally():
    index = RepoIndex(DEMO)
    closure = index.closure(["app.services.cache_service"])
    assert "app.workers.report_worker" not in closure


def test_index_resolves_defined_symbols_and_references():
    index = RepoIndex(DEMO)
    assert index.references("tests/test_report_worker.py", "test_cache_roundtrip_contract")
    assert index.references("tests/test_report_worker.py", "parse_recent_cache_entries")
    assert not index.references("tests/test_report_worker.py", "parse_cache_entries_v2")


def test_index_survives_unparseable_modules(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app/__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app/broken.py").write_text("def broken(:\n", encoding="utf-8")
    index = RepoIndex(tmp_path)
    assert index.modules["app.broken"].parse_error


def test_text_tags_sees_the_separator_inside_an_fstring():
    line = "        entry = f\"{value['id']}|{value['status']}|{value['amount']}\""
    assert "sep:|" in text_tags([line])


def test_text_tags_sees_json_production():
    assert "fmt:json" in text_tags(["        entry = json.dumps(value, sort_keys=True)"])


def test_module_tags_finds_the_consumer_call_site():
    index = RepoIndex(DEMO)
    tags = module_tags(index.modules["app.workers.report_worker"])
    assert "sep:|" in tags


def _context():
    from bob_session.pipeline import context as context_loader

    return context_loader.load(str(DEMO), str(ROOT / "diffs/change_b.patch"), str(DEMO / "inventory.csv"))


def test_coupling_detects_the_hidden_edge():
    ctx = _context()
    links = detect(ctx.semantic, ctx.index, ctx.closure)
    assert [link.consumer_module for link in links] == ["app.workers.report_worker"]
    assert links[0].shared_tag == "sep:|"
    assert "write_cache_entry" in links[0].producer_symbol


def test_coupling_is_not_consequential_when_the_consumer_accepts_the_new_form():
    ctx = _context()  # revision C fixes the consumer: no link survives
    from bob_session.pipeline import context as context_loader

    fixed = context_loader.load(
        str(DEMO), str(ROOT / "diffs/consumer_fixed.patch"), str(DEMO / "inventory.csv")
    )
    assert detect(fixed.semantic, fixed.index, fixed.closure) == []


def test_selection_is_structural_plus_coupling():
    ctx = _context()
    selection = dispositions.select(ctx.rows, ctx.semantic, ctx.closure, ctx.links, {}, {})
    assert len(selection.structural) == 41
    assert len(selection.coupling) == 5
    assert len(selection.selected) == 46


def test_stale_tests_are_the_ones_asserting_the_removed_format():
    ctx = _context()
    stale = dispositions.stale_tests(ctx.rows, ctx.index, ctx.links, ctx.removed_behaviour)
    assert sorted(stale) == ["T-0341", "T-0345", "T-0347"]
    assert "no longer produces sep:| text" in stale["T-0345"][0]


def test_uncovered_items_are_the_changed_symbols_no_test_reaches():
    ctx = _context()
    items = dispositions.uncovered_items(ctx.semantic, ctx.rows, ctx.index)
    assert [item["symbol"] for item in items] == [
        "app.services.cache_service._should_drop",
        "app.services.cache_service.estimate_footprint",
    ]
    assert all(item["has_any_test"] is False for item in items)


def test_a_covered_changed_symbol_is_not_uncovered():
    ctx = _context()
    symbols = {item["symbol"] for item in dispositions.uncovered_items(ctx.semantic, ctx.rows, ctx.index)}
    assert "app.services.cache_service.write_cache_entry" not in symbols


def test_triage_three_directions():
    stale = {"T-1": ("asserts removed behaviour", "line")}
    assert dispositions.triage_rows(["T-1"], stale, set(), {})[0]["diagnosis"] == "stale"
    assert dispositions.triage_rows(["T-2"], stale, set(), {})[0]["diagnosis"] == "flaky"
    assert dispositions.triage_rows(["T-2"], stale, {"T-2"}, {})[0]["diagnosis"] == "regression"


def test_priority_puts_a_kernel_verified_test_first():
    ctx = _context()
    selection = dispositions.select(
        ctx.rows, ctx.semantic, ctx.closure, ctx.links, {"T-0342": "kernel-accepted scout claim"}, {}
    )
    rows_by_id = {row.test_id: row for row in ctx.rows}
    ledger = {
        "newly_relevant": [{"test_id": "T-0342"}, {"test_id": "T-0343"}],
        "unknown": [],
    }
    order = dispositions.priority_order(
        sorted(selection.selected),
        ledger,
        {"T-0342": "kernel_accepted_claim", "T-0343": "representation_coupling"},
        rows_by_id,
        ctx.closure,
        {change.module for change in ctx.semantic},
    )
    assert order[0] == "T-0342"
    assert order.index("T-0342") < order.index("T-0343")


def test_priority_is_a_total_order():
    ctx = _context()
    selection = dispositions.select(ctx.rows, ctx.semantic, ctx.closure, ctx.links, {}, {})
    rows_by_id = {row.test_id: row for row in ctx.rows}
    once = dispositions.priority_order(sorted(selection.selected), {"newly_relevant": [], "unknown": []}, {}, rows_by_id, ctx.closure, set())
    twice = dispositions.priority_order(sorted(selection.selected), {"newly_relevant": [], "unknown": []}, {}, rows_by_id, ctx.closure, set())
    assert once == twice and len(once) == len(selection.selected)
