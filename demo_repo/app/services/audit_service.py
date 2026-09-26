"""Audit trail lines.

Every privileged action is mirrored into the cache so that the audit report
can be rebuilt from cached entries alone.
"""

from app.services.cache_service import write_cache_entry

SENSITIVE_ACTIONS = ("delete", "export", "transfer")


def audit_line(action, actor):
    """A stable ``actor action`` audit line."""
    return f"{actor} {action}"


def is_sensitive(action):
    """True when the action is on the privileged list."""
    return action in SENSITIVE_ACTIONS


def record_audit(action, actor, sink=None):
    """Record an audit line for a sensitive action, else return None."""
    if not is_sensitive(action):
        return None
    return write_cache_entry(actor, action, 1, sink=sink)
