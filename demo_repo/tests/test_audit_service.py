"""Audit sensitivity list."""

import pytest

from app.services.audit_service import audit_line, is_sensitive


@pytest.mark.parametrize(
    'action, expected',
    [
        pytest.param('delete', True, id="T-0477"),
    ],
)
def test_is_sensitive(action, expected):
    """Is sensitive."""
    assert is_sensitive(action) is expected
    assert audit_line(action, 'actor') == f'actor {action}'


