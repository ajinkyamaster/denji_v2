#!/usr/bin/env python3
"""Populate the proposal cache from the recorded role outputs.

This is the recording step of the workflow: the four roles' outputs live in
``bob_session/roles/recorded/<role>.json`` and are written into the
content-addressed cache under the digest of the exact input bundle they
were produced from. A later run with the same inputs replays them; a run
with different inputs misses the cache and degrades to the deterministic
baseline, which is the designed behaviour rather than a failure.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from bob_session import PROMPT_VERSION
from bob_session.pipeline import context as context_loader
from bob_session.pipeline import dispositions
from bob_session.proposal_cache import ProposalCache
from bob_session.roles import ROLE_PROMPTS, bundles


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="demo")
    parser.add_argument("--diff", default="diffs/change_b.patch")
    parser.add_argument("--inventory", default="demo/inventory.csv")
    parser.add_argument("--cache", default="bob_session/proposal_cache")
    parser.add_argument("--recorded", default="bob_session/roles/recorded")
    args = parser.parse_args(argv)

    ctx = context_loader.load(args.repo, args.diff, args.inventory)
    selection = dispositions.select(ctx.rows, ctx.semantic, ctx.closure, ctx.links, {}, {})
    uncovered = dispositions.uncovered_items(ctx.semantic, ctx.rows, ctx.index)
    built = bundles.build(
        rows=ctx.rows,
        index=ctx.index,
        semantic=ctx.semantic,
        links=ctx.links,
        closure=ctx.closure,
        file_changes=ctx.file_changes,
        diff_text=ctx.diff_text,
        inventory_text=ctx.inventory_text,
        symbolically_selected=sorted(selection.selected),
        uncovered_items=uncovered,
    )
    cache = ProposalCache(args.cache)
    cache.root.mkdir(parents=True, exist_ok=True)
    for role in bundles.ROLE_ORDER:
        recorded_path = pathlib.Path(args.recorded) / f"{role}.json"
        if not recorded_path.exists():
            print(f"{role}: no recorded proposal set at {recorded_path}")
            continue
        payload = __import__("json").loads(recorded_path.read_text(encoding="utf-8"))
        digest = built[role]["cache_key"]
        stored = cache.store(role, PROMPT_VERSION, digest, payload)
        print(f"{role}: {len(payload.get('claims', []))} claim(s), {payload.get('coins', 0)} coins -> {stored.name}")
        print(f"   prompt: {ROLE_PROMPTS[role].split('.')[0]}.")
    print(f"cache: {cache.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
