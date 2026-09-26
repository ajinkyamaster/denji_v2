# TestScope — Architecture v2: The Test–Code Link Ledger

**Relationship to `ARCHITECTURE.md`.** That document (v1) describes the *selection engine*: implemented, measured, and enforced by 15 gates and 203 tests. It stays true and stays green. This document is the **ideation-phase specification for v2**, which answers a strictly larger question. Every claim here is marked:

| Mark | Meaning |
|---|---|
| **[BUILT]** | On disk in this repo, verified by a gate or test that can fail. |
| **[PROVEN]** | Follows from a measurement already in this repo. |
| **[SPEC]** | Specified, not yet implemented. No claim of behaviour. |

Nothing in §4 onward is built. The reason this document exists before the code does is that the last three defects found in v1 (an OS-dependent theme, two column widths derived from the wrong set, a silent numeric coercion) were all *design* defects, not coding defects. Design is cheaper to fix on paper.

---

## 0. Why v2 exists: the reframe from *selection* to *disposition*

v1 answers: **which tests must run?** That is one question, and the literature has a name for it — *regression test selection* — inside a triad of *minimization, selection, prioritization* (Yoo & Harman, STVS 2012, 2,180 citations).

The actual problem is larger. Restated from the field rather than from a slide:

> A developer has ~2,500 test cases against a module. They change the code. Afterwards, some tests no longer assert anything true (**stale**), some are unchanged (**valid**), some that never had a reason to care now do (**newly relevant**), and some of the new behaviour has no test at all (**uncovered**). They must also author the missing tests.

This enumerates **four** questions. The literature asks them too — a regression-testing programme states the design space as *"how to find obsolete test cases, how to repair test cases, how to efficiently rerun test cases, how to create new effective test suites."* Those are four different problems. v1 solves one of them. **v2 solves all four, and its contribution is that they are four cases of one relation rather than four tools.**

| Question | Literature name | v1 | v2 |
|---|---|---|---|
| Which must run? | selection | ✅ 47 of 500 | ✅ |
| Which are now invalid? | minimization / repair | ❌ | **[SPEC]** |
| Which need authoring? | generation | ❌ | **[SPEC]** |
| In what order? | prioritization | ❌ | **[SPEC]** |

---

## 1. The one abstraction: the link relation

Everything in v2 is a statement about a single mathematical object.

**Definition 1 (link relation).** Let `T` be the test set and `C` the set of code entities (functions, modules, wire formats, constants, contracts). The **link relation** is

```
L ⊆ T × C
```

`(t, c) ∈ L` iff executing `t` can observe the behaviour of `c`.

**Definition 2 (link delta).** For a change `D`, the induced delta is

```
ΔL(D) = { (t,c) ∈ L : c is modified by D }  ∪  { (t,c) ∉ L : (t,c) ∈ L* \ L }
```

where `L*` is the true (unknowable) relation. The first term is *known links whose target changed*. The second term is **missing links made consequential by the change** — the only term that requires discovery.

**Definition 3 (verdict).** The disposition of `t` under `D` is a function of `ΔL`:

| Verdict | Predicate | Developer action |
|---|---|---|
| **VALID** | `∃(t,c) ∈ ΔL`, `D` preserves `c`'s contract | run it; green means something |
| **STALE** | `∃(t,c) ∈ ΔL`, `D` removes/redefines `c`'s contract | **repair or delete the test** — its red is noise |
| **NEWLY_RELEVANT** | `(t,c) ∈ L* \ L` and `(t,c) ∈ ΔL` | **run it now**; its green was false assurance |
| **UNCOVERED** | `∃c ∈ Σ(D)` with `∄t : (t,c) ∈ L` | **author a test** — this is the uncovered set |
| **UNKNOWN** | cannot be decided from available evidence | run it (safe direction) |

