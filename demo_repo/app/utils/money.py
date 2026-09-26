"""Integer-cent money helpers.

Nothing here converts through float; ``to_cents`` parses the decimal string
directly so that ``"0.10"`` is exactly 10 cents on every platform.
"""


def to_cents(amount_text):
    """Parse a decimal money string into integer cents.

    Raises ``ValueError`` on anything that is not ``[+-]?d+(\\.d{1,2})?``.
    """
    text = amount_text.strip()
    sign = 1
    if text[:1] in "+-":
        if text[0] == "-":
            sign = -1
        text = text[1:]
    if not text:
        raise ValueError(f"not an amount: {amount_text!r}")
    whole, dot, fraction = text.partition(".")
    if not whole.isdigit() or (dot and (not fraction.isdigit() or len(fraction) > 2)):
        raise ValueError(f"not an amount: {amount_text!r}")
    cents = int(whole) * 100
    if dot:
        cents += int(fraction.ljust(2, "0"))
    return sign * cents


def format_amount(cents):
    """Render integer cents as a decimal string with two places."""
    sign = "-" if cents < 0 else ""
    magnitude = abs(cents)
    return f"{sign}{magnitude // 100}.{magnitude % 100:02d}"


def apply_rate(cents, basis_points):
    """Apply a rate expressed in basis points, truncating toward zero."""
    return cents * basis_points // 10000


def split_amount(cents, parts):
    """Split ``cents`` into ``parts`` shares, remainder to the first share.

    Raises ``ValueError`` for a non-positive ``parts``.
    """
    if parts <= 0:
        raise ValueError("parts must be positive")
    base = cents // parts
    shares = [base] * parts
    shares[0] += cents - base * parts
    return shares
