"""Token hashing and role scopes.

Hashing here is for audit correlation only: it is a truncated SHA-256 digest
of a test token, not a password store.
"""

import hashlib
import hmac

ROLE_SCOPES = {
    "viewer": ("read",),
    "operator": ("read", "write"),
    "admin": ("read", "write", "delete"),
}
DIGEST_LENGTH = 16


def scopes_for(role):
    """Sorted scopes for a role; empty for an unknown role."""
    return sorted(ROLE_SCOPES.get(role, ()))


def is_allowed(role, scope):
    """True when the role carries the scope."""
    return scope in ROLE_SCOPES.get(role, ())


def hash_token(token):
    """Truncated hex digest used to correlate audit entries."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:DIGEST_LENGTH]


def verify_token(token, digest):
    """Constant-time comparison of a token against a stored digest."""
    return hmac.compare_digest(hash_token(token), digest)
