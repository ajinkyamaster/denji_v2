#!/usr/bin/env python3
"""Build ``dashboard/mock_report.json`` — the fixture the dashboard is developed against.

Why a generator instead of a typed file: the fixture must describe a 500-test suite
(``summary.total == 500``, ``selected_for_run == 47``), and the interesting content is
about a dozen rows. Hand-typing 440 filler rows is how filler rows end up wrong; the
parts that carry meaning are hand-authored below and the rest is deterministic.

WHAT IS HAND-AUTHORED (the part a reader should read):
    * the 6 behavioural catches, including the hero T-0342
    * the 3 STALE tests, with the behaviour each one still asserts
    * the 4 UNCOVERED work items, 2 of each kind
    * the 2 UNKNOWN dispositions (safe direction: included)
    * the claims counters, the 3 rejections with their verbatim gate reasons
    * the triage rows (one regression, one stale, one flaky)
    * the measurement block, with ``oracle.complete == false`` on purpose so the VOID
      path can be exercised — see PERSON C section 7.4

WHAT IS GENERATED: the 41 syntactic rows and the 453 not-affected rows, deterministically
(``random.Random(seed)``), so re-running produces byte-identical JSON.

Run:  python3 dashboard/make_mock_report.py
"""

from __future__ import annotations

import json
import random
from pathlib import Path

OUT = Path(__file__).with_name("mock_report.json")
SEED = 20260926

# --- the diff, as the pipeline reports it ------------------------------------
DIFF_FILES = ["README.md", "app/services/billing_service.py", "app/services/cache_service.py"]

EXPLANATION_CHANGE = (
    "The diff changes write_cache_entry so it now writes json.dumps() payloads "
    "instead of |-delimited strings."
)
EXPLANATION_INERT = (
    "Change is a cosmetic README edit with no code path to this test."
)

# --- hand-authored: the 6 behavioural catches (classification.semantically_affected)
SEMANTIC = [
    ("T-0342", "test_report_worker_parses_recent_cache_entries", "app.workers.report_worker",
     "report_worker.py:44 parses cache values with str.split('|'), assuming the "
     "pipe-delimited format cache_service.py wrote before this diff. The diff changed the "
     "write path to json.dumps() with no corresponding update here. No import edge exists "
     "between report_worker.py and cache_service.py, so import-graph-based test selection "
     "would not surface this test."),
    ("T-0343", "test_report_worker_malformed_entry_count", "app.workers.report_worker",
     "report_worker.py:56 counts malformed cache payloads with str.split('|'), assuming the "
     "pipe-delimited format cache_service.py wrote before this diff. No import edge exists "
     "between report_worker.py and cache_service.py, so import-graph-based test selection "
     "would not surface this test."),
    ("T-0411", "test_billing_invoice_export_consumes_cached_rows", "app.workers.billing_export_worker",
     "billing_export_worker.py:73 reads the cached row shape produced by cache_service. "
     "It imports only app.workers.*, so it is absent from the changed module's import "
     "closure while still depending on the payload format this diff rewrites."),
    ("T-0412", "test_audit_log_round_trip_after_cache_write", "app.services.audit_service",
     "audit_service.py:91 round-trips a cached record through the same writer. No import "
     "edge to cache_service; the coupling is through the persisted representation."),
    ("T-0417", "test_dashboard_widget_renders_cached_payload", "app.api.dashboard_controller",
     "dashboard_controller.py:128 renders fields parsed out of a cached payload. No import "
     "edge exists, but the rendered contract changes with this diff."),
    ("T-0418", "test_healthcheck_reports_last_cache_write", "app.api.health_controller",
     "health_controller.py:37 asserts on the value written by cache_service, reached only "
     "at runtime. No import edge, so static selection misses it."),
]

# --- hand-authored: 3 STALE tests (ledger.stale) -----------------------------
STALE = [
    ("T-0210", "test_cache_service_write_entry_pipe_format",
     "Still asserts that write_cache_entry returns a '|'-joined payload. The diff replaced "
     "that contract with json.dumps(), so this test can only fail — and its red is noise.",
     "pipe-delimited f-string payload",
     ["tests/test_cache_service.py:44"]),
    ("T-0211", "test_cache_service_write_entry_legacy_round_trip",
     "Round-trips the legacy pipe format end to end. The format no longer exists after "
     "this diff; the test asserts a contract the change removed.",
     "round-trip through '|'-splitting",
     ["tests/test_cache_service.py:61"]),
    ("T-0212", "test_reporting_parse_pipe_payload",
     "Parses a pipe payload produced by write_cache_entry. With the writer moved to JSON "
     "this assertion cannot be satisfied by any correct implementation.",
     "reporting parses '|'-delimited cache output",
     ["tests/test_reporting.py:29"]),
]

