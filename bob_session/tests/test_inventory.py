"""The inventory loader: malformed input is normal, silent coercion is not.

The non-numeric-runtime case is a regression test for a real defect: the value was
once coerced to 0, which made a corrupt row look like the fastest test in the
suite and silently won the duration tie-break.
"""

import pytest

from bob_session.pipeline.errors import InventoryError
from bob_session.pipeline.inventory import REQUIRED_COLUMNS, load_inventory

from .conftest import INVENTORY, INVENTORY_XLSX


def test_demo_inventory_loads_500_rows(inventory_rows):
    assert len(inventory_rows) == 500
    assert len({row.test_id for row in inventory_rows}) == 500


def test_required_columns_are_present_and_named(inventory_rows):
    assert REQUIRED_COLUMNS == ("test_id", "test_name", "module", "avg_runtime_ms")
    assert all(row.test_name for row in inventory_rows)


def test_missing_column_is_refused(tmp_path):
    path = tmp_path / "inventory.csv"
    path.write_text("test_id,test_name,module\nT-0001,t,mod\n", encoding="utf-8")
    with pytest.raises(InventoryError, match="missing required inventory column"):
        load_inventory(path)


def test_renamed_column_is_refused_not_ignored(tmp_path):
    path = tmp_path / "inventory.csv"
    path.write_text("id,test_name,module,avg_runtime_ms\nT-0001,t,mod,5\n", encoding="utf-8")
    with pytest.raises(InventoryError):
        load_inventory(path)


def test_duplicate_test_id_is_refused(tmp_path):
    path = tmp_path / "inventory.csv"
    path.write_text(
        "test_id,test_name,module,avg_runtime_ms\nT-0001,t,mod,5\nT-0001,u,mod,6\n", encoding="utf-8"
    )
    with pytest.raises(InventoryError, match="duplicate test_id"):
        load_inventory(path)


def test_non_numeric_runtime_is_refused_not_coerced(tmp_path):
    path = tmp_path / "inventory.csv"
    path.write_text("test_id,test_name,module,avg_runtime_ms\nT-0001,t,mod,fast\n", encoding="utf-8")
    with pytest.raises(InventoryError, match="not numeric"):
        load_inventory(path)


def test_blank_trailing_rows_are_ignored(tmp_path):
    path = tmp_path / "inventory.csv"
    path.write_text(
        "test_id,test_name,module,avg_runtime_ms\nT-0001,t,mod,5\n,,,,,,\n", encoding="utf-8"
    )
    rows = load_inventory(path)
    assert [row.test_id for row in rows] == ["T-0001"]


def test_csv_and_xlsx_agree_row_for_row():
    """Two serialisations of one inventory must not drift apart.

    The loader supports both because real QA inventories arrive as spreadsheets;
    if the two forms ever disagree, every downstream number becomes ambiguous.
    """
    openpyxl = pytest.importorskip("openpyxl", reason="xlsx support requires openpyxl")
    assert INVENTORY.exists() and INVENTORY_XLSX.exists()
    csv_rows = load_inventory(INVENTORY)
    xlsx_rows = load_inventory(INVENTORY_XLSX)
    assert len(csv_rows) == len(xlsx_rows)
    for left, right in zip(csv_rows, xlsx_rows):
        assert left == right


def test_unsupported_format_is_refused_loudly(tmp_path):
    path = tmp_path / "inventory.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(InventoryError, match="unsupported inventory format"):
        load_inventory(path)
