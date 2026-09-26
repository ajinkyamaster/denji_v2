"""Domain records for accounts and invoices.

All amounts are integer cents. Floating point money is a defect, not a style
choice, so nothing here ever produces a float.
"""


def make_account(account_id, owner, balance_cents=0):
    """Build an account record in the ``open`` state."""
    return {
        "id": account_id,
        "owner": owner,
        "balance_cents": balance_cents,
        "state": "open",
    }


def line_total(line):
    """``unit_cents * quantity`` for one invoice line."""
    return line["unit_cents"] * line["quantity"]


def make_invoice(account_id, lines, tax_bps=0):
    """Build an invoice, computing subtotal and tax in integer arithmetic."""
    subtotal = sum(line_total(line) for line in lines)
    tax = subtotal * tax_bps // 10000
    return {
        "account_id": account_id,
        "lines": list(lines),
        "subtotal_cents": subtotal,
        "tax_cents": tax,
        "total_cents": subtotal + tax,
    }


def invoice_total(invoice):
    """Subtotal plus tax for an invoice record."""
    return invoice["subtotal_cents"] + invoice["tax_cents"]


def account_is_open(account):
    """True when the account is in the ``open`` state."""
    return account["state"] == "open"
