"""TestScope: the test-code link ledger.

Strata:
  S (symbolic)  bob_session/pipeline   - pure functions of (repo, diff, inventory)
  K (kernel)    bob_session/verify.py  - deterministic verifier, the trust boundary
  I (inference) bob_session/roles      - recorded proposals, replayed through a
                                         content-addressed cache
"""

ENGINE_VERSION = "2.0.0"
SCHEMA_VERSION = "2.0"
PROMPT_VERSION = "v2.0.0"
