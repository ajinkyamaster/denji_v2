"""Ingest worker: turns incoming events into cache entries."""

from app.services.cache_service import write_cache_entry

STATUSES = ("ok", "retry", "failed")


def normalise_status(raw):
    """Map an arbitrary status string onto the known set, defaulting to retry."""
    return raw if raw in STATUSES else "retry"


def ingest_event(event, sink=None):
    """Write one event into the cache and return the payload."""
    status = normalise_status(event.get("status", ""))
    return write_cache_entry(event["key"], status, int(event.get("count", 1)), sink=sink)


def ingest_batch(events, sink=None):
    """Ingest a sequence of events, returning the payloads in order."""
    return [ingest_event(event, sink=sink) for event in events]


def summarise_batch(events):
    """Count events per normalised status, in sorted key order."""
    counts = {}
    for event in events:
        status = normalise_status(event.get("status", ""))
        counts[status] = counts.get(status, 0) + 1
    return {key: counts[key] for key in sorted(counts)}
