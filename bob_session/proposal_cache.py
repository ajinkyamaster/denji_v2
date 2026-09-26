"""Content-addressed proposal cache.

Determinism is a property of the kernel and the cache, not of the models:
the artefact is ``f(inputs, K(P))`` where ``P`` is addressed by content. A
warm cache replays byte-identically; a cold cache with no model available
degrades to the deterministic baseline and says so.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Dict, Iterable, List, Optional

DEFAULT_CACHE_DIR = "bob_session/proposal_cache"


def canonical(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def repo_digest(root: str | pathlib.Path) -> str:
    """Content digest of a repository tree (ignoring VCS and caches)."""
    base = pathlib.Path(root)
    hasher = hashlib.sha256()
    skip = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".venv", "var"}
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        if any(part in skip for part in path.relative_to(base).parts):
            continue
        hasher.update(path.relative_to(base).as_posix().encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
        hasher.update(b"\n")
    return hasher.hexdigest()


def bundle_digest(role: str, bundle: dict) -> str:
    """The cache key's input digest: role plus the whole input bundle."""
    return hashlib.sha256(canonical({"role": role, "bundle": bundle}).encode("utf-8")).hexdigest()


def cache_key(role: str, prompt_version: str, digest: str) -> str:
    return f"{role}-{prompt_version}-{digest[:16]}"


class ProposalCache:
    """A directory of content-addressed proposal sets."""

    def __init__(self, root: str | pathlib.Path) -> None:
        self.root = pathlib.Path(root)

    def path_for(self, role: str, prompt_version: str, digest: str) -> pathlib.Path:
        return self.root / f"{cache_key(role, prompt_version, digest)}.json"

    def lookup(self, role: str, prompt_version: str, digest: str) -> Optional[dict]:
        path = self.path_for(role, prompt_version, digest)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def store(self, role: str, prompt_version: str, digest: str, payload: dict) -> pathlib.Path:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path_for(role, prompt_version, digest)
        body = {
            "role": role,
            "prompt_version": prompt_version,
            "bundle_digest": digest,
            "coins": payload.get("coins", 0),
            "model": payload.get("model", "recorded"),
            "recorded_at": payload.get("recorded_at", "2026-09-26T00:00:00Z"),
            "claims": payload.get("claims", []),
        }
        path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def clear(self) -> None:
        if self.root.exists():
            for path in sorted(self.root.glob("*.json")):
                path.unlink()
