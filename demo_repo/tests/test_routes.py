"""Route resolution."""

import pytest

from app.api.routes import is_known, resolve


@pytest.mark.parametrize(
    'method, path',
    [
        pytest.param('GET', '/accounts', id="T-0468"),
    ],
)
def test_resolve(method, path):
    """Resolve."""
    assert resolve(method, path) == 'list_accounts'


@pytest.mark.parametrize(
    'method, path',
    [
        pytest.param('GET', '/reports/recent', id="T-0469"),
    ],
)
def test_is_known(method, path):
    """Is known."""
    assert is_known(method, path) is True


