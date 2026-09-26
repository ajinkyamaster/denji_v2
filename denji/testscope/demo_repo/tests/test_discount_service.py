"""Discount code validation and application."""

import pytest

from app.services.discount_service import apply, discount_for, is_valid_code


@pytest.mark.parametrize(
    'code, expected',
    [
        pytest.param('SAVE10', True, id="T-0400"),
        pytest.param('SAVE99', True, id="T-0401"),
        pytest.param('SAVE00', True, id="T-0402"),
        pytest.param('SAVE1', False, id="T-0403"),
        pytest.param('SAVE100', False, id="T-0404"),
        pytest.param('save10', False, id="T-0405"),
        pytest.param('SAVE1A', False, id="T-0406"),
        pytest.param('NOPE10', False, id="T-0407"),
        pytest.param('', False, id="T-0408"),
        pytest.param(None, False, id="T-0409"),
    ],
)
def test_is_valid_code(code, expected):
    """Is valid code."""
    assert is_valid_code(code) is expected


@pytest.mark.parametrize(
    'code, cents, expected',
    [
        pytest.param('SAVE10', 1000, 100, id="T-0410"),
        pytest.param('SAVE50', 999, 499, id="T-0411"),
        pytest.param('SAVE00', 12345, 0, id="T-0412"),
        pytest.param('SAVE99', 100, 99, id="T-0413"),
        pytest.param('NOPE10', 1000, 0, id="T-0414"),
        pytest.param('SAVE20', 0, 0, id="T-0415"),
        pytest.param('SAVE33', 1234, 407, id="T-0416"),
        pytest.param('SAVE10', 1, 0, id="T-0417"),
        pytest.param('SAVE10', 9, 0, id="T-0418"),
        pytest.param('SAVE99', 99999, 98999, id="T-0419"),
    ],
)
def test_discount_for(code, cents, expected):
    """Discount for."""
    assert discount_for(code, cents) == expected


@pytest.mark.parametrize(
    'code, cents, expected',
    [
        pytest.param('SAVE10', 1000, (100, 900), id="T-0420"),
        pytest.param('SAVE25', 2500, (625, 1875), id="T-0421"),
        pytest.param('SAVE00', 0, (0, 0), id="T-0422"),
        pytest.param('SAVE50', 7, (3, 4), id="T-0423"),
        pytest.param('NOPE10', 500, (0, 500), id="T-0424"),
        pytest.param('SAVE99', 10000, (9900, 100), id="T-0425"),
        pytest.param('SAVE01', 99, (0, 99), id="T-0426"),
        pytest.param('SAVE10', 55, (5, 50), id="T-0427"),
        pytest.param('SAVE20', 123456, (24691, 98765), id="T-0428"),
        pytest.param('SAVE75', 4, (3, 1), id="T-0429"),
    ],
)
def test_apply(code, cents, expected):
    """Apply."""
    assert apply(code, cents) == expected


