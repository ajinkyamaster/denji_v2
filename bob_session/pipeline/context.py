"""The analysis context: everything the symbolic stratum derives from inputs.

Both the ledger run and the proposal recorder build this, so the cache keys
and the verdicts are computed from exactly the same inputs.
"""
from __future__ import annotations

import dataclasses
import pathlib
from typing import Dict, List, Sequence

from bob_session.pipeline import coupling, diffparse, inventory
from bob_session.pipeline.coupling import CouplingLink
from bob_session.pipeline.diffparse import FileChange, SymbolChange
from bob_session.pipeline.index import RepoIndex
from bob_session.pipeline.inventory import Row


@dataclasses.dataclass
class Context:
    repo_path: pathlib.Path
    rows: List[Row]
    diff_text: str
    inventory_text: str
    file_changes: List[FileChange]
    docs_changed: List[str]
    changes: List[SymbolChange]
    semantic: List[SymbolChange]
    closure: Dict[str, int]
    links: List[CouplingLink]
    index: RepoIndex

    @property
    def removed_behaviour(self) -> str:
        if not self.links:
            return "behaviour removed by the diff"
        link = self.links[0]
        return f"{link.producer_module}.{link.producer_symbol} no longer produces {link.shared_tag} text"


def load(repo: str | pathlib.Path, diff_path: str | pathlib.Path, inventory_path: str | pathlib.Path) -> Context:
    repo_path = pathlib.Path(repo)
    rows = inventory.load(inventory_path)
    inventory_text = pathlib.Path(inventory_path).read_text(encoding="utf-8")
    diff_text = pathlib.Path(diff_path).read_text(encoding="utf-8")
    file_changes = diffparse.parse_diff(diff_text)
    index = RepoIndex(repo_path)
    changes: List[SymbolChange] = []
    docs_changed: List[str] = []
    for file_change in file_changes:
        if not file_change.is_python:
            docs_changed.append(file_change.path)
            continue
        post_text = (repo_path / file_change.path).read_text(encoding="utf-8")
        module = index.module_of_path(file_change.path) or file_change.path
        changes.extend(diffparse.attribute(file_change, post_text, module))
    semantic = [change for change in changes if change.semantic]
    closure = index.closure([change.module for change in semantic])
    links = coupling.detect(semantic, index, closure)
    return Context(
        repo_path=repo_path,
        rows=rows,
        diff_text=diff_text,
        inventory_text=inventory_text,
        file_changes=file_changes,
        docs_changed=docs_changed,
        changes=changes,
        semantic=semantic,
        closure=closure,
        links=links,
        index=index,
    )
