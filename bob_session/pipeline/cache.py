"""Content-addressed replay, and the assumptions reuse depends on.

Determinism is a property of the kernel plus the cache, not of the models
(Theorem 1). This module is the replay half: it keys a stored artefact by the
content of everything that could change it, so a replay cannot return yesterday's
answer as today's.

Soundness conditions, stated rather than assumed:

  * content-hash invalidation is sound with respect to **source** changes — the
    key contains the content hash of the repository, the diff, the inventory, the
    prompt version and the tool version;
  * it is **not** sound with respect to environment changes (interpreter, OS,
    library versions), test-order effects and cross-test pollution, time/locale/
    random seed, or external fixtures. Those are declared below and the
    environment fingerprint is in the key as the cheap partial defence;
  * an unsound cache is worse than no cache: it reports a stale answer with full
    confidence. So every reuse is recorded in the artefact, with the reason.

Writes are atomic (temp file plus ``os.replace``) so a killed run cannot leave a
truncated artefact behind. The cache never writes inside the analysed repository:
the analysed repository is input, and writing into it would break invariant K1.
"""

import hashlib
import json
import os
import platform
import shutil
import sys
import tempfile
from pathlib import Path

from .paths import MAX_FILE_BYTES, is_generated, read_text

DECLARED_ASSUMPTIONS = [
    "content-hash invalidation is sound for source changes and NOT sound for environment changes",
    "test order and cross-test pollution are not modelled; gate G2 detects order dependence where it can",
    "time, locale and random seed are assumed not to affect the selection",
    "external fixtures and network services are assumed to be stable between the compared runs",
    "the inventory is assumed to be a faithful description of the suite it was written about",
]


def environment_fingerprint():
    """A deterministic fingerprint of the interpreter and platform.

    No clock, no hostname, no user: this value is part of a cache key, so it must
    be a pure function of the environment it describes.
    """
    parts = [
        f"python={sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        f"impl={platform.python_implementation()}",
        f"system={platform.system()}",
        f"machine={platform.machine()}",
    ]
    return "|".join(parts)


def _hash_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def content_hash_of_tree(root, *, max_bytes=MAX_FILE_BYTES):
    """SHA-256 over ``(relative path, content)`` pairs, in sorted path order."""
    root = Path(root)
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or is_generated(path):
            continue
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\x00")
        try:
            if path.stat().st_size > max_bytes:
                digest.update(b"<oversized>")
                continue
            with open(path, "rb") as handle:
                digest.update(handle.read())
        except OSError:
            digest.update(b"<unreadable>")
        digest.update(b"\x00")
    return digest.hexdigest()


def cache_key(*, repo_hash, diff_hash, inventory_hash, prompt_version, tool_version, env_fingerprint, extra=()):
    """The cache key: a pure function of the content everything depends on."""
    payload = json.dumps(
        {
            "repo": repo_hash,
            "diff": diff_hash,
            "inventory": inventory_hash,
            "prompt_version": prompt_version,
            "tool_version": tool_version,
            "environment": env_fingerprint,
            "extra": sorted(extra),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ArtifactCache:
    """A tiny content-addressed store of serialised artefacts."""

    def __init__(self, directory):
        self.directory = Path(directory)

    def ensure_outside(self, repo_root):
        """Refuse to store anything inside the analysed repository (invariant K1)."""
        from .errors import SafetyError

        repo = Path(repo_root).resolve()
        target = self.directory.resolve()
        if target == repo or repo in target.parents:
            raise SafetyError(
                f"cache directory {target} is inside the analysed repository {repo}: "
                "the analysed repository is input and is never written to"
            )
        return self

    def path_for(self, key):
        return self.directory / f"{key}.json"

    def load(self, key):
        path = self.path_for(key)
        if not path.exists():
            return None
        text, reason = read_text(path)
        if text is None:
            return None
        return text

    def store(self, key, text):
        self.directory.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=str(self.directory), prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path_for(key))
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return self.path_for(key)

    def invalidate_all(self):
        if self.directory.exists():
            shutil.rmtree(self.directory, ignore_errors=True)
