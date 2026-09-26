# MCP tool descriptions for `.bob/mcp.json` (coordination note for Person A)

Person A owns `.bob/mcp.json`. Bob selects tools by reading their descriptions, so the
descriptions below are written to Bob's documented standard: **what it does, its
purpose, its prerequisites, and the expected outcome** — plus the required sentence
"This tool is deterministic; it decides exactly and costs no model tokens."

Copy them verbatim into the server configuration. Every description says what the tool
*does not* do as well, because that is what keeps a model from asking it for the wrong
thing.

---

## `testscope_ledger`

> Computes the change-impact ledger for a code change: parses the diff, indexes the
> repository, builds the test-to-code link relation, computes the link delta, and
> emits the artefact `bob_session/testscope_report.json` (classification, ledger,
> uncovered worklist, measurement, triage, priority order).
>
> Purpose: decide everything that is exactly decidable, so no model is asked about
> it. Prerequisites: paths to the repository root, the diff bundle, and the test
> inventory CSV. Expected outcome: the full artefact as JSON on stdout; no writes to
> the repository; it never imports or executes the target repository (`ast.parse`
> only).
>
> This tool is deterministic; it decides exactly and costs no model tokens.

## `testscope_verify`

> Re-derives proposed claims against the repository. Each claim carries citations;
> the citations are obligations. The tool re-opens every cited file, resolves the
> cited symbol, and accepts, rejects, or marks the claim unconfirmed. Rejected claims
> carry the gate that rejected them (`citation_invalid`, `symbol_mismatch`,
> `contradicts_symbolic`).
>
> Purpose: THE trust boundary. Nothing a model proposes becomes a verdict without
> this call. Prerequisites: a list of claim envelopes and the repository path.
> Expected outcome: `{"accepted": [...], "rejected": [...], "unconfirmed": [...]}`.
>
> This tool is deterministic; it decides exactly and costs no model tokens.

## `testscope_oracle`

> Produces ground truth by running the test suite at both revisions in a temporary
> working copy and diffing the outcomes: `Δ(t) = [outcome_A(t) ≠ outcome_B(t)]`.
> Runs with ALL markers (`-m ""`) and asserts collection completeness; an incomplete
> collection makes the measurement void rather than optimistic.
>
> Purpose: measure recall against executed behaviour, never against an assumption.
> Prerequisites: repository path, revision A sha, revision B sha, and the run command.
> Expected outcome: `{"collected", "inventory_total", "complete", "changed",
> "outcome"}`; the input repository is never mutated.
>
> This tool is deterministic; it decides exactly and costs no model tokens.

## `testscope_gate`

> Adjudicates one authored test by execution in a sandbox: G1 buildable, G2 passes
> 5x in randomised order (anti-flake), G3 the assertion FIRES against the previous
> revision (a collection or import error does not satisfy G3), G4 mutation strength
> restricted to the changed lines, G5 specification anchoring when an intent artefact
> exists.
>
> Purpose: nothing authored enters the suite unverified. Prerequisites: the
> repository path, the test patch (unified diff), and the symbol it pins. Expected
> outcome: the per-gate booleans and `accepted`. Writes only inside a sandbox temp
> directory; no network; timeout 120s.
>
> **Approval: FALSE.** This is the only tool that touches test files. Auto-approving
> it would remove the trust boundary — in Bob's permission model the human click IS
> the boundary.

---

## Configuration policy (for `.bob/mcp.json`)

| Tool | `alwaysAllow` |
|---|---|
| `testscope_ledger` | `true` |
| `testscope_oracle` | `true` |
| `testscope_verify` | `true` |
| `testscope_gate` | **`false`** |

Server: `{"command": "python3", "args": ["bob_session/mcp_server.py"], "cwd": "<repo root>"}`,
STDIO transport, one JSON request on stdin per call. The client used by the cognitive
layer is `bob_session/roles/kernel_client.py` and sends
`{"tool": "<name>", "input": {...}}`; if the server frames requests differently,
change `_frame` in that one file — nothing else in the layer assumes a wire format.

## Verify the seam before calling the integration ready

```bash
python3 bob_session/roles/kernel_conformance.py --reference   # the contract, no server needed
python3 bob_session/roles/kernel_conformance.py               # against bob_session/mcp_server.py
```

`HANDOFF_PERSON_A.md` in this directory is the full contract: payloads, response keys,
the echo rule that voids a run, and what the demo repository must contain for the
workflow to have anything to do.
