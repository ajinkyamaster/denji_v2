"""Cleanup worker: trims cache files and reports what it removed."""

from app.services.cache_service import read_cache_entries

MAX_ENTRIES = 500


def trim(entries, limit=MAX_ENTRIES):
    """Keep the newest ``limit`` entries (the tail of the sequence)."""
    if limit < 0:
        raise ValueError("limit must not be negative")
    return list(entries[-limit:]) if limit else []


def is_blank(payload):
    """True when a payload carries no content."""
    return not payload.strip()


def clean_cache(path, limit=MAX_ENTRIES):
    """Read, drop blanks, trim, and return ``(kept, dropped)`` counts."""
    entries = read_cache_entries(path)
    without_blanks = [entry for entry in entries if not is_blank(entry)]
    kept = trim(without_blanks, limit)
    return len(kept), len(without_blanks) - len(kept)
