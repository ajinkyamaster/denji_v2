"""Measurement: the numbers, with the direction of every error stated.

``Delta(t) = [outcome_A(t) != outcome_B(t)]`` is a **lower bound** on the truly
affected set: a test can be affected and still pass twice. So this measurement can
establish recall and can never establish precision — over-selection is invisible
to it. That asymmetry is published rather than hidden, because the alternative is
a number that looks stronger than it is.

``recall`` is reported as ``null`` when the oracle found **no** discriminating
test. That is not a 1.0 and it is not a 0.0: the denominator is zero, so the
quantity is undefined. Saying so is cheaper than defending a fabricated value.
"""


def _to_test_ids(nodes, inventory_by_name):
    """Map pytests node ids onto inventory test ids.

    The oracle speaks node ids (``...[T-0342]``) and the ledger speaks inventory
    ids. Comparing the two sets directly produces a recall of 0.0 against a
    perfect selection - quietly, and with a straight face. So the mapping is
    explicit here, and a node that cannot be mapped is kept verbatim rather than
    dropped.
    """
    from .triage import test_id_from_node

    mapped = []
    for node in nodes:
        test_id = test_id_from_node(node, inventory_by_name)
        mapped.append(test_id or node)
    return sorted(set(mapped))


def build_measurement(*, oracle, inventory, selected_ids, structural_ids, model_layer, ablation=None):
    """Assemble the measurement block of the artefact."""
    inventory_by_name = {row.test_name: row.test_id for row in inventory}
    changed = _to_test_ids(oracle.get("changed") or [], inventory_by_name) if oracle else []
    selected = set(selected_ids)
    inventory_total = len(inventory)
    oracle_block = {
        "collected": (oracle or {}).get("collected"),
        "collected_a": (oracle or {}).get("collected_a"),
        "collected_b": (oracle or {}).get("collected_b"),
        "inventory_total": inventory_total,
        "complete": bool((oracle or {}).get("complete")),
        "rev_a": (oracle or {}).get("rev_a"),
        "rev_b": (oracle or {}).get("rev_b"),
        "run_cmd": (oracle or {}).get("run_cmd"),
        "flaky_excluded": sorted((oracle or {}).get("flaky_excluded") or []),
        "already_red": sorted((oracle or {}).get("already_red") or []),
        "mode": (oracle or {}).get("mode"),
        "note": (oracle or {}).get(
            "note",
            "no oracle result supplied: recall is undefined for this run",
        ),
    }
    truth_size = len(changed)
    if not oracle or not oracle_block["complete"]:
        recall = None
        missed = []
        recall_note = (
            "measurement VOID: the oracle did not report complete=true. A recall computed from a partial "
            "instrument would look like evidence while being noise (invariant O1)."
        )
    elif truth_size == 0:
        recall = None
        missed = []
        recall_note = (
            "no discriminating test between the two revisions: recall is undefined, not 1.0. "
            "The oracle is a lower bound, so this may mean the change is unobservable by execution, "
            "or that the instrument is still blind."
        )
    else:
        hit = len(selected & set(changed))
        recall = hit / truth_size
        missed = sorted(set(changed) - selected)
        recall_note = (
            f"recall = |selected ∩ changed| / |changed| = {hit}/{truth_size}. "
            "This is a lower bound: a test can be affected and still pass twice."
        )
    structural = sorted(structural_ids)
    price_of_safety = len(selected) - len(structural)
    delta = 0.0
    if ablation and ablation.get("recall_enabled") is not None and ablation.get("recall_disabled") is not None:
        delta = round(ablation["recall_enabled"] - ablation["recall_disabled"], 6)
    return {
        "oracle": oracle_block,
        "truth_size": truth_size,
        "selected": len(selected),
        "structurally_reachable": len(structural),
        "recall": recall,
        "recall_note": recall_note,
        "missed": missed,
        "price_of_safety": price_of_safety,
        "price_of_safety_note": (
            "selected minus structurally reachable: the tests a semantics-only selector adds. "
            "The price is paid in run time; what it buys is the regression an import graph cannot see."
        ),
        "model_layer": model_layer,
        "model_layer_recall_delta": delta,
    }
