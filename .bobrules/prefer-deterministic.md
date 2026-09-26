# Prefer deterministic

Before any model call, ask: can a deterministic tool answer this exactly?

If it can, call the tool and do not call a model. Deterministic steps cost no
Bobcoins and are exact; every question asked of a model that the engine could have
answered is a coin burned for nothing.

- The four tools: `testscope_ledger`, `testscope_oracle`, `testscope_verify`,
  `testscope_gate`.
- The sufficiency gate in `bob_session/roles/context.py` runs BEFORE any call and
  refuses a bundle that cannot decide, at zero cost.
- Enforcement: the cascade never calls a model for a decidable question; every
  CLI step in `bob_session/roles/WORKFLOW.md` is listed with its tool.
