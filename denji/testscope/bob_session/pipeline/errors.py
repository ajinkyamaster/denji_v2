"""Typed pipeline errors.

Governing principle (kept from v1, extended here): **fail loud on uncertainty,
degrade explicitly on irrelevance, never silently coerce.** Every error below is
raised rather than papered over, and every degradation is recorded in the
artefact so it is visible rather than silent.
"""


class TestScopeError(Exception):
    """Base class for every error this package raises."""


class InventoryError(TestScopeError):
    """The inventory cannot be trusted: a missing column, a duplicate test id,

    or a value that is not the type it claims to be. Never repaired by
    coercion: a corrupt row that looks like a fast test is worse than a crash.
    """


class DiffError(TestScopeError):
    """The diff cannot be parsed. Naming the offending line is part of the contract."""


class RepoIndexError(TestScopeError):
    """The repository index could not be built (bad root, unreadable tree)."""


class SafetyError(TestScopeError):
    """A path escaped the analysed repository.

    Raised for absolute paths, ``..`` traversal, and symlinks that resolve
    outside the repository root. The analysed repository is untrusted input.
    """


class GateError(TestScopeError):
    """A behavioural gate could not be executed (missing interpreter, timeout)."""
