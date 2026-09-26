"""CSV export of cached entries."""

from app.services.cache_service import read_cache_entries

HEADER = "entry,length"


def export_rows(entries):
    """Render ``entry,length`` rows for a sequence of cache payloads."""
    return [HEADER] + [f"{entry},{len(entry)}" for entry in entries]


def export_filename(prefix, stamp):
    """Deterministic export file name."""
    return f"{prefix}-{stamp}.csv"


def export_cache(path, prefix, stamp):
    """Read a cache file and return ``(filename, rows)``."""
    return export_filename(prefix, stamp), export_rows(read_cache_entries(path))
