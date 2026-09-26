"""Account lifecycle service.

Account events are mirrored into the recent-entry cache so that the reporting
worker can summarise activity without touching the account store.
"""

from app.services.cache_service import read_cache_entries, write_cache_entry

OPEN_STATE = "open"
CLOSED_STATE = "closed"


def open_account(account_id, owner):
    """Create an account record and mirror the event into the cache."""
    record = {"id": account_id, "owner": owner, "state": OPEN_STATE}
    write_cache_entry(account_id, OPEN_STATE, 1)
    return record


def record_event(account_id, kind, count=1, sink=None):
    """Mirror one account event into the cache sink."""
    return write_cache_entry(account_id, kind, count, sink=sink)


def account_summary(account_id, cache_path):
    """Count the cached entries that belong to ``account_id``."""
    entries = read_cache_entries(cache_path)
    return sum(1 for entry in entries if entry.startswith(account_id))
