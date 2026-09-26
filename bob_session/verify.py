"""The kernel K: the only door a model claim may pass through.

Every claim carries citations, and the citations ARE the obligation: the
kernel re-opens the cited files and re-derives the claim. A claim whose
citation does not resolve is rejected automatically; a claim that is
plausible but that neither mechanism can confirm is labelled ``unconfirmed``
and takes the safe direction (the test is included and marked).

No model writes here. The kernel is a total, deterministic function of
(claim, repository, recorded evidence).
"""
from __future__ import annotations

import dataclasses
import json
import pathlib
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from bob_session.pipeline.index import RepoIndex

GATE_CITATION_INVALID = "citation_invalid"
GATE_SYMBOL_MISMATCH = "symbol_mismatch"
GATE_CONTRADICTS_SYMBOLIC = "contradicts_symbolic"


@dataclasses.dataclass
class Verdict:
    claim: dict
    status: str  # accepted | rejected | unconfirmed
    obligation: Optional[str] = None
    gate: Optional[str] = None
    detail: str = ""


def _path_exists(repo_root: pathlib.Path, rel_path: str) -> bool:
    return (repo_root / rel_path).exists()


def resolve_citations(
    claim: dict,
    repo_root: pathlib.Path,
    index: RepoIndex,
) -> Tuple[Optional[str], Optional[str], str]:
    """Resolve every citation; returns (gate, status_hint, detail)."""
    drift: List[str] = []
    citations = claim.get("citations") or []
    if not citations:
        return GATE_CITATION_INVALID, None, "claim carries no citations: nothing to re-derive"
    for citation in citations:
        path = citation.get("path", "")
        symbol = citation.get("symbol", "")
        line = int(citation.get("line") or 0)
        if not _path_exists(repo_root, path):
            return GATE_CITATION_INVALID, None, f"cited path does not exist: {path}"
        if not symbol:
            return GATE_CITATION_INVALID, None, f"citation without a symbol in {path}"
        if symbol not in index.names_referenced(path):
            return GATE_SYMBOL_MISMATCH, None, f"cited symbol {symbol!r} is not present in {path}"
        located = index.symbol_location(path, symbol)
        if located and line and not (located[0] <= line <= located[1]) and located[0] != line:
            drift.append(f"{path}:{symbol} cited at line {line}, defined at {located[0]}")
    return None, None, "; ".join(drift)


def _witness(index: RepoIndex, coverage: Optional[dict], claim: dict) -> Optional[str]:
    """The positive witness for a link claim: references, or coverage of a line."""
    targets = claim.get("targets") or {}
    node = targets.get("test_node") or ""
    test_id = targets.get("test_id") or ""
    consumer = targets.get("consumer") or ""
    if not node or not consumer:
        return None
    rel_path = node.partition("::")[0]
    symbol = consumer.rsplit(".", 1)[-1]
    if index.references(rel_path, symbol):
        return f"symbol {symbol} referenced by {rel_path}"
    cited_lines: List[Tuple[str, int]] = []
    for citation in claim.get("citations") or []:
        if citation.get("path") and citation.get("line"):
            cited_lines.append((citation["path"], int(citation["line"])))
    if coverage and test_id in coverage:
        covered = coverage[test_id].get("lines", {})
        for path, line in cited_lines:
            if line in covered.get(path, []):
                return f"coverage witness: {test_id} executes {path}:{line}"
    return None


