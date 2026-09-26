"""Fee arithmetic and receipts."""

import pytest

from app.services.billing_service import apply_fee, build_receipt, settle


@pytest.mark.parametrize(
    'amount_cents, expected',
    [
        pytest.param(0, 0, id="T-0071"),
        pytest.param(1, 0, id="T-0072"),
        pytest.param(39, 0, id="T-0073"),
        pytest.param(40, 0, id="T-0074"),
        pytest.param(100, 0, id="T-0075"),
        pytest.param(101, 0, id="T-0076"),
        pytest.param(999, 2, id="T-0077"),
        pytest.param(1000, 2, id="T-0078"),
        pytest.param(2500, 6, id="T-0079"),
        pytest.param(10000, 25, id="T-0080"),
        pytest.param(12345, 30, id="T-0081"),
        pytest.param(99999, 249, id="T-0082"),
        pytest.param(100000, 250, id="T-0083"),
        pytest.param(250000, 625, id="T-0084"),
        pytest.param(400, 1, id="T-0085"),
        pytest.param(800, 2, id="T-0086"),
        pytest.param(1200, 3, id="T-0087"),
        pytest.param(1600, 4, id="T-0088"),
        pytest.param(2000, 5, id="T-0089"),
        pytest.param(2400, 6, id="T-0090"),
        pytest.param(3600, 9, id="T-0091"),
        pytest.param(4800, 12, id="T-0092"),
        pytest.param(6000, 15, id="T-0093"),
        pytest.param(7200, 18, id="T-0094"),
        pytest.param(8400, 21, id="T-0095"),
    ],
)
def test_apply_fee(amount_cents, expected):
    """Apply fee."""
    assert apply_fee(amount_cents) == expected


