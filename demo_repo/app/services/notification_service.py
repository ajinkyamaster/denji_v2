"""Account notifications.

This module is one import away from the cache service: it reads account
records, and account records are the module that talks to the cache.
"""

from app.services.account_service import OPEN_STATE

CHANNELS = {"email": 0, "sms": 1, "push": 2}
MAX_BODY = 240


def channels_for(account):
    """Notification channels for an account, by account state."""
    if account.get("state") == OPEN_STATE:
        return ["email", "push"]
    return ["email"]


def render_message(template, values):
    """Render ``template`` with ``values`` substituted by name.

    Raises ``KeyError`` when the template names a value that was not supplied,
    so a missing substitution is loud rather than rendered as ``{name}``.
    """
    return template.format(**values)


def should_notify(account, event):
    """True when ``event`` is worth notifying about for ``account``."""
    if event in ("settled", "failed"):
        return True
    return account.get("state") == OPEN_STATE and event == "opened"


def body_length(message):
    """Length of a rendered message, clipped to ``MAX_BODY``."""
    return min(len(message), MAX_BODY)