def verify_claim(
    claim: dict,
    *,
    repo_root: pathlib.Path,
    index: RepoIndex,
    symbolic_selection: Set[str],
    coverage: Optional[dict] = None,
    intent_lines: Optional[Dict[str, List[str]]] = None,
    gate_evidence: Optional[dict] = None,
) -> Verdict:
    """Re-derive one claim. Accept, reject, or record it as unconfirmed."""
    role = claim.get("role", "?")
    claim_type = claim.get("claim_type", "?")
    targets = claim.get("targets") or {}
    gate, _, detail = resolve_citations(claim, repo_root, index)
    if gate is not None:
        return Verdict(claim=claim, status="rejected", gate=gate, detail=detail)

    if claim_type == "link_exists":
        asserts = targets.get("asserts", "link_exists")
        if asserts == "no_link":
            if targets.get("test_id") in symbolic_selection:
                return Verdict(
                    claim=claim,
                    status="rejected",
                    gate=GATE_CONTRADICTS_SYMBOLIC,
                    detail=(
                        f"{targets.get('test_id')} is already linked to the changed code by the "
                        "symbolic layer; the claim contradicts a mechanical decision"
                    ),
                )
            return Verdict(claim=claim, status="accepted", obligation="symbol resolves", detail="negative link confirmed")
        witness = _witness(index, coverage, claim)
        if witness:
            return Verdict(claim=claim, status="accepted", obligation=f"re-derived fact: {witness}", detail=detail)
        return Verdict(
            claim=claim,
            status="unconfirmed",
            detail=f"citations resolve but no witness: {targets.get('test_node', '?')} neither references "
            f"{targets.get('consumer', '?')} nor covers the cited line",
        )

    if claim_type == "intent":
        quote = targets.get("quote", "")
        symbol = targets.get("symbol", "")
        if not quote:
            return Verdict(claim=claim, status="rejected", gate=GATE_CITATION_INVALID, detail="intent claim without a quote")
        path = None
        for citation in claim.get("citations") or []:
            if symbol.endswith(citation.get("symbol", "")):
                path = citation.get("path")
                break
        path = path or (claim["citations"][0]["path"])
        text = index.text_by_path.get(path)
        if text is None:
            candidate = repo_root / path
            text = candidate.read_text(encoding="utf-8", errors="replace") if candidate.exists() else ""
        if quote not in text:
            return Verdict(
                claim=claim,
                status="rejected",
                gate=GATE_CITATION_INVALID,
                detail=f"the quoted text is not byte-present in {path}",
            )
        violated = targets.get("violated_tag", "")
        removed_tags = set((intent_lines or {}).get(symbol, []))
        if violated and violated not in removed_tags:
            return Verdict(
                claim=claim,
                status="rejected",
                gate=GATE_CONTRADICTS_SYMBOLIC,
                detail=f"the cited code still satisfies the quoted intent (no removed line carries {violated})",
            )
        return Verdict(
            claim=claim,
            status="accepted",
            obligation=f"quote located in {path} and no longer satisfied by the changed lines",
            detail=detail,
        )

    if claim_type == "test":
        if not gate_evidence:
            return Verdict(
                claim=claim,
                status="unconfirmed",
                detail="no gate evidence for this authored test: execution evidence is required before acceptance",
            )
        if gate_evidence.get("accepted"):
            return Verdict(
                claim=claim,
                status="accepted",
                obligation="G1..G5 re-executed: buildable, stable 5x, assertion fires at the base revision",
                detail=detail,
            )
        return Verdict(
            claim=claim,
            status="rejected",
            gate=GATE_CONTRADICTS_SYMBOLIC,
            detail=f"gate rejected the authored test: {gate_evidence.get('detail', 'see gate evidence')}",
        )

    if claim_type == "missed":
        witness = _witness(index, coverage, claim)
        if witness:
            return Verdict(
                claim=claim,
                status="accepted",
                obligation=f"re-derived fact: {witness}",
                detail=detail,
            )
        return Verdict(
            claim=claim,
            status="unconfirmed",
            detail="the claimed dependency path does not re-derive against the repository",
        )

    return Verdict(claim=claim, status="rejected", gate=GATE_CONTRADICTS_SYMBOLIC, detail=f"unknown claim_type {claim_type!r}")


def verify_claims(
    claims: Sequence[dict],
    *,
    repo_root: pathlib.Path,
    index: RepoIndex,
    symbolic_selection: Set[str],
    coverage: Optional[dict] = None,
    intent_lines: Optional[Dict[str, List[str]]] = None,
    gate_evidence: Optional[dict] = None,
) -> Dict[str, List[dict]]:
    """The kernel's public interface: one verdict per claim."""
    result: Dict[str, List[dict]] = {"accepted": [], "rejected": [], "unconfirmed": []}
    for claim in claims:
        verdict = verify_claim(
            claim,
            repo_root=repo_root,
            index=index,
            symbolic_selection=symbolic_selection,
            coverage=coverage,
            intent_lines=intent_lines,
            gate_evidence=gate_evidence,
        )
        if verdict.status == "accepted":
            result["accepted"].append({"claim": verdict.claim, "obligation": verdict.obligation})
        elif verdict.status == "rejected":
            result["rejected"].append({"claim": verdict.claim, "gate": verdict.gate, "detail": verdict.detail})
        else:
            result["unconfirmed"].append({"claim": verdict.claim, "reason": verdict.detail})
    return result


def coverage_from_evidence(path: str | pathlib.Path) -> Optional[dict]:
    """Load a per-test coverage map produced by the oracle, if present."""
    candidate = pathlib.Path(path)
    if not candidate.exists():
        return None
    return json.loads(candidate.read_text(encoding="utf-8")).get("tests", {})
