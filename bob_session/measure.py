#!/usr/bin/env python3
"""measure.py: the prefix of the submission that is a number (D1).

Reads the ledger artefact and the oracle's executed ground truth and emits
``submissions/measurement.json``:

    truth_size, selected, structurally_reachable, recall, missed,
    price_of_safety, oracle (verbatim), ablation

Four rules are enforced here, not merely documented:

  M1  neither truth_size nor recall is published unless oracle.complete is
      true; otherwise the field carries the literal string "VOID"
  M2  recall measures recall only: the oracle is a LOWER BOUND on the truly
      affected set, so over-selection is invisible to it
  M3  ``missed`` is always emitted, even when empty
  M4  every number here is reproduced by running this file

Usage:

    python3 bob_session/measure.py \
        --artefact bob_session/testscope_report.json \
        --disabled submissions/ablation/disabled.json \
        --oracle bob_session/evidence/oracle.json \
        --inventory demo/inventory.csv \
        --out submissions/measurement.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Dict, List, Optional, Sequence, Set

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from bob_session.pipeline import context as context_loader
from bob_session.pipeline import dispositions, inventory as inventory_mod
from bob_session.pipeline import artefact as artefact_mod
from bob_session.pipeline.run_analysis import run as run_ledger

VOID = "VOID"

LIMITS = {
    "recall_direction": "lower bound",
    "oracle_definition": "outcome_A(t) != outcome_B(t) over the full inventory at both revisions",
    "what_it_cannot_see": (
        "a test can be affected and still pass twice, so over-selection is invisible: "
        "a high recall does NOT mean the selection is tight, and an empty missed list means "
        "'we missed nothing the instrument could see', not 'we missed nothing'"
    ),
    "no_precision_claim": True,
    "no_completeness_guarantee": "by Rice's theorem, deciding whether a change affects a test is undecidable",
}


def _node_to_id(rows: Sequence[inventory_mod.Row]) -> Dict[str, str]:
    return {row.node_id: row.test_id for row in rows}


def measure(
    *,
    artefact_path: str,
    oracle_path: str,
    inventory_path: str,
    disabled_path: Optional[str] = None,
    repo: str = "demo",
    diff_path: str = "diffs/change_b.patch",
) -> dict:
    art = json.loads(pathlib.Path(artefact_path).read_text(encoding="utf-8"))
    rows = inventory_mod.load(inventory_path)
    node_to_id = _node_to_id(rows)
    oracle = json.loads(pathlib.Path(oracle_path).read_text(encoding="utf-8")) if pathlib.Path(oracle_path).exists() else None

    selected: Set[str] = set(art["priority_order"])
    changed_nodes: List[str] = list((oracle or {}).get("changed", []))
    changed_ids = {node_to_id[node] for node in changed_nodes if node in node_to_id}
    complete = bool((oracle or {}).get("complete"))

    missed = sorted(changed_ids - selected) if complete else []
    if complete and changed_ids:
        recall: object = round(len(selected & changed_ids) / len(changed_ids), 6)
        recall_note = None
    else:
        recall = VOID
        recall_note = (
            "oracle incomplete: the instrument is narrower than the inventory it measures (M1)"
            if not complete
            else "no discriminating test found: recall is undefined, not zero"
        )
    truth_size: object = len(changed_nodes) if complete else VOID

    # Cross-check: the harness recomputes recall independently of the engine.
    engine_recall = (art.get("measurement") or {}).get("recall")
    cross_check = "not-comparable"
    if isinstance(recall, float) and isinstance(engine_recall, (int, float)):
        cross_check = "agree" if abs(recall - engine_recall) < 1e-9 else "DISAGREE"

    disabled = None
    if disabled_path and pathlib.Path(disabled_path).exists():
        disabled = json.loads(pathlib.Path(disabled_path).read_text(encoding="utf-8"))
    ablation = None
    baseline_assertions: List[dict] = []
    if disabled is not None:
        baseline = run_ledger(
            repo=repo,
            diff_path=diff_path,
            inventory_path=inventory_path,
            model_layer="disabled",
        )
        disabled_selection = list(disabled["priority_order"])
        baseline_selection = list(baseline["priority_order"])
        baseline_assertions.append(
            {
                "assertion": "the disabled run equals the deterministic baseline byte for byte",
                "passed": disabled_selection == baseline_selection,
            }
        )
        baseline_assertions.append(
            {
                "assertion": "the enabled selection contains every disabled selection entry (monotonicity)",
                "passed": set(disabled_selection).issubset(selected),
            }
        )
        ctx = context_loader.load(repo, diff_path, inventory_path)
        symbolic = dispositions.select(ctx.rows, ctx.semantic, ctx.closure, ctx.links, {}, {})
        baseline_assertions.append(
            {
                "assertion": "the disabled selection is exactly structural closure + representation coupling",
                "passed": set(disabled_selection) == set(symbolic.selected),
            }
        )
        disabled_changed = changed_ids & set(disabled_selection) if complete else set()
        disabled_recall: object = (
            (round(len(disabled_changed) / len(changed_ids), 6) if changed_ids else VOID) if complete else VOID
        )
        enabled_changed = changed_ids & selected if complete else set()
        delta = None
        if complete and changed_ids:
            delta = round(len(enabled_changed) / len(changed_ids) - len(disabled_changed) / len(changed_ids), 6)
        additional_true_positives = len(enabled_changed - disabled_changed)
        coins = int(art["run_metadata"].get("coins_spent", 0))
        ablation = {
            "disabled_recall": disabled_recall,
            "enabled_recall": recall,
            "delta": delta,
            "model_layer": art["run_metadata"].get("model_layer"),
            "model_status": art["run_metadata"].get("model_status"),
            "coins_spent": coins,
            "additional_true_positives": additional_true_positives,
            "coins_per_additional_true_positive": round(coins / max(1, additional_true_positives), 4),
            "statement": (
                "the model layer contributed "
                f"{additional_true_positives} additional true positive(s) for {coins} coins on this change"
            ),
            "zero_is_published": True,
            "assertions": baseline_assertions,
        }

    result = {
        "generated_by": "bob_session/measure.py",
        "artefact": str(artefact_path),
        "oracle_input": str(oracle_path),
        "repo": repo,
        "diff": diff_path,
        "truth_size": truth_size,
        "selected": len(selected),
        "structurally_reachable": art["measurement"].get("structurally_reachable"),
        "recall": recall,
        "recall_note": recall_note,
        "recall_cross_check": cross_check,
        "missed": missed,
        "price_of_safety": art["measurement"].get("price_of_safety"),
        "oracle": (oracle or {}),
        "ablation": ablation,
        "limits": LIMITS,
        "summary": {
            "total_tests_in_suite": art["summary"]["total"],
            "selected_for_run": art["summary"]["selected_for_run"],
            "reduction_pct": art["summary"]["reduction_pct"],
            "stale_count": art["summary"]["stale_count"],
            "uncovered_count": art["summary"]["uncovered_count"],
            "newly_relevant_count": art["summary"]["newly_relevant_count"],
        },
        "artefact_digest": artefact_mod.digest(art),
    }
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--artefact", default="bob_session/testscope_report.json")
    parser.add_argument("--disabled", default="submissions/ablation/disabled.json")
    parser.add_argument("--oracle", default="bob_session/evidence/oracle.json")
    parser.add_argument("--inventory", default="demo/inventory.csv")
    parser.add_argument("--repo", default="demo")
    parser.add_argument("--diff", default="diffs/change_b.patch")
    parser.add_argument("--out", default="submissions/measurement.json")
    args = parser.parse_args(argv)

    result = measure(
        artefact_path=args.artefact,
        oracle_path=args.oracle,
        inventory_path=args.inventory,
        disabled_path=args.disabled,
        repo=args.repo,
        diff_path=args.diff,
    )
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"measurement written: {out}")
    print(f"  oracle complete: {result['oracle'].get('complete')} "
          f"(collected {result['oracle'].get('collected')}/{result['oracle'].get('inventory_total')}, "
          f"missing {len(result['oracle'].get('missing', []))}, unmapped {len(result['oracle'].get('unmapped', []))}, "
          f"already_red {len(result['oracle'].get('already_red', []))}, "
          f"flaky_excluded {result['oracle'].get('flaky_excluded_count')})")
    print(f"  truth_size: {result['truth_size']}  selected: {result['selected']}  "
          f"structurally_reachable: {result['structurally_reachable']}  price_of_safety: {result['price_of_safety']}")
    print(f"  recall: {result['recall'] if not isinstance(result['recall'], float) else format(result['recall'], '.3f')}"
          f"  (cross-check: {result['recall_cross_check']})")
    print(f"  missed (always published): {result['missed'] if result['missed'] else '[]'}")
    if result["ablation"]:
        ablation = result["ablation"]
        print(f"  ablation: disabled {ablation['disabled_recall']} -> enabled {ablation['enabled_recall']} "
              f"(delta {ablation['delta']}); {ablation['statement']}")
        for assertion in ablation["assertions"]:
            print(f"    assertion {'PASS' if assertion['passed'] else 'FAIL'}: {assertion['assertion']}")
    if result["recall"] == VOID:
        print("  VOID: recall is not published because the oracle is incomplete (M1)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