# --- hand-authored: 2 UNKNOWN dispositions -----------------------------------
# Both sit in classification.definitely_affected (they import the changed module) but
# the engine could not decide whether the contract survives, so the safe direction
# was taken: they are in the run list.
UNKNOWN = [
    ("T-0155", "test_cache_service_write_entry_empty_value",
     "Imports the changed module, but the empty-value path is neither preserved nor "
     "removed by this diff and no oracle run distinguishes them. Included: the safe "
     "direction is to run it."),
    ("T-0156", "test_cache_service_write_entry_unicode_key",
     "Unicode key handling is exercised on a path the diff does not touch directly, and "
     "the representation change could plausibly affect it. Included rather than skipped."),
]

# --- hand-authored: 4 UNCOVERED work items -----------------------------------
UNCOVERED = [
    ("app.services.billing_service.settle_invoice", "app/services/billing_service.py", 88,
     [87, 88, 89], "UNCOVERED_NEW"),
    ("app.services.cache_service.format_cache_value", "app/services/cache_service.py", 61,
     [60, 61], "UNCOVERED_NEW"),
    ("app.services.reporting.parse_payload_rows", "app/services/reporting.py", 33,
     [32, 33], "UNCOVERED_BY_STALENESS"),
    ("app.services.session_service.serialise_session", "app/services/session_service.py", 19,
     [18, 19], "UNCOVERED_BY_STALENESS"),
]

# --- generated filler --------------------------------------------------------
FILLER_MODULES = [
    "app.services.auth_service", "app.services.user_service", "app.services.billing_service",
    "app.services.payment_service", "app.services.session_service", "app.services.inventory_service",
    "app.workers.email_worker", "app.workers.report_worker", "app.api.health_controller",
    "app.api.dashboard_controller", "app.core.config", "app.core.logging", "qa.manual.exploratory",
]
# The longest name in the real report is 60 characters; keeping a 60-char name in the
# fixture as well means the column-width requirement is exercised by both artefacts.
NAME_PARTS = [
    "happy_path", "rejects_expired", "handles_missing", "propagates", "bounds",
    "concurrent_writes", "unicode_round_trip", "timeout_behaviour", "idempotent_retry",
    "empty_input", "large_payload", "permission_denied",
]
NAME_VERBS = ["test_create", "test_update", "test_delete", "test_list", "test_parse",
              "test_serialise", "test_retry", "test_validate", "test_cache", "test_dispatch"]


