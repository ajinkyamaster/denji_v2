"""The artefact: assembly, validation, and the serialisation contract.

v1's three keys keep their exact shape (``run_metadata``, ``classification``,
``summary``) so v1's dashboard, schema validator and gates keep passing; the new
keys are additive alongside them. Nothing here replaces a v1 key.

``validate`` is the falsifier for the artefact itself. Every invariant it checks
is a way the artefact could lie, and each is checked by *recomputing* rather than
by trusting a recorded flag:

  I1   every inventory row is in exactly one classification bucket
  I2   each bucket's ``reason`` comes from that bucket's allowed set
  I13  the four ledger buckets partition the suite; counts agree with classification
  I14  ``measurement.oracle.complete`` is recomputed from the run's own numbers
  I15  every accepted claim has a matching verdict in the ledger
  I16  ``len(rejection_ledger) == claims.rejected``
  I17  the routing ring: schema 2.0 and the four canonical tools exist

I3 (byte-identical output for the same inputs) and I4 (reproducible from source)
are properties of a *run*, so they are gates rather than checks on one artefact.
"""

import json
import os
import tempfile

from ..tools_spec import SCHEMA_VERSION, TOOL_NAMES, TOOL_VERSION

REQUIRED_TOP_LEVEL = (
    "run_metadata",
    "classification",
    "ledger",
    "uncovered",
    "claims",
    "rejection_ledger",
    "measurement",
    "triage",
    "priority_order",
    "summary",
)

LEDGER_KEYS = ("valid", "stale", "newly_relevant", "unknown")
DIAGNOSES = ("regression", "stale", "flaky")


def build_artifact(
    *,
    run_metadata,
    classification,
    ledger,
    uncovered,
    couplings,
    claims,
    rejection_ledger,
    measurement,
    triage,
    priority_order,
    inventory,
    uncovered_counters=None,
):
    """Assemble the artefact. Pure: no clock, no randomness, no iteration order leak."""
    definitely = classification.test_ids("definitely_affected")
    semantically = classification.test_ids("semantically_affected")
    selected = sorted(definitely + semantically)
    total = len(inventory)
    ledger_counts = ledger.counts()
    summary = {
        "total": total,
        "selected_for_run": len(selected),
        "definitely_affected_count": len(definitely),
        "semantically_affected_count": len(semantically),
        "reduction_pct": round(100.0 * (1 - (len(selected) / total)), 1) if total else 0.0,
        "stale_count": ledger_counts["stale_count"],
        "uncovered_count": len(uncovered),
        "newly_relevant_count": ledger_counts["newly_relevant_count"],
        "valid_count": ledger_counts["valid_count"],
        "unknown_count": ledger_counts["unknown_count"],
    }
    return {
        "run_metadata": run_metadata,
        "classification": classification.as_artifact(),
        "ledger": ledger.as_artifact(),
        "uncovered": uncovered,
        "claims": claims,
        "rejection_ledger": rejection_ledger,
        "measurement": measurement,
        "triage": triage,
        "priority_order": priority_order,
        "summary": summary,
        "couplings": [
            {
                "producer": f"{coupling.producer_module}.{coupling.producer_symbol}",
                "consumer": f"{coupling.consumer_module}.{coupling.consumer_symbol}",
                "separator": coupling.separator,
                "evidence": coupling.evidence,
            }
            for coupling in couplings
        ],
        "uncovered_counters": uncovered_counters or {},
        "declared_assumptions": _assumptions(),
    }


def _assumptions():
    from .cache import DECLARED_ASSUMPTIONS

    return list(DECLARED_ASSUMPTIONS)


