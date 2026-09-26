"""Duration parsing and formatting."""

import pytest

from app.utils.timeutil import add_seconds, format_duration, is_business_day, parse_duration_ms


@pytest.mark.parametrize(
    'text, expected',
    [
        pytest.param('0ms', 0, id="T-0206"),
        pytest.param('1ms', 1, id="T-0207"),
        pytest.param('999ms', 999, id="T-0208"),
        pytest.param('1s', 1000, id="T-0209"),
        pytest.param('2s', 2000, id="T-0210"),
        pytest.param('59s', 59000, id="T-0211"),
        pytest.param('1m', 60000, id="T-0212"),
        pytest.param('90m', 5400000, id="T-0213"),
        pytest.param('1h', 3600000, id="T-0214"),
        pytest.param('24h', 86400000, id="T-0215"),
    ],
)
def test_parse_duration_ms(text, expected):
    """Parse duration ms."""
    assert parse_duration_ms(text) == expected


@pytest.mark.parametrize(
    'milliseconds, expected',
    [
        pytest.param(0, '0ms', id="T-0216"),
        pytest.param(1, '1ms', id="T-0217"),
        pytest.param(500, '500ms', id="T-0218"),
        pytest.param(1000, '1s', id="T-0219"),
        pytest.param(2000, '2s', id="T-0220"),
        pytest.param(59000, '59s', id="T-0221"),
        pytest.param(60000, '1m', id="T-0222"),
        pytest.param(90000, '90s', id="T-0223"),
        pytest.param(3600000, '1h', id="T-0224"),
        pytest.param(7200000, '2h', id="T-0225"),
    ],
)
def test_format_duration(milliseconds, expected):
    """Format duration."""
    assert format_duration(milliseconds) == expected


@pytest.mark.parametrize(
    'epoch_seconds, seconds, expected',
    [
        pytest.param(0, 0, 0, id="T-0226"),
        pytest.param(0, 60, 60, id="T-0227"),
        pytest.param(1000, -500, 500, id="T-0228"),
        pytest.param(86399, 1, 86400, id="T-0229"),
        pytest.param(1700000000, 3600, 1700003600, id="T-0230"),
        pytest.param(1, 1, 2, id="T-0231"),
        pytest.param(-10, 5, -5, id="T-0232"),
        pytest.param(99, 1, 100, id="T-0233"),
        pytest.param(123456789, 987654, 124444443, id="T-0234"),
        pytest.param(5, 0, 5, id="T-0235"),
    ],
)
def test_add_seconds(epoch_seconds, seconds, expected):
    """Add seconds."""
    assert add_seconds(epoch_seconds, seconds) == expected


@pytest.mark.parametrize(
    'weekday, expected',
    [
        pytest.param(0, True, id="T-0236"),
        pytest.param(1, True, id="T-0237"),
        pytest.param(2, True, id="T-0238"),
        pytest.param(3, True, id="T-0239"),
        pytest.param(4, True, id="T-0240"),
        pytest.param(5, False, id="T-0241"),
        pytest.param(6, False, id="T-0242"),
        pytest.param(-1, False, id="T-0243"),
        pytest.param(7, False, id="T-0244"),
        pytest.param(3, True, id="T-0245"),
    ],
)
def test_is_business_day(weekday, expected):
    """Is business day."""
    assert is_business_day(weekday) is expected


