"""The test inventory: a human-written document, so malformed input is normal.

Three defects are rejected outright, because each of them has a silent failure
mode that produces a plausible-but-wrong artefact:

  * a missing or renamed required column -> :class:`InventoryError`
  * a duplicate ``test_id`` -> :class:`InventoryError`
  * a non-numeric ``avg_runtime_ms`` -> :class:`InventoryError`. This one was
    once silently coerced to 0, which makes a corrupt row look like the fastest
    test in the suite and silently wins the duration tie-break.

Column names are matched case-insensitively and the file format is chosen by
extension (``.xlsx`` via openpyxl, ``.csv`` via the standard library). No other
dependency is used, and no dependency is required to read the CSV form.
"""

import csv
from dataclasses import dataclass

from .errors import InventoryError

REQUIRED_COLUMNS = ("test_id", "test_name", "module", "avg_runtime_ms")
OPTIONAL_COLUMNS = ("description", "status", "owner")


@dataclass(frozen=True)
class InventoryRow:
    """One row of the QA inventory, in file order."""

    test_id: str
    test_name: str
    module: str
    avg_runtime_ms: int
    description: str
    sequence: int

    @property
    def runtime(self):
        return self.avg_runtime_ms


def _normalise_header(raw_header):
    return [str(cell).strip().lower() if cell is not None else "" for cell in raw_header]


def _validate_header(header, source):
    missing = [column for column in REQUIRED_COLUMNS if column not in header]
    if missing:
        raise InventoryError(
            f"{source}: missing required inventory column(s): {', '.join(missing)}. "
            f"Required: {', '.join(REQUIRED_COLUMNS)}"
        )
    return {column: header.index(column) for column in REQUIRED_COLUMNS + OPTIONAL_COLUMNS if column in header}


def _read_rows(path):
    """Return ``(header, rows, source)`` for a .csv or .xlsx file."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with open(path, "r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            try:
                header = next(reader)
            except StopIteration:
                raise InventoryError(f"{path}: empty inventory file") from None
            return header, [row for row in reader], str(path)
    if suffix in (".xlsx", ".xlsm"):
        try:
            from openpyxl import load_workbook
        except ImportError as error:  # pragma: no cover - exercised via the CSV path
            raise InventoryError(
                f"{path}: reading .xlsx requires openpyxl; export the inventory as .csv "
                "or install openpyxl (see requirements.txt)"
            ) from error
        workbook = load_workbook(filename=str(path), read_only=True, data_only=True)
        sheet = workbook[workbook.sheetnames[0]]
        rows = list(sheet.iter_rows(values_only=True))
        workbook.close()
        if not rows:
            raise InventoryError(f"{path}: empty inventory file")
        return list(rows[0]), [list(row) for row in rows[1:]], str(path)
    raise InventoryError(f"{path}: unsupported inventory format {suffix!r}; use .csv or .xlsx")


def load_inventory(path):
    """Load and validate an inventory file into a list of :class:`InventoryRow`.

    Returns rows in file order, which is the deterministic ordering used
    everywhere downstream.
    """
    header, raw_rows, source = _read_rows(path)
    columns = _validate_header(_normalise_header(header), source)
    rows = []
    seen = {}
    for offset, raw in enumerate(raw_rows, start=2):  # line 1 is the header
        values = list(raw) + [None] * (len(header) - len(raw))

        def cell(name):
            index = columns.get(name)
            if index is None or index >= len(values) or values[index] is None:
                return ""
            return str(values[index]).strip()

        test_id = cell("test_id")
        if not test_id:
            continue  # a fully blank trailing row is not a claim about a test
        if test_id in seen:
            raise InventoryError(
                f"{source}: line {offset}: duplicate test_id {test_id!r} "
                f"(first seen on line {seen[test_id]})"
            )
        seen[test_id] = offset

        raw_runtime = cell("avg_runtime_ms")
        try:
            runtime = int(raw_runtime)
        except ValueError:
            raise InventoryError(
                f"{source}: line {offset}: avg_runtime_ms for {test_id} is not numeric: "
                f"{raw_runtime!r}. Refusing to coerce it to 0."
            ) from None

        rows.append(
            InventoryRow(
                test_id=test_id,
                test_name=cell("test_name"),
                module=cell("module"),
                avg_runtime_ms=runtime,
                description=cell("description"),
                sequence=len(rows),
            )
        )
    if not rows:
        raise InventoryError(f"{source}: no inventory rows")
    return rows


def module_of(row):
    """The inventory's *declared* module for a row (a claim, not a fact)."""
    return row.module
