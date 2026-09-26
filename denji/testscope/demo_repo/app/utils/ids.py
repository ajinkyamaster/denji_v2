"""Identifier formatting and validation helpers."""

_PREFIXES = ("ACCT", "INV", "TXN")


def account_id(number):
    """``ACCT-000123`` style account identifier."""
    return f"ACCT-{number:06d}"


def invoice_id(number):
    """``INV-000123`` style invoice identifier."""
    return f"INV-{number:06d}"


def is_valid_id(value):
    """True when ``value`` is ``<PREFIX>-<6 digits>`` with a known prefix.

    The check is written against the prefix rather than against a total length,
    because the prefixes are not all the same length (``ACCT`` is four
    characters, ``INV`` and ``TXN`` are three).
    """
    if not isinstance(value, str):
        return False
    for prefix in _PREFIXES:
        if value.startswith(f"{prefix}-"):
            digits = value[len(prefix) + 1 :]
            return len(digits) == 6 and digits.isdigit()
    return False


def next_sequence(values):
    """One past the largest numeric suffix in ``values``.

    Non-conforming values are ignored. An empty input yields 1.
    """
    highest = 0
    for value in values:
        if is_valid_id(value):
            highest = max(highest, int(value.split("-")[-1]))
    return highest + 1
