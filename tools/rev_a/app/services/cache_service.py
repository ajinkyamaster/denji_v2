"""In-memory write-through cache for demo-service.

Entries are serialised as pipe-delimited text before they are handed to the
storage backend, so an operator can grep the cache file during an incident
(runbook, section "Cache file format").
"""
import json
from typing import Any, Dict, Optional

from app.config import cache_path, max_entries
from app.logging_setup import get_logger
from app.models import CacheEntry
from app.storage.backends import MemoryBackend
from app.telemetry import record
from app.utils.text import make_cache_key, truncate
from app.utils.timeutil import is_expired, now_ms
from app.validators import require

logger = get_logger(__name__)


class CacheService:
    """A write-through cache that serialises entries before storing them."""

    def __init__(self, backend: Optional[MemoryBackend] = None) -> None:
        self._backend = backend or MemoryBackend()
        self._entries: Dict[str, Dict[str, Any]] = {}

    def storage_path(self) -> str:
        """Return the configured cache file path."""
        return cache_path()

    def _storage_key(self, key: str) -> str:
        return make_cache_key("entry", key.encode("utf-8"))

    def write_cache_entry(self, key: str, value: Dict[str, Any]) -> str:
        """Serialise one entry, store it, and return the serialised form."""
        require(isinstance(value, dict), "value must be a mapping")
        key = truncate(str(key), 64)
        if len(self._entries) >= max_entries():
            self.evict_expired(now_ms())
        entry = f"{value['id']}|{value['status']}|{value['amount']}"
        self._backend.set(self._storage_key(key), entry)
        self._entries[key] = dict(value)
        record("cache.write")
        return entry

    def read_cache_entry(self, key: str) -> Optional[Dict[str, Any]]:
        """Read one entry back, accepting the layout that is on disk."""
        raw = self._backend.get(self._storage_key(truncate(str(key), 64)))
        if raw is None:
            record("cache.miss")
            return None
        record("cache.read")
        return self._deserialize(raw)

    def _deserialize(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse a stored entry, trying the JSON layout first."""
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            return parsed
        return self._parse_legacy(text)

    def _parse_legacy(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse the pipe-delimited layout written by older releases."""
        parts = text.split("|")
        if len(parts) < 3:
            return None
        try:
            return {"id": int(parts[0]), "status": parts[1], "amount": int(parts[2])}
        except ValueError:
            return None

    def _should_drop(self, value: Dict[str, Any], moment: int) -> bool:
        """Return True when an entry must be dropped at the given moment."""
        return is_expired(int(value.get("expires_at", 0)), moment)

    def evict_expired(self, now: Optional[int] = None) -> int:
        """Drop expired entries and return how many were removed."""
        moment = now_ms() if now is None else now
        removed = 0
        for key in list(self._entries):
            value = self._entries[key]
            if self._should_drop(value, moment):
                del self._entries[key]
                self._backend.delete(self._storage_key(key))
                removed += 1
        record("cache.evict", removed)
        return removed

    def entry_count(self) -> int:
        """Return the number of live entries."""
        return len(self._entries)
