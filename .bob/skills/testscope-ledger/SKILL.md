---
name: testscope-ledger
description: >-
  Compute what a code change did to a test suite — which tests must run, which are
  now stale, which became newly relevant, and which changed behaviour has no test —
  with every claim mechanically re-checked against the repository. Use when a diff
  must be assessed against a test inventory, when a suite is too large to re-run,
  or when tests may be lying about behaviour a change removed.
---

# TestScope ledger

Re-run the whole analysis in one invocation. Deterministic steps first; they cost no
Bobcoins and their evidence exists before any model speaks.

## 1. Deterministic engine (0 coins)

```bash
python3 bob_session/run_analysis.py                 # bundled demo repository
python3 bob_session/run_analysis.py --repo <path> --diff <bundle> --inventory <csv>
```

Then read the artefact `bob_session/testscope_report.json`: `ledger`, `uncovered`,
`claims`, `rejection_ledger`, `measurement`, `priority_order`, `summary`.

Do **not** ask a model anything this tool already answers. That is a wasted coin.

## 2. Ground truth (0 coins)

```bash
python3 bob_session/reliability_check.py
```

Call the `testscope_oracle` tool for the dual-revision run. It runs with **all
markers** (`-m ""`) and asserts collection completeness; an incomplete oracle is
void, not a number. Never claim a recall figure yourself — it comes from here.

## 3. Sufficiency gate (0 coins)

`bob_session/roles/context.py` builds one bundle per unit and refuses the ones that
cannot decide. A skipped unit takes the safe direction: include the test and mark it.
Do not call a model to "fill in" a missing bundle.

## 4. Proposers (coins)

Dispatch one subagent per unit, each with ONLY its bundle, using the verbatim role
prompts: `bob_session/roles/scout.md`, then `cartographer.md` on escalation. Every
claim must be the claim envelope, with citations. No prose, no votes, no merged
judgement.

## 5. The kernel (0 coins)

Call `testscope_verify` with the claim batch. Accepted claims are facts; rejected
claims go to the rejection ledger with their gate. Nothing a model says becomes a
verdict without this call — there is no fast path.

## 6. The developer gate

Ask which STALE tests to repair and which UNCOVERED behaviours to author. Show the
rejection ledger next to the findings. Wait for the answer.

## 7. Author (coins)

One subagent per uncovered symbol, one file each, never two writers on one file
(`bob_session/roles/dispatch.py` enforces it). Use `bob_session/roles/author.md`.
The post-change implementation stays withheld; supply the class to extend, the intent
artefact when one exists, and the PRE-change body.

## 8. Filtration (0 coins, one human click)

Call `testscope_gate` with the patch and the symbol. Accept only what clears
G1..G5: buildable, passes 5×, an assertion fires at the previous revision (a
collection or import error does not count), mutation strength on the changed lines,
and specification anchoring when an intent artefact exists. One retry, then stop.

## 9. Render and record

Render the ledger and the dashboard; capture the screenshots named in
`bob_session/session_screenshots/README.md`. The falsifier runs **last and alone**
over the unselected rows only (`bob_session/roles/falsifier.md`).

## Invariants

* `selection = baseline ∪ verified additions` — a model can only ever cause
  over-selection, never under-selection.
* Same inputs ⇒ byte-identical artefact (kernel + content-addressed cache).
* Confidence orders results; it never authorises acceptance.
* "Pinned" is not "correct". No completeness guarantees. No "first ever" claims.
