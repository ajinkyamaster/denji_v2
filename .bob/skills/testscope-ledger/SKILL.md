# Skill: analyse a change with the TestScope ledger

Use this when a diff must be adjudicated against a test inventory.

## Steps

1. `testscope_ledger` with `{repo, diff, inventory, generated_at}`.
   Deterministic, zero coins. It emits the artefact: classification, ledger,
   uncovered work items, claims, rejection ledger, measurement, triage and
   priority order.
2. `testscope_oracle` with `{repo, rev_a, rev_b, run_cmd}`.
   Deterministic, zero coins. It reports `complete`, which is computed (not
   asserted) from `collected`, `missing` and `unmapped`. If `complete` is
   false, **stop**: recall is VOID and no number about it may be published.
3. Sufficiency gate: read the artefact and keep only the questions the
   symbolic layer could not answer. If the coupling detector already linked a
   consumer, do not spend a coin asking a model about it.
4. Scout and cartographer subagents, in parallel, one context per unit. They
   return claims; they do not decide anything.
5. `testscope_verify` with the claims. The kernel re-opens the cited files and
   re-derives each claim. Accepted claims only ever ADD tests.
6. Select Action: the developer confirms which STALE tests to repair and
   which UNCOVERED behaviours to author. This is the human gate.
7. Author subagents, one per uncovered symbol, one test file each. The
   Author sees the PRE-change body and the intent artefact; the post-change
   body is withheld.
8. `testscope_gate` with the authored patch. G1..G5 decide: buildable, stable
   5x, an assertion fires at the base revision, mutation strength over the
   changed lines, and (when an intent artefact exists) specification
   anchoring.
9. Render the artefact and the visual summary. Deterministic, zero coins.

## Rules

- Never edit another role's artefact: the ledger is written by the engine, the
  verdicts by the kernel.
- A claim whose citation does not resolve is rejected, not repaired.
- Report `unconfirmed` claims as `unconfirmed`; they take the safe direction
  (the test is included and marked), and they are never presented as verified.
