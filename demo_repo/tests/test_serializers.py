"""Response serialisation."""

import pytest

from app.api.serializers import serialise_account, serialise_error


@pytest.mark.parametrize(
    'account',
    [
        pytest.param({'id': 'ACCT-1', 'state': 'open'}, id="T-0470"),
    ],
)
def test_serialise_account(account):
    """Serialise account."""
    assert serialise_account(account) == 'id=ACCT-1;state=open'


@pytest.mark.parametrize(
    'code, message',
    [
        pytest.param(404, 'missing', id="T-0471"),
    ],
)
def test_serialise_error(code, message):
    """Serialise error."""
    assert serialise_error(code, message) == 'error 404: missing'


