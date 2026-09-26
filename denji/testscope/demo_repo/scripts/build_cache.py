#!/usr/bin/env python3
"""Build a recent-entry cache file.

The report worker reads what this script writes, but the two never import each
other: the shared contract is the wire format produced by
``app.services.cache_service``.

This lives under ``scripts/`` rather than inside the ``app`` package on purpose:
it is an operator entry point, not part of the application's module graph. It
still depends on the cache service, and the ledger says so separately.

Run from the repository root:

    python scripts/build_cache.py --out cache/recent.cache
"""

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.cache_service import write_cache_entry  # noqa: E402 - path set above

DEFAULT_ROWS = (
    ("acct-1", "ok", 2),
    ("acct-2", "retry", 1),
    ("acct-3", "failed", 4),
)


def build(path, rows=DEFAULT_ROWS):
    """Write ``rows`` as cache entries to ``path``; return the payloads."""
    payloads = [write_cache_entry(key, status, count) for key, status, count in rows]
    target = pathlib.Path(path)
    if target.parent != pathlib.Path(""):
        target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for payload in payloads:
            handle.write(payload + "\n")
    return payloads


def main(argv=None):
    """Parse arguments and build the cache file."""
    parser = argparse.ArgumentParser(description="build a recent-entry cache file")
    parser.add_argument("--out", required=True, help="destination path")
    args = parser.parse_args(argv)
    payloads = build(args.out)
    print(f"wrote {len(payloads)} entries to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
