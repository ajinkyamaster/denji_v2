"""Red triage: why is this test red, and what should the developer do?

DeFlaker's rule is the published state of the art and it is cheap: *a test that
fails while executing none of the changed code is flaky*. Its hidden premise is
``L* ⊆ L_cov`` — that coverage is a **complete** dependence proxy — and A1 refutes
exactly that. So the rule mislabels the case this product exists for: a failure
that propagates through a wire format with no import edge, where the test process
covers none of the changed lines because the producer ran elsewhere.

The refinement, stated so it can be attacked:

    a failure is exonerated as FLAKY only if coverage/import evidence is silent
    AND no kernel-admissible link to the changed code exists.

If a verified representation link exists, the red is **not** written off. In the
demo repository the three contract tests fail while covering none of the changed
lines in-process (the producer runs in a child process), and a link is admissible:
``cache_service`` produces ``|``, ``report_worker`` consumes it, no import edge.
DeFlaker's rule would quarantine the tests; this rule calls it a regression, which
is what it is.
"""

import re

NODE_ID = re.compile(r"\[(T-\d{4})\]")


def test_id_from_node(node_id, inventory_by_name=None):
    """Map a pytest node id onto an inventory test id.

    Parametrized ids carry the inventory id (``...[T-0342]``), which is why the
    fixture uses explicit ids everywhere. A plain function name is the fallback.
    """
    match = NODE_ID.search(node_id or "")
    if match:
        return match.group(1)
    if inventory_by_name:
        name = (node_id or "").split("::")[-1].split("[")[0]
        return inventory_by_name.get(name)
    return None


def build_triage(index, inventory, classification, ledger, couplings, oracle, *, structural_modules=None):
    """Return the triage list for failing tests (or predicted failures).

    When an oracle result is available the entries are *observed* failures at the
    post-change revision. Without one, the entries are the hidden-coupling rows,
    labelled as predictions rather than as measurements.
    """
    by_name = {row.test_name: row.test_id for row in inventory}
    stale_ids = {entry["test_id"] for entry in ledger.stale}
    coupling_evidence = {}
    for coupling in couplings:
        coupling_evidence.setdefault(coupling.consumer_module, []).append(coupling)

    failing = []
    if oracle and oracle.get("complete"):
        outcomes = oracle.get("outcome") or {}
        if outcomes:
            for node, outcome in sorted(outcomes.items()):
                if outcome.get("b") in (None, "passed"):
                    continue
                test_id = test_id_from_node(node, by_name)
                if test_id:
                    failing.append((test_id, node, "observed"))
        else:
            # A compact oracle result carries the discriminating nodes but not the
            # per-node outcome map. Those nodes are observed failures too.
            for node in sorted(oracle.get("changed") or []):
                test_id = test_id_from_node(node, by_name)
                if test_id:
                    failing.append((test_id, node, "observed"))
    if not failing:
        for entry in ledger.newly_relevant:
            failing.append((entry["test_id"], None, "predicted"))

    entries = []
    for test_id, node, kind in failing:
        verdict = classification.verdicts.get(test_id)
        if verdict is None:
            continue
        test_module = index.module_named(verdict.test_module) if verdict.test_module else None
        reached = []
        if test_module is not None and structural_modules:
            reached = sorted(structural_modules & index.forward_closure(test_module.name))
        consumer = coupling_evidence.get(verdict.module, [])
        if test_id in stale_ids:
            diagnosis = "stale"
            signal = (
                "asserts behaviour the change removed; repair the test, do not bisect the change"
            )
        elif not reached and not consumer:
            diagnosis = "flaky"
            signal = (
                "fails while reaching none of the changed code and with no kernel-admissible link: "
                "quarantine it, do not chase it"
            )
        else:
            diagnosis = "regression"
            parts = []
            if reached:
                parts.append(f"reaches changed module(s) {', '.join(reached)}")
            if consumer:
                coupling = consumer[0]
                parts.append(
                    "import/coverage evidence is silent, but a kernel-admissible representation link exists: "
                    f"{coupling.producer_module}.{coupling.producer_symbol} -> "
                    f"{coupling.consumer_module}.{coupling.consumer_symbol} via {coupling.separator!r}"
                )
            parts.append("fix the code, not the test")
            signal = "; ".join(parts)
        if kind == "predicted":
            signal = "predicted, not observed (no oracle result supplied): " + signal
        entries.append({"test_id": test_id, "diagnosis": diagnosis, "signal": signal, "node_id": node})
    entries.sort(key=lambda entry: entry["test_id"])
    return entries
