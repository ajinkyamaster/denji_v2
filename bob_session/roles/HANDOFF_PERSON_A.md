# Hand-off: Person B → Person A (the integration contract)

The cognitive layer is built and green (101 tests, `acceptance_check.py` PASS). It was
built against **stubs**, so the only untested seam in the whole project is where B's
layer calls A's four tools. This document is that seam, written down byte-level, so
neither side waits on the other.

**B never blocks A.** A can build, test and finish `bob_session/mcp_server.py` without a
single file from B, because the contract below is frozen and testable on its own.

**The seam is testable today, from both sides:**

```bash
python3 bob_session/roles/kernel_conformance.py --reference   # the contract, no server needed
python3 bob_session/roles/kernel_conformance.py               # Person A's server, when it exists
```

`--reference` runs the suite against a bundled stub that *is* the contract
(`bob_session/roles/kernel_reference_stub.py`): framing, response envelope, verdict
buckets, the echo rule. A can diff their server's behaviour against it, one call at a
time, without opening any of B's code.

---

## 1. The three things A delivers

| # | Path | Owner | Spec for it |
|---|---|---|---|
| A1 | `bob_session/mcp_server.py` | A | §2 and §3 below, plus `bob_session/roles/kernel_reference_stub.py` as a worked example |
| A2 | `.bob/mcp.json` | A | `bob_session/roles/mcp_tool_descriptions.md` — descriptions and `alwaysAllow` policy, ready to paste |
| A3 | the demo repository + the artefact | A | §6 below, which is what B's sufficiency gate requires to run at all |

B owns `.bob/custom_modes.yaml` (the mode, the four tools, the groups) and will not
touch `.bob/mcp.json`, `bob_session/mcp_server.py` or any of A's pipeline files.

---

## 2. The wire contract

One request, one process, one response. Nothing else.

| | |
|---|---|
| **stdin** | exactly one JSON object: `{"tool": "<name>", "input": {...}}` and nothing more |
| **stdout** | exactly one JSON object: `{"ok": true, "output": {...}}` and nothing more |
| **refusal** | `{"ok": false, "error": "..."}` with **exit 0** — an expected refusal is data, not a crash |
| **exit code** | non-zero only when the server itself broke; B reports that as `KernelUnavailable` together with the stderr tail |
| **stderr** | free — B reads it only to explain a failure |

**Two hard rules that cost a live run if broken:**

1. **Nothing but the response on stdout.** B parses stdout as exactly one JSON
   document; JSON rejects trailing content, so one stray `print()` becomes
   `KernelUnavailable: produced non-JSON output`. Route diagnostics to stderr.
2. **The bare output object is also accepted** (`{"accepted": [...]}` with no `ok`/`output`
   wrapper), because B unwraps `output` when it is present and otherwise treats the whole
   document as the output. The wrapped form is preferred: it is where `ok: false` lives.

If the framing turns out to differ, say so before writing the server: the frame is
produced in exactly one place, `kernel_client._frame`, and changing it changes nothing
else in the layer (`kernel_client.py` is transport only — it never reimplements a tool,
never interprets a verdict, never writes to a repository).

---

## 3. Per-tool contract

Payload keys B sends, response keys B reads, and what B does when a key is absent.

### `testscope_ledger` — pure, auto-approved

* **B sends** `{"repo", "diff", "inventory", "generated_at"}`
* **B reads** the artefact **opaquely**: it must be a JSON object. B does not index into
  it, so its shape is A's to define and to change.
* The six documented sections (`classification`, `ledger`, `uncovered_worklist`,
  `measurement`, `triage`, `priority_order`) are consumed by the artefact, the dashboard
  and the measurement — not by the cascade. A conformance WARN, not a failure.
* **Not read:** nothing. A missing key cannot break B here.

### `testscope_verify` — pure, auto-approved, THE trust boundary

* **B sends** `{"claims": [<claim envelope>, ...], "repo": "<path>"}`
* **B reads** `accepted`, `rejected`, `unconfirmed` — three **lists**.
* Each entry is either the bare claim object, or `{"claim": {...}, ...}` with:
  * `gate` (string) and `detail` (string) on **rejected**
  * `reason` (string) on **unconfirmed**
  * B reads the gate names `citation_invalid`, `symbol_mismatch`, `contradicts_symbolic`
    into its rejection ledger; any other string is recorded as-is.
