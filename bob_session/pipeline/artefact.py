"""Artefact serialisation and invariant checking.

The artefact is a pure function of the inputs and of the kernel's verdicts:
no clock, no RNG, deterministic ordering, canonical JSON. ``dumps`` is the
only writer, so the digest of a run is a property of its content.
"""
from __future__ import annotations

import hashlib
import json
from typing import Dict, Iterable, List, Sequence

ALLOWED_REASONS = {
    "definitely_affected": {"structural_modification", "structural_closure"},
    "semantically_affected": {
        "representation_coupling",
        "kernel_accepted_claim",
        "unconfirmed_claim",
    },
    "not_affected": {"no_link"},
}

LEDGER_KEYS = ("valid", "stale", "newly_relevant", "unknown")


def dumps(artefact: dict) -> str:
    """Canonical serialisation: sorted keys, fixed indent, trailing newline."""
    return json.dumps(artefact, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def digest(artefact: dict) -> str:
    return hashlib.sha256(dumps(artefact).encode("utf-8")).hexdigest()


def validate(artefact: dict) -> List[str]:
    """Every enforced invariant, as a list of violations (empty == pass)."""
    problems: List[str] = []
    classification = artefact.get("classification") or {}
    ledger = artefact.get("ledger") or {}
    summary = artefact.get("summary") or {}
    claims = artefact.get("claims") or {}
    measurement = artefact.get("measurement") or {}

    # I1: every inventory row appears in exactly one classification bucket.
    seen: Dict[str, str] = {}
    for bucket in ("definitely_affected", "semantically_affected", "not_affected"):
        for row in classification.get(bucket, []):
            test_id = row.get("test_id")
            if test_id in seen:
                problems.append(f"I1: {test_id} appears in both {seen[test_id]} and {bucket}")
            seen[test_id] = bucket
    total = summary.get("total", 0)
    if len(seen) != total:
        problems.append(f"I1: classification holds {len(seen)} rows, summary.total is {total}")
    for bucket, rows in classification.items():
        for row in rows:
            reason = row.get("reason", "")
            if reason not in ALLOWED_REASONS.get(bucket, set()):
                problems.append(f"I2: reason {reason!r} does not belong to bucket {bucket}")

    # I13: the ledger partitions the suite, and the summary agrees with it.
    ledger_count = 0
    for bucket in LEDGER_KEYS:
        ledger_count += len(ledger.get(bucket, []))
    if ledger_count != total:
        problems.append(f"I13: ledger holds {ledger_count} rows, summary.total is {total}")
    pairs = (
        ("newly_relevant_count", "newly_relevant"),
        ("stale_count", "stale"),
        ("valid_count", "valid"),
        ("unknown_count", "unknown"),
    )
    for summary_key, bucket in pairs:
        if summary.get(summary_key) != len(ledger.get(bucket, [])):
            problems.append(
                f"I13: summary.{summary_key}={summary.get(summary_key)} != ledger.{bucket}={len(ledger.get(bucket, []))}"
            )
    # A linked test can be stale (it asserts removed behaviour) and then sits in
    # the stale bucket while still being counted as semantically affected.
    expected_semantic = (
        summary.get("newly_relevant_count", 0)
        + summary.get("unknown_count", 0)
        + summary.get("stale_linked_count", 0)
    )
    if summary.get("semantically_affected_count") != expected_semantic:
        problems.append(
            f"I13: semantically_affected_count={summary.get('semantically_affected_count')} != "
            f"newly_relevant+unknown+stale_linked={expected_semantic}"
        )

    # I14: oracle completeness is recomputed, never asserted.
    oracle = measurement.get("oracle") or {}
    if oracle.get("complete") is not None:
        expected = (oracle.get("collected", 0) - len(oracle.get("unmapped", []))) + len(
            oracle.get("missing", [])
        ) >= oracle.get("inventory_total", 0)
        if bool(oracle.get("complete")) != bool(expected):
            problems.append(
                f"I14: oracle.complete={oracle.get('complete')} but the counts imply {expected}"
            )

    # I15: every accepted claim has a matching entry in the ledger.
    ledger_evidence = {
        entry.get("test_id"): " ".join(entry.get("link_evidence", []))
        for bucket in LEDGER_KEYS
        for entry in ledger.get(bucket, [])
    }
    for accepted in (artefact.get("claims_detail") or {}).get("accepted", []):
        targets = (accepted.get("claim") or {}).get("targets") or {}
        test_id = targets.get("test_id")
        if not test_id:
            continue
        ref = accepted.get("claim_ref", "")
        if ref and ref not in ledger_evidence.get(test_id, ""):
            problems.append(f"I15: accepted claim {ref} has no matching ledger evidence for {test_id}")

    # I16: the rejection ledger is complete.
    if len(artefact.get("rejection_ledger", [])) != claims.get("rejected", 0):
        problems.append(
            f"I16: rejection_ledger has {len(artefact.get('rejection_ledger', []))} entries, "
            f"claims.rejected is {claims.get('rejected', 0)}"
        )

    # I4: the measurement block is internally consistent.
    if measurement.get("selected") != summary.get("selected_for_run"):
        problems.append("I4: measurement.selected disagrees with summary.selected_for_run")
    if measurement.get("price_of_safety") is not None:
        expected_price = measurement.get("selected", 0) - measurement.get("structurally_reachable", 0)
        if measurement.get("price_of_safety") != expected_price:
            problems.append("I4: price_of_safety is not selected - structurally_reachable")
    return problems
