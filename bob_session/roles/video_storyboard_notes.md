# Video storyboard notes (Person B deliverable B6 — Person D records)

Target: **≥ 90s of live demo**, plus problem framing, subagent narration and a close.
Total ≈ 2:35. Every screen shown below already exists as an evidence file in
`bob_session/session_screenshots/` (see that README for the capture order).

## 0:00–0:20 — the problem (live screen, not slides)

Show a 2,500-test suite and one line change. Say it plainly:

> "A change lands. Which tests must run? That question has tools. But two questions
> don't: which of my existing tests are now **lying to me**, and which of my new
> behaviours has **no test at all**."

Then the one sentence: *"TestScope computes what a change did to your test suite, not
just which tests to run — and every claim it makes is mechanically re-checked against
your repository."*

**Screen:** the dashboard's four-answer view, or the terminal running step 1.

## 0:20–1:50 — the live demo, deterministic steps FIRST (this order is the argument)

1. **`python3 bob_session/run_analysis.py`** — the deterministic engine. Call out:
   *"This cost zero model tokens. Everything decidable is decided here."*
   **Screen:** `workflow-deterministic-steps-completing.png`.
2. **`testscope_oracle`** — *"ground truth: the suite executed at both revisions, with
   all markers, and completeness asserted. If the oracle is blind, the number is void,
   not optimistic."*
3. **`testscope_verify` rejecting a claim** — *"this is the trust boundary. A model
   proposed a link; the kernel re-opened the citation and refused it. The rejection is
   in the ledger with its gate."*
   **Screen:** `kernel-rejects-fabricated-citation.png`.
4. **The Select Action gate** — *"nothing is written to your suite without this
   answer."* **Screen:** `select-action-developer-gate.png`.
5. **G3 on the authored test** — *"the assertion fires before the change and passes
   after it. We say 'pinned', not 'correct'."*
   **Screen:** `g3-assertion-fires-before-change.png`.

## 1:50–2:15 — the subagent narration and the syntactic-vs-semantic distinction

Show a subagent working in its own context window
(`subagent-own-context-window.png`), then say:

> "Most tools are deterministic over code structure. Structure is a **one-sided
> oracle**: sound for inclusion, unsound for exclusion. Our hero case is a change that
> breaks a test which imports nothing from the changed file and is absent from its
> import closure at every depth. Coverage and import graphs cannot see it — that is
> not a bug we could fix, it is the wrong abstraction."

Then the cascade in one breath: *"cheap proposer, exact mechanical verifier, escalation
only on verification failure; two tiers, maximum; and the falsifier runs last and alone
to hunt the test we missed."*

## 2:15–2:35 — close

> "Every claim was re-checked against the repository before it counted. The claim that
> the model layer added value is itself measured against executed ground truth, and if
> the delta is zero we say so. The kernel, not the model, is the trust boundary."

**Screen:** `final-artefact-dashboard.png`, then `bob-task-session-summary.png`.

## Say / never say

**Say:** "measured recall against an executed oracle"; "pinned, not correct"; "the
symbolic layer decides, the kernel verifies, the models only propose"; "the price of
safety"; "monotone soundness — a model can only ever add tests to the run set".

**Never say:** "first ever", "no one has done this", "guaranteed complete", "100%
recall", any recall figure not printed by the oracle in this session, any reduction
percentage not shown on screen. LDRA highlights untested changed code; test selection
is a mature market; agents are table stakes. Demonstrate, do not claim primacy.

## Capture checklist for the recording session

* [ ] Run and screen-record steps 1–3 **before** any model call.
* [ ] Record the deliberate kernel rejection (fabricated citation), with its ledger entry.
* [ ] Record the escalation event showing both tiers' proposals.
* [ ] Record the falsifier pass over the unselected rows.
* [ ] Drop the seven screenshots into `bob_session/session_screenshots/` with the names
      from the capture plan.
* [ ] Fill the AI rows of `bob_session/coins.md` from Bob's own settings panel.
