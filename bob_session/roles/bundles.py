"""Deterministic input bundles for the four inference roles.

Each bundle is a pure function of (repository text, diff, inventory), so its
digest is a cache key: same inputs, same key, same replay. The Author's
bundle carries the PRE-change body and the intent artefact, and never the
post-change body (the information asymmetry the architecture requires).
"""
from __future__ import annotations

import hashlib
from typing import Dict, Iterable, List, Sequence

from bob_session.pipeline.coupling import text_tags
from bob_session.pipeline.diffparse import FileChange, SymbolChange, reconstruct_pre
from bob_session.pipeline.dispositions import document_symbol
from bob_session.pipeline.index import RepoIndex
from bob_session.pipeline.coupling import CouplingLink
from bob_session.pipeline.inventory import Row
from bob_session.proposal_cache import bundle_digest, repo_digest

ROLE_ORDER = ("scout", "cartographer", "author", "falsifier")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _consumers_of(index: RepoIndex, rel_path: str, tag: str) -> bool:
    """True when a test file consumes the given format tag."""
    text = index.text_by_path.get(rel_path)
    if text is None:
        path = index.root / rel_path
        if not path.exists():
            return False
        text = path.read_text(encoding="utf-8", errors="replace")
    return tag in text_tags(text.splitlines())


def build(
    *,
    rows: Sequence[Row],
    index: RepoIndex,
    semantic: Sequence[SymbolChange],
    links: Sequence[CouplingLink],
    closure: Dict[str, int],
    file_changes: Sequence[FileChange],
    diff_text: str,
    inventory_text: str,
    symbolically_selected: Sequence[str],
    uncovered_items: Sequence[dict],
    authored_symbols: Iterable[str] = (),
) -> Dict[str, dict]:
    """The four role input bundles, in the cascade's order."""
    repo_tree_digest = repo_digest(index.root)
    diff_digest = _sha(diff_text)
    inventory_digest = _sha(inventory_text)
    coupled_modules = {link.consumer_module for link in links}
    removed_tags = sorted({tag for change in semantic for tag in text_tags(text for text, _ in change.removed)})
    separators = [tag.split("sep:", 1)[1] for tag in removed_tags if tag.startswith("sep:")]

    candidates: List[dict] = []
    for row in rows:
        rel_path = row.node_id.partition("::")[0]
        if row.module in coupled_modules or row.module in closure:
            continue
        for tag in removed_tags:
            if _consumers_of(index, rel_path, tag):
                demonstrate = [
                    link.evidence() for link in links if link.shared_tag == tag
                ]
                candidates.append(
                    {
                        "test_id": row.test_id,
                        "test_node": row.node_id,
                        "declared_module": row.module,
                        "shared_tag": tag,
                        "known_coupling": demonstrate,
                    }
                )
                break

    scout = {
        "repo_digest": repo_tree_digest,
        "diff_digest": diff_digest,
        "inventory_digest": inventory_digest,
        "removed_tags": removed_tags,
        "candidate_pairs": candidates,
        "verified_couplings": [link.evidence() for link in links],
    }

    cartographer = {
        "producer_file_digest": _sha(index.text_by_path.get(semantic[0].path, "")) if semantic else "",
        "symbols": [
            {
                "symbol": document_symbol(change.module, change.symbol),
                "path": change.path,
                "removed_tags": sorted(text_tags(text for text, _ in change.removed)),
            }
            for change in semantic
            if change.removed
        ],
    }

    authored = set(authored_symbols)
    by_symbol = {document_symbol(change.module, change.symbol): change for change in semantic}
    author = {
        "test_file": "tests/test_cache_service.py",
        "symbols": [
            {
                "symbol": item["symbol"],
                "path": item["path"],
                "pre_body_digest": _sha(_pre_body(index, by_symbol[item["symbol"]], file_changes)),
                "intent_artefact": _intent_quote(index, by_symbol[item["symbol"]]),
                "post_change_body": "WITHHELD",
            }
            for item in uncovered_items
            if item["symbol"] in by_symbol and item["symbol"] not in authored
        ],
    }

    falsifier = {
        "diff_digest": diff_digest,
        "symbolic_selection_digest": _sha(",".join(sorted(symbolically_selected))),
        "unselected": [
            {"test_id": row.test_id, "test_node": row.node_id, "declared_module": row.module}
            for row in rows
            if row.test_id not in set(symbolically_selected)
        ],
    }

    bundles = {"scout": scout, "cartographer": cartographer, "author": author, "falsifier": falsifier}
    for role, bundle in bundles.items():
        bundle["cache_key"] = bundle_digest(role, bundle)
    return bundles


def bundle_keys(bundles: Dict[str, dict]) -> Dict[str, str]:
    return {role: bundle["cache_key"] for role, bundle in bundles.items()}


def _pre_body(index: RepoIndex, change: SymbolChange, file_changes: Sequence[FileChange]) -> str:
    """The PRE-change source of a changed symbol (reconstructed from the diff)."""
    post_text = index.text_by_path.get(change.path, "")
    path_change = _file_change_for(file_changes, change.path)
    if path_change is None:
        return ""
    pre_text = reconstruct_pre(post_text, path_change)
    lines = pre_text.splitlines()
    numbers = [number for _, number in change.removed] or [number for _, number in change.added]
    if not numbers:
        return ""
    start, end = min(numbers), max(numbers)
    return "\n".join(lines[max(start - 1, 0) : end])


def _file_change_for(file_changes: Sequence[FileChange], rel_path: str) -> FileChange | None:
    for candidate in file_changes:
        if candidate.path == rel_path:
            return candidate
    return None


def _intent_quote(index: RepoIndex, change: SymbolChange) -> str:
    """The first non-empty line of the module docstring of the changed file."""
    text = index.text_by_path.get(change.path, "")
    lines = text.splitlines()
    for line in lines[:20]:
        stripped = line.strip().strip('"').strip()
        if stripped and not stripped.startswith(("import", "from", "#")):
            return stripped
    return ""
