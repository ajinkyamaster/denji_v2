"""Account lifecycle, asserting shape only."""

import pytest

from app.services.account_service import account_summary, open_account, record_event


@pytest.mark.parametrize(
    'account_id, owner',
    [
        pytest.param('ACCT-000001', 'owner-1', id="T-0462"),
    ],
)
def test_open_account(account_id, owner):
    """Open account."""
    assert open_account(account_id, owner) == {'id': account_id, 'owner': owner, 'state': 'open'}


@pytest.mark.parametrize(
    'blank',
    [
        pytest.param(None, id="T-0463"),
    ],
)
def test_account_summary_counts_cached_entries(blank, tmp_path):
    """Account summary counts cached entries."""
    path = tmp_path / 'cache.txt'
    path.write_text('ACCT-000001|x|1\nACCT-000002|x|1\n', encoding='utf-8')
    assert record_event('ACCT-000001', 'ok') is not None
    assert account_summary('ACCT-000001', path) == 1


