"""Price tables, discounts and tiers."""

import pytest

from app.services.pricing_service import base_price, discounted, tier_for, total_for


@pytest.mark.parametrize(
    'sku, expected',
    [
        pytest.param('starter', 900, id="T-0344"),
        pytest.param('standard', 2500, id="T-0345"),
        pytest.param('premium', 7900, id="T-0346"),
        pytest.param('starter', 900, id="T-0347"),
        pytest.param('standard', 2500, id="T-0348"),
        pytest.param('premium', 7900, id="T-0349"),
        pytest.param('starter', 900, id="T-0350"),
        pytest.param('standard', 2500, id="T-0351"),
        pytest.param('premium', 7900, id="T-0352"),
        pytest.param('starter', 900, id="T-0353"),
        pytest.param('standard', 2500, id="T-0354"),
        pytest.param('premium', 7900, id="T-0355"),
        pytest.param('starter', 900, id="T-0356"),
        pytest.param('standard', 2500, id="T-0357"),
    ],
)
def test_base_price(sku, expected):
    """Base price."""
    assert base_price(sku) == expected


@pytest.mark.parametrize(
    'price_cents, percent, expected',
    [
        pytest.param(900, 0, 900, id="T-0358"),
        pytest.param(900, 10, 810, id="T-0359"),
        pytest.param(2500, 25, 1875, id="T-0360"),
        pytest.param(7900, 50, 3950, id="T-0361"),
        pytest.param(100, 100, 0, id="T-0362"),
        pytest.param(99, 33, 67, id="T-0363"),
        pytest.param(1, 50, 1, id="T-0364"),
        pytest.param(123456, 7, 114815, id="T-0365"),
        pytest.param(500, 1, 495, id="T-0366"),
        pytest.param(500, 99, 5, id="T-0367"),
        pytest.param(1000, 5, 950, id="T-0368"),
        pytest.param(1000, 15, 850, id="T-0369"),
        pytest.param(2500, 100, 0, id="T-0370"),
        pytest.param(7, 7, 7, id="T-0371"),
    ],
)
def test_discounted(price_cents, percent, expected):
    """Discounted."""
    assert discounted(price_cents, percent) == expected


@pytest.mark.parametrize(
    'units, expected',
    [
        pytest.param(0, 'none', id="T-0372"),
        pytest.param(1, 'single', id="T-0373"),
        pytest.param(9, 'single', id="T-0374"),
        pytest.param(10, 'team', id="T-0375"),
        pytest.param(11, 'team', id="T-0376"),
        pytest.param(99, 'team', id="T-0377"),
        pytest.param(100, 'volume', id="T-0378"),
        pytest.param(101, 'volume', id="T-0379"),
        pytest.param(1000, 'volume', id="T-0380"),
        pytest.param(5, 'single', id="T-0381"),
        pytest.param(50, 'team', id="T-0382"),
        pytest.param(500, 'volume', id="T-0383"),
        pytest.param(99, 'team', id="T-0384"),
        pytest.param(100, 'volume', id="T-0385"),
    ],
)
def test_tier_for(units, expected):
    """Tier for."""
    assert tier_for(units) == expected


@pytest.mark.parametrize(
    'sku, units, expected',
    [
        pytest.param('starter', 0, 0, id="T-0386"),
        pytest.param('starter', 1, 900, id="T-0387"),
        pytest.param('starter', 10, 9000, id="T-0388"),
        pytest.param('standard', 1, 2500, id="T-0389"),
        pytest.param('standard', 3, 7500, id="T-0390"),
        pytest.param('premium', 2, 15800, id="T-0391"),
        pytest.param('premium', 0, 0, id="T-0392"),
        pytest.param('starter', 100, 90000, id="T-0393"),
        pytest.param('standard', 100, 250000, id="T-0394"),
        pytest.param('premium', 10, 79000, id="T-0395"),
        pytest.param('starter', 7, 6300, id="T-0396"),
        pytest.param('standard', 11, 27500, id="T-0397"),
        pytest.param('premium', 13, 102700, id="T-0398"),
        pytest.param('starter', 99, 89100, id="T-0399"),
    ],
)
def test_total_for(sku, units, expected):
    """Total for."""
    assert total_for(sku, units) == expected


