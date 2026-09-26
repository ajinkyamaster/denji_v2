# Video storyboard (90 seconds of live demo and up)

Built on the real recorded session. **Honest gap:** this workspace has no Bob installation, so the
screen recording of the Bob IDE session must be captured where Bob runs; the proposal set it produced is
already recorded in `bob_session/roles/recorded/` and replayed through the content-addressed cache, so
the ledger, the kernel, the gate and the measurement below are all reproducible today with
`./verify.sh`. Do not film a fabricated session: capture the real one, and if a step misbehaves keep it
and narrate it.

## ~20s — the problem

- Show the change: `git -C demo show rev-b` — `cache_service.write_cache_entry` moving from
  pipe-delimited text to `json.dumps`.
- Run the default suite at both revisions: green, twice. The regression is invisible.
- One sentence: coverage can prove a test ran; it can never prove a test did not need to run.

## ~90s — the live demo

1. `python3 -m bob_session.pipeline.run_analysis` — the deterministic step, announce the coin cost:
   zero. Show `selected 48 of 500`.
2. `python3 -m bob_session.oracle` — executed ground truth, zero coins, and the fact that it reports
   its own blindness: `complete=True`, one missing row, one already-red test, zero flaky.
3. The sufficiency gate: show that the coupled consumer was already found symbolically, so no coin is
   spent asking about it.
4. One subagent, in its own context window: the scout bundle and its three claims.
5. **The money shot:** the kernel rejects a claim live — `symbol_mismatch` on
   `parse_recent_cache_entries_v2` — and the rejection ledger records it.
6. The ledger: the semantic catch (`T-0342`, first in the priority order), the three stale tests whose
   green is false assurance, the two uncovered work items.
7. Select Action: the developer picks the uncovered symbol and approves the gate click.
8. `python3 -m bob_session.gate` — G1..G5, with G3 firing an assertion at the base revision and G4
   reporting mutation strength 0.75.

## ~25s — the narration

- Structural versus semantic: the 41 tests a closure finds, the 7 it does not, and the one test static
  tooling would have skipped.
- The kernel is the trust boundary; determinism is a property of the kernel and the cache, not of the
  models.

## ~10s — the close

- The measured numbers with their limits in one breath: recall 1.0 against a lower-bound ground truth,
  48 of 500 selected, one additional true positive for 23 coins, seven tests of safety margin.
- The two questions no competitor answers: which of my tests are now lying to me, and which of my new
  behaviours has no test.
