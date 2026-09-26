"""Billing service: settles accounts and builds receipts.

CAUSAL CONTROL, not a shipped revision. This variant differs from revision B in
exactly one token: the fee rate. It exists so that the inertness rule can be
shown to be load-bearing: if the same module's change is *semantics-modifying*
instead of an inert log reword, every test of the module must come back into the
selection (47 -> 122). A rule that cannot be shown to change its answer when the
input changes is a slogan, not a rule.
"""

import logging

logger = logging.getLogger(__name__)

FEE_BPS = 30
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
