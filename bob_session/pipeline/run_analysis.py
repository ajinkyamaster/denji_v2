#!/usr/bin/env python3
"""testscope_ledger: the deterministic engine.

    python3 -m bob_session.pipeline.run_analysis \
        --repo demo --diff diffs/change_b.patch --inventory demo/inventory.csv \
        --out bob_session/testscope_report.json

Everything the engine can decide, it decides here: zero model calls, zero
coins. The model layer enters only as recorded proposals looked up by the
digest of their input bundle, and every claim of theirs is re-derived by the
kernel before it can appear in the artefact.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from typing import Dict, List, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from bob_session import ENGINE_VERSION, PROMPT_VERSION, SCHEMA_VERSION
from bob_session.pipeline import artefact as artefact_mod
from bob_session.pipeline import context as context_loader
from bob_session.pipeline import dispositions
from bob_session.pipeline.coupling import text_tags
from bob_session.pipeline.dispositions import document_symbol
from bob_session.proposal_cache import ProposalCache
from bob_session.roles import bundles
from bob_session import verify

DEFAULT_TIMESTAMP = "2026-09-26T00:00:00Z"


def _read_json(path: pathlib.Path) -> Optional[dict]:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _changed_lines_by_path(semantic) -> Dict[str, Set[int]]:
    out: Dict[str, Set[int]] = {}
    for change in semantic:
        out.setdefault(change.path, set()).update(change.changed_lines)
    return out


def run(
    *,
    repo: str = "demo",
    diff_path: str = "diffs/change_b.patch",
    inventory_path: str = "demo/inventory.csv",
    generated_at: str = DEFAULT_TIMESTAMP,
    model_layer: str = "enabled",
    proposal_cache: str = "bob_session/proposal_cache",
    evidence_dir: str = "bob_session/evidence",
    ablation_baseline: Optional[str] = None,
) -> dict:
    """Build the ledger artefact for one change."""
    if model_layer not in ("enabled", "disabled"):
        raise ValueError("model_layer must be 'enabled' or 'disabled'")
    ctx = context_loader.load(repo, diff_path, inventory_path)
    symbolic = dispositions.select(ctx.rows, ctx.semantic, ctx.closure, ctx.links, {}, {})
    uncovered_symbolic = dispositions.uncovered_items(ctx.semantic, ctx.rows, ctx.index)

    evidence_path = pathlib.Path(evidence_dir)
    coverage = verify.coverage_from_evidence(evidence_path / "coverage_b.json")
    gate_evidence = _read_json(evidence_path / "gate_author.json")
    oracle = _read_json(evidence_path / "oracle.json")

    # -- the inference stratum: recorded proposals, replayed by content -----
    claims: List[dict] = []
    coins = 0
    hits = 0
    role_coins: Dict[str, int] = {}
    if model_layer == "enabled":
        built = bundles.build(
            rows=ctx.rows,
            index=ctx.index,
            semantic=ctx.semantic,
            links=ctx.links,
            closure=ctx.closure,
            file_changes=ctx.file_changes,
            diff_text=ctx.diff_text,
            inventory_text=ctx.inventory_text,
            symbolically_selected=sorted(symbolic.selected),
            uncovered_items=uncovered_symbolic,
        )
        cache = ProposalCache(proposal_cache)
        for role in bundles.ROLE_ORDER:
            entry = cache.lookup(role, PROMPT_VERSION, built[role]["cache_key"])
            if entry is None:
                continue
            hits += 1
            coins += int(entry.get("coins", 0))
            role_coins[role] = int(entry.get("coins", 0))
            claims.extend(entry.get("claims", []))
        if hits == len(bundles.ROLE_ORDER):
            model_status = "warm-cache-replay"
        elif hits:
            model_status = "partial-cache"
        else:
            model_status = "model-unavailable"
    else:
        model_status = "disabled"
    model_coverage = hits / len(bundles.ROLE_ORDER)

    intent_lines = {
        document_symbol(change.module, change.symbol): sorted(text_tags(text for text, _ in change.removed))
        for change in ctx.semantic
    }
    verdicts = (
        verify.verify_claims(
            claims,
            repo_root=ctx.repo_path,
            index=ctx.index,
            symbolic_selection=symbolic.selected,
            coverage=coverage,
            intent_lines=intent_lines,
            gate_evidence=gate_evidence,
        )
        if claims
        else {"accepted": [], "rejected": [], "unconfirmed": []}
    )

    accepted_tests: Dict[str, str] = {}
    accepted_refs: Dict[str, str] = {}
    unconfirmed_tests: Dict[str, str] = {}
    claims_detail = {"accepted": [], "rejected": [], "unconfirmed": []}
    rejection_ledger: List[dict] = []
    by_role: Dict[str, dict] = {}

    def role_stats(role: str) -> dict:
        return by_role.setdefault(role, {"proposed": 0, "accepted": 0, "rejected": 0, "unconfirmed": 0, "coins": role_coins.get(role, 0)})

    for item in verdicts["accepted"]:
        claim = item["claim"]
        targets = claim.get("targets") or {}
        test_id = targets.get("test_id")
        ref = f"{claim.get('role')}:{claim.get('claim_type')}:{test_id or targets.get('symbol', '-')}"
        claims_detail["accepted"].append({"claim": claim, "obligation": item.get("obligation"), "claim_ref": ref})
        role_stats(claim.get("role", "?")).__setitem__("accepted", role_stats(claim.get("role", "?")).get("accepted", 0) + 1)
        if test_id:
            accepted_tests[test_id] = (
                f"kernel-accepted {claim.get('role')} claim for {test_id}: {item.get('obligation')}"
            )
            accepted_refs[test_id] = ref
    for item in verdicts["rejected"]:
        claim = item["claim"]
        ref = f"{claim.get('role')}:{claim.get('claim_type')}:{(claim.get('targets') or {}).get('test_id', '-')}"
        claims_detail["rejected"].append(
            {"claim": claim, "gate": item.get("gate"), "detail": item.get("detail"), "claim_ref": ref}
        )
        role_stats(claim.get("role", "?"))["rejected"] += 1
        rejection_ledger.append(
            {"role": claim.get("role"), "gate": item.get("gate"), "detail": item.get("detail"), "claim_ref": ref}
        )
    for item in verdicts["unconfirmed"]:
        claim = item["claim"]
        targets = claim.get("targets") or {}
        test_id = targets.get("test_id")
        claims_detail["unconfirmed"].append({"claim": claim, "reason": item.get("reason")})
        role_stats(claim.get("role", "?"))["unconfirmed"] += 1
        if test_id:
            unconfirmed_tests[test_id] = f"unconfirmed {claim.get('role')} claim: {item.get('reason')}"
    for claim in claims:
        role_stats(claim.get("role", "?"))["proposed"] += 1

    selection = dispositions.select(
        ctx.rows, ctx.semantic, ctx.closure, ctx.links, accepted_tests, unconfirmed_tests
    )

    # -- the four answers ---------------------------------------------------
    stale = dispositions.stale_tests(ctx.rows, ctx.index, ctx.links, ctx.removed_behaviour)
    stale_ids = set(stale)
    newly_ids = (set(selection.coupling) | set(selection.model)) - stale_ids
    unknown_ids = set(selection.unconfirmed) - stale_ids - newly_ids
    all_ledger = stale_ids | newly_ids | unknown_ids
    valid_ids = [row.test_id for row in ctx.rows if row.test_id not in all_ledger]

    authored_symbols = {
        (item["claim"].get("targets") or {}).get("symbol")
        for item in claims_detail["accepted"]
        if item["claim"].get("claim_type") == "test"
    }
    uncovered = [dict(item) for item in uncovered_symbolic]
    for item in uncovered:
        item["authored"] = item["symbol"] in authored_symbols

    # -- triage and ordering ------------------------------------------------
    node_to_id = {row.node_id: row.test_id for row in ctx.rows}
    rows_by_id = {row.test_id: row for row in ctx.rows}
    changed_nodes = list(oracle.get("changed", [])) if oracle else []
    failing_ids = [node_to_id[node] for node in changed_nodes if node in node_to_id]
    changed_lines = _changed_lines_by_path(ctx.semantic)
    covered_changed: Dict[str, bool] = {}
    if coverage:
        for test_id, entry in coverage.items():
            lines = entry.get("lines", {})
            covered_changed[test_id] = any(
                set(lines.get(path, [])) & numbers for path, numbers in changed_lines.items()
            )
    triage = dispositions.triage_rows(failing_ids, stale, selection.selected, covered_changed)
    priority = dispositions.priority_order(
        sorted(selection.selected),
        {"newly_relevant": [{"test_id": test_id} for test_id in sorted(newly_ids)],
         "unknown": [{"test_id": test_id} for test_id in sorted(unknown_ids)]},
        selection.reason,
        rows_by_id,
        ctx.closure,
        {change.module for change in ctx.semantic},
    )

    # -- classification (v1 shape, unchanged) -------------------------------
    def classification_row(row) -> dict:
        return {
            "test_id": row.test_id,
            "test_name": row.test_name,
            "module": row.module,
            "reason": selection.reason.get(row.test_id, "no_link"),
            "explanation": selection.explanation.get(row.test_id, "no structural or behavioural link to the diff"),
        }

    linked = set(selection.coupling) | set(selection.model) | set(selection.unconfirmed)
    classification = {
        "definitely_affected": [classification_row(row) for row in ctx.rows if row.test_id in selection.structural],
        "semantically_affected": [classification_row(row) for row in ctx.rows if row.test_id in linked],
        "not_affected": [
            classification_row(row)
            for row in ctx.rows
            if row.test_id not in selection.structural and row.test_id not in linked
        ],
    }

    # -- the ledger ---------------------------------------------------------
    ledger = {
        "valid": [
            {"test_id": test_id, "why": "no link to the changed code; its assertions are untouched by the change"}
            for test_id in valid_ids
        ],
        "stale": [
            {
                "test_id": test_id,
                "why": why,
                "removed_behaviour": ctx.removed_behaviour,
                "link_evidence": [signal]
                + ([accepted_refs[test_id]] if test_id in accepted_refs else []),
            }
            for test_id, (why, signal) in sorted(stale.items())
        ],
        "newly_relevant": [
            {
                "test_id": test_id,
                "why": selection.explanation[test_id],
                "link_evidence": _link_evidence(test_id, selection, accepted_refs, ctx),
            }
            for test_id in sorted(newly_ids)
        ],
        "unknown": [
            {
                "test_id": test_id,
                "why": selection.explanation[test_id],
                "link_evidence": [f"safe direction: {test_id} was included because its claim could not be confirmed"],
            }
            for test_id in sorted(unknown_ids)
        ],
    }

    # -- measurement --------------------------------------------------------
    inventory_total = len(ctx.rows)
    changed_ids = [node_to_id[node] for node in changed_nodes if node in node_to_id]
    complete = bool(oracle.get("complete")) if oracle else False
    truth_size = len(changed_ids) if complete else None
    missed = sorted(set(changed_ids) - selection.selected) if complete else []
    if complete and changed_ids:
        recall: Optional[float] = round(len(set(changed_ids) & selection.selected) / len(changed_ids), 6)
        recall_reason = None
    elif complete:
        recall = None
        recall_reason = "the oracle found no discriminating test on this change; recall is undefined, not zero"
    else:
        recall = None
        recall_reason = "oracle incomplete: a measurement narrower than the inventory is VOID (M1)"
    ablation_delta = None
    baseline = _read_json(pathlib.Path(ablation_baseline)) if ablation_baseline else None
    if baseline is not None:
        baseline_recall = (baseline.get("measurement") or {}).get("recall")
        if baseline_recall is not None and recall is not None:
            ablation_delta = round(recall - baseline_recall, 6)
    measurement = {
        "oracle": {
            "collected": (oracle or {}).get("collected", 0),
            "inventory_total": (oracle or {}).get("inventory_total", inventory_total),
            "complete": complete,
            "missing": sorted((oracle or {}).get("missing", [])),
            "unmapped": sorted((oracle or {}).get("unmapped", [])),
            "already_red": sorted((oracle or {}).get("already_red", [])),
            "flaky_excluded": sorted((oracle or {}).get("flaky_excluded", [])),
            "flaky_excluded_count": len((oracle or {}).get("flaky_excluded", [])),
            "strategy": (oracle or {}).get("strategy", "not run"),
        },
        "truth_size": truth_size,
        "selected": len(selection.selected),
        "structurally_reachable": len(selection.structural),
        "recall": recall,
        "recall_reason": recall_reason,
        "missed": missed,
        "price_of_safety": len(selection.selected) - len(selection.structural),
        "model_layer_recall_delta": ablation_delta,
    }

    total = inventory_total
    selected_count = len(selection.selected)
    summary = {
        "total": total,
        "selected_for_run": selected_count,
        "definitely_affected_count": len(selection.structural),
        "semantically_affected_count": len(linked),
        "stale_linked_count": len(stale_ids & linked),
        "reduction_pct": round(100.0 * (1 - selected_count / total), 1) if total else 0.0,
        "stale_count": len(stale_ids),
        "uncovered_count": len(uncovered),
        "newly_relevant_count": len(newly_ids),
        "valid_count": len(valid_ids),
        "unknown_count": len(unknown_ids),
    }

    art = {
        "run_metadata": {
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "diff_files": sorted(file_change.path for file_change in ctx.file_changes),
            "docs_files": sorted(ctx.docs_changed),
            "changed_symbols": sorted(document_symbol(change.module, change.symbol) for change in ctx.semantic),
            "inert_symbols": sorted(
                document_symbol(change.module, change.symbol) for change in ctx.changes if not change.semantic
            ),
            "import_closure": {module: depth for module, depth in sorted(ctx.closure.items())},
            "total_tests_in_suite": total,
            "generated_at": generated_at,
            "model_layer": model_layer,
            "model_status": model_status,
            "model_coverage": model_coverage,
            "prompt_version": PROMPT_VERSION,
            "coins_spent": coins,
            "coins_note": "recorded session cost, replayed from the content-addressed cache; the replay itself spends none",
        },
        "classification": classification,
        "ledger": ledger,
        "uncovered": uncovered,
        "claims": {
            "proposed": len(claims),
            "accepted": len(claims_detail["accepted"]),
            "rejected": len(claims_detail["rejected"]),
            "unconfirmed": len(claims_detail["unconfirmed"]),
            "by_role": by_role,
        },
        "claims_detail": claims_detail,
        "rejection_ledger": rejection_ledger,
        "measurement": measurement,
        "triage": triage,
        "priority_order": priority,
        "summary": summary,
    }
    violations = artefact_mod.validate(art)
    art["invariants"] = {"checked": ["I1", "I2", "I4", "I13", "I14", "I15", "I16"], "violations": violations}
    return art


def _link_evidence(test_id: str, selection, accepted_refs: Dict[str, str], ctx) -> List[str]:
    evidence = list(selection.evidence.get(test_id, []))
    if test_id in accepted_refs and accepted_refs[test_id] not in " ".join(evidence):
        evidence.append(accepted_refs[test_id])
    if not evidence:
        evidence.append(f"{test_id} is linked to changed code with no recorded evidence line")
    return evidence


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="TestScope ledger engine (MCP tool: testscope_ledger)")
    parser.add_argument("--repo", default="demo")
    parser.add_argument("--diff", default="diffs/change_b.patch")
    parser.add_argument("--inventory", default="demo/inventory.csv")
    parser.add_argument("--out", default="bob_session/testscope_report.json")
    parser.add_argument("--generated-at", default=os.environ.get("TESTSCOPE_GENERATED_AT", DEFAULT_TIMESTAMP))
    parser.add_argument("--model-layer", default="enabled", choices=("enabled", "disabled"))
    parser.add_argument("--proposal-cache", default="bob_session/proposal_cache")
    parser.add_argument("--evidence-dir", default="bob_session/evidence")
    parser.add_argument("--ablation-baseline", default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    art = run(
        repo=args.repo,
        diff_path=args.diff,
        inventory_path=args.inventory,
        generated_at=args.generated_at,
        model_layer=args.model_layer,
        proposal_cache=args.proposal_cache,
        evidence_dir=args.evidence_dir,
        ablation_baseline=args.ablation_baseline,
    )
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(artefact_mod.dumps(art), encoding="utf-8")
    if not args.quiet:
        summary = art["summary"]
        print(f"ledger written: {out}")
        print(f"  selected {summary['selected_for_run']}/{summary['total']} ({summary['reduction_pct']}% reduction)")
        print(f"  structural {summary['definitely_affected_count']}, semantic {summary['semantically_affected_count']}, "
              f"stale {summary['stale_count']}, uncovered {summary['uncovered_count']}")
        print(f"  model layer: {art['run_metadata']['model_layer']} ({art['run_metadata']['model_status']}, "
              f"coverage {art['run_metadata']['model_coverage']})")
        if art["invariants"]["violations"]:
            for problem in art["invariants"]["violations"]:
                print(f"  INVARIANT VIOLATION: {problem}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
