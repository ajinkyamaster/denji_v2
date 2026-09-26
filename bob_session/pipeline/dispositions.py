"""Verdict computation: the four answers, from one link relation.

  classification   v1's three buckets (definitely / semantically / not affected)
  ledger           the disposition view: valid / stale / newly_relevant / unknown
  uncovered        changed symbols with no test link at all (work items)
  triage           why a failing test is red: regression / stale / flaky
  priority_order   a deterministic total order over the run list
"""
from __future__ import annotations

import ast
import dataclasses
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from bob_session.pipeline.coupling import CouplingLink, SEPARATOR_RE
from bob_session.pipeline.diffparse import SymbolChange
from bob_session.pipeline.index import RepoIndex
from bob_session.pipeline.inventory import Row

LEDGER_BUCKETS = ("valid", "stale", "newly_relevant", "unknown")
CLASS_BUCKETS = ("definitely_affected", "semantically_affected", "not_affected")


@dataclasses.dataclass
class Selection:
    """The run list, with the provenance of every addition."""

    selected: Set[str]
    structural: Set[str]
    coupling: Set[str]
    model: Set[str]
    unconfirmed: Set[str]
    reason: Dict[str, str]
    explanation: Dict[str, str]
    evidence: Dict[str, List[str]]


def document_symbol(module: str, symbol: str) -> str:
    return f"{module}.{symbol}" if symbol != "<module>" else module


def select(
    rows: Sequence[Row],
    changes: Sequence[SymbolChange],
    closure: Dict[str, int],
    links: Sequence[CouplingLink],
    accepted_tests: Dict[str, str],
    unconfirmed_tests: Dict[str, str],
) -> Selection:
    """Structural closure, representation coupling and kernel-accepted claims."""
    changed_modules = {change.module for change in changes}
    consumers = {link.consumer_module: link for link in links}
    structural: Set[str] = set()
    coupling: Set[str] = set()
    model: Set[str] = set()
    unconfirmed: Set[str] = set()
    reason: Dict[str, str] = {}
    explanation: Dict[str, str] = {}
    evidence: Dict[str, List[str]] = {}

    for row in rows:
        if row.module in changed_modules:
            structural.add(row.test_id)
            reason[row.test_id] = "structural_modification"
            explanation[row.test_id] = (
                f"{row.module} is modified by the change, so its own tests must run"
            )
        elif row.module in closure:
            depth = closure[row.module]
            structural.add(row.test_id)
            reason[row.test_id] = "structural_closure"
            explanation[row.test_id] = (
                f"{row.module} is in the import closure of the changed module "
                f"{sorted(changed_modules)[0]} (depth {depth})"
            )
        if row.module in consumers:
            link = consumers[row.module]
            coupling.add(row.test_id)
            reason[row.test_id] = "representation_coupling"
            explanation[row.test_id] = link.evidence()
            evidence[row.test_id] = [link.evidence()]

    for test_id, why in sorted(accepted_tests.items()):
        model.add(test_id)
        reason[test_id] = "kernel_accepted_claim"
        explanation[test_id] = why
        evidence.setdefault(test_id, []).append(why)

    for test_id, why in sorted(unconfirmed_tests.items()):
        unconfirmed.add(test_id)
        reason.setdefault(test_id, "unconfirmed_claim")
        explanation.setdefault(test_id, why)
        evidence.setdefault(test_id, []).append(f"unconfirmed (safe direction): {why}")

    return Selection(
        selected=structural | coupling | model | unconfirmed,
        structural=structural,
        coupling=coupling,
        model=model,
        unconfirmed=unconfirmed,
        reason=reason,
        explanation=explanation,
        evidence=evidence,
    )


# ---------------------------------------------------------------------------
# STALE: a test that asserts behaviour the change removed
# ---------------------------------------------------------------------------
def _test_function_source(index: RepoIndex, node_id: str) -> Optional[Tuple[str, List[str]]]:
    rel_path, _, name = node_id.partition("::")
    text = index.text_by_path.get(rel_path)
    if text is None:
        return None
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            start = node.lineno - 1
            end = getattr(node, "end_lineno", node.lineno)
            return rel_path, text.splitlines()[start:end]
    return None


