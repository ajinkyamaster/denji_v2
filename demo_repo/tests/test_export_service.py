"""CSV rendering of cached entries."""

import pytest

from app.services.export_service import export_filename, export_rows


@pytest.mark.parametrize(
    'entries',
    [
        pytest.param(['ab', 'c'], id="T-0466"),
    ],
)
def test_export_rows(entries):
    """Export rows."""
    assert export_rows(entries) == ['entry,length', 'ab,2', 'c,1']


@pytest.mark.parametrize(
    'prefix, stamp',
    [
        pytest.param('recent', '20260101', id="T-0467"),
    ],
)
def test_export_filename(prefix, stamp):
    """Export filename."""
    assert export_filename(prefix, stamp) == 'recent-20260101.csv'


