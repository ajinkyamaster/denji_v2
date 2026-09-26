# AGENTS.md — TestScope

Persistent project context for Bob. Owner: **Person B** (agent engineer). Keep it
accurate to the repository; every figure here must be reproducible by one command.

## What this repository is

TestScope is a change-impact ledger for test suites. Given a code change, a test
inventory and the repository, it answers four questions about every test — not one:

* which tests **must run** (selection),
* which are now **STALE** (they assert behaviour the change removed),
* which became **NEWLY RELEVANT** (hidden behavioural coupling no import graph shows),
* what has **NO test at all** (uncovered behaviour → author a test).

> TestScope computes what a change did to your test suite, not just which tests to
> run — and every claim it makes is mechanically re-checked against your repository.

The reduction percentage is the demo. The product is the two questions no existing
tool answers: which of my tests are now lying to me, and which of my new behaviours
has no test. Coverage is a **one-sided oracle** — sound for inclusion, unsound for
exclusion — so exclusions must rest on invariance, never on absence of coverage.

## Workload owners (do not edit another owner's files)

| Person | Owns |
|---|---|
| A | `bob_session/pipeline/**`, `bob_session/oracle.py`, `bob_session/mcp_server.py`, `bob_session/verify.py`, `bob_session/tests/**`, `.bob/mcp.json` |
| B | `.bob/**` (except `mcp.json`), `.bobrules/**`, `.bobignore`, `AGENTS.md`, `bob_session/roles/**`, `bob_session/coins.md`, `bob_session/session_screenshots/**` |
| C | `dashboard/**` |
| D | `bob_session/measure.py`, `bob_session/reliability_check.py`, `submissions/**`, `README.md`, `VERIFICATION.md` |

A cross-owner change requires editing the frozen interface in the team's master
prompt first, then notifying the other owners, then changing code. Never fork a
contract.

## Frozen interfaces (consume, do not redefine)

**The artefact** — `bob_session/testscope_report.json`. v1 keys (`run_metadata`,
`classification`, `summary`) keep their exact shape; v2 adds `ledger`, `uncovered`,
`claims`, `rejection_ledger`, `measurement`, `triage`, `priority_order`.
Invariants: every inventory row in exactly one classification bucket; same inputs ⇒
byte-identical output; ledger counts agree with classification; `measurement.oracle.complete`
is computed, not asserted; every accepted claim has a matching ledger verdict; the
rejection ledger length equals `claims.rejected`.

**The four MCP tools** (Person A's server, `.bob/mcp.json`):

| Tool | Reads | Writes | Approval | Returns |
|---|---|---|---|---|
| `testscope_ledger` | repo, diff, inventory | no | auto | the full artefact |
| `testscope_oracle` | temp working copy | no | auto | dual-revision outcomes |
| `testscope_verify` | repo | no | auto | accepted / rejected / unconfirmed |
| `testscope_gate` | sandbox | temp only | **HUMAN CLICK** | G1..G5 |

None of them imports or executes the target repository: they `ast.parse` it.

**The claim envelope** — the only language models may speak to the kernel:
`{"claim_type","role","targets","citations","confidence","rationale"}`. Citations
are obligations; the kernel re-derives them. `confidence` orders results and never
affects acceptance. A missing path rejects; a drifted line with the right symbol
accepts with `line_drift`; a wrong symbol rejects. Unconfirmed ⇒ safe direction
(include the test, mark it).

## The workflow

`bob_session/roles/WORKFLOW.md` holds the 9-step workflow in Bob's own taxonomy
(deterministic / AI / interactive) with exact context bundles, plus the
machine-readable manifest. The role prompts are `bob_session/roles/{scout,
cartographer, author, falsifier}.md`; the cascade and dispatch rules live beside
them in code. Three of nine steps cost coins; deterministic steps cost none.

## Coin budget (160 Bobcoins for the whole team; never replenished)

Roughly 40 per account, 4 accounts. Allocation: ~15% role-prompt development and
rehearsal, ~45% the recorded end-to-end session, ~20% the second and third runs after
a defect is found, ~10% the falsification passes that prove the kernel rejects, ~10%
reserve — never spend the reserve; if you are spending it, a step is misdesigned.
Live spend and the "was this answerable deterministically?" audit: `bob_session/coins.md`.

## Commands

```bash
python3 bob_session/run_analysis.py            # the deterministic engine → the artefact
./verify.sh                                    # the gates; writes VERIFICATION.md + evidence
python3 -m pytest -q                           # the test suite (if pytest is installed)
python3 -m unittest discover -s bob_session/roles/tests -t .   # the cognitive layer's tests
python3 bob_session/reliability_check.py       # measurement / reliability harness
python3 bob_session/mcp_server.py              # the MCP kernel (stdio)
python3 -m http.server 8117                    # then open http://127.0.0.1:8117/dashboard/
```

## Rules

1. Never ask a model a question the symbolic layer can answer exactly.
2. Never let a model verdict into an artefact unverified — the kernel is the only door.
3. Never use majority voting for correctness; diversity is for discovery only.
4. Never use a model as the verifier.
5. Never accept a generated test because it increases coverage; an assertion must
   fire before the change (G3).
6. State what is **built** and what is **specified**; never blur the two.
7. Every claim in a document must be reproducible by running one command.
8. No "first ever" / "no one has done this" claims anywhere, in any artefact.
9. Say "pinned", never "correct", unless an intent artefact anchors the assertion.
10. Never auto-approve `testscope_gate` in Bob's MCP settings. The click is the
    trust boundary.