def stale_tests(
    rows: Sequence[Row],
    index: RepoIndex,
    links: Sequence[CouplingLink],
    removed_behaviour: str,
) -> Dict[str, Tuple[str, str]]:
    """test_id -> (why, evidence line) for tests asserting a removed format."""
    separators = {
        link.shared_tag.split("sep:", 1)[1]
        for link in links
        if link.shared_tag.startswith("sep:") and link.shared_tag.split("sep:", 1)[1].strip()
    }
    if not separators:
        return {}
    found: Dict[str, Tuple[str, str]] = {}
    for row in rows:
        located = _test_function_source(index, row.node_id)
        if located is None:
            continue
        rel_path, lines = located
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for literal in _string_literals(line):
                if any(separator in literal for separator in separators):
                    found[row.test_id] = (
                        f"asserts the removed wire format ({removed_behaviour}); "
                        f"the assertion still passes, so its green is false assurance",
                        f"{rel_path}: {stripped}",
                    )
                    break
            if row.test_id in found:
                break
    return found


def _string_literals(line: str) -> List[str]:
    text = line.strip()
    if not text:
        return []
    tree = None
    for mode in ("eval", "exec"):
        try:
            tree = ast.parse(text, mode=mode)
            break
        except SyntaxError:
            continue
    if tree is None:
        return []
    found: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            for part in node.values:
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    found.append(part.value)
    return found


# ---------------------------------------------------------------------------
# UNCOVERED: changed symbols with no test link at all
# ---------------------------------------------------------------------------
def uncovered_items(
    changes: Sequence[SymbolChange],
    rows: Sequence[Row],
    index: RepoIndex,
) -> List[dict]:
    """One work item per changed symbol no test reaches."""
    items: List[dict] = []
    test_files = sorted({row.node_id.partition("::")[0] for row in rows})
    for change in changes:
        if not change.semantic or change.kind == "removed":
            continue
        reached = any(index.references(rel_path, change.symbol) for rel_path in test_files)
        if reached:
            continue
        items.append(
            {
                "symbol": document_symbol(change.module, change.symbol),
                "path": change.path,
                "line": change.line,
                "changed_lines": change.changed_lines,
                "has_any_test": False,
                "kind": change.kind,
                "reason": "changed symbol with no test referencing it",
            }
        )
    return sorted(items, key=lambda item: (item["path"], item["line"], item["symbol"]))


# ---------------------------------------------------------------------------
# TRIAGE: why is a failing test red?
# ---------------------------------------------------------------------------
def triage_rows(
    failing: Sequence[str],
    stale: Dict[str, Tuple[str, str]],
    selected: Set[str],
    covered_changed: Dict[str, bool],
) -> List[dict]:
    """Classify each failing test as regression, stale or flaky."""
    out: List[dict] = []
    for test_id in sorted(set(failing)):
        if test_id in stale:
            why, signal = stale[test_id]
            out.append({"test_id": test_id, "diagnosis": "stale", "signal": signal})
        elif test_id in selected or covered_changed.get(test_id):
            out.append(
                {
                    "test_id": test_id,
                    "diagnosis": "regression",
                    "signal": "fails at the new revision and is linked to the changed code",
                }
            )
        else:
            out.append(
                {
                    "test_id": test_id,
                    "diagnosis": "flaky",
                    "signal": (
                        "fails while executing none of the changed code and with no kernel-verified link; "
                        "quarantine rather than chase"
                    ),
                }
            )
    return out


# ---------------------------------------------------------------------------
# PRIORITY: a deterministic total order over the run list
# ---------------------------------------------------------------------------
SOURCE_RANK = {
    "kernel_accepted_claim": 0,
    "representation_coupling": 1,
    "structural_modification": 2,
    "structural_closure": 3,
    "unconfirmed_claim": 4,
}


def priority_order(
    selected: Sequence[str],
    ledger: Dict[str, List[dict]],
    reasons: Dict[str, str],
    rows_by_id: Dict[str, Row],
    closure: Dict[str, int],
    changed_modules: Set[str],
) -> List[str]:
    """Tier 0 newly-relevant, 1 unknown, 2 covers changed code, 3 the rest."""
    newly_relevant = {entry["test_id"] for entry in ledger["newly_relevant"]}
    unknown = {entry["test_id"] for entry in ledger["unknown"]}

    def tier(test_id: str) -> int:
        if test_id in newly_relevant:
            return 0
        if test_id in unknown:
            return 1
        if rows_by_id[test_id].module in changed_modules or rows_by_id[test_id].module in closure:
            return 2
        return 3

    def sort_key(test_id: str) -> Tuple[int, int, int, int, str]:
        row = rows_by_id[test_id]
        depth = closure.get(row.module, 0)
        return (
            tier(test_id),
            SOURCE_RANK.get(reasons.get(test_id, ""), 9),
            -depth,
            row.avg_runtime_ms,
            test_id,
        )

    return sorted(selected, key=sort_key)
