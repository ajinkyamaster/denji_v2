"""Recent-activity reporting.

Wire format (written by :func:`app.services.cache_service.write_cache_entry`):
cache entries are pipe-delimited records ``key|status|count``. This module
parses that format; it deliberately imports nothing from the cache service,
because the format is the contract rather than the module.

A payload that does not have exactly three fields is kept as ``{"raw": ...}``
instead of raising: a half-understood entry must not take the report down.
"""


def read_cache_file(path):
    """Read a cache file into a list of payload strings, blank lines dropped."""
    with open(path, "r", encoding="utf-8") as handle:
        return [line.rstrip("\n") for line in handle if line.strip()]


def parse_recent_cache_entries(entries):
    """Parse cache payloads into ``{key, status, count}`` records.

    Entries whose payload does not have three pipe-delimited fields are
    returned as ``{"raw": payload}``.
    """
    parsed = []
    for entry in entries:
        fields = entry.split("|")
        if len(fields) != 3:
            parsed.append({"raw": entry})
            continue
        key, status, count_text = fields
        parsed.append({"key": key, "status": status, "count": int(count_text)})
    return parsed


def summarise_entries(entries):
    """Total count across parsed entries that carry a numeric count."""
    return sum(record.get("count", 0) for record in parse_recent_cache_entries(entries))


def recent_keys(entries, limit=10):
    """The first ``limit`` keys, in cache order."""
    return [record["key"] for record in parse_recent_cache_entries(entries) if "key" in record][:limit]