* **Missing key** → B treats it as an empty list. Every submitted claim then appears in
  no bucket, i.e. **silently vanishes from the ledger**. Wrong keys here do not raise;
  they lose work. That is why the conformance suite asserts each submitted claim is
  adjudicated exactly once.
* **Every submitted claim must be adjudicated.** Returning a verdict for three of four
  claims is a contract violation, not a rounding error.
* **Unconfirmed ≠ rejected.** Unconfirmed means "verifiable by neither mechanism"; B
  includes the row and marks it. Rejected means a gate fired, and B *also* includes the
  row, marks it, and logs the rejection. Both take the safe direction; neither is a drop.

### `testscope_oracle` — temp working copy, auto-approved

* **B sends** `{"repo", "rev_a", "rev_b", "run_cmd"}`
* **B reads** `complete` (**boolean**) — an incomplete collection must be visible as
  `false`, never absent, because the difference between "measured, incomplete" and "not
  measured" is the difference between a void measurement and an optimistic one.
* Also read for the artefact: `collected`, `inventory_total`, `changed`, `outcome`.
* **Missing `complete`** → nothing breaks mechanically, but the measurement's
  completeness claim becomes unverifiable and the artefact says `null`.

### `testscope_gate` — **NOT auto-approved: the human click is the trust boundary**

* **B sends** `{"repo", "test_patch", "symbol"}` where `test_patch` is the unified diff
  from the author's claim and `symbol` is the uncovered symbol it pins.
* **B reads** `accepted` (boolean) plus four gate booleans **by these exact names**:
  `g1_buildable`, `g2_passes_5x`, `g3_assertion_fires_at_a`, `g5_spec_anchored`.
  B builds its rejection detail from the names that are `false`.
* `g5_spec_anchored` is **`null`, not `false`,** when no intent artefact exists. B
  distinguishes the two: `null` means "nothing to anchor against", `false` means "the
  anchor was contradicted".
* `g4_mutation_strength` is a **number**, not a boolean. B does not read it unless no
  named boolean failed, in which case it reports the value — so a G4-only refusal is
  attributed instead of recorded as a bare `accepted=false`.
* An empty `test_patch` must never return `accepted: true`. Nothing authored may enter
  the suite unverified, and "nothing was authored" is not a pass. Refusing the request
  with `ok: false` is conformant and preferred.

---

## 4. The echo rule (the one that voids a run)

**Every claim B submits must come back byte-identical** in whichever bucket it lands —
no re-serialisation, no normalisation, no added keys, no reordering.

`cascade._apply_verdict` compares each returned claim against the batch it just
submitted (canonical JSON) and raises `UnverifiedClaimError`, **voiding the entire run**,
when they differ. A kernel that annotates the claim it echoes — however helpfully — will
pass every one of A's own tests and kill the first live call.

