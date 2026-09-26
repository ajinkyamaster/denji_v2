"""Search and ranking over entry payloads."""

import pytest

from app.services.search_service import match_accounts, rank


@pytest.mark.parametrize(
    'entries, query',
    [
        pytest.param(['Alpha', 'beta', 'ALPHABET', 'gamma'], 'alph', id="T-0464"),
    ],
)
def test_match_accounts(entries, query):
    """Match accounts."""
    assert match_accounts(entries, query) == ['Alpha', 'ALPHABET']


@pytest.mark.parametrize(
    'entries, query',
    [
        pytest.param(['bb', 'a', 'bbb'], 'b', id="T-0465"),
    ],
)
def test_rank(entries, query):
    """Rank."""
    assert rank(entries, query) == ['bbb', 'bb']


