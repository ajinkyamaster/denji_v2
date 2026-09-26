"""Duration parsing and formatting helpers (millisecond granularity)."""

_UNITS_MS = {"ms": 1, "s": 1000, "m": 60000, "h": 3600000}


def parse_duration_ms(text):
    """Parse ``"1500ms"``/``"2s"``/``"1m"``/``"1h"`` into milliseconds.

    Raises ``ValueError`` on an unknown unit or a non-numeric quantity.
    """
    for suffix in ("ms", "h", "m", "s"):
        if text.endswith(suffix):
            quantity = text[: -len(suffix)]
            if not quantity.isdigit():
                raise ValueError(f"not a duration: {text!r}")
            return int(quantity) * _UNITS_MS[suffix]
    raise ValueError(f"not a duration: {text!r}")


def format_duration(milliseconds):
    """Render milliseconds using the largest unit that divides exactly."""
    for unit in ("h", "m", "s"):
        size = _UNITS_MS[unit]
        if milliseconds and milliseconds % size == 0:
            return f"{milliseconds // size}{unit}"
    return f"{milliseconds}ms"


def add_seconds(epoch_seconds, seconds):
    """Add ``seconds`` to an epoch timestamp."""
    return epoch_seconds + seconds


def is_business_day(weekday):
    """True for Monday..Friday, where Monday is 0."""
    return 0 <= weekday <= 4
