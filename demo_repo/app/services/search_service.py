"""Account search over cached entry payloads."""

from app.services.cache_service import read_cache_entries


def match_accounts(entries, query):
    """Entries whose text contains ``query``, case-insensitively."""
    needle = query.lower()
    return [entry for entry in entries if needle in entry.lower()]


def search_cache(path, query):
    """Search a cache file for ``query``."""
    return match_accounts(read_cache_entries(path), query)


def rank(entries, query):
    """Rank matches by descending text length, then by content (total order)."""
    matches = match_accounts(entries, query)
    return sorted(matches, key=lambda entry: (-len(entry), entry))
