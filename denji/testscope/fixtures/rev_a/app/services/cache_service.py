"""Cache service: writes the recent-entry records that other modules consume.

Entries are serialised as pipe-delimited records (``key|status|count``); the
consumer in ``app.workers.report_worker`` parses that format.
"""

CACHE_SCHEMA = "recent-v1"


def write_cache_entry(key, status, count, sink=None):
    """Serialise one cache entry and optionally append it to ``sink``.

    ``sink`` is any object with ``append`` (a list, typically). The serialised
    payload is returned either way.
    """
    payload = f"{key}|{status}|{count}"
    if sink is not None:
        sink.append(payload)
    return payload


def read_cache_entries(path):
    """Read a cache file into a list of payload strings, blank lines dropped."""
    with open(path, "r", encoding="utf-8") as handle:
        return [line.rstrip("\n") for line in handle if line.strip()]
