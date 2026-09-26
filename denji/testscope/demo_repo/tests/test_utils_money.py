"""Integer-cent money arithmetic."""

import pytest

from app.utils.money import apply_rate, format_amount, split_amount, to_cents


@pytest.mark.parametrize(
    'amount_text, expected',
    [
        pytest.param('0.00', 0, id="T-0306"),
        pytest.param('0.10', 10, id="T-0307"),
        pytest.param('1.00', 100, id="T-0308"),
        pytest.param('99.99', 9999, id="T-0309"),
        pytest.param('-2.50', -250, id="T-0310"),
        pytest.param('+3', 300, id="T-0311"),
        pytest.param('7', 700, id="T-0312"),
        pytest.param('12.3', 1230, id="T-0313"),
    ],
)
def test_to_cents(amount_text, expected):
    """To cents."""
    assert to_cents(amount_text) == expected


@pytest.mark.parametrize(
    'cents, expected',
    [
        pytest.param(0, '0.00', id="T-0314"),
        pytest.param(5, '0.05', id="T-0315"),
        pytest.param(10, '0.10', id="T-0316"),
        pytest.param(100, '1.00', id="T-0317"),
        pytest.param(9999, '99.99', id="T-0318"),
        pytest.param(-250, '-2.50', id="T-0319"),
        pytest.param(123456, '1234.56', id="T-0320"),
        pytest.param(1, '0.01', id="T-0321"),
    ],
)
def test_format_amount(cents, expected):
    """Format amount."""
    assert format_amount(cents) == expected


@pytest.mark.parametrize(
    'cents, basis_points, expected',
    [
        pytest.param(10000, 250, 250, id="T-0322"),
        pytest.param(10000, 0, 0, id="T-0323"),
        pytest.param(999, 1, 0, id="T-0324"),
        pytest.param(100, 10000, 100, id="T-0325"),
        pytest.param(12345, 725, 895, id="T-0326"),
        pytest.param(1, 9999, 0, id="T-0327"),
        pytest.param(5000, 5000, 2500, id="T-0328"),
        pytest.param(999999, 1, 99, id="T-0329"),
    ],
)
def test_apply_rate(cents, basis_points, expected):
    """Apply rate."""
    assert apply_rate(cents, basis_points) == expected


@pytest.mark.parametrize(
    'cents, parts, expected',
    [
        pytest.param(0, 1, [0], id="T-0330"),
        pytest.param(10, 1, [10], id="T-0331"),
        pytest.param(10, 2, [5, 5], id="T-0332"),
        pytest.param(10, 3, [4, 3, 3], id="T-0333"),
        pytest.param(100, 3, [34, 33, 33], id="T-0334"),
        pytest.param(7, 4, [4, 1, 1, 1], id="T-0335"),
        pytest.param(-10, 2, [-5, -5], id="T-0336"),
        pytest.param(1, 3, [1, 0, 0], id="T-0337"),
    ],
)
def test_split_amount(cents, parts, expected):
    """Split amount."""
    assert split_amount(cents, parts) == expected


