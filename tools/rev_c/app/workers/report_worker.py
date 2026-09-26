"""Builds operator reports from the most recent cache entries.

The report worker reads the cache file directly and deliberately does not
import the cache service: it runs as a separate process with a read-only
view of the cache.
"""
import json
from typing import Any, Dict, List, Optional

from app.models import CacheEntry, Report
from app.telemetry import record

STATUS_UNKNOWN = "unknown"


def parse_recent_cache_entries(raw_line: str) -> Optional[Dict[str, Any]]:
    """Parse one serialised cache entry.

    The cache stores entry objects as JSON text; the legacy pipe-delimited
    layout is still accepted for files written by older releases.
    """
    if not raw_line or not raw_line.strip():
        return None
    text = raw_line.strip()
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        parsed = None
    if isinstance(parsed, dict):
        try:
            return {"id": int(parsed["id"]), "status": str(parsed["status"]), "amount": int(parsed["amount"])}
        except (KeyError, TypeError, ValueError):
            return None
    parts = text.split("|")
    if len(parts) < 3:
        return None
    try:
        return {"id": int(parts[0]), "status": parts[1], "amount": int(parts[2])}
    except ValueError:
        return None


def build_report(lines: List[str]) -> Report:
    """Fold raw cache lines into an aggregated report."""
    report = Report()
    for line in lines:
        parsed = parse_recent_cache_entries(line)
        if parsed is None:
            continue
        entry = CacheEntry(
            id=parsed["id"],
            status=parsed["status"] or STATUS_UNKNOWN,
            amount=int(parsed["amount"]),
        )
        report.add(entry)
    record("report.built", report.entries)
    return report
