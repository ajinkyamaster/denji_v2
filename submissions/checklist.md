# Submission checklist

Status legend: **PASS** (present and gated), **HONEST GAP** (absent, disclosed), **FAIL** (absent and
not acceptable as a gap).

| item | status | evidence |
|---|---|---|
| Public repository, coherent, everything under the project root | PASS | `./verify.sh` regenerates every artefact |
| Bob IDE demonstrated as a core component (eligibility) | PASS (artefacts) | `.bob/mcp.json`, `.bob/custom_modes.yaml`, `.bob/skills/testscope-ledger/SKILL.md`, `.bobrules/testscope.md`, `bob_session/mcp_server.py` |
| Bob task session-summary screenshots in `bob_session/session_screenshots/` | **HONEST GAP** | no Bob installation in this workspace; the directory carries a README stating what to capture |
| `IBM_BOB_USAGE_STATEMENT.md`, <= 500 words, specific | PASS | gated by scorecard S2 |
| `PROBLEM_SOLUTION_STATEMENT.md`, <= 500 words | PASS | gated by scorecard S2 |
| README accurate to the repository, competitor table included, no contradictory figure | PASS | gated by scorecard R7 (no unsourced number) |
| Video >= 90s live demo, framing, subagent narration | **HONEST GAP** | storyboard written in `VIDEO_STORYBOARD.md`; must be filmed against a real Bob session |
| `submissions/measurement.json` with recall, missed, price_of_safety and the ablation | PASS | `python3 bob_session/measure.py` |
| Scorecard present with R1..R10, each gate observed to fail once | PASS | `submissions/scorecard.json`, `submissions/scorecard.md` |
| `bob_session/coins.md` present and within budget | PASS | recorded 23 of the 160-coin budget |
| The verification script passes, the engine suite is green | PASS | `./verify.sh`, `VERIFICATION.md` |
| No "first ever" / "nobody has" / "no one has" claims anywhere in the submission documents | PASS | gated by scorecard S3 |
| Handoff statements kept in the repository for transparency | PASS | `handoff/` (`ARCHITECTURE_V2.md`, `person_d.txt`; the other person files were not supplied to this workspace) |
| Submitted with margin | PASS | the repository is complete and reproducible as of this commit |

## What is deliberately not claimed

- No completeness guarantee, and no "first ever" for any capability a competitor already ships
  (LDRA reports untested changed code; Change Advisor updates stale tests from declared schemas; test
  selection is a saturated market).
- No precision claim from the oracle: it is a lower-bound instrument, so over-selection is invisible
  to it.
- No live Bob session claim. The proposals are a recorded set replayed through the content-addressed
  cache, and that is stated in `IBM_BOB_USAGE_STATEMENT.md`.