def serialize(artifact):
    """The one canonical serialisation: sorted keys, two-space indent, trailing newline."""
    return json.dumps(artifact, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def digest(artifact):
    """SHA-256 of the canonical serialisation (what the determinism gate compares)."""
    import hashlib

    return hashlib.sha256(serialize(artifact).encode("utf-8")).hexdigest()


def write_artifact(artifact, path):
    """Write atomically: a killed run must not leave a truncated artefact."""
    target = str(path)
    directory = os.path.dirname(os.path.abspath(target))
    os.makedirs(directory, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=directory, prefix=".artifact-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(serialize(artifact))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


def validate(artifact, *, inventory_ids=None, tool_names=None):
    """Return a sorted list of invariant violations (empty means valid)."""
    problems = []
    for key in REQUIRED_TOP_LEVEL:
        if key not in artifact:
            problems.append(f"missing top-level key: {key}")
    if problems:
        return sorted(problems)

    classification = artifact["classification"]
    ledger = artifact["ledger"]
    summary = artifact["summary"]
    measurement = artifact["measurement"]
    claims = artifact["claims"]

    # --- I1 / I2: the classification partition ---------------------------- #
    from .classify import REASONS

    seen = {}
    for bucket in ("definitely_affected", "semantically_affected", "not_affected"):
        if bucket not in classification:
            problems.append(f"I1: classification is missing bucket {bucket}")
            continue
        for entry in classification[bucket]:
            test_id = entry.get("test_id")
            if test_id in seen:
                problems.append(f"I1: {test_id} appears in both {seen[test_id]} and {bucket}")
            seen[test_id] = bucket
            if entry.get("reason") not in REASONS[bucket]:
                problems.append(f"I2: reason {entry.get('reason')!r} is not allowed in {bucket}")
            for field in ("test_id", "test_name", "module", "reason", "explanation"):
                if field not in entry:
                    problems.append(f"I2: classification entry {test_id} is missing {field}")
    if inventory_ids is not None:
        expected = set(inventory_ids)
        if expected != set(seen):
            missing = sorted(expected - set(seen))[:5]
            extra = sorted(set(seen) - expected)[:5]
            problems.append(f"I1: classification does not partition the inventory (missing={missing}, extra={extra})")

    # --- I13: the ledger partition and its agreement with classification --- #
    for key in LEDGER_KEYS:
        if key not in ledger:
            problems.append(f"I13: ledger is missing bucket {key}")
    ledger_total = sum(len(ledger.get(key, ())) for key in LEDGER_KEYS)
    if ledger_total != summary.get("total"):
        problems.append(f"I13: ledger buckets sum to {ledger_total}, summary.total is {summary.get('total')}")
    ledger_test_ids = [entry["test_id"] for key in LEDGER_KEYS for entry in ledger.get(key, ())]
    if len(ledger_test_ids) != len(set(ledger_test_ids)):
        problems.append("I13: a test id appears in more than one ledger bucket")
    if len(ledger.get("newly_relevant", ())) != summary.get("semantically_affected_count"):
        problems.append(
            "I13: ledger.newly_relevant does not agree with summary.semantically_affected_count"
        )
    if summary.get("stale_count") != len(ledger.get("stale", ())):
        problems.append("I13: summary.stale_count disagrees with the ledger")
    if summary.get("valid_count") != len(ledger.get("valid", ())):
        problems.append("I13: summary.valid_count disagrees with the ledger")
    selected = {entry["test_id"] for entry in classification["definitely_affected"]} | {
        entry["test_id"] for entry in classification["semantically_affected"]
    }
    if summary.get("selected_for_run") != len(selected):
        problems.append("I13: summary.selected_for_run disagrees with the classification buckets")
    order = artifact["priority_order"]
    if len(order) != len(set(order)):
        problems.append("I13: priority_order contains duplicates")
    if set(order) != selected:
        problems.append("I13: priority_order is not exactly the run list")
    stale_ids = {entry["test_id"] for entry in ledger.get("stale", ())}
    if stale_ids & selected:
        problems.append(
            "I13: a stale test is in the run list; a stale test's red is noise and it must be repaired, not run"
        )
    uncovered = artifact["uncovered"]
    if len(uncovered) != summary.get("uncovered_count"):
        problems.append("summary.uncovered_count disagrees with the uncovered list")
    for item in uncovered:
        for field in ("symbol", "path", "line", "kind", "has_any_test"):
            if field not in item:
                problems.append(f"uncovered item {item.get('symbol')} is missing {field}")
        if item.get("kind") not in ("UNCOVERED_NEW", "UNCOVERED_BY_STALENESS"):
            problems.append(f"uncovered item {item.get('symbol')} has an unknown kind {item.get('kind')!r}")

    # --- I14: completeness is computed, not asserted ----------------------- #
    oracle = measurement.get("oracle", {})
    observed = oracle.get("collected")
    recomputed = bool(
        oracle.get("collected_a") is not None
        and oracle.get("collected_a") == oracle.get("collected_b")
        and observed is not None
        and isinstance(oracle.get("inventory_total"), int)
        and observed >= oracle["inventory_total"]
    )
    if bool(oracle.get("complete")) != recomputed:
        problems.append(
            f"I14: measurement.oracle.complete={oracle.get('complete')!r} but recomputation says {recomputed}"
        )
    if not oracle.get("complete") and measurement.get("recall") is not None:
        problems.append("I14: recall is reported from an incomplete oracle; the measurement must be void")
    if measurement.get("recall") is not None and measurement.get("truth_size", 0) == 0:
        problems.append("recall must be null when truth_size is 0")

    # --- I15 / I16: claims ------------------------------------------------ #
    ledger_index = set(ledger_test_ids)
    for entry in artifact.get("accepted_claims", ()):
        test_id = (entry.get("targets") or {}).get("test_id")
        if test_id and test_id not in ledger_index:
            problems.append(f"I15: accepted claim for {test_id} has no verdict in the ledger")
    rejected = len(artifact.get("rejection_ledger", ()))
    if rejected != claims.get("rejected"):
        problems.append(f"I16: rejection_ledger has {rejected} entries but claims.rejected is {claims.get('rejected')}")

    # --- I17: the routing ring -------------------------------------------- #
    if artifact["run_metadata"].get("schema_version") != SCHEMA_VERSION:
        problems.append(f"I17: schema_version is not {SCHEMA_VERSION}")
    if artifact["run_metadata"].get("tool_version") != TOOL_VERSION:
        problems.append(f"I17: tool_version is not {TOOL_VERSION}")
    exposed = tuple(tool_names or TOOL_NAMES)
    for name in TOOL_NAMES:
        if name not in exposed:
            problems.append(f"I17: canonical tool {name} is not exposed by the tool surface")

    # --- triage shape ------------------------------------------------------ #
    for entry in artifact.get("triage", ()):
        if entry.get("diagnosis") not in DIAGNOSES:
            problems.append(f"triage entry {entry.get('test_id')} has unknown diagnosis {entry.get('diagnosis')!r}")

    # --- declared assumptions must be visible ------------------------------ #
    if not artifact.get("declared_assumptions"):
        problems.append("declared assumptions are absent: reuse without visible assumptions is unsound")
    return sorted(problems)
