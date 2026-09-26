"""Billing settlement for demo-service."""
from app.logging_setup import get_logger
from app.telemetry import record
from app.validators import require

logger = get_logger(__name__)

CURRENCIES = ("EUR", "USD", "INR")


def settle(amount: int, currency: str = "EUR") -> dict:
    """Settle an amount and return the receipt fields."""
    require(amount >= 0, "amount must not be negative")
    require(currency in CURRENCIES, f"unsupported currency: {currency}")
    logger.info("billing settle: starting")
    record("billing.settle")
    return {"amount": amount, "currency": currency, "settled": amount >= 0}


def refund(receipt: dict) -> dict:
    """Reverse a settled receipt and return the refund fields."""
    require(isinstance(receipt, dict), "receipt must be a mapping")
    require(receipt.get("settled") is True, "receipt was not settled")
    record("billing.refund")
    return {"amount": receipt["amount"], "currency": receipt["currency"], "refunded": True}


def net_amount(receipt: dict, fee: int = 0) -> int:
    """Return the receipt amount minus a flat fee."""
    require(isinstance(receipt, dict), "receipt must be a mapping")
    return int(receipt["amount"]) - fee
