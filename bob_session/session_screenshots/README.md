<<<<<<< HEAD
# Bob session screenshots (Person B, deliverable B5)

The hackathon requires Bob IDE to be demonstrated as a core component and requires
task session-summary screenshots in the repository as **evidence of Bob usage**. This
directory is where they live.

**Name each file after what it PROVES, not after its order.** A screenshot whose name
states its claim is evidence; a numbered one is a picture.

## Capture order and the claim each file makes

| # | Filename | What it proves |
|---|---|---|
| 1 | `workflow-deterministic-steps-completing.png` | the workflow mid-run, with the deterministic steps (ledger, oracle, sufficiency gate) completing before any model is asked |
| 2 | `subagent-own-context-window.png` | a subagent working in its OWN context window: context hygiene in one picture |
| 3 | `kernel-rejects-fabricated-citation.png` | **the most valuable shot in the submission**: the kernel refusing a claim, with the gate and the reason visible, and the rejection ledger entry beside it. It proves verification is real rather than narrated |
| 4 | `select-action-developer-gate.png` | the Select Action gate, with the developer choosing what to repair and what to author — the human controls the execution |
| 5 | `g3-assertion-fires-before-change.png` | the G3 result: the authored test failing (on an assertion) before the change and passing after |
| 6 | `final-artefact-dashboard.png` | the final artefact and the dashboard, showing the four answers in one view |
| 7 | `bob-task-session-summary.png` | the Bob task session summary panel itself — the eligibility evidence |

## How to capture them (order matters)

1. Run steps 1–3 first and screenshot the `[PASS]` lines from `./verify.sh`: the
   evidence then exists independently of the AI. Recording an AI step first makes the
   demo look like a chatbot with a calculator attached — the opposite of this design.
2. Then run the cascade and capture 2–5 in the order above. For #3, deliberately
   inject a broken claim (a citation to a path that does not exist) so the rejection is
   observed rather than described. A gate never observed to fail is not a gate.
3. Capture #6 and #7 last, when the artefact is stable.

## Also hand over (not screenshots, but the same evidence pack)

* **The kernel rejection transcript**: the claim, its citation, and the rejection
  reason (`bob_session/roles/cascade.py` writes each rejection with its gate).
* **The escalation event**, with both tiers' proposals: tier 1 rejected → tier 2 asked.
* **The G3 result**: the authored test's outcome before and after the change.
* **The sufficiency-gate skip log**: what was NOT asked, and why that saved budget
  (the gate's `missing` list is recorded on the outcome).
* **`bob_session/coins.md`** with the observed spend per step and the determinism audit.

Person D needs items 1–7 and the pack above for the video storyboard: ~20s problem,
≥ 90s live demo, ~25s on the subagent steps and the syntactic-vs-semantic distinction,
~10s close.
=======
# Session screenshots (to be captured in Bob)

**Status: honest gap.** No Bob installation exists in the workspace where this repository was
assembled, so no live task-session screenshot could be produced here. Capture these against a real
Bob session and name each file after what it PROVES, not after its order:

| file name | what it proves |
|---|---|
| `mcp_tools_registered_alwaysallow.png` | the four tools are registered, three of them `alwaysAllow`, and the gate tool requires a click |
| `workflow_deterministic_steps_zero_coins.png` | the workflow's step taxonomy with the deterministic steps marked as costing nothing |
| `scout_subagent_own_context.png` | one subagent in its own context window, with the bundle it was given |
| `kernel_rejects_fabricated_citation.png` | the kernel rejecting `parse_recent_cache_entries_v2` with `symbol_mismatch` |
| `ledger_semantic_catch_and_stale.png` | the ledger showing T-0342 selected semantically, three stale tests and two uncovered work items |
| `select_action_developer_click.png` | the interactive Select Action gate, with the developer choosing |
| `gate_g1_to_g5_result.png` | G1..G5 with the assertion firing at the base revision and mutation strength 0.75 |
| `coins_spent_counter.png` | Bob's coin counter before and after the run |

Until these exist, the coin figure in `bob_session/coins.md` is a recorded figure, not a screenshot, and
`IBM_BOB_USAGE_STATEMENT.md` says so.
>>>>>>> origin/saurabh
