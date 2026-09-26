# TestScope — the 9-step workflow (Person B, deliverable B2)

Owner: Person B. Consumed by `.bob/custom_modes.yaml`, `.bob/skills/testscope-ledger/SKILL.md`,
`.bobrules/`, and the cascade in `bob_session/roles/cascade.py`.

The design principle is IBM's and it is not decoration: workflows blend deterministic
scripting with AI reasoning; deterministic steps consume no model tokens; AI steps
benefit from a clean, highly focused context prepared by the preceding deterministic
steps; and **anything that can be done deterministically, should be**. Sub-agents are
for tasks that "take this clearly defined input, produce this specific output, and
ignore everything else".

In this workflow the deterministic steps decide everything decidable, the AI steps
propose only what the symbolic layer cannot, and the kernel (`testscope_verify` /
`testscope_gate`) is the only door into the artefact.

## The table

| # | Step | Kind | Cost | Tool, role file, or gate | Context bundle |
|---|------|------|------|--------------------------|----------------|
| 1 | Ledger: parse diff, index repo, build `L`, compute `ΔL`, emit verdicts | DETERMINISTIC | 0 coins | MCP tool `testscope_ledger` (CLI: `python3 bob_session/run_analysis.py`) | — |
| 2 | Oracle: dual-revision execution, compute `Δ(t)` under all markers | DETERMINISTIC | 0 coins | MCP tool `testscope_oracle` | — |
| 3 | Context assembly + sufficiency gate | DETERMINISTIC | 0 coins | `bob_session/roles/context.py` | one candidate unit per question |
| 4 | Scout / Cartographer propose links and intent anchors (parallel subagents) | **AI** | ●●● | `bob_session/roles/scout.md`, `bob_session/roles/cartographer.md` | scout bundle, then cartographer bundle (below) |
| 5 | Kernel: re-derive every obligation | DETERMINISTIC | 0 coins | MCP tool `testscope_verify` | the claim batch |
| 6 | **Select Action**: developer confirms what to repair and what to author | **INTERACTIVE** | 0 coins | the developer (human gate) | the ledger, the uncovered worklist, the rejection ledger |
| 7 | Author synthesises one test per uncovered symbol (parallel subagents) | **AI** | ●● | `bob_session/roles/author.md` | author bundle (below) |
| 8 | Filtration: G1..G5, execution in a sandbox | DETERMINISTIC | 0 coins | MCP tool `testscope_gate` — **requires a human click** | the patch + the symbol |
| 9 | Render the ledger + visual summary | DETERMINISTIC | 0 coins | the artefact `bob_session/testscope_report.json` (dashboard renders it) | — |

Three of nine steps cost anything, and each expensive step is fed by a free one.
Run steps 1–3 **before** asking any model anything: the baseline and its evidence
then exist independently of the AI.

**After step 9 (never before):** the falsifier runs LAST and ALONE over the unselected
rows — `bob_session/roles/falsifier.md`, wired by `cascade.run_falsifier`. It is not a
tenth workflow step; it is the adversarial pass over a finished ledger.

## AI step bundles — the exact fields

The sufficiency gate in `bob_session/roles/context.py` refuses to render a prompt when
a required field is empty, so a model is never asked to guess at absent evidence.

### Step 4a — scout bundle (`context.assemble_scout`)

| Field | Required | Purpose |
|---|---|---|
| `changed_symbol` | yes | the symbol the diff modified |
| `producer_call_site` | yes | where a value is produced (`path:line`) |
| `producer_format_expr` | yes | the format-producing expression the change touched |
| `consumer_call_site` | yes | where the value is consumed (`path:line`) |
| `consumer_parse_site` | yes | the parsing expression at the consumer |
| `test_row` | yes | `test_id`, `test_name`, `module`, `description` |
| `diff_hunks` | yes | the verbatim diff |

### Step 4b — cartographer bundle (`context.assemble_cartographer`)

| Field | Required | Purpose |
|---|---|---|
| `changed_symbol_body` | yes | the changed symbol, signature and body |
| `intent_artefacts` | yes | docstrings / comments / README / PR text, each with `path`, `line`, `kind`, `text` |
| `diff_hunks` | yes | the verbatim diff |

