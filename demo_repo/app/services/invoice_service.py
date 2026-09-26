"""Invoice issuing.

Depends on the notification service, which depends on the account service,
which depends on the cache service: three import hops from the cache.
"""

from app.services.notification_service import render_message

DUE_DAYS = 30
ISSUED_TEMPLATE = "invoice {invoice} issued to {account}"


def issue(account, invoice):
    """Return the issuing message for an invoice."""
    return render_message(
        ISSUED_TEMPLATE,
        {"invoice": invoice["id"], "account": account["id"]},
    )


def due_date(issued_on_day, due_days=DUE_DAYS):
    """Day number on which the invoice falls due."""
    return issued_on_day + due_days


def is_overdue(due_day, today):
    """True when ``today`` is strictly after the due day."""
    return today > due_day
