"""Discount codes.

Codes are fixed-width and carry their own percentage: ``SAVE10`` is ten
percent. Unknown codes are rejected rather than silently ignored.
"""

import string

CODE_LENGTH = 6
_PREFIX = "SAVE"


def is_valid_code(code):
    """True for ``SAVE`` followed by exactly two digits."""
    if not isinstance(code, str) or len(code) != CODE_LENGTH:
        return False
    prefix, digits = code[:4], code[4:]
    return prefix == _PREFIX and all(char in string.digits for char in digits)


def discount_for(code, cents):
    """Discount amount in cents for a valid code, else 0."""
    if not is_valid_code(code):
        return 0
    return cents * int(code[4:]) // 100


def apply(code, cents):
    """Apply a discount code, returning ``(discount_cents, net_cents)``."""
    discount = discount_for(code, cents)
    return discount, cents - discount
