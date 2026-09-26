"""Invoice issuing and due dates."""

import pytest

from app.services.invoice_service import due_date, is_overdue, issue


@pytest.mark.parametrize(
    'account, invoice',
    [
        pytest.param({'id': 'ACCT-1'}, {'id': 'INV-2'}, id="T-0498"),
    ],
)
def test_issue(account, invoice):
    """Issue."""
    assert issue(account, invoice) == 'invoice INV-2 issued to ACCT-1'


@pytest.mark.parametrize(
    'issued_on_day',
    [
        pytest.param(0, id="T-0499"),
    ],
)
def test_due_date(issued_on_day):
    """Due date."""
    assert due_date(issued_on_day) == 30


@pytest.mark.parametrize(
    'due_day, today',
    [
        pytest.param(30, 31, id="T-0500"),
    ],
)
def test_is_overdue(due_day, today):
    """Is overdue."""
    assert is_overdue(due_day, today) is True


