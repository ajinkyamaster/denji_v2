# Handoff folder

Kept in the repository for transparency, per the submission checklist.

| file | what it is | status |
|---|---|---|
| `ARCHITECTURE_V2.md` | the normative design of record: the link relation, the five verdicts, the three strata, the determinism theorem, the ontology, the plan | present (copied verbatim) |
| `person_d.txt` | the measurement workstream's assignment: the harness, the four measurement rules, the ablation, the scorecard gates, the submission rules | present (copied verbatim) |

**Not supplied to this workspace:** `MASTER_PROMPT.txt` and `person_a.txt`, `person_b.txt`,
`person_c.txt`. The workstreams they assign (the deterministic core and MCP kernel, the Bob workflow
and role prompts, the dashboard) are implemented here to the extent the measurement workstream needs
them: `bob_session/pipeline/`, `bob_session/oracle.py`, `bob_session/verify.py`, `bob_session/gate.py`,
`bob_session/mcp_server.py`, `bob_session/roles/` and the `.bob/` configuration. The dashboard is not
built; the artefact is rendered as JSON and the evidence tables in `README.md` and `VERIFICATION.md`.

That gap is recorded in `submissions/checklist.md` rather than papered over.
