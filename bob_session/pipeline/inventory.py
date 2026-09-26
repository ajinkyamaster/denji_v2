"""Test inventory loading, with loud validation.

The v1 discipline is kept: malformed input fails loudly, it is never
silently coerced. A non-numeric runtime used to become 0; now it is an
InventoryError naming the line.
"""
from __future__ import annotations

import csv
import dataclasses
from typing import Dict, List, Set

REQUIRED_COLUMNS = ("test_id", "test_name", "module", "node_id", "description", "avg_runtime_ms")


class InventoryError(ValueError):
    """Raised when the inventory cannot be trusted."""


@dataclasses.dataclass(frozen=True)
class Row:
    test_id: str
    test_name: str
    module: str
    node_id: str
    description: str
    avg_runtime_ms: int


def load(path: str) -> List[Row]:
    """Load and validate an inventory CSV."""
    rows: List[Row] = []
    seen: Set[str] = set()
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        missing = [column for column in REQUIRED_COLUMNS if column not in headers]
        if missing:
            raise InventoryError(f"missing inventory column(s): {', '.join(missing)}")
        for line_number, raw in enumerate(reader, start=2):
            test_id = (raw.get("test_id") or "").strip()
            if not test_id:
                raise InventoryError(f"line {line_number}: empty test_id")
            if test_id in seen:
                raise InventoryError(f"line {line_number}: duplicate test_id {test_id}")
            seen.add(test_id)
            runtime_text = (raw.get("avg_runtime_ms") or "").strip()
            try:
                runtime = int(runtime_text)
            except ValueError:
                raise InventoryError(
                    f"line {line_number}: avg_runtime_ms is not an integer: {runtime_text!r}"
                ) from None
            if runtime < 0:
                raise InventoryError(f"line {line_number}: avg_runtime_ms is negative")
            module = (raw.get("module") or "").strip()
            if not module:
                raise InventoryError(f"line {line_number}: empty module")
            rows.append(
                Row(
                    test_id=test_id,
                    test_name=(raw.get("test_name") or "").strip(),
                    module=module,
                    node_id=(raw.get("node_id") or "").strip(),
                    description=(raw.get("description") or "").strip(),
                    avg_runtime_ms=runtime,
                )
            )
    if not rows:
        raise InventoryError("inventory is empty")
    return rows


def by_id(rows: List[Row]) -> Dict[str, Row]:
    return {row.test_id: row for row in rows}
