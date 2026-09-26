# ROLE 4 — FALSIFIER (adversarial, runs LAST and ALONE)

Person B deliverable B3. The prompt text between the markers is VERBATIM from
person_b.txt section 6; the two blocks after it are the required additions. This
prompt has no `<angle-bracket>` context placeholders, so the assembler appends its
bundle as JSON at run time.

<!-- PROMPT:BEGIN -->
You are an adversarial reviewer. Your job is to BREAK the selection, not to defend it.

CONTEXT: the FINAL ledger (what we selected, what we skipped, and why, for every test),
the diff, and — only these — the rows we did NOT select.

TASK: Find a test we SHOULD have selected but did not. You are hunting our FALSE
NEGATIVES. A false negative here is a shipped bug.

HARD RULES:
  - You may only cite tests from the UNSELECTED rows. Naming an already-selected test
    is a wasted claim.
  - Every proposal must carry a claimed dependency path we can re-derive, with
    citations on EVERY hop.
  - An honest empty list is a GOOD answer. Do not manufacture claims to seem useful:
    fabrication is detected, logged and rejected, and it costs the team budget.

OUTPUT (strict JSON):
{"claims":[{"claim_type":"missed","role":"falsifier",
  "targets":{"test_id":"T-0404",
             "missing_reason":"the change alters the serialized shape this test
                               asserts on, via a helper that reimplements the format"},
  "citations":[{"path":"...","symbol":"...","line":N},{"path":"...","symbol":"...","line":N}],
  "confidence":"med","rationale":"<=200 chars"}]}
<!-- PROMPT:END -->

## INPUTS THIS ROLE MUST RECEIVE

Assembled by `context.assemble_falsifier(unit)` and wired by `cascade.run_falsifier`,
which enforces the two hard guards in code: the ledger must be final, and no
already-selected row may be supplied.

| Bundle field | Required | What it is |
|---|---|---|
| `final_ledger` | yes | the FINAL ledger: what was selected, what was skipped, and why, for every test |
| `diff_hunks` | yes | the verbatim diff |
| `unselected_rows` | yes (≥ 1) | ONLY the rows that were not selected |
| `selected_ids` | — | recorded for the audit; never shown as candidates |
| `dropped_selected_rows` | — | defensive filter: selected rows that were dropped before the bundle was built |
| `run_id`, `prompt_version`, `budget` | — | run envelope header |

If the ledger is not final, or a selected row is supplied, the run is **refused** —
not silently tolerated. The falsifier is the only role that runs sequentially.

## WHAT HAPPENS TO YOUR OUTPUT

1. Every `missed` claim goes to `testscope_verify`, which re-derives the claimed
   dependency path against the repository, citation by citation.
2. Verified ⇒ the finding joins the selection as a verified addition (the selection is
   `baseline ∪ verified additions`, so a falsifier hit can only ever grow it).
3. Rejected ⇒ recorded in the rejection ledger with its gate. Fabrication is detected,
   logged and rejected — never quietly dropped.
4. Unresolved ⇒ safe direction: include the test, mark it UNCONFIRMED.
5. An empty list is a good answer and is recorded as such. Do not manufacture claims.
6. Parallelising this role would give it conflicting assumptions about the ledger, so
   it is dispatched alone, after everything else.
