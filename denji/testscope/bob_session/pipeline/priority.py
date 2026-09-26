"""Ordering: reduce how long until the *first* failure, not just how many tests run.

The objective is the classic one (Elbaum et al., 2002): maximise the rate of
fault detection. The thesis of this product, made operational, is tier 0 —
``NEWLY_RELEVANT`` first. If the selector's unique contribution is the test
nobody would have run, run it first: it is the highest-surprise, highest-signal
row in the list.

The order is a **total** order, so the artefact is a pure function of the inputs:

    tier (newly-relevant 0, unknown 1, reaches changed code 2, other 3)
    then descending dependency depth
    then ascending declared duration
    then test id
"""

TIERS = ("newly_relevant", "unknown", "reaches_changed_code", "other")


def tier_of(test_id, ledger, classification):
    if any(entry["test_id"] == test_id for entry in ledger.newly_relevant):
        return 0
    if any(entry["test_id"] == test_id for entry in ledger.unknown):
        return 1
    verdict = classification.verdicts.get(test_id)
    if verdict is not None and verdict.bucket == "definitely_affected":
        return 2
    return 3


def priority_order(inventory, classification, ledger, *, selection):
    """Order the run list (``selection``) deterministically."""
    rows = {row.test_id: row for row in inventory}
    selected = sorted(set(selection))
    decorated = []
    for test_id in selected:
        row = rows[test_id]
        verdict = classification.verdicts.get(test_id)
        depth = (verdict.depth or 0) if verdict is not None else 0
        decorated.append((tier_of(test_id, ledger, classification), -depth, row.avg_runtime_ms, test_id))
    decorated.sort()
    return [test_id for _, _, _, test_id in decorated]
