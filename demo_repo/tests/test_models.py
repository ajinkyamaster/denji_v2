"""Domain record construction."""

import pytest

from app.models import invoice_total, line_total, make_account, make_invoice


@pytest.mark.parametrize(
    'account_id, owner, expected',
    [
        pytest.param('ACCT-000000', 'owner-0', {'id': 'ACCT-000000', 'owner': 'owner-0', 'balance_cents': 0, 'state': 'open'}, id="T-0031"),
        pytest.param('ACCT-000001', 'owner-1', {'id': 'ACCT-000001', 'owner': 'owner-1', 'balance_cents': 0, 'state': 'open'}, id="T-0032"),
        pytest.param('ACCT-000002', 'owner-2', {'id': 'ACCT-000002', 'owner': 'owner-2', 'balance_cents': 0, 'state': 'open'}, id="T-0033"),
        pytest.param('ACCT-000003', 'owner-3', {'id': 'ACCT-000003', 'owner': 'owner-3', 'balance_cents': 0, 'state': 'open'}, id="T-0034"),
        pytest.param('ACCT-000004', 'owner-4', {'id': 'ACCT-000004', 'owner': 'owner-4', 'balance_cents': 0, 'state': 'open'}, id="T-0035"),
        pytest.param('ACCT-000005', 'owner-5', {'id': 'ACCT-000005', 'owner': 'owner-5', 'balance_cents': 0, 'state': 'open'}, id="T-0036"),
        pytest.param('ACCT-000006', 'owner-6', {'id': 'ACCT-000006', 'owner': 'owner-6', 'balance_cents': 0, 'state': 'open'}, id="T-0037"),
        pytest.param('ACCT-000007', 'owner-7', {'id': 'ACCT-000007', 'owner': 'owner-7', 'balance_cents': 0, 'state': 'open'}, id="T-0038"),
        pytest.param('ACCT-000008', 'owner-8', {'id': 'ACCT-000008', 'owner': 'owner-8', 'balance_cents': 0, 'state': 'open'}, id="T-0039"),
        pytest.param('ACCT-000009', 'owner-9', {'id': 'ACCT-000009', 'owner': 'owner-9', 'balance_cents': 0, 'state': 'open'}, id="T-0040"),
    ],
)
def test_make_account(account_id, owner, expected):
    """Make account."""
    assert make_account(account_id, owner) == expected


@pytest.mark.parametrize(
    'line, expected',
    [
        pytest.param({'unit_cents': 100, 'quantity': 3}, 300, id="T-0041"),
        pytest.param({'unit_cents': 0, 'quantity': 5}, 0, id="T-0042"),
        pytest.param({'unit_cents': 250, 'quantity': 1}, 250, id="T-0043"),
        pytest.param({'unit_cents': 999, 'quantity': 7}, 6993, id="T-0044"),
        pytest.param({'unit_cents': 1, 'quantity': 1}, 1, id="T-0045"),
        pytest.param({'unit_cents': 1250, 'quantity': 2}, 2500, id="T-0046"),
        pytest.param({'unit_cents': 40, 'quantity': 10}, 400, id="T-0047"),
        pytest.param({'unit_cents': 7, 'quantity': 9}, 63, id="T-0048"),
        pytest.param({'unit_cents': 5000, 'quantity': 3}, 15000, id="T-0049"),
        pytest.param({'unit_cents': 33, 'quantity': 33}, 1089, id="T-0050"),
    ],
)
def test_line_total(line, expected):
    """Line total."""
    assert line_total(line) == expected


