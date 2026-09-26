# Coin accounting

Bobcoins are consumed per AI interaction and are not replenished, so the workflow is ordered
deterministic-first: a question the symbolic engine can answer exactly is never sent to a model.

## Budget (team plan)

| line | planned | spent |
|---|---|---|
| exploration and building the `.bob` layer | 45 | 0 (built without model calls) |
| the clean recorded end-to-end session | 40 | 23 (recorded below) |
| reliability and repeat runs | 25 | 0 (every gate is deterministic and free to re-run) |
| ad-hoc debugging with a model | 20 | 0 |
| reserve | 30 | 0 (untouched) |
| **total** | **160** | **23** |

## What the 23 coins bought

| role | coins | what it returned |
|---|---|---|
| scout | 6 | three `link_exists` claims: one accepted (T-0342, the hero), one rejected `contradicts_symbolic`, one rejected `symbol_mismatch` |
| cartographer | 5 | two intent claims: one anchored to the module docstring the change invalidated, one rejected `citation_invalid` because the quote is not byte-present |
| author | 8 | one test patch for the uncovered `_should_drop`, accepted by G1..G5 (G4 strength 0.75) |
| falsifier | 4 | one `missed` claim that re-derives: the ops smoke test the declared-module coupling had not selected |

## What cost nothing

Steps 1, 2, 3, 5, 8 and 9 of the workflow: the ledger, the oracle, the sufficiency gate, the kernel,
the gate execution and the rendering. The kernel is the expensive half of the idea and it is free.

## Marginal value

Measured against executed ground truth, the model layer contributed **one additional true positive for
23 coins** on this change: recall with the layer disabled is 0.666667, with it enabled 1.0. The number
is reported as a marginal figure for this one change, not as a success rate; if it had been zero it
would have been published as zero.

## Replay

The recorded proposals are content-addressed, so re-running the ledger replays them byte-identically and
spends nothing. With the cache cold and no model reachable, the run logs `model-unavailable`, sets model
coverage to 0.0 and returns the deterministic baseline — the scorecard gate R10 asserts the selection is
then byte-identical to the baseline.