No intent artefact in the repository ⇒ no call; the unit is UNKNOWN and takes the safe
direction. Do not invent a specification to have something to ask about.

### Step 7 — author bundle (`context.assemble_author`)

| Field | Required | Purpose |
|---|---|---|
| `symbol`, `symbol_signature` | yes | the uncovered symbol |
| `test_class_file`, `test_class_source` | yes | the EXISTING test file/class to extend |
| `pre_change_body` | yes | the PREVIOUS implementation (the author must fail against it) |
| `intent_artefact` | optional | absent ⇒ G5 is `null` and the claim says *pinned*, not *correct* |
| `post_change_body` | **WITHHELD** | never copied into the bundle; the content is not passed |

The withholding is deliberate: an author that can read the new code transcribes it and
the test becomes a snapshot that can never disagree with the code. A unit test asserts
the withheld body never reaches the rendered prompt.

### Falsifier bundle (`context.assemble_falsifier`)

`final_ledger` (required), `diff_hunks` (required), `unselected_rows` (required, ≥ 1),
`selected_ids`, plus `dropped_selected_rows` as a defensive audit. The ledger must be
final and no selected row may be supplied — both are refused in code.

## Deterministic steps and the tool they call

| Step | Tool | Notes |
|---|---|---|
| 1 | `testscope_ledger` | pure; never imports or executes the target repository (`ast.parse` only) |
| 2 | `testscope_oracle` | temp working copy; runs with **all markers** (`-m ""`); completeness is computed, not asserted — `collected >= inventory_total`, else the measurement is void |
| 3 | `bob_session/roles/context.py` | pure; zero model calls; fills the role-file placeholders at run time |
| 5 | `testscope_verify` | the kernel: every claim re-derived from its citations |
| 8 | `testscope_gate` | G1 buildable, G2 passes 5× (randomised order), G3 assertion fires at A (assertion-origin only), G4 mutation strength on the changed lines, G5 spec-anchored when an intent artefact exists |
| 9 | `testscope_ledger` output + dashboard | byte-identical across runs |

`testscope_gate` is the only tool that touches test files, and it is **not**
auto-approved: the human click is the trust boundary in Bob's permission model.

## Step 6 — the Select Action gate, verbatim

Bob asks the developer:

> I have run the deterministic engine, the oracle, the sufficiency gate, the
> deterministic verifier, and only then the subagents. Here is what the ledger says:
>
> * **STALE** — tests that assert behaviour this change removed: they should be
>   repaired or deleted, and their red is noise.
> * **UNCOVERED** — changed behaviour with no test at all: candidates for authoring.
> * **NEWLY_RELEVANT** — verified hidden coupling: they run first.
> * **REJECTED** — claims the kernel refused, each with its gate and reason in the
>   rejection ledger.
>
> Which STALE tests should I repair, and which UNCOVERED behaviours should I author?
>
> Nothing is written to your suite until you answer, and every authored test must
> clear G1..G5 through `testscope_gate`, which requires your click.

This is not ceremony. It is the point where strategy becomes execution: without it we
would be an autonomous agent editing someone's test suite on our own judgement. With
it, we are an advisor whose every claim was already mechanically checked.

## Where escalation and the safe direction are applied

The cascade (`bob_session/roles/cascade.py`) escalates on a **mechanical verification
failure**, never on a confidence number:

```
SUFFICIENCY GATE -> SCOUT -> testscope_verify -> accepted (stop)
                                   | rejected
                                   v
                  CARTOGRAPHER -> testscope_verify -> accepted
                                   | rejected
                                   v
                  UNCONFIRMED + SAFE DIRECTION + rejection ledger
```

* at most **two model tiers per unit**; there is no third ask;
* the safe direction (include the test, mark it) is applied in exactly four places:
  sufficiency-gate failure, tier-cap exhaustion, kernel "unconfirmed", and — for the
  selection as a whole — the invariant `selection = baseline ∪ verified additions`;
* a kernel outage accepts **nothing** and leaves the baseline intact;
* no claim reaches an outcome without a `testscope_verify` call, asserted in code.

## Recording order and evidence

1. Run steps 1–3 first and show the `[PASS]` lines from `./verify.sh`: the evidence
   exists before any model speaks.
