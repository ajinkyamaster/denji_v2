"""Base pricing tables and tiers."""

BASE_PRICES_CENTS = {
    "starter": 900,
    "standard": 2500,
    "premium": 7900,
}
TIERS = ((100, "volume"), (10, "team"), (1, "single"))


def base_price(sku):
    """Base price in cents; ``KeyError`` for an unknown sku."""
    return BASE_PRICES_CENTS[sku]


def discounted(price_cents, percent):
    """Apply a percentage discount, truncating toward zero."""
    return price_cents - price_cents * percent // 100


def tier_for(units):
    """Tier name for a unit count, lowest tier below one unit."""
    for threshold, name in TIERS:
        if units >= threshold:
            return name
    return "none"


def total_for(sku, units):
    """Undiscounted total for ``units`` of ``sku``."""
    return base_price(sku) * units
