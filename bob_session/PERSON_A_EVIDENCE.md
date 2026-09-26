# Person A — Evidence Pack (§11)

Every number below was produced by the command beside it, in this repository, in
one run. Nothing is transcribed from a document: if a command does not reproduce
a line, the line is wrong. Interpreter everywhere is `.venv/bin/python`
(Py3.14, PEP 668 — the project venv is the only install location).

    ./verify.sh                                          -> 55/55 PASS (v1 16/16 + sabotage 18/18 + new 21/21)
    .venv/bin/python -m pytest bob_session/tests -q       -> 131 passed
    bash -c 'grep -RE "exec\(|eval\(|__import__|importlib" bob_session/pipeline'  -> EMPTY (exit 1)

---

## 1. Oracle — executed ground truth for the demo repo

Source of truth: `bob_session/testscope_oracle.json`
Reproduce: `.venv/bin/python -m pytest bob_session/tests/test_oracle.py -q`

| field | value |
|---|---|
| `collected_a` / `collected_b` | 500 / 500 |
| `inventory_total` | 500 |
| `complete` | **true** |
| `mode` | `patch` (reverse-applied diff; no git history on this machine) |
| `default_marker_collected` | **497** (the blind spot: `addopts = -m "not contract"`) |
| `outcome_count` | 500 |
| `flaky_excluded` | `[]` |
| `already_red` | `[]` |

`changed` (the truth set, SMALL and SPECIFIC and NON-EMPTY):

    tests.test_report_worker::test_recent_entries_round_trip_contract[T-0340]
    tests.test_report_worker::test_recent_entries_round_trip_statuses[T-0341]
    tests.test_report_worker::test_recent_entries_round_trip_totals[T-0342]

note: `flakiness detection requires repeat>1; flaky_excluded is empty by construction`

The same instrument run under the **default** marker set collects 497 < 500 and
reports `complete:false` with `VOID` in the note — the instrument reports its own
blindness (T4, gate N04, sabotage S04).

## 2. The artefact from a clean run, `generated_at` pinned

    .venv/bin/python bob_session/run_analysis.py --repo demo_repo \
      --diff demo_repo/revisions/post_change.diff --inventory inventory.csv \
      --generated-at 2026-09-27T04:12:00Z --oracle bob_session/testscope_oracle.json \
      --model-layer disabled --no-cache --out bob_session/testscope_report.json

| field | value |
|---|---|
| sha256 of the artefact | `04a5af4219fa73e35710f05838246652916af9ba5b96d101978d30b11d0d1df4` |
| `generated_at` | `2026-09-27T04:12:00Z` (input, not a clock read) |
| `schema_version` / `model_layer` | `2.0` / `disabled` |
| summary | total 500, selected **47** (41 definite + 6 semantic), reduction **90.6%** |
| ledger | valid 494, stale 0, newly_relevant 6, unknown 0 |
| uncovered | 1 |
| claims | proposed 0, accepted 0, rejected 0 (model layer disabled) |
| rejection_ledger | `[]` |

## 3. The measured numbers (recall / missed / price of safety)

| measurement | value |
|---|---|
| `recall` | **1.0** = 3/3 (`|selected ∩ changed| / |changed|`) |
| `missed` | `[]` (always emitted, even when empty) |
| `truth_size` | 3 |
| `selected` | 47 |
| `structurally_reachable` | 41 |
| `price_of_safety` | **6** (47 − 41: what semantics-only selection adds over an import-graph selector) |
| `model_layer_recall_delta` | 0.0 (model layer disabled in this run) |

recall is a LOWER bound and measures recall only — it can never measure
precision, because `Delta(t)` is one-sided (a test can be affected and still
pass twice).

## 4. The uncovered work item

    symbol       app.services.cache_service.purge_stale_entries
    path:line    app/services/cache_service.py:37
    changed      37,38,39,40,41,42,43
    kind         UNCOVERED_NEW        has_any_test: false

Reproduce: read `uncovered` in the artefact (gate N03 / sabotage S03).

## 5. Eight-run determinism

8 cold runs (`--no-cache`), each written to its own file, SHA-256 of the bytes:

    distinct digests = 1
    04a5af4219fa73e35710f05838246652916af9ba5b96d101978d30b11d0d1df4

Same digest as the committed artefact (gate V16 + V15, test T7/T9).

## 6. Monotonicity run — the model layer can only add

Same claims file, two runs (the claim is a *verified* link for T-0146):

    --model-layer disabled  -> selected 47, semantically 6, price_of_safety 6, claims.proposed 0, claims_ignored true
    --model-layer enabled   -> selected 48, semantically 7, price_of_safety 7, claims.proposed 1, accepted 1

    removed by the model layer: []            <- nothing is ever taken away
    added by the model layer  : ['T-0146']    <- only ever adds

A hostile claim (fabricated symbol) instead lands in `rejection_ledger` with gate
`symbol_mismatch` and the selection stays exactly 47 (T8, gates N08/S08).

## 7. MCP server — tools/list and one kernel rejection over the wire

    .venv/bin/python bob_session/tools/capture_wire_evidence.py

tools/list (name -> alwaysAllow):

    testscope_ledger  true
    testscope_verify  true
    testscope_oracle  true
    testscope_gate    false      <- the click IS the trust boundary

Kernel rejection, gate named, returned over STDIO:

    gate    citation_invalid
    detail  app/services/does_not_exist.py is not readable (unreadable: FileNotFoundError)
    accepted []   unconfirmed []

stdout carried protocol JSON only; the server banner went to stderr
(`returncode 0`). alwaysAllow in `.bob/mcp.json` contains exactly three tools.

## 8. The causal controls (why the 90.6% is not a trick)

| control | result | command |
|---|---|---|
| inertness control: same repo, the inert log hunk made behavioural | 47 -> **122** (116 definite + 6 semantic, reduction 75.6%) | `--diff demo_repo/revisions/post_change_behavioural_billing.diff` |
| docs-only change | **0** selected, 500 valid | `--diff demo_repo/revisions/docs_only.diff` |
| link correction | T-0146 declared `app.utils.ids`, derived `app.utils.text` (import is a fact) | `run_metadata.link_corrections` |
| closure | 11 modules, depth histogram {0:1, 1:8, 2:1, 3:1}, 41 rows (18 direct + 23 transitive) | `run_metadata.import_closure` |
| hero | T-0342 selected with reason `representation_coupling`, priority head | `classification.semantically_affected` |

## 9. Trust-boundary grep (§9, must be EMPTY)

    $ grep -RE "exec\(|eval\(|__import__|importlib" bob_session/pipeline
    $ echo $?
    1

Gate N10 (test T10) runs the same scan as a test over `pipeline/**` **and** over
the server-side surface (`mcp_server.py`, `verify.py`, `oracle.py`, `gates.py`);
sabotage S10 proves it fails when a forbidden token is injected.