@pytest.mark.parametrize(
    'account_id, amount_cents, expected',
    [
        pytest.param('ACCT-000000', 0, {'account_id': 'ACCT-000000', 'amount_cents': 0, 'fee_cents': 0, 'net_cents': 0, 'status': 'settled'}, id="T-0096"),
        pytest.param('ACCT-000001', 1, {'account_id': 'ACCT-000001', 'amount_cents': 1, 'fee_cents': 0, 'net_cents': 1, 'status': 'settled'}, id="T-0097"),
        pytest.param('ACCT-000039', 39, {'account_id': 'ACCT-000039', 'amount_cents': 39, 'fee_cents': 0, 'net_cents': 39, 'status': 'settled'}, id="T-0098"),
        pytest.param('ACCT-000040', 40, {'account_id': 'ACCT-000040', 'amount_cents': 40, 'fee_cents': 0, 'net_cents': 40, 'status': 'settled'}, id="T-0099"),
        pytest.param('ACCT-000100', 100, {'account_id': 'ACCT-000100', 'amount_cents': 100, 'fee_cents': 0, 'net_cents': 100, 'status': 'settled'}, id="T-0100"),
        pytest.param('ACCT-000101', 101, {'account_id': 'ACCT-000101', 'amount_cents': 101, 'fee_cents': 0, 'net_cents': 101, 'status': 'settled'}, id="T-0101"),
        pytest.param('ACCT-000999', 999, {'account_id': 'ACCT-000999', 'amount_cents': 999, 'fee_cents': 2, 'net_cents': 997, 'status': 'settled'}, id="T-0102"),
        pytest.param('ACCT-001000', 1000, {'account_id': 'ACCT-001000', 'amount_cents': 1000, 'fee_cents': 2, 'net_cents': 998, 'status': 'settled'}, id="T-0103"),
        pytest.param('ACCT-002500', 2500, {'account_id': 'ACCT-002500', 'amount_cents': 2500, 'fee_cents': 6, 'net_cents': 2494, 'status': 'settled'}, id="T-0104"),
        pytest.param('ACCT-010000', 10000, {'account_id': 'ACCT-010000', 'amount_cents': 10000, 'fee_cents': 25, 'net_cents': 9975, 'status': 'settled'}, id="T-0105"),
        pytest.param('ACCT-012345', 12345, {'account_id': 'ACCT-012345', 'amount_cents': 12345, 'fee_cents': 30, 'net_cents': 12315, 'status': 'settled'}, id="T-0106"),
        pytest.param('ACCT-099999', 99999, {'account_id': 'ACCT-099999', 'amount_cents': 99999, 'fee_cents': 249, 'net_cents': 99750, 'status': 'settled'}, id="T-0107"),
        pytest.param('ACCT-100000', 100000, {'account_id': 'ACCT-100000', 'amount_cents': 100000, 'fee_cents': 250, 'net_cents': 99750, 'status': 'settled'}, id="T-0108"),
        pytest.param('ACCT-250000', 250000, {'account_id': 'ACCT-250000', 'amount_cents': 250000, 'fee_cents': 625, 'net_cents': 249375, 'status': 'settled'}, id="T-0109"),
        pytest.param('ACCT-000400', 400, {'account_id': 'ACCT-000400', 'amount_cents': 400, 'fee_cents': 1, 'net_cents': 399, 'status': 'settled'}, id="T-0110"),
        pytest.param('ACCT-000800', 800, {'account_id': 'ACCT-000800', 'amount_cents': 800, 'fee_cents': 2, 'net_cents': 798, 'status': 'settled'}, id="T-0111"),
        pytest.param('ACCT-001200', 1200, {'account_id': 'ACCT-001200', 'amount_cents': 1200, 'fee_cents': 3, 'net_cents': 1197, 'status': 'settled'}, id="T-0112"),
        pytest.param('ACCT-001600', 1600, {'account_id': 'ACCT-001600', 'amount_cents': 1600, 'fee_cents': 4, 'net_cents': 1596, 'status': 'settled'}, id="T-0113"),
        pytest.param('ACCT-002000', 2000, {'account_id': 'ACCT-002000', 'amount_cents': 2000, 'fee_cents': 5, 'net_cents': 1995, 'status': 'settled'}, id="T-0114"),
        pytest.param('ACCT-002400', 2400, {'account_id': 'ACCT-002400', 'amount_cents': 2400, 'fee_cents': 6, 'net_cents': 2394, 'status': 'settled'}, id="T-0115"),
        pytest.param('ACCT-003600', 3600, {'account_id': 'ACCT-003600', 'amount_cents': 3600, 'fee_cents': 9, 'net_cents': 3591, 'status': 'settled'}, id="T-0116"),
        pytest.param('ACCT-004800', 4800, {'account_id': 'ACCT-004800', 'amount_cents': 4800, 'fee_cents': 12, 'net_cents': 4788, 'status': 'settled'}, id="T-0117"),
        pytest.param('ACCT-006000', 6000, {'account_id': 'ACCT-006000', 'amount_cents': 6000, 'fee_cents': 15, 'net_cents': 5985, 'status': 'settled'}, id="T-0118"),
        pytest.param('ACCT-007200', 7200, {'account_id': 'ACCT-007200', 'amount_cents': 7200, 'fee_cents': 18, 'net_cents': 7182, 'status': 'settled'}, id="T-0119"),
        pytest.param('ACCT-008400', 8400, {'account_id': 'ACCT-008400', 'amount_cents': 8400, 'fee_cents': 21, 'net_cents': 8379, 'status': 'settled'}, id="T-0120"),
    ],
)
def test_build_receipt(account_id, amount_cents, expected):
    """Build receipt."""
    assert build_receipt(account_id, amount_cents) == expected