def build() -> dict:
    rng = random.Random(SEED)
    used: set[int] = {int(tid.split("-")[1]) for tid, *_ in SEMANTIC + STALE + UNKNOWN}
    used |= {11, 12, 13, 4, 31, 71, 106, 120, 277, 371}

    def next_id() -> str:
        number = 1
        while number in used:
            number += 1
        used.add(number)
        return f"T-{number:04d}"

    # 41 syntactic rows: they import their way to the changed module.
    syntactic_names = [
        "test_cache_service_write_entry_happy_path",
        "test_session_service_create_session_payload",
        "test_inventory_service_cache_stock_round_trip",
        "test_billing_service_settle_success",
        "test_notification_service_template_missing_key_legacy_client",
    ]
    syntactic: list[dict] = []
    for name in syntactic_names:
        syntactic.append({
            "test_id": next_id(),
            "test_name": name,
            "module": rng.choice(["app.services.cache_service", "app.services.session_service",
                                  "app.services.inventory_service", "app.services.billing_service"]),
            "reason": "syntactic",
            "explanation": (
                f"Test targets app.services.cache_service, which this diff edits directly. "
                f"{EXPLANATION_CHANGE}"
            ),
        })
    while len(syntactic) < 39:
        module = rng.choice(FILLER_MODULES[:6])
        name = f"{rng.choice(NAME_VERBS)}_{rng.choice(NAME_PARTS)}"
        syntactic.append({
            "test_id": next_id(),
            "test_name": name,
            "module": module,
            "reason": "syntactic",
            "explanation": (
                f"Test targets {module}, which imports its way to app.services.cache_service "
                f"({module} -> app.services.cache_service). {EXPLANATION_CHANGE}"
            ),
        })

    semantic = [{"test_id": tid, "test_name": name, "module": module, "reason": "semantic",
                 "explanation": why}
                for tid, name, module, why in SEMANTIC]

    # 453 not-affected rows: 3 STALE + 2 UNKNOWN are drawn from this population.
    not_affected: list[dict] = []
    for tid, name, why, _removed, _evidence in STALE:
        not_affected.append({
            "test_id": tid, "test_name": name,
            "module": "app.services.cache_service" if "cache" in name else "app.services.reporting",
            "reason": "unaffected", "explanation": why,
        })
    for tid, name, why in UNKNOWN:
        # UNKNOWN rows are part of the selected set, so they are not in this bucket.
        _ = (tid, name, why)
    while len(not_affected) < 453:
        module = rng.choice(FILLER_MODULES)
        if module == "app.services.reporting":
            module = "app.services.inventory_service"
        name = f"{rng.choice(NAME_VERBS)}_{rng.choice(NAME_PARTS)}"
        reason = (EXPLANATION_INERT if rng.random() < 0.18 else
                  "No import path or shared payload format connects this module to the "
                  "changed files, so this diff cannot change the outcome of this test.")
        not_affected.append({
            "test_id": next_id(), "test_name": name, "module": module,
            "reason": "unaffected", "explanation": reason,
        })

    # UNKNOWN rows must live in a classification bucket; they are conservatively included,
    # so they join the syntactic bucket and are counted as selected.
    for tid, name, _why in UNKNOWN:
        syntactic.append({
            "test_id": tid, "test_name": name, "module": "app.services.cache_service",
            "reason": "syntactic",
            "explanation": (
                "Imports the changed module; whether the contract survives could not be "
                "decided, so the safe direction was taken and the test is included."
            ),
        })

    # The 2 UNKNOWN rows were appended to `syntactic` above (safe direction: included),
    # so the bucket holds 39 generated + 2 unknown = 41.
    assert len(syntactic) == 41, len(syntactic)
    assert len(semantic) == 6, len(semantic)
    assert len(not_affected) == 453, len(not_affected)

    # The ledger partitions all 500 tests exactly once:
    #   syntactic -> valid (41) | semantic -> newly_relevant (6)
    #   not_affected -> valid (450) | stale (3)
    #   unknown (2) sits inside the syntactic 41.
    all_ids = [e["test_id"] for e in syntactic + semantic + not_affected]
    assert len(all_ids) == len(set(all_ids)) == 500

    valid_ids = [e["test_id"] for e in syntactic if e["test_id"] not in {t for t, *_ in UNKNOWN}]
    valid_ids += [e["test_id"] for e in not_affected
                  if e["test_id"] not in {t for t, *_ in STALE}]

    ledger = {
        "newly_relevant": [
            {"test_id": tid, "why": why,
             "link_evidence": [
                 "no import edge to app.services.cache_service",
                 "coupled through the persisted payload format",
             ]}
            for tid, _name, module, why in SEMANTIC
        ],
        "stale": [
            {"test_id": tid, "why": why, "removed_behaviour": removed, "evidence": evidence}
            for tid, _name, why, removed, evidence in STALE
        ],
        "unknown": [{"test_id": tid, "why": why} for tid, _name, why in UNKNOWN],
        "valid": [{"test_id": tid, "why": "The change preserved what this test protects."}
                  for tid in sorted(valid_ids)],
    }
    assert len(ledger["valid"]) + len(ledger["stale"]) + len(ledger["unknown"]) + \
        len(ledger["newly_relevant"]) == 500

    claims = {
        "proposed": 12, "accepted": 5, "rejected": 3, "unconfirmed": 4,
        "by_role": {"scout": 4, "cartographer": 2, "author": 5, "falsifier": 1},
    }
    # I16: rejection_ledger length == claims.rejected
    rejection_ledger = [
        {"role": "scout", "gate": "citation_invalid",
         "detail": "path 'app/workers/report_worker.py' does not exist at that revision",
         "claim_ref": "scout:link_exists:T-0342#a"},
        {"role": "scout", "gate": "symbol_mismatch",
         "detail": "cited symbol 'parse_recent_cache' is not present in the cited file",
         "claim_ref": "scout:link_exists:T-0343#b"},
        {"role": "author", "gate": "contradicts_symbolic",
         "detail": "claims write_cache_entry is unreferenced; the import graph shows 41 "
                   "tests reach it",
         "claim_ref": "author:test:app.services.cache_service.write_cache_entry"},
    ]
    assert len(rejection_ledger) == claims["rejected"]

    return {
        "run_metadata": {
            "schema_version": "2.0",
            "diff_files": DIFF_FILES,
            "total_tests_in_suite": 500,
            "generated_at": "2026-09-27T04:12:00Z",
            "model_layer": "enabled",
            "prompt_version": "v2.0.0",
            "coins_spent": 0,
            "environment_fingerprint": "python3.11|pytest-8.0|linux-x86_64",
            "cache": {"warm": True, "invalidated": []},
        },
        "classification": {
            "definitely_affected": syntactic,
            "semantically_affected": semantic,
            "not_affected": not_affected,
        },
        "ledger": ledger,
        "uncovered": [
            {"symbol": symbol, "path": path, "line": line, "changed_lines": changed,
             "kind": kind, "has_any_test": False}
            for symbol, path, line, changed, kind in UNCOVERED
        ],
        "claims": claims,
        "verified_claims": [
            # Every accepted claim points at a test that appears in a ledger bucket
            # (invariant I15: accepted ⇒ a matching verdict exists).
            {
                "claim_type": "link_exists", "role": "scout", "confidence": "high",
                "subject": "T-0342",
                "rationale": "report_worker parses the payloads cache_service.write_cache_entry "
                             "writes, so a change to the writer reaches this test.",
                "citations": [
                    {"path": "app/workers/report_worker.py",
                     "symbol": "parse_recent_cache_entries", "line": 44},
                    {"path": "app/services/cache_service.py",
                     "symbol": "write_cache_entry", "line": 57},
                ],
                "obligation": "symbol resolves in both files",
            },
            {
                "claim_type": "link_exists", "role": "scout", "confidence": "med",
                "subject": "T-0343",
                "rationale": "malformed-entry counting reads the same pipe-delimited payload.",
                "citations": [
                    {"path": "app/workers/report_worker.py",
                     "symbol": "malformed_entry_count", "line": 56, "line_drift": True},
                ],
                "obligation": "symbol resolves", "line_drift": True,
            },
            {
                "claim_type": "intent", "role": "cartographer", "confidence": "high",
                "subject": "T-0210",
                "rationale": "the docstring still promises a pipe-delimited payload, which "
                             "the diff removed.",
                "citations": [
                    {"path": "app/services/cache_service.py",
                     "symbol": "write_cache_entry", "line": 12},
                ],
                "obligation": "quote is byte-present at the cited location",
            },
            {
                "claim_type": "test", "role": "author", "confidence": "med",
                "subject": "T-0212",
                "rationale": "repaired assertion fires at revision A and passes at B.",
                "citations": [
                    {"path": "tests/test_reporting.py",
                     "symbol": "test_reporting_parse_pipe_payload", "line": 29},
                ],
                "obligation": "G3 assertion fires at A, G2 passes 5x at B",
            },
            {
                "claim_type": "missed", "role": "falsifier", "confidence": "low",
                "subject": "T-0411",
                "rationale": "billing export reads cached rows, so it belongs in the run list.",
                "citations": [
                    {"path": "app/workers/billing_export_worker.py",
                     "symbol": "invoice_export_rows", "line": 73},
                ],
                "obligation": "dependency path re-derives against the repository",
            },
        ],
        "rejection_ledger": rejection_ledger,
        "measurement": {
            # complete == false on purpose: the fixture exercises the VOID path.
            "oracle": {"collected": 78, "inventory_total": 500, "complete": False},
            "truth_size": 3, "selected": 47, "structurally_reachable": 41,
            "recall": 1.0, "missed": [], "price_of_safety": 6,
            "model_layer_recall_delta": 0.0,
        },
        "triage": [
            {"test_id": "T-0342", "diagnosis": "regression",
             "signal": "fails at revision B, passes at A; assertion fires on "
                       "parse_recent_cache_entries"},
            {"test_id": "T-0210", "diagnosis": "stale",
             "signal": "asserts behaviour the diff removed; repair the test, not the code"},
            {"test_id": "T-0106", "diagnosis": "flaky",
             "signal": "flips between revisions while covering no changed line"},
        ],
        "priority_order": (
            [tid for tid, *_ in SEMANTIC]
            + [e["test_id"] for e in syntactic]
        ),
        "summary": {
            "total": 500, "selected_for_run": 47,
            "definitely_affected_count": 41, "semantically_affected_count": 6,
            "reduction_pct": 90.6,
            "stale_count": 3, "uncovered_count": 4, "newly_relevant_count": 6,
            "unknown_count": 2, "valid_count": 489,
        },
    }


def main() -> int:
    payload = build()
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
