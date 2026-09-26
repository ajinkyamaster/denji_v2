"""Cache service: writes the recent-entry records that other modules consume.

Revision B of this module serialises entries as JSON objects. Revision A used
a pipe-delimited record (``key|status|count``); the consumer in
``app.workers.report_worker`` is responsible for reading what this module
writes.
"""

import json

CACHE_SCHEMA = "recent-v2"


def build_cache_payload(key, status, count):
    """Serialise one cache entry as a JSON object with sorted keys."""
    return json.dumps({"key": key, "status": status, "count": count}, sort_keys=True)


def write_cache_entry(key, status, count, sink=None):
    """Serialise one cache entry and optionally append it to ``sink``.

    ``sink`` is any object with ``append`` (a list, typically). The serialised
    payload is returned either way.
    """
    payload = build_cache_payload(key, status, count)
    if sink is not None:
        sink.append(payload)
    return payload


def read_cache_entries(path):
    """Read a cache file into a list of payload strings, blank lines dropped."""
    with open(path, "r", encoding="utf-8") as handle:
        return [line.rstrip("\n") for line in handle if line.strip()]


def purge_stale_entries(entries, max_age_seconds):
    """Drop cache entries whose recorded age exceeds ``max_age_seconds``.

    ``entries`` is a sequence of ``(payload, age_seconds)`` pairs; the returned
    list keeps only the payloads that are still fresh.
    """
    return [payload for payload, age_seconds in entries if age_seconds <= max_age_seconds]