**These five are exhaustive and mutually exclusive** by construction: they partition on (does a link exist?) × (is the target changed?) × (is the target's contract preserved?). `Σ(D)` is the changed-symbol set from v1's diff parser **[BUILT]**.

**Why one relation and not four techniques:** the four answers then share one evidence base, one verifier, and — critically — one *invalidator*. When `c` changes, every verdict about `c` is invalidated together. Four independent tools would each need their own staleness logic, and they would disagree.

---

## 2. The central lemma: coverage is a one-sided oracle

This single lemma is the reason the product exists, and it explains every design decision downstream.

**Lemma 1.** Let `L_cov` be the link set derived from executed-code coverage, and `L*` the true relation. Then

```
L_cov  ⊆  L*          (sound for inclusion)
L*     ⊄  L_cov       (unsound for exclusion)
```

*Proof of the strict part, inside this repository* **[PROVEN]**. Commit B changes `app/services/cache_service.py` from `f"{v['id']}|{v['status']}|..."` to `json.dumps(value)`. `app/workers/report_worker.py`, untouched and importing nothing from `cache_service`, parses that output at line 44 with `entry.split("|")`. The dependency is real — `pytest -m contract` is 3 passed at A, 3 failed at B — yet `report_worker` is **not in `cache_service`'s import closure at any depth**.

Measured closure **[BUILT]**: 11 modules, 41 inventory rows, depth histogram `{0:1, 1:8, 2:1, 3:1}`, 18 direct + 23 transitive. `report_worker` is absent from all of it.

**Consequences, and they are not stylistic:**

1. Any tool that *excludes* on the basis of coverage assumes `L* ⊆ L_cov`. That assumption is false. This is not a missing feature; it is the wrong abstraction.
2. Coverage remains **fully trustworthy in one direction**: if a test covered a line, it executed it. So coverage is admissible as a *positive witness* for a proposed link, and inadmissible as a *negative witness*. Every use of it in v2 respects that asymmetry.
3. It compounds with a second published finding: coverage is only weakly correlated with test-suite effectiveness once suite size is controlled (Inozemtseva & Holmes, ICSE 2014, **ACM Distinguished Paper**). So coverage is a weak oracle in *both* roles. v2 uses it only as a witness.

The complement matters equally: the same analysis proves the README typo and the `billing_service.settle` log reword cannot matter, and that inertness propagates. That is what keeps 75 control tests out of the selection, and it is a *sound* exclusion because it rests on non-modification, not on non-coverage.

---

## 3. The epistemic boundary: what is knowable, and what is not

An architecture that cannot state its own limits will overclaim. The limits here are theorems, not engineering shortfalls.

**3.1 The impossibility.** "Does change `D` alter the observable behaviour of test `t`?" asks a non-trivial semantic property of a program. By **Rice's theorem**, such properties are undecidable. Recent work states the consequence directly: *"Rice's Theorem, and the undecidability of program equivalence impose hard limits on what can be guaranteed about a patch's correctness."*

**Corollary (the honest headline).** No tool — and no model — can guarantee *completeness* of test selection. This is not a limitation v2 can engineer away, and any tool claiming a soundness guarantee on arbitrary code is wrong by theorem. **AI does not escape Rice.**

So v2 claims exactly two things, each weaker than a guarantee and each *measurable*:

| Claim | Kind | How it is established |
|---|---|---|
| **Monotone soundness** | inductive, testable | the model layer can only *add* tests; disable it and the selection equals the deterministic baseline **[SPEC: test]** |
| **Measured recall** | empirical | compare the selection to an *executed* oracle over many commits |

**3.2 The oracle.** Completeness is not argued; it is measured against ground truth that execution can provide:

**Definition 4 (outcome discriminant).**
```
Δ(t) = [ outcome_A(t) ≠ outcome_B(t) ]
```
where `outcome` is the test's pass/fail at the pre- and post-change revisions. `Δ` is a **lower bound** on the true affected set — a test can be affected and still pass twice — so it measures recall, never precision-in-absolute (over-selection is invisible to it). That asymmetry is stated rather than hidden.

**A defect this analysis caught before it shipped [PROVEN]:** the first implementation of the oracle ran the default suite at both revisions and found **zero** discriminating tests. Cause: the demo repo's `pytest.ini` carries `addopts = -m "not contract"`, so the three contract tests — *the only tests that discriminate* — are excluded by default. The oracle was blind, and it reported "no regression" with a straight face.

**Defined behaviour, now a rule:** the oracle must run under `-m ""` (all markers) **and assert that collected tests == `run_metadata.total_tests_in_suite`**. An oracle that collects less than the inventory silently reports false confidence. This is invariant **O1: oracle completeness** — a measurement of recall is meaningless if the measuring instrument is narrower than the measured population.

**3.3 The oracle problem, and the split v2 refuses to blur.** Existence of a *test* is not existence of an *oracle*. Determining expected output is the oracle problem (Barr et al., IEEE TSE 41(5), 2015). It splits into two guarantees that a dishonest tool would merge:

| Guarantee | Meaning | Mechanism | Honest bound |
|---|---|---|---|
| **PINS** | the test will detect *future* changes to this behaviour | change-discriminating test (§10.3) | says nothing about whether *this* change was correct |
| **SPECIFIES** | the assertion encodes *intended* behaviour | anchored to a specification artefact (docstring, PR/issue, reproducer) | only as good as the artefact |

`PINS` is mechanical. `SPECIFIES` requires an intent artefact, and when none exists v2 **downgrades the claim instead of inflating it**: *"this behaviour is now pinned"*, never *"this behaviour is correct."* Conflating the two produces precisely the dishonest signal described in the literature — *"high coverage with weak tests is a dishonest signal: 'this is tested' when it isn't."*

---

## 4. Three strata, and the determinism theorem

**The requirement is exact:** the tool must be intelligent *and* deterministic. These are not in tension if the system is split at the **decision** boundary rather than at the "AI" boundary.

```
┌─ S: SYMBOLIC ──────────────────────────────────────────────────────┐
│ pure functions of (repo, diff, inventory)                          │
│ DECIDES everything it can decide. 0 model calls. 0 coins.          │
│ v1's pipeline, extended to emit dispositions and obligations.      │
└────────────────────────────▲───────────────────────────────────────┘
                             │ every claim must compile to an obligation
┌─ K: KERNEL ────────────────┴───────────────────────────────────────┐
│ deterministic verifier. Re-executes every obligation against the   │
│ repo. Accept / reject / downgrade. THE TRUST BOUNDARY.             │
│ Total function. No model may write here.                           │
└────────────────────────────▲───────────────────────────────────────┘
                             │ proposals enter only through K
┌─ I: INFERENCE ─────────────┴───────────────────────────────────────┐
│ stochastic proposers (4 roles, 4 keys). SEALED: their output is    │
│ inert until K accepts it. Cache content-addressed for replay.      │
└────────────────────────────────────────────────────────────────────┘
```

**Theorem 1 (determinism by construction).** If `K` is a total deterministic function and the proposal set `P` is content-addressed, the emitted artefact is byte-identical across runs, *regardless of the models' non-determinism*.

*Proof sketch.* The artefact is `f(inputs, K(P))`. `K` is deterministic by assumption and `P` is a pure function of content hashes, so `K(P)` is deterministic; `f` is a pure function (v1's rule: no clock, no RNG, total ordering). Therefore the composition is deterministic. ∎

This is the answer to "you have to make this deterministic": **determinism is a property of the kernel plus the cache, not of the models.** It is achieved by construction, not by hoping.

**Three mechanisms, three distinct guarantees — do not merge them:**

| Mechanism | Guarantees | Does NOT guarantee |
|---|---|---|
| Constrained decoding (grammar/schema at token level) | **valid structure** — the output *cannot* be malformed, so no validate-retry loop is needed | anything about content |
| The kernel `K` | **valid semantics** — every accepted claim is mechanically re-derived | completeness |
| Content-addressed cache | **replay** — same inputs ⇒ same artefact | that the model was right |

Research is unambiguous that the third layer is load-bearing: identical inputs to a hosted model **do not** reproduce identical outputs even at `temperature=0` with a fixed seed. Anyone claiming determinism from sampling settings has not measured it. v1's own evidence is stronger — 8 runs, **one** distinct SHA-256 **[BUILT]** — and v2 preserves it by keeping every model output outside the artefact path until `K` has accepted it.

**Monotonicity (the safety property).**

**Lemma 2.** Let `B` = deterministic baseline selection, `A` = kernel-accepted model additions. The final selection is `B ∪ A`. Therefore a model that is unavailable, wrong, malicious, or rate-limited can only ever cause **over**-selection, never under-selection relative to `B`.

This is a real, testable guarantee, and it makes degradation graceful: with all four keys revoked the tool still returns the baseline and says so. **Corollary (injection containment):** the repository is untrusted input — prose in a comment can say anything. Because acceptance is mechanical (§10.2), a hostile prompt can at worst produce a *false proposal*, which `K` rejects, or a *true* proposal, which only ever adds tests to the run set. **Untrusted text cannot cause an unsound accept.** The verifier, not the model, is the trust boundary.

---

## 5. The ontology — defined concepts

This is the vocabulary. Every term below is defined, and every term has an enforcer or an explicit `[SPEC]` marker. A concept without an enforcer is a slogan, so there are none.

| # | Concept | Definition | Enforcer | Status |
|---|---|---|---|---|
| C1 | **Link relation `L`** | `(t,c) ∈ L` iff running `t` can observe `c` | derived from evidence primitives E1–E3 | [SPEC] |
| C2 | **Link delta `ΔL(D)`** | §1 Def. 2 — known-changed links ∪ missing links made consequential | diff `Σ(D)` ∩ `L` | [SPEC] |
| C3 | **Verdict** | §1 Def. 3 — VALID / STALE / NEWLY_RELEVANT / UNCOVERED / UNKNOWN | exclusive partition | [SPEC] |
| C4 | **Outcome discriminant `Δ(t)`** | §3.2 Def. 4 — outcome differs A vs B | dual-revision execution | [SPEC] |
| C5 | **Oracle completeness (O1)** | the oracle run must collect the full inventory | asserted: `collected == total_tests_in_suite` | [SPEC] |
| C6 | **Semantics-modifying (SM)** | a change to `c`'s observable contract | v1 skeleton comparison over removed/added lines | **[BUILT]** |
| C7 | **Inert change** | `¬SM` — provably cannot alter behaviour | skeleton multiset equality | **[BUILT]** |
| C8 | **Representation coupling `K`** | two modules bound by a shared *wire format* with no import edge (a class of stamp coupling) | AST call detection on `split`/`join`/`partition` + separator provenance | **[BUILT]** |
| C9 | **One-sided oracle** | §2 Lemma 1 — sound for inclusion, unsound for exclusion | every coverage use must be positive-witness only | **[PROVEN]** |
| C10 | **Obligation** | a model claim compiled to a mechanically checkable predicate `(claim_type, targets, citations)` | `K` re-executes it against the repo | [SPEC] |
| C11 | **Citation validity** | the cited path/symbol exists at the cited location | filesystem + AST lookup; line drift downgrades, symbol mismatch rejects | [SPEC] |
| C12 | **Sufficiency gate** | a zero-token precondition: is the context bundle even capable of deciding this? | asserts required AST nodes present before any call | [SPEC] |
| C13 | **Change-discriminating test (CDT)** | test that **fails at A and passes at B** — the literature's *patch test* | executed twice | [SPEC] |
| C14 | **Assertion-firing** | CDT qualification: the failure at A is an assertion failure, not a collection/import error | inspect failure origin | [SPEC] |
| C15 | **Test strength** | sensitivity of an assertion to perturbation of the target | mutation analysis restricted to `Σ(D)` | [SPEC] |
| C16 | **Specification anchoring** | the assertion is anchored to an intent artefact, upgrading PINS → SPECIFIES | quote-located in docstring/PR/issue | [SPEC] |
| C17 | **Filtration** | the Assured-LLMSE discipline: discard any candidate that fails to clear every guarantee (Alshahwan et al., FSE 2024) | sequential gates §10.3 | [SPEC] |
| C18 | **Safe direction** | on unresolved uncertainty, include the test | tie-break rule in `K` | [SPEC] |
| C19 | **Replay determinism** | §4 Thm. 1 | content-addressed proposal cache | [SPEC] |
| C20 | **Rejection ledger** | every rejected proposal recorded with the gate that rejected it | append-only log in the artefact | [SPEC] |
| C21 | **Marginal value** | `Δrecall(model layer) / Δcost` measured against the oracle | ablation gate | [SPEC] |
| C22 | **Coin budget** | Bobcoins are consumed per AI interaction and are **not replenished** | deterministic-first step design | [SPEC] |
| C23 | **Context tax** | tool definitions are re-sent every interaction, so a larger tool surface costs coins on every turn | minimal coarse tool surface (§8.5) | [SPEC] |
| C24 | **Red triage** | classify a failure as regression / stale / flaky | §12 | [SPEC] |
| C25 | **Priority** | deterministic total order over the run list to maximise fault-detection *rate* | §12.3 | [SPEC] |

---

## 6. The five verdicts, mechanically

| Verdict | Evidence required | How computed | Developer action |
|---|---|---|---|
| **VALID** | `(t,c) ∈ ΔL`, `c` preserved | structural closure ∩ inventory, `c ∉ ρ(D)` | run; green is meaningful |
| **STALE** | a removed behaviour is *asserted* by `t` | `assertion_target(t) ∩ ρ(D) ≠ ∅`, or `t`'s module no longer exists | **repair or delete**; do not chase its red |
| **NEWLY_RELEVANT** | a *recovered* link to changed code | `K`-verified proposal, or representation coupling `K` **[BUILT]** | run now; it may be red and the red is real |
| **UNCOVERED** | `c ∈ Σ(D)`, no `t` links to it | `Σ(D) \ ⋃ covered` | **author**; emit as a work item |
| **UNKNOWN** | sufficiency gate failed | bundle lacked the AST nodes needed | run (safe direction) |

`ρ(D)` — the *removed behaviour* — is the new primitive STALE needs and v1 already parses the raw material for it **[BUILT]** (removed lines with skeletons). A test whose declared module no longer exists is **definitionally obsolete**, which gives STALE a second, purely structural detector: an **orphan**.

---

## 7. The two soundness levers, and evidence both are here

The literature offers exactly two ways to move the soundness boundary of RTS, and v1 already implements both:

**Lever 1 — find more dependencies.** Rothermel & Harrold's frame; realised by *dynamic* dependency tracking (Ekstazi tracks test→file dependencies at runtime; Gligoric et al., 2015) and by hybrid static+dynamic schemes (JcgEks, ASE 2024). v2's `L` is built the same way: static AST closure **[BUILT]** plus dynamic coverage contexts **[SPEC]** (coverage.py records per-test *contexts*, so the test→line map is *measured*, not inferred).

**Lever 2 — prove a change cannot matter.** "More Precise Regression Test Selection via Reasoning about Semantics-Modifying Changes" (Liu et al., 2023) is exactly this: identifying that a change is *not* semantics-modifying licenses safely *not* re-running tests. v1 independently arrived at this as the **inertness rule** **[BUILT]**, and it is validated causally by the *sensitivity* control: make the inert log reword behavioural and **75 control tests return** (47 → 122). Without that control, "we correctly excluded 75 tests" would be unfalsifiable.

**And the second lever is unavoidable, not optional.** §2 proves `R* ⊊ δ*`. So no amount of import-graph precision suffices, and the semantic term is load-bearing. The *cost* of that safety is measurable and should be reported:

```
price of semantic safety = |selected| − |{t : t reaches changed code}|
```

v1's baseline: 47 selected, 41 structural ⇒ **price = 6 tests** **[BUILT]**, and one of those 6 is the regression.

---

## 8. Model orchestration: the verification-gated cascade

Motive: four API keys, and a real budget (C22). The goal is *maximum intelligence per coin*.

### 8.1 Three patterns rejected before choosing

| Pattern | Why rejected |
|---|---|
| **Majority voting across the 4 models** | Its guarantee descends from Condorcet's jury theorem, which **assumes independent voters**. LLMs trained on overlapping corpora have correlated errors, so the independence premise fails — the literature's own summary is *"Three Models Agreed. It Was Still Wrong."* Voting may be used to *rank discoveries*; it may never be used to *establish correctness*. |
| **LLM-as-judge to verify claims** | Documented **systematic** (not random) bias: position bias (Shi et al., 2025), verbosity bias, self-preference bias. A verifier with systematic bias cannot underwrite a reliability claim. Rejected as a *verifier*; retained only as an *author*, whose output is then mechanically verified. |
| **LLMs for graph/type inference** | Measured: *"traditional static analysis tools such as PyCG for Python and Jelly for JavaScript consistently outperform LLMs"* for call-graph construction. Asking a model what an AST can answer exactly is pure waste — of coins and of correctness. |

**The rule that falls out of the third rejection — Rule 1:** *never send a model a question the symbolic stratum can answer exactly.* This is the primary defence against the failure mode of "scattered AI slop": the model is not asked to be clever about things that are decidable.

### 8.2 The pattern chosen: cascade with an exact escalation scorer

FrugalGPT (Chen et al., 2023) reduces cost up to 98% by *cascading*: try cheap, escalate only when insufficient. Its difficulty is that the escalation decision needs a *learned, calibrated* scorer — which needs training data and drifts.

**v2's improvement:** the **kernel replaces the scorer**, and it needs no training because it is exact.

```
candidate  ──►  SUFFICIENCY GATE (0 coins)  ──►  [skip: undecidable, go to UNKNOWN]
                                                 │
                                                 ▼
                              ┌── ROLE-1 SCOUT (cheap, wide) ──┐
                              │  proposes links + citations    │
                              └────────────────┬───────────────┘
                                               ▼
                                    KERNEL K  (0 coins)
                          verified? ──► ACCEPT, stop escalating  ◄── most proposals end here
                          reject ────┐
                                     ▼
                         ┌── ROLE-2 CARTOGRAPHER (spec/doc mining) ──┐
                         └───────────────────┬─────────────────────┘
                                             ▼  KERNEL K — verified? → ACCEPT
                                             │  reject ↓
                         ┌── ROLE-4 FALSIFIER (adversarial: find the test we missed) ──┐
                         └──────────────────────┬─────────────────────────────────────┘
                                                ▼  KERNEL K
                                                │  still unresolved → SAFE DIRECTION (C18)
                                                ▼            + UNCONFIRMED label
```

Escalation is *triggered by mechanical failure*, not by a confidence number. Expected cost is therefore dominated by the cheapest tier — the same economics as FrugalGPT, without the calibration problem.

### 8.3 Four roles, four keys — and why diversity is honest here

| Role | Model class | Job | Why this needs a *different* model |
|---|---|---|---|
| **1 Scout** | cheap/fast, highest volume | propose candidate links across all candidate pairs + citations | breadth; this is where volume is |
| **2 Cartographer** | strong, reads documents | mine intent from docstrings, README, PR/issue text, and the manual-test descriptions → specification anchors | *document understanding* is a distinct capability |
| **3 Author** | strong, code-capable | synthesise tests for UNCOVERED behaviours, as extensions to existing test files | generation |
| **4 Falsifier** | strong, adversarial | given the ledger, **find a test that should have been selected but wasn't** | the critic must not be the author |

Meta's deployment makes the ensemble case for *discovery*: *"each combination tends to contribute uniquely to the overall number of test cases found."* Different models have different blind spots, so **diversity raises recall of discovery** — and that is the only thing v2 uses it for. Voting for *correctness* is rejected (§8.1); using several searchers to *find* more candidates, each mechanically verified, is sound. The Falsifier is the same idea applied to the selector itself: it is the "can this gate fail?" principle promoted from a control to an agent.

### 8.4 Token-efficiency funnel (`Rule 1` in numbers)

| Stage | Model calls | Coins |
|---|---|---|
| 500 inventory rows | **0** — classification is symbolic **[BUILT]** | 0 |
| Diff parse, repo index, closure, coupling | **0** — 67.2 ms total **[BUILT]** | 0 |
| Candidate pairs needing semantic judgement | only pairs with *no* structural edge but a representation-adjacency signal — **2 findings** in the demo repo **[BUILT]** | small |
| Escalations | only kernel-rejected proposals | small |
| Authoring | only UNCOVERED items | medium |

The funnel is the point: `500 rows → ~2 model-relevant candidates`. A naive "ask the model about each test" design would be 500 calls; this is closer to 2. That is roughly a **250×** reduction in the model-call surface *before* any caching, and it exists because the symbolic stratum runs first **[BUILT]**.

### 8.5 The context tax and the tool surface (C23)

Bob's own documentation states that tool definitions consume context, and that disabling unused tools *"reduces the amount of context consumed by tool definitions."* Tool schemas are re-sent every interaction, so **the tool surface is a recurring tax on the coin budget**. Therefore:

- **Minimise the tool count; maximise each tool's output value.** Prefer one tool that returns a complete, compact ledger over ten that return fragments.
- **Return digests, not dumps.** The symbolic stratum does the work; Bob receives a token-efficient document.
- **Coarse over fine**, because a narrow tool forces multi-turn iteration, which costs *more* coins than a wide one.

---

## 9. Every model I/O, exhaustively

For each role: the exact payload, the exact output, the precondition, the verifier, and the defined behaviour on every failure. Output is **grammar-constrained** (C-guarantee: structure cannot be malformed).

### 9.1 Common envelope

**Input envelope (all roles):**
```
run_id            : content hash of (repo HEAD, diff hash, inventory hash)
role              : "scout" | "cartographer" | "author" | "falsifier"
prompt_version    : pinned string, part of the cache key
budget            : max_output_tokens
untrusted         : [list of repo-derived strings]   # declared as DATA, not instructions
```
**Non-negotiable input rules:** every repo-derived string is passed as data inside a fenced block, never as an instruction; the model is told its output is a *proposal* that will be mechanically re-derived; no secrets, no environment, no network identifiers.

**Output envelope (all roles):**
```
{"claims":[{"claim_type":<enum>,"targets":[...],"citations":[{"path":..,"symbol":..,"line":..}],"confidence":"low|med|high"}]}
```
`confidence` is recorded and may influence *ordering* only. **It never influences acceptance** — that is `K`'s job alone. This is deliberate: it removes any incentive to talk the model into a verdict.

### 9.2 Role table

| | **1 Scout** | **2 Cartographer** | **3 Author** | **4 Falsifier** |
|---|---|---|---|---|
| `claim_type` | `link_exists(t,c)` | `intent(c, quote)` | `test(path, body)` | `missed(t, reason)` |
| Input payload | changed-symbol summary + candidate test rows (id, name, description, declared module) + the *format-producing/parsing* call sites | target entity source + its surrounding docstring/README/PR text + the manual test's natural-language steps | **the test class to extend + the intent artefact + the PRE-change implementation. The post-change body is withheld** (see 10.4) | the full ledger digest + the diff + the *unselected* rows only |
| Sufficiency precondition (0 coins) | candidate pair has ≥1 representation-adjacency signal | an intent artefact exists at the cited location | an UNCOVERED symbol exists with a resolvable module | ledger non-empty and ≥1 unselected row |
| Output | ≤5 claims, each with citation | ≤3 anchors, each with an exact quote | ≤1 test per uncovered symbol, as a patch to an existing test file | ≤5 missed tests with a *claimed* dependency path |
| Verifier `K` | citation exists ∧ (symbol referenced by `t`) ∨ (t covers c dynamically) | the quoted text is byte-present at the cited location ∧ the code no longer satisfies it | buildable ∧ passes B ∧ **citation-firing assertion fails at A** ∧ stable 5× ∧ sandboxed | citation exists ∧ the claimed path is re-derivable |
| On citation-invalid | reject | reject | reject | reject |
| On unverifiable-but-plausible | include as `UNCONFIRMED` (safe direction) | record as `CANDIDATE` for review | discard | record, do not act |
| Cache key | `H(repo,diff,inventory,prompt_v)` | `H(file_blob,prompt_v)` | `H(symbol,intent_blob,pre_body,prompt_v)` | `H(ledger_digest,prompt_v)` |
| Coin cost | lowest (many, small) | low volume, larger context | medium, bounded by calls | low volume |
| Idempotent | yes (cache) | yes | yes | yes |
| Parallelisable | yes (per pair, subagents) | yes (per file) | yes (per symbol, subagents) | no (needs the final ledger) |

### 9.3 Defined failure behaviour (no silent paths)

| Condition | Behaviour |
|---|---|
| Timeout / network error | retry once, then degrade to the deterministic baseline for that item; log `MODEL_UNAVAILABLE` |
| Rate limited / out of coins | stop escalating; artefact still complete, `model_coverage` field records the shortfall |
| Refusal | treat as empty proposal; log |
| Malformed output | impossible under constrained decoding; if it occurs, reject and log `SCHEMA_VIOLATION` (a signal the grammar is wrong) |
| Output contradicts another model | **not** resolved by voting — each claim is verified independently; survivors union |
| Claim verified but selects a test with no inventory row | keep as `unmapped_finding` **[BUILT]** — never dropped |
| All four keys unavailable | emit baseline; `model_layer: "disabled"`; Monotonicity (Lemma 2) still holds |

---

## 10. Verification: how we know the model gave us something we *need*

Three families of gate, ordered cheapest-first. Nothing reaches the artefact without clearing all that apply.

### 10.1 Input side — the sufficiency gate (C12)

Zero tokens. Before any call, assert the bundle contains what the question needs — e.g. for Scout: the producer's format expression *and* the consumer's parse site both exist in the bundle. If not: **do not call**. This is simultaneously an efficiency mechanism (no coins spent on unanswerable questions) and a correctness mechanism (the model is never asked to guess at absent evidence). An item that fails the gate becomes `UNKNOWN` → safe direction.

### 10.2 Claim side — obligations and the citation rule (C10, C11)

Every claim compiles to a predicate over the repository, and *the citation is the obligation*: a claim naming `report_worker.py:44` and `cache_service.write_cache_entry` is only admissible if those things exist there and the relation re-derives. Two properties follow: hallucinated citations are impossible to smuggle through, and line drift is *defined* behaviour (symbol match in the correct file → accept with a `line_drift` note; symbol mismatch → reject).

### 10.3 Behaviour side — the five-gate filtration for authored tests (C13–C17)

Applying the Assured-LLMSE discipline: discard anything that cannot be *guaranteed* to improve the suite, so hallucination cannot reach the artefact.

| Gate | Predicate | Source |
|---|---|---|
| G1 buildable | the test file imports and collects | TestGen-LLM filter 1 |
| G2 passes at B, **5×** | anti-flake; a test that does not pass on every one of five executions is flaky and discarded | TestGen-LLM filter 2; repeated-execution flaky detection |
| G3 **CDT** | **assertion fires at A** — the test fails before the change and passes after; the literature's *patch test* | Cleverest (Liu et al., 2025) |
| G4 **strength** | mutation analysis restricted to `Σ(D)`; weak-assertion tests discarded | test amplification uses mutation analysis as the selection criterion |
| G5 **spec anchor** *(conditional)* | when an intent artefact exists, the assertion must match it | doc→spec mining |

**Why G3 rather than coverage — an explicit rejection of TestGen-LLM's third filter.** Meta's third filter is *increases coverage*. But coverage is only weakly correlated with effectiveness (Inozemtseva & Holmes 2014), while **assertions** are strongly correlated (Zhang et al., FSE 2015) — and, decisively, 2026 work on LLM-generated tests reports that *"coverage- and mutation-based adequacy criteria are **poor indicators** of fault-detection capability"* because *"LLM-generated assertions frequently encode **actual program behavior rather than expected behavior, turning bugs into passing tests."*

That failure mode — **implementation-derived assertions** — is the single greatest hazard to the Author role, and it is why G3 requires an *assertion to fire*, not a *line to be covered*. G3 is strictly stronger than G3′ ("line covered"): a test that executes the changed code while asserting nothing passes G3′ and fails G3.

**G3 must be qualified (C14).** A test can fail at A because A lacks the symbol, not because the behaviour differs — that is a *collection* error, not a discriminating assertion. So G3 accepts only assertion-origin failures (assertion failure, or an explicit value mismatch), and rejects ImportError/AttributeError-at-collection. Without this qualification G3 would pass trivially-wrong tests, which is exactly the "all 400 pass, none catch the bug" failure the field warns about.

### 10.4 Information asymmetry — the defence against implementation-derived assertions **[SPEC]**

If the assertion author can read the post-change implementation, it can transcribe it, and the test becomes a behaviour snapshot that can never disagree with the code. Therefore the Author's context **withholds the post-change body** and provides instead (a) the test class to extend, (b) the intent artefact, and (c) the **pre-change** implementation. The rationale mirrors the finding that *extending an existing test class is easier and better than generating from scratch*, and it is testable: G3-yield and the rate of "assertion mirrors the new implementation" are both measurable with and without withholding.

### 10.5 Does the model layer earn its coins? (C21)

The question "how do you verify the model gave you something you need" has an empirical answer, not an architectural one:

```
marginal value = Δrecall measured against the oracle (§3.2)
                 ÷ coins spent
```
The ablation is trivial to run because Lemma 2 makes the baseline a valid configuration: **disable all four roles, run the oracle, measure recall; enable, measure again.** The difference is the model layer's contribution, in tests and in coins. Reported in the artefact, for every run. If it is zero, that is a finding, and it is published rather than hidden.

---

## 11. Incremental maintenance of `L` (making 2,500 affordable)

Recomputing `L` per commit does not scale, and the field says why it need not: *incremental static analyses provide results* ***"in time proportional to the size of a code change, not the entire code base"*** (IncA; Szabó et al., OOPSLA 2018/PLDI 2021). The catch stated in that literature is that reuse induces memory cost and demands that reuse be **sound** — a cached result is only valid while its justification holds.

So `L` is not recomputed; it is **maintained**:

```
L_new = ( L_old \ invalidated )  ∪  recompute(affected slice)
invalidated = { (t,c) ∈ L_old :
      content_hash(t) changed  ∨ content_hash(c) changed
   ∨ any transitive dependency of t or c changed
   ∨ the environment fingerprint changed }
```

**Soundness conditions on reuse, stated rather than assumed.** Content-hash invalidation is sound with respect to *source* changes. It is **not** sound with respect to: environment fingerprint (interpreter/OS/library versions), test-order effects and cross-test pollution, time/locale/random seed, and external fixtures. Those are declared assumptions, checked where cheap (fingerprint recorded) and disclosed where not. An unsound cache is worse than no cache: it reports yesterday's answer as today's with full confidence.

Cost model: first run `O(N·S)`; subsequent runs `O(change)`. This is what makes the 2,500-row case routine rather than heroic, and it is a prerequisite for the STALE/UNCOVERED verdicts bearing the *same* oracle as NEWLY_RELEVANT (one consistency requirement: **all four verdicts must be computed from the same `L`**, or they can contradict each other).

---

## 12. Red triage, and ordering

### 12.1 Three reasons a test goes red

Once the ledger exists, a failing test has exactly three explanations, and telling them apart is most of the developer's pain at 2,500 tests:

| Diagnosis | Signal | Action |
|---|---|---|
| **REGRESSION** | the test is VALID or NEWLY_RELEVANT, and its covered code intersects `Σ(D)` | fix the code |
| **STALE** | the test asserts `ρ(D)` — removed/redefined behaviour | fix the test; **do not bisect** |
| **FLAKY** | it fails while executing none of the changed code | quarantine; do not chase |

### 12.2 Improving DeFlaker's rule, with its own assumption made explicit

DeFlaker diagnoses flakiness *without re-running*: *"if a test fails but does not cover any changed code"* it is reported flaky (Bell et al., ICSE 2018, 326 citations). This is cheap and effective, and Google reports roughly one in seven tests having some flakiness.

But the rule's hidden premise is **`L* ⊆ L_cov`** — that coverage is a *complete* dependence proxy. §2 refutes exactly that. So the rule mislabels precisely the case this product exists for: a failure propagated through a wire format with no import edge. **v2's refinement:** a failure is exonerated as flaky **only if** coverage is silent **and** no `K`-verified link exists. When a verified semantic link exists, the failure is *not* written off — it is escalated as a candidate regression. This is a concrete, falsifiable improvement over a published tool, and the demo repo contains a live instance of the case it corrects.

### 12.3 Ordering (C25)

Selection reduces *how many* tests run; ordering reduces *how long until the first failure*. The objective is the classic one — maximise the **rate** of fault detection (Elbaum et al., 2002, 1,328 citations) — and the same study finds *fine-grained* techniques outperform coarse ones, which is why the coverage map is reused here.

```
priority = ( verdict == NEWLY_RELEVANT  ? tier 0    # highest surprise, highest signal
           : verdict == UNKNOWN         ? tier 1
           : covers Σ(D)                ? tier 2
           : tier 3 )
         then by descending dependency depth, then by duration ascending, then by test_id  # total order: determinism
```
`NEWLY_RELEVANT` first is the thesis made operational: if the selector's unique contribution is the test nobody would have run, run it *first*.

---

## 13. Edge cases and defined behaviours

Because the inputs are written by humans, malformed input is normal. The governing principle from v1 is kept and extended: **fail loud on uncertainty, degrade explicitly on irrelevance, never silently coerce.**

### 13.1 Input defects

| Case | Detection | Defined behaviour |
|---|---|---|
| missing/renamed inventory column | header check | `InventoryError` **[BUILT]** |
| duplicate `test_id` | loader | `InventoryError` **[BUILT]** |
| non-numeric `avg_runtime_ms` | loader | `InventoryError` — **was silently coerced to 0; fixed** **[BUILT]** |
| test's module does not exist | inventory ↔ index diff | **STALE (orphan)** — definitionally obsolete |
| test_id present but test absent from the suite | inventory ↔ collected diff | `MISSING`; excluded from the oracle denominator (could not distort recall) |
| inventory claims module X, test actually imports Y | declare/derive diff | record **link correction**; use the *derived* link, keep the declared one as evidence |
| malformed hunk header | parser | `ValueError` naming the line **[BUILT]** |
| unparseable Python | guarded `ast.parse` | skip module, record path, **select conservatively** **[BUILT]** |
| non-Python file in the diff | extension check | declared unsupported; never silently ignored |
| binary/undecodable file | decode guard | skip + record |
| empty diff | emptiness check | 0 selected, 0 model calls, exit 0 |
| docs-only diff | cosmetic classification | nothing selected — the reachability control **[BUILT]** |
| rename/move | rename detection | must not appear as delete+add, which would mark every test UNCOVERED |
| multi-line change inside one function | hunk line-walking | charged to the owning `def` **[BUILT]** |

### 13.2 Oracle defects

| Case | Defined behaviour |
|---|---|
| oracle collects fewer tests than the inventory | **hard failure (O1)** — the recall measurement is void |
| oracle run excluded marked tests by default | **hard failure** — this was the real defect; run with all markers |
| test is flaky and flips A↔B | excluded from ground truth; else the oracle measures noise |
| test fails at both A and B | not discriminating; excluded from recall, counted in `already_red` |
| test passes at both A and B | not discriminating; this is the *lower-bound* limitation, disclosed |

### 13.3 Model defects

| Case | Defined behaviour |
|---|---|
| citation to a path that does not exist | reject |
| citation to a file that exists, wrong line | accept if symbol resolves in that file, annotate `line_drift` |
| citation to the right line, wrong symbol | reject |
| contradicts the symbolic layer | symbolic wins; model claim recorded as rejected with reason |
| two models disagree | no vote (§8.1); verify each independently; survivors union |
| proposal selects nothing | recorded as `unmapped_finding`, never dropped **[BUILT pattern]** |
| prompt injection inside repo prose | contained by Lemma 2's corollary — cannot cause an unsound accept |
| memorised/leaked test | irrelevant: acceptance is by execution (G1–G4), not by novelty |
| authored test passes at A too | reject at G3 (does not pin the change) |
| authored test fails at A by import error | reject at G3 via C14 qualification |
| authored test writes files / opens sockets | sandbox: temp dir, no network, timeout |
| authored test depends on execution order | detected by G2's 5 executions in randomised order |

### 13.4 Cache and environment defects

| Case | Defined behaviour |
|---|---|
| cache hit after the repo changed | impossible: key includes content hashes |
| cache hit after the prompt changed | impossible: `prompt_version` in the key |
| environment fingerprint changed | invalidate dynamic-derived links only; keep structural |
| test pollution / order dependence | declared assumption; detected where possible by G2 |
| all keys rate-limited | baseline only; `model_coverage: 0.0`; artefact still valid |

---

## 14. Bob 2.0 mapping — Bob as the *core component* (an eligibility requirement)

The hackathon guide is explicit: *"to be eligible for judging, your solution must showcase IBM Bob IDE as a core component,"* and *"participants are required to upload all relevant Bob IDE task session summary screenshots to their code repository as evidence of Bob usage."* So the Bob integration is not decoration — it is the submission.

**14.1 The decisive alignment.** IBM's own documented design principle for Bob v2 is: *"anything that can be done deterministically, should be."* Workflows *"seamlessly blend deterministic scripting with AI reasoning"*: deterministic steps *"do not consume any AI tokens,"* and AI steps *"benefit significantly from a clean, highly focused context prepared by the preceding deterministic steps."* Sub-agents are for tasks that *"take this clearly defined input, produce this specific output, and ignore everything else."*

That is a description of §4's three strata and §8.2's cascade. v2 is not an external tool bolted onto Bob; it is an implementation of Bob's stated architecture for this problem domain.

**14.2 The workflow, in Bob's own step taxonomy.** IBM's Java Unit Testing Workflow has 8 steps, each labelled deterministic / AI / interactive. TestScope's ledger workflow maps almost one-to-one:

| # | Step | Kind | Coins |
|---|---|---|---|
| 1 | `testscope_ledger` — parse diff, index repo, build `L`, compute `ΔL`, emit verdicts | **deterministic** | 0 |
| 2 | `testscope_oracle` — dual-revision execution, compute `Δ(t)` | **deterministic** | 0 |
| 3 | Sufficiency gate + candidate selection | **deterministic** | 0 |
| 4 | Scout / Cartographer propose links and intent anchors (parallel subagents) | **AI** | ●●● |
| 5 | `testscope_verify` — kernel re-derives every obligation | **deterministic** | 0 |
| 6 | **Select Action** — interactive gate: developer confirms which STALE tests to repair, which UNCOVERED to author | **interactive** | 0 |
| 7 | Author synthesises tests (parallel subagents) | **AI** | ●● |
| 8 | `testscope_gate` — G1–G4 filtration, execution in sandbox | **deterministic** | 0 |
| 9 | Render the ledger + visual summary | **deterministic** | 0 |

Three of nine steps cost coins, and the expensive steps are fed by clean contexts produced by free ones — which is the whole point of the coin budget (C22).

**14.3 Repository artefacts (Bob-native, versioned, reviewable).**

| Path | Purpose |
|---|---|
| `.bob/mcp.json` | exposes the kernel; `alwaysAllow` on the pure read-only tools, approval required for anything writing |
| `.bob/custom_modes.yaml` | a `testscope` mode: role, when-to-use, tool permissions |
| `.bob/skills/testscope-ledger/SKILL.md` | the repeatable analyse-a-change workflow |
| `.bob/AGENTS.md` | persistent project context (`/init`) |
| `.bobrules/` | the cross-cutting rule: **no model verdict may reach the artefact without kernel verification** — the invariant is enforced by *configuration*, not by request |
| `.bobignore` | excludes sandbox/temp artefacts from Bob's context (also a context-tax saving) |

**14.4 The MCP tool surface.** Per the documented STDIO contract (`command`, `args`, `cwd`, `env`, `alwaysAllow`, `disabled`) and the documented context-tax property (C23), a deliberately **small and coarse** surface — four tools, not twenty:

| Tool | Reads | Writes | `alwaysAllow` | Returns |
|---|---|---|---|---|
| `testscope_ledger` | repo, diff, inventory | no | **yes** | the verdict ledger, compact |
| `testscope_verify` | repo | no | **yes** | obligation verdicts |
| `testscope_gate` | sandbox | temp only | **yes** | G1–G4 results |
| `testscope_repair` | — | test files | **no** (requires a click) | patch proposal |

Only pure functions are auto-approved; the single mutating tool requires explicit human approval. That is `K`'s boundary expressed in Bob's own permission model.

**14.5 Document understanding.** The guide names *document understanding* as a feature to leverage. This is exactly the Cartographer's substrate: the **manual QA inventory is a document**, the **docstrings/README/PR text are documents**, and the intended behaviour of a test case is written in *prose*. Recall the v1 defect where a coupling detector fired on a docstring **[BUILT, fixed]** — that prose was not a false positive; it was **the specification**, and the change violated it. v2 uses it as such.

**14.6 Coin budget plan.** 4 members × 40 = **160 Bobcoins**. Allocation: build ≈ 60, the recorded end-to-end session ≈ 40, reliability runs ≈ 30, reserve ≈ 30. Every retry of a step that could have been deterministic is a coin burned, so the deterministic-first ordering is also the plan's risk control.

---

## 15. Rejected alternatives

An architecture is defined by its refusals. Each costs something, and the cost is named.

| Alternative | Why rejected |
|---|---|
| Coverage-based selection (the industry default) | §2: unsound for exclusion. Provable inside this repo. |
| Majority voting across 4 models | Condorcet's premise (independence) fails for models with correlated errors; "three models agreed" is not evidence |
| LLM-as-judge verification | systematic position/verbosity/self-preference bias — not admissible as a verifier |
| LLMs for call-graph/type inference | static tools measurably outperform them; wastes coins (Rule 1) |
| Coverage as the acceptance criterion for generated tests | weak correlation with effectiveness; rewards implementation-derived assertions |
| Single-shot generation without execution feedback | execution feedback is measurably necessary for regression-test generation quality |
| Embedding-similarity link recovery | non-deterministic, uncalibrated threshold, cannot express *direction*, unexplainable in one sentence |
| History/co-change mining | needs long clean history; degrades exactly where the coupling has never broken; non-deterministic w.r.t. clone depth |
| Optimal test-suite minimization | set-cover-hard; the ledger's job is *disposition*, not provably-minimal reduction |
| Recomputing `L` per commit | does not scale; incremental maintenance is the published fix |
| A large fine-grained MCP tool surface | tool definitions are a per-interaction context tax (C23) |
| Whole-suite execution | the baseline being improved; its cost is the problem statement |
| Auth / DB / multi-tenant / CI wiring | not judged; no demonstrated capability gained |

---

## 16. Status: built versus specified

| Capability | Status |
|---|---|
| Diff parse, repo index, inventory load, coupling detectors, classification, report schema | **[BUILT]** — 15/15 gates, 203 tests |
| Inertness rule (Lever 2) and its causal control (47 → 122) | **[BUILT]** |
| Semantic coupling `K` and the hero catch (6 tests, incl. `T-0342`) | **[BUILT]** |
| Determinism: 8 runs, 1 digest; artifact reproducible from source | **[BUILT]** |
| Counterexample proving `R* ⊊ δ*` inside the repo | **[PROVEN]** — closure 11 modules/41 rows |
| Oracle blindness defect found and the rule (O1) derived | **[PROVEN]** — oracle returned empty before this |
| Link relation as the unifying object; five verdicts; ontology C1–C25 | **[SPEC]** |
| Coverage contexts for a measured test→code map | **[SPEC]** |
| Incremental `L` with sound invalidation | **[SPEC]** |
| MCP kernel, custom mode, skill, rules, `.bob` artefacts | **[SPEC]** |
| 4-role cascade with kernel escalation | **[SPEC]** |
| G1–G5 filtration, CDT, information asymmetry | **[SPEC]** |
| Red triage, ordering, rejection ledger, marginal-value ablation | **[SPEC]** |

**Still un-fabricable, as in v1:** the live Bob session, its session-summary screenshots, and the video. `session_screenshots/README.md` specifies exactly what to capture; the workflow above specifies the steps to capture.

---

## 17. Plan to the deadline

1. **Bob-native scaffolding** — `.bob/mcp.json`, custom mode, skill, rules; wrap v1's core as the four MCP tools. *Highest leverage: it converts an existing, verified engine into Bob-native capability and satisfies the eligibility requirement.*
2. **Oracle** — dual-revision execution with O1 asserted; produces the recall baseline. *Highest intellectual return: it turns every claim into a measurement.*
3. **`L` v0 + five verdicts** — structural + representation links, STALE from `ρ(D)`, UNCOVERED from `Σ(D)`.
4. **Cartographer** — spec mining from docstrings/README/inventory prose; citation-verified.
5. **Author + G1–G5** on one uncovered symbol end to end, then subagents in parallel.
6. **Red triage + ordering.**
7. **Live Bob session** — record, screenshot, narrate the subagent steps.
8. **Ablation** — model layer off vs on, measured against the oracle; report marginal value.

Each step ends in a gate that can fail, in keeping with the rule that carried v1: *a claim without a falsifier is a slogan.*

---

*Reproduce v1: `./verify.sh` · Re-derive v1's numbers: `python3 bob_session/run_analysis.py` · v1 record: `ARCHITECTURE.md`*