@pytest.mark.parametrize(
    'account_id, line_rows, tax_bps, expected',
    [
        pytest.param('acct', [{'unit_cents': 100, 'quantity': 2}], 0, {'account_id': 'acct', 'lines': [{'unit_cents': 100, 'quantity': 2}], 'subtotal_cents': 200, 'tax_cents': 0, 'total_cents': 200}, id="T-0051"),
        pytest.param('acct', [{'unit_cents': 100, 'quantity': 2}], 1900, {'account_id': 'acct', 'lines': [{'unit_cents': 100, 'quantity': 2}], 'subtotal_cents': 200, 'tax_cents': 38, 'total_cents': 238}, id="T-0052"),
        pytest.param('acct', [], 0, {'account_id': 'acct', 'lines': [], 'subtotal_cents': 0, 'tax_cents': 0, 'total_cents': 0}, id="T-0053"),
        pytest.param('acct', [{'unit_cents': 2500, 'quantity': 1}], 500, {'account_id': 'acct', 'lines': [{'unit_cents': 2500, 'quantity': 1}], 'subtotal_cents': 2500, 'tax_cents': 125, 'total_cents': 2625}, id="T-0054"),
        pytest.param('acct', [{'unit_cents': 999, 'quantity': 3}], 2500, {'account_id': 'acct', 'lines': [{'unit_cents': 999, 'quantity': 3}], 'subtotal_cents': 2997, 'tax_cents': 749, 'total_cents': 3746}, id="T-0055"),
        pytest.param('acct', [{'unit_cents': 1, 'quantity': 1}], 1, {'account_id': 'acct', 'lines': [{'unit_cents': 1, 'quantity': 1}], 'subtotal_cents': 1, 'tax_cents': 0, 'total_cents': 1}, id="T-0056"),
        pytest.param('acct', [{'unit_cents': 40, 'quantity': 10}, {'unit_cents': 60, 'quantity': 10}], 1000, {'account_id': 'acct', 'lines': [{'unit_cents': 40, 'quantity': 10}, {'unit_cents': 60, 'quantity': 10}], 'subtotal_cents': 1000, 'tax_cents': 100, 'total_cents': 1100}, id="T-0057"),
        pytest.param('acct', [{'unit_cents': 0, 'quantity': 10}], 2000, {'account_id': 'acct', 'lines': [{'unit_cents': 0, 'quantity': 10}], 'subtotal_cents': 0, 'tax_cents': 0, 'total_cents': 0}, id="T-0058"),
        pytest.param('acct', [{'unit_cents': 123456, 'quantity': 2}], 725, {'account_id': 'acct', 'lines': [{'unit_cents': 123456, 'quantity': 2}], 'subtotal_cents': 246912, 'tax_cents': 17901, 'total_cents': 264813}, id="T-0059"),
        pytest.param('acct', [{'unit_cents': 5, 'quantity': 5}], 9999, {'account_id': 'acct', 'lines': [{'unit_cents': 5, 'quantity': 5}], 'subtotal_cents': 25, 'tax_cents': 24, 'total_cents': 49}, id="T-0060"),
    ],
)
def test_make_invoice(account_id, line_rows, tax_bps, expected):
    """Make invoice."""
    assert make_invoice(account_id, line_rows, tax_bps) == expected


@pytest.mark.parametrize(
    'invoice, expected',
    [
        pytest.param({'account_id': 'acct', 'lines': [{'unit_cents': 100, 'quantity': 2}], 'subtotal_cents': 200, 'tax_cents': 0, 'total_cents': 200}, 200, id="T-0061"),
        pytest.param({'account_id': 'acct', 'lines': [{'unit_cents': 100, 'quantity': 2}], 'subtotal_cents': 200, 'tax_cents': 38, 'total_cents': 238}, 238, id="T-0062"),
        pytest.param({'account_id': 'acct', 'lines': [], 'subtotal_cents': 0, 'tax_cents': 0, 'total_cents': 0}, 0, id="T-0063"),
        pytest.param({'account_id': 'acct', 'lines': [{'unit_cents': 2500, 'quantity': 1}], 'subtotal_cents': 2500, 'tax_cents': 125, 'total_cents': 2625}, 2625, id="T-0064"),
        pytest.param({'account_id': 'acct', 'lines': [{'unit_cents': 999, 'quantity': 3}], 'subtotal_cents': 2997, 'tax_cents': 749, 'total_cents': 3746}, 3746, id="T-0065"),
        pytest.param({'account_id': 'acct', 'lines': [{'unit_cents': 1, 'quantity': 1}], 'subtotal_cents': 1, 'tax_cents': 0, 'total_cents': 1}, 1, id="T-0066"),
        pytest.param({'account_id': 'acct', 'lines': [{'unit_cents': 40, 'quantity': 10}, {'unit_cents': 60, 'quantity': 10}], 'subtotal_cents': 1000, 'tax_cents': 100, 'total_cents': 1100}, 1100, id="T-0067"),
        pytest.param({'account_id': 'acct', 'lines': [{'unit_cents': 0, 'quantity': 10}], 'subtotal_cents': 0, 'tax_cents': 0, 'total_cents': 0}, 0, id="T-0068"),
        pytest.param({'account_id': 'acct', 'lines': [{'unit_cents': 123456, 'quantity': 2}], 'subtotal_cents': 246912, 'tax_cents': 17901, 'total_cents': 264813}, 264813, id="T-0069"),
        pytest.param({'account_id': 'acct', 'lines': [{'unit_cents': 5, 'quantity': 5}], 'subtotal_cents': 25, 'tax_cents': 24, 'total_cents': 49}, 49, id="T-0070"),
    ],
)
def test_invoice_total(invoice, expected):
    """Invoice total."""
    assert invoice_total(invoice) == expected


