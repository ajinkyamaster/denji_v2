# TestScope — project context

## What this is

A change-impact ledger for test suites. Given a diff, a test inventory and a
repository it answers four questions about every test: must it run, is it now
STALE, did it become NEWLY RELEVANT, and which changed behaviour has NO TEST.

## The one rule that matters

**No model output becomes a verdict until the kernel re-derives it against the
repository.** `bob_session/verify.py` is the only door; a claim's citations are
obligations. Deterministic steps cost zero coins, so the engine decides
everything it can decide exactly, and models are asked only what the symbolic
stratum cannot answer.

## Layout

| path | what it is |
|---|---|
| `bob_session/pipeline/` | the symbolic stratum: pure functions of (repo, diff, inventory) |
| `bob_session/verify.py` | the kernel: citation resolution and re-derivation |
| `bob_session/oracle.py` | executed ground truth (dual-revision outcome discriminant) |
| `bob_session/gate.py` | G1..G5 for authored tests, in a sandbox |
| `bob_session/roles/` | the four role prompts and the recorded proposal set |
| `bob_session/measure.py` | recall + ablation, with the M1..M4 rules enforced |
| `bob_session/reliability_check.py` | the scorecard R1..R10, each gate falsified |
| `demo/` | the target repository (a git history with revisions A, B, C, D) |
| `diffs/` | the change under analysis and the three control diffs |
| `submissions/` | measurement, scorecard, checklist, external sources |

## Commands

```bash
./verify.sh                                        # regenerate everything, run every gate
python3 -m bob_session.pipeline.run_analysis       # the ledger (MCP tool 1)
python3 -m bob_session.oracle                      # executed ground truth (tool 3)
python3 -m bob_session.gate                        # G1..G5 (tool 4)
python3 bob_session/measure.py                     # measurement.json (D1)
python3 bob_session/reliability_check.py           # the scorecard (D2/D3)
python3 -m pytest tests -q                         # the engine's own suite
```

## Conventions

- Numbers published in documents must appear in `submissions/measurement.json`,
  `submissions/scorecard.json`, `VERIFICATION.md` or `submissions/external_sources.json`.
  `reliability_check.py` R7 enforces this.
- Every gate must have been observed to fail at least once when deliberately
  broken; the scorecard records that evidence per gate.
- Publish a zero rather than hide one.