2. Then run the AI steps and capture, in order: the workflow mid-run; a subagent in its
   own context window; **the kernel rejecting a claim, with its reason**; the Select
   Action gate with the developer choosing; the G3 result; the final artefact and
   dashboard; the Bob task session summary.
3. Name every screenshot after what it proves
   (see `bob_session/session_screenshots/README.md`).

## Machine-readable manifest

`bob_session/roles/acceptance_check.py` parses this block; keep it in step.

```json
{
  "prompt_version": "v2.0.0",
  "steps": [
    {"step": 1, "id": "testscope_ledger", "kind": "DETERMINISTIC", "coins": "0", "tool": "testscope_ledger"},
    {"step": 2, "id": "testscope_oracle", "kind": "DETERMINISTIC", "coins": "0", "tool": "testscope_oracle"},
    {"step": 3, "id": "sufficiency_gate", "kind": "DETERMINISTIC", "coins": "0", "tool": "bob_session/roles/context.py"},
    {"step": 4, "id": "scout_cartographer", "kind": "AI", "coins": "●●●", "role_prompt": ["bob_session/roles/scout.md", "bob_session/roles/cartographer.md"]},
    {"step": 5, "id": "testscope_verify", "kind": "DETERMINISTIC", "coins": "0", "tool": "testscope_verify"},
    {"step": 6, "id": "select_action", "kind": "INTERACTIVE", "coins": "0", "gate": "developer"},
    {"step": 7, "id": "author", "kind": "AI", "coins": "●●", "role_prompt": "bob_session/roles/author.md"},
    {"step": 8, "id": "testscope_gate", "kind": "DETERMINISTIC", "coins": "0", "tool": "testscope_gate", "requires_human_click": true},
    {"step": 9, "id": "render_artefact", "kind": "DETERMINISTIC", "coins": "0", "tool": "bob_session/testscope_report.json"}
  ],
  "post_steps": [
    {"id": "falsifier", "kind": "AI", "coins": "●", "role_prompt": "bob_session/roles/falsifier.md", "order": "LAST, alone, over the unselected rows only"}
  ]
}
```

## Trust-boundary audit — anything that could let an unverified claim through

Person B's close-out report (prompt B8). Each item names the residual risk honestly.

| Item | Status | Residual risk |
|---|---|---|
| Two doors only: `cascade.run_cascade` sets `accepted` from `_apply_verdict`; `run_author` sets it from the gate's `accepted` | checked | none: both are after a kernel/gate call, and `_apply_verdict` refuses any claim not in the submitted batch |
| `confidence` never read for acceptance | checked (`grep -n confidence bob_session/roles/*.py` shows only the enum validation in `envelope.py`) | none |
| Rejected claims always reach the rejection ledger with their gate | checked | a kernel that returns a rejection without a `gate` is recorded as `unspecified`, never silently dropped |
| `parse_claims` accepts an already-parsed envelope dict as well as raw text | by design (the adapter seam) | a careless adapter could pass a hand-built dict; it still cannot be accepted without a verify call, so this is a provenance gap, not a soundness gap |
| `kernel_client` trusts Person A's server stdout | transport boundary | as with any client: the layer proves what it does with a verdict, not what the server does internally |
| Tests prove the wiring, not the live model identity | structural limit | the recorded session is the evidence that a real model was behind `propose`; that is why the session is a deliverable and not decoration |
| Live MCP server, demo repository and Bob permissions (`.bob/mcp.json`) | outside Person B's ownership | `testscope_gate` must not be auto-approved; the description and policy are in `bob_session/roles/mcp_tool_descriptions.md` for Person A to apply |

Run the layer's own check before every session:

```bash
python3 bob_session/roles/acceptance_check.py      # PASS/FAIL for the code layer, PENDING for live items
python3 -m unittest discover -s bob_session/roles/tests -t .   # the layer's own tests
```

## Anti-slop rules that govern this workflow

1. Never ask a model a question the symbolic layer can answer exactly.
2. Never let a model verdict into an artefact unverified — the kernel is the only door.
3. Never use majority voting for correctness; diversity is for discovery only.
4. Never use a model as the verifier.
5. Never accept a generated test because it increases coverage; G3 requires an
   assertion to fire before the change.
6. State what is built and what is specified.
7. Every claim in a document must be reproducible by running one command.