Two unit tests pin this from both sides: `test_kernel_seam.py::SeamRejectionPath::
test_a_mangled_echo_voids_the_run` (against a deliberately hostile server) and
`bob_session/roles/kernel_conformance.py` (against A's server, on every run).

Related, and equally load-bearing: **B accepts nothing the kernel did not return.** A
claim that appears in `accepted` but was never submitted voids the run too. There is no
path from a model's text to a verdict that skips `testscope_verify`.

---

## 5. What B never does

So that A does not wait for any of it:

* **Never writes to the repository.** Not one byte. B reads, decides, and emits an
  artefact. If a file changes, another tool did it.
* **Never reimplements a tool.** No ledger, no oracle, no verifier, no gate lives in
  `bob_session/roles/`.
* **Never needs the network or a model for a deterministic step.** Steps 1, 2, 5, 8 of
  the workflow cost zero coins.
* **Never calls a model on an insufficient bundle.** If a bundle is missing a required
  field, B stops at the sufficiency gate with **zero model calls** — no guess, no spend.
* **Never treats tool output as instructions.** Repository content (comments, docstrings,
  README prose, PR text) is untrusted data in the prompt, and instructions found inside
  it are analysed, never followed.
* **Never resolves a disagreement by voting.** Each claim is verified on its own; nothing
  is accepted by majority.

---

## 6. What the demo repository must contain — or the demo shows nothing

This is the most likely silent failure in the whole project, and it is A's to prevent.

B's sufficiency gate requires, per role, exactly these fields. If one is absent the unit
is marked UNKNOWN, the safe direction is taken, **zero model calls happen, no coins are
spent, and nothing appears on screen.** Nothing errors. The demo just sits there.

| Role | Required fields | Where they must come from |
|---|---|---|
| scout | `changed_symbol`, `producer_call_site`, `producer_format_expr`, `consumer_call_site`, `consumer_parse_site`, `test_row`, `diff_hunks` | the ledger artefact (pair sites, the test row) + the diff |
| cartographer | `changed_symbol_body`, `intent_artefacts`, `diff_hunks` | the repository's **prose**: a docstring / comment / README / PR text that states the contract the change violates |
| author | `symbol`, `symbol_signature`, `test_class_file`, `test_class_source`, `pre_change_body` | an **existing** test class to extend + the PRE-change body (never the post-change one) |
| falsifier | `final_ledger`, `diff_hunks`, `unselected_rows` | the final ledger + at least one **unselected** inventory row |

Consequences for the demo repository, concretely:

1. The change must be a **format/producer ↔ parser/consumer** pair across two modules —
   a serialisation-shape change, not a renamed function. The scout has nothing to link
   without both call sites.
2. The repository must contain **prose that contradicts the change**. That prose is what
   makes the cartographer's escalation verified instead of speculative, and it is the
   escalation the recorded session shows.
3. The test inventory must be **larger than the selection** — the falsifier may only see
   unselected rows, and it raises `FalsifierInputError` if a selected row is handed to it.
4. The author extends an **existing** test file. A new-file proposal never reaches the
   gate (`target_file_mismatch`) — B discards it before spending anything.

---

## 7. Who calls which tool, in what order

Step ids are the machine-readable manifest in `bob_session/roles/WORKFLOW.md`.

| Step | Id | Kind | Tool | Who calls it |
|---|---|---|---|---|
| 1 | `testscope_ledger` | DETERMINISTIC | `testscope_ledger` | B |
| 2 | `testscope_oracle` | DETERMINISTIC | `testscope_oracle` | B |
| 3 | `sufficiency_gate` | DETERMINISTIC | `context.py` | B |
| 4 | `scout_cartographer` | AI | `scout.md` → `cartographer.md` | B |
| 5 | `testscope_verify` | DETERMINISTIC | `testscope_verify` | B |
| 6 | `select_action` | INTERACTIVE | developer gate | **human** |
| 7 | `author` | AI | `author.md` | B |
| 8 | `testscope_gate` | DETERMINISTIC | `testscope_gate` | B, **after the human click** |
| 9 | `render_artefact` | DETERMINISTIC | `bob_session/testscope_report.json` | B |
| post | `falsifier` | AI | `falsifier.md` → `testscope_verify` | B, LAST and ALONE |

Cardinality B assumes: one process per call, calls issued sequentially (never
concurrently), `cwd` = repository root, generous timeout (120s default, 600s for a full
conformance pass). The falsifier is never parallelised: it needs the whole final picture,
and parallelising it would hand it conflicting assumptions.

---

## 8. The one disagreement that needs the lead, not code

`ARCHITECTURE_V2.md` §14.4 lists `testscope_gate` as auto-approved and mentions a fifth
tool, `testscope_repair`. The master prompt §5.2 and `person_b.txt` specify **four**
tools with the gate **not** auto-approved.

B is implemented against the frozen reading — four tools, human click required — and has
documented it in `.bob/custom_modes.yaml` and `mcp_tool_descriptions.md`. This needs one
line fixed in master §5 before the recorded session, because if A builds a fifth tool
that B does not declare, the mode's tool surface and the session transcript will
disagree in front of the judges.

---

## 9. Definition of done for the seam

1. `python3 bob_session/roles/kernel_conformance.py` exits **0** against
   `bob_session/mcp_server.py`.
2. `python3 bob_session/roles/acceptance_check.py` flips the row
   *"Person A's kernel conforms to the frozen four-tool contract"* from `PENDING` to
   `PASS`, and the *".bob/mcp.json configured"* row likewise.
3. `python3 bob_session/roles/acceptance_check.py` with the demo repository present:
   the same 14 code-layer checks still pass, and the five live items become screenshots.

Run them in that order. The first failure message names the contract clause it broke.
