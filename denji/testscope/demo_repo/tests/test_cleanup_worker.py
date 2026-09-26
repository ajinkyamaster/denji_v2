"""Cache trimming."""

import pytest

from app.workers.cleanup_worker import clean_cache, trim


@pytest.mark.parametrize(
    'entries, limit, expected',
    [
        pytest.param([1, 2, 3], 2, [2, 3], id="T-0475"),
    ],
)
def test_trim(entries, limit, expected):
    """Trim."""
    assert trim(entries, limit) == expected


@pytest.mark.parametrize(
    'limit, expected',
    [
        pytest.param(1, (1, 1), id="T-0476"),
    ],
)
def test_clean_cache(limit, expected, tmp_path):
    """Clean cache."""
    path = tmp_path / 'cache.txt'
    path.write_text('one\n\n two \n', encoding='utf-8')
    assert clean_cache(path, limit) == expected