@pytest.mark.parametrize(
    'account_id, amount_cents, expected',
    [
        pytest.param('ACCT-000000', 0, {'account_id': 'ACCT-000000', 'amount_cents': 0, 'fee_cents': 0, 'net_cents': 0, 'status': 'settled'}, id="T-0121"),
        pytest.param('ACCT-000001', 1, {'account_id': 'ACCT-000001', 'amount_cents': 1, 'fee_cents': 0, 'net_cents': 1, 'status': 'settled'}, id="T-0122"),
        pytest.param('ACCT-000039', 39, {'account_id': 'ACCT-000039', 'amount_cents': 39, 'fee_cents': 0, 'net_cents': 39, 'status': 'settled'}, id="T-0123"),
        pytest.param('ACCT-000040', 40, {'account_id': 'ACCT-000040', 'amount_cents': 40, 'fee_cents': 0, 'net_cents': 40, 'status': 'settled'}, id="T-0124"),
        pytest.param('ACCT-000100', 100, {'account_id': 'ACCT-000100', 'amount_cents': 100, 'fee_cents': 0, 'net_cents': 100, 'status': 'settled'}, id="T-0125"),
        pytest.param('ACCT-000101', 101, {'account_id': 'ACCT-000101', 'amount_cents': 101, 'fee_cents': 0, 'net_cents': 101, 'status': 'settled'}, id="T-0126"),
        pytest.param('ACCT-000999', 999, {'account_id': 'ACCT-000999', 'amount_cents': 999, 'fee_cents': 2, 'net_cents': 997, 'status': 'settled'}, id="T-0127"),
        pytest.param('ACCT-001000', 1000, {'account_id': 'ACCT-001000', 'amount_cents': 1000, 'fee_cents': 2, 'net_cents': 998, 'status': 'settled'}, id="T-0128"),
        pytest.param('ACCT-002500', 2500, {'account_id': 'ACCT-002500', 'amount_cents': 2500, 'fee_cents': 6, 'net_cents': 2494, 'status': 'settled'}, id="T-0129"),
        pytest.param('ACCT-010000', 10000, {'account_id': 'ACCT-010000', 'amount_cents': 10000, 'fee_cents': 25, 'net_cents': 9975, 'status': 'settled'}, id="T-0130"),
        pytest.param('ACCT-012345', 12345, {'account_id': 'ACCT-012345', 'amount_cents': 12345, 'fee_cents': 30, 'net_cents': 12315, 'status': 'settled'}, id="T-0131"),
        pytest.param('ACCT-099999', 99999, {'account_id': 'ACCT-099999', 'amount_cents': 99999, 'fee_cents': 249, 'net_cents': 99750, 'status': 'settled'}, id="T-0132"),
        pytest.param('ACCT-100000', 100000, {'account_id': 'ACCT-100000', 'amount_cents': 100000, 'fee_cents': 250, 'net_cents': 99750, 'status': 'settled'}, id="T-0133"),
        pytest.param('ACCT-250000', 250000, {'account_id': 'ACCT-250000', 'amount_cents': 250000, 'fee_cents': 625, 'net_cents': 249375, 'status': 'settled'}, id="T-0134"),
        pytest.param('ACCT-000400', 400, {'account_id': 'ACCT-000400', 'amount_cents': 400, 'fee_cents': 1, 'net_cents': 399, 'status': 'settled'}, id="T-0135"),
        pytest.param('ACCT-000800', 800, {'account_id': 'ACCT-000800', 'amount_cents': 800, 'fee_cents': 2, 'net_cents': 798, 'status': 'settled'}, id="T-0136"),
        pytest.param('ACCT-001200', 1200, {'account_id': 'ACCT-001200', 'amount_cents': 1200, 'fee_cents': 3, 'net_cents': 1197, 'status': 'settled'}, id="T-0137"),
        pytest.param('ACCT-001600', 1600, {'account_id': 'ACCT-001600', 'amount_cents': 1600, 'fee_cents': 4, 'net_cents': 1596, 'status': 'settled'}, id="T-0138"),
        pytest.param('ACCT-002000', 2000, {'account_id': 'ACCT-002000', 'amount_cents': 2000, 'fee_cents': 5, 'net_cents': 1995, 'status': 'settled'}, id="T-0139"),
        pytest.param('ACCT-002400', 2400, {'account_id': 'ACCT-002400', 'amount_cents': 2400, 'fee_cents': 6, 'net_cents': 2394, 'status': 'settled'}, id="T-0140"),
        pytest.param('ACCT-003600', 3600, {'account_id': 'ACCT-003600', 'amount_cents': 3600, 'fee_cents': 9, 'net_cents': 3591, 'status': 'settled'}, id="T-0141"),
        pytest.param('ACCT-004800', 4800, {'account_id': 'ACCT-004800', 'amount_cents': 4800, 'fee_cents': 12, 'net_cents': 4788, 'status': 'settled'}, id="T-0142"),
        pytest.param('ACCT-006000', 6000, {'account_id': 'ACCT-006000', 'amount_cents': 6000, 'fee_cents': 15, 'net_cents': 5985, 'status': 'settled'}, id="T-0143"),
        pytest.param('ACCT-007200', 7200, {'account_id': 'ACCT-007200', 'amount_cents': 7200, 'fee_cents': 18, 'net_cents': 7182, 'status': 'settled'}, id="T-0144"),
        pytest.param('ACCT-008400', 8400, {'account_id': 'ACCT-008400', 'amount_cents': 8400, 'fee_cents': 21, 'net_cents': 8379, 'status': 'settled'}, id="T-0145"),
    ],
)
def test_settle(account_id, amount_cents, expected):
    """Settle."""
    assert settle(account_id, amount_cents) == expected


