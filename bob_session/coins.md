# Bobcoin spend and the determinism audit (Person B, deliverable B4)

## The hard number

Bobcoins are the metered resource for AI reasoning in Bob. The hackathon grants about
**40 Bobcoins per account** and states that no additional Bobcoins will be provided.
With four accounts that is roughly **160 for the whole team, for the whole build** —
a design constraint, not a meter to watch at the end.

## Allocation (agreed in the first hour)

| Share | Purpose | ≈ coins |
|---|---|---|
| ~15% | the four role prompts' development and rehearsal | 24 |
| ~45% | the real recorded session on the real demo repository | 72 |
| ~20% | the second and third runs after a defect is found | 32 |
| ~10% | falsification passes — injecting a broken claim to prove the kernel rejects it | 16 |
| ~10% | reserve. Never spend this; if it is being spent, a step is misdesigned | 16 |

## How to read the ledger below

**Real numbers only.** A figure is written here when it has been observed in Bob's own
settings panel — never estimated from memory, never back-filled to look tidy. An
unobserved figure is written `PENDING`, and the audit column is filled at the same time
as the spend.

Every row answers one question in the audit column: **was this answerable
deterministically?** If that answer is ever `yes`, the step is misdesigned and gets
fixed — a deterministic step costs zero coins and is exact.

## Per-step ledger

| Date | Step | Kind | Spend (coins) | Cumulative | Was this answerable deterministically? | Note |
|---|---|---|---|---|---|---|
| — | 1. `testscope_ledger` | DETERMINISTIC | 0 | 0 | yes — that is why it is a tool call | pure engine; 0 coins by construction |
| — | 2. `testscope_oracle` | DETERMINISTIC | 0 | 0 | yes — execution, not reasoning | ground truth; temp copy only |
| — | 3. sufficiency gate + context assembly | DETERMINISTIC | 0 | 0 | yes — a precondition is not a question | `bob_session/roles/context.py` |
| — | 4. scout + cartographer subagents | AI | PENDING | PENDING | no — behavioural coupling with no structural edge is not decidable | coins recorded at capture time |
| — | 5. `testscope_verify` | DETERMINISTIC | 0 | 0 | yes — the kernel re-derives, it does not opine | the trust boundary |
| — | 6. Select Action (developer gate) | INTERACTIVE | 0 | 0 | yes — the human decides the policy; nothing to model | the human gate |
| — | 7. author subagents | AI | PENDING | PENDING | no — synthesis of a test is not decidable | one file per symbol |
| — | 8. `testscope_gate` G1..G5 | DETERMINISTIC | 0 | 0 | yes — execution in a sandbox | requires the human click |
| — | 9. render artefact + summary | DETERMINISTIC | 0 | 0 | yes — a pure function of the artefact | byte-identical across runs |
| — | post. falsifier | AI | PENDING | PENDING | no — adversarial search over unselected rows | runs last, alone |

**Recorded spend to date: 0 coins.** No live Bob session has been run at this commit;
the three AI rows carry `PENDING` until the recorded session (hours 16–20 of the
schedule) writes the observed figures here. Reporting a number nobody observed would be
worse than reporting that it is not yet known.

## Discipline

* Deterministic steps first, always. Every question that could have been answered by
  calling `testscope_ledger` is a coin burned for nothing.
* Ten candidate pairs handled by one subagent in one context costs far less than ten
  subagents each paying for the same context. Batch where the units are independent.
* Tool definitions are re-sent every interaction: four wide tools beat twenty narrow
  ones (`bob_session/roles/mcp_tool_descriptions.md`).
* Do not spend the session budget while experimenting; rehearse on cheap units.
* A retry of a step that a tool could answer deterministically is a coin burned: fix
  the step instead.
