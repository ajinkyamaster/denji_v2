"""Path confinement and guarded reads.

The analysed repository is untrusted input. A diff is a text file written by
somebody else, so every path it names (``+++ b/...``, ``--- a/...``) is attacker-
controlled. The rules enforced here:

  * a repository-relative path may not be absolute, may not contain ``..``, and
    may not contain NUL or backslashes (which Windows treats as separators);
  * the resolved path must stay inside the repository root *after* symlinks are
    resolved, so a symlink inside the repository cannot be used to read
    ``/etc/shadow``;
  * reads are size-capped and decoding is guarded, so a 10 GB file or an invalid
    UTF-8 sequence is a recorded skip rather than a crash or an OOM.
"""

import os
from pathlib import Path

from .errors import SafetyError

MAX_FILE_BYTES = 8 * 1024 * 1024


def assert_inside(repo_root, candidate):
    """True when ``candidate`` resolves inside ``repo_root``."""
    try:
        root = Path(repo_root).resolve()
        resolved = Path(candidate).resolve()
    except OSError:
        return False
    return resolved == root or root in resolved.parents


def refuse_reason(relative):
    """Return the reason a repository-relative path is refused, else ``None``.

    This is the *single* statement of the path rule. It exists as a predicate
    (not only as the raise in :func:`resolve_in_repo`) because a diff may name a
    hostile path, and the ledger has to choose between two honest options: crash,
    or **declare and exclude** it. A predicate lets the second happen without a
    second copy of the rule drifting away from the first - two copies of a
    security rule is one copy too many.

    Never touches the filesystem: symlink escapes are decided by
    :func:`assert_inside`, which needs the resolved path.
    """
    if not isinstance(relative, str) or not relative:
        return "empty path in diff"
    if "\x00" in relative:
        return "NUL byte in path"
    if relative.startswith(("/", "\\")) or (os.name == "nt" and ":" in relative.split("/")[0]):
        return f"absolute path refused: {relative!r}"
    if "\\" in relative:
        return f"backslash separator refused: {relative!r}"
    parts = relative.split("/")
    if any(part in ("..", "") for part in parts):
        return f"parent traversal refused: {relative!r}"
    return None


def is_confined_relative(relative):
    """True when ``relative`` is a plain repository-relative path."""
    return refuse_reason(relative) is None


def resolve_in_repo(repo_root, relative, *, must_exist=False):
    """Resolve a repository-relative path, refusing anything that escapes.

    Returns an absolute ``Path``. Raises :class:`SafetyError` on an absolute
    path, parent traversal, NUL, a backslash, or a symlink escape.
    """
    reason = refuse_reason(relative)
    if reason is not None:
        raise SafetyError(reason)
    candidate = Path(repo_root) / relative
    if must_exist and not candidate.exists():
        raise SafetyError(f"path does not exist: {relative!r}")
    if not assert_inside(repo_root, candidate):
        raise SafetyError(f"path escapes the repository: {relative!r}")
    return candidate


def read_text(path, *, max_bytes=MAX_FILE_BYTES):
    """Read a text file, returning ``(text, reason)`` where reason is None on success.

    Never raises for size or encoding: an undecodable or oversized file is a
    *recorded skip*, because the alternative is a crash on somebody else's
    repository.
    """
    try:
        size = os.path.getsize(path)
    except OSError as error:
        return None, f"unreadable: {error.__class__.__name__}"
    if size > max_bytes:
        return None, f"too large: {size} bytes > {max_bytes}"
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read(), None
    except UnicodeDecodeError:
        return None, "undecodable: not valid utf-8"
    except OSError as error:
        return None, f"unreadable: {error.__class__.__name__}"


def is_generated(path):
    """True for paths that are build outputs rather than repository sources."""
    parts = Path(path).parts
    return any(part in ("__pycache__", ".pytest_cache", ".mypy_cache", ".git") for part in parts)
