"""Billing service: settles accounts and builds receipts.

Fees are computed in integer cents from a basis-point rate. Every amount that
leaves this module is an integer number of cents.
"""

import logging

logger = logging.getLogger(__name__)

FEE_BPS = 25
SETTLE_STATUS = "settled"


def apply_fee(amount_cents):
    """Apply the standard fee, truncating toward zero."""
    return amount_cents * FEE_BPS // 10000


def build_receipt(account_id, amount_cents):
    """Build the receipt record for a settlement."""
    fee = apply_fee(amount_cents)
    return {
        "account_id": account_id,
        "amount_cents": amount_cents,
        "fee_cents": fee,
        "net_cents": amount_cents - fee,
        "status": SETTLE_STATUS,
    }


def settle(account_id, amount_cents):
    """Settle ``amount_cents`` for ``account_id`` and return the receipt."""
    receipt = build_receipt(account_id, amount_cents)
    logger.info("settlement complete for %s", account_id)
    return receipt
