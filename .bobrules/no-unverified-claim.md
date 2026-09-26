# No unverified claim

NEVER write a model claim into any artefact.

A claim may enter an artefact ONLY through `testscope_verify`, which re-opens the
cited files and re-derives the claim against the repository. Cite or abstain.

- A citation is an obligation, not decoration.
- `confidence` orders results for a human. It NEVER authorises acceptance.
- If the verifier rejects, log the rejection with its gate. Do not re-ask to argue.
- An authored test enters the suite ONLY through `testscope_gate` G1..G5, and that
  tool requires an explicit human click.
- Enforcement: `bob_session/roles/cascade.py` submits every claim to the verifier
  before it can reach an outcome, and refuses an accepted claim that was never
  submitted; `bob_session/roles/tests/test_cascade.py` asserts both.
