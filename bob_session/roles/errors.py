"""Error taxonomy for the cognitive layer (Person B).

Every failure mode in this layer has a NAME and a DEFINED behaviour; nothing here
improvises. The taxonomy exists so the cascade can distinguish four kinds of
failure that need four different responses:

  bundle defect          -> InsufficientBundleError : do NOT call a model (zero coins)
  model transport defect -> ModelUnavailable        : retry once, then degrade to the
                                                       deterministic baseline
  kernel transport defect-> KernelUnavailable       : accept nothing; selection equals
                                                       the baseline (monotonicity)
  model output defect    -> EnvelopeError           : reject the proposal; NEVER salvage
  trust-boundary defect  -> UnverifiedClaimError    : fail loud (this must never happen)
  ordering defect        -> FalsifierOrderError     : fail loud (falsifier runs last)
  dispatch defect        -> TwoWritersOneFile       : fail loud (one writer per file)

Layer rule: the kernel is the only door to a verdict. These errors are the doors
that stay shut.
"""

from __future__ import annotations


class TestScopeLayerError(RuntimeError):
    """Base class for every error raised by bob_session/roles."""


class InsufficientBundleError(TestScopeLayerError):
    """The sufficiency gate failed: the bundle cannot decide the question, so no
    model may be asked. Defined behaviour: UNKNOWN + safe direction (include the
    candidate test and mark it). Costs zero coins."""


class ModelUnavailable(TestScopeLayerError):
    """A proposer could not be reached (timeout, rate limit, no coins left, refusal).
    Defined behaviour: retry exactly once, then degrade this item to the
    deterministic baseline and log MODEL_UNAVAILABLE."""


class KernelUnavailable(TestScopeLayerError):
    """testscope_verify / testscope_gate could not be reached. Defined behaviour:
    accept NOTHING. The selection equals the deterministic baseline byte for byte;
    the artefact stays valid. Monotonicity (Lemma 2) still holds."""


class EnvelopeError(ValueError):
    """A model returned something that is not strictly the claim envelope.
    Defined behaviour: reject the proposal (gate: schema_violation) and log it.
    There is no best-effort JSON salvage path -- that is how a verifier silently
    becomes a guesser."""


class UnverifiedClaimError(TestScopeLayerError):
    """The trust boundary was crossed: an accepted claim appeared that was never
    submitted to the kernel. This must be impossible by construction; if it fires,
    the run is void and loud."""


class FalsifierOrderError(TestScopeLayerError):
    """The falsifier was invoked before the ledger was final. It runs LAST, alone."""


class FalsifierInputError(TestScopeLayerError):
    """The falsifier received already-SELECTED rows. It may only ever see the
    unselected rows, or it wastes claims on tests we are already running."""


class TwoWritersOneFile(TestScopeLayerError):
    """Two subagents were about to write the same file. Defined behaviour: refuse
    the second claim and serialise instead. This is the rule teams break first."""


class SequentialRoleInParallel(TestScopeLayerError):
    """A role that must run sequentially (the falsifier) was dispatched in a
    parallel wave."""
