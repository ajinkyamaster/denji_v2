"""Identifier formatting and sequencing."""

import pytest

from app.utils.ids import account_id, invoice_id, is_valid_id, next_sequence


@pytest.mark.parametrize(
    'number, expected',
    [
        pytest.param(0, 'ACCT-000000', id="T-0246"),
        pytest.param(1, 'ACCT-000001', id="T-0247"),
        pytest.param(9, 'ACCT-000009', id="T-0248"),
        pytest.param(10, 'ACCT-000010', id="T-0249"),
        pytest.param(99, 'ACCT-000099', id="T-0250"),
        pytest.param(100, 'ACCT-000100', id="T-0251"),
        pytest.param(999, 'ACCT-000999', id="T-0252"),
        pytest.param(1000, 'ACCT-001000', id="T-0253"),
        pytest.param(999999, 'ACCT-999999', id="T-0254"),
        pytest.param(123456, 'ACCT-123456', id="T-0255"),
    ],
)
def test_account_id(number, expected):
    """Account id."""
    assert account_id(number) == expected


@pytest.mark.parametrize(
    'number, expected',
    [
        pytest.param(0, 'INV-000000', id="T-0256"),
        pytest.param(1, 'INV-000001', id="T-0257"),
        pytest.param(9, 'INV-000009', id="T-0258"),
        pytest.param(10, 'INV-000010', id="T-0259"),
        pytest.param(99, 'INV-000099', id="T-0260"),
        pytest.param(100, 'INV-000100', id="T-0261"),
        pytest.param(999, 'INV-000999', id="T-0262"),
        pytest.param(1000, 'INV-001000', id="T-0263"),
        pytest.param(999999, 'INV-999999', id="T-0264"),
        pytest.param(123456, 'INV-123456', id="T-0265"),
    ],
)
def test_invoice_id(number, expected):
    """Invoice id."""
    assert invoice_id(number) == expected


@pytest.mark.parametrize(
    'value, expected',
    [
        pytest.param('ACCT-000001', True, id="T-0266"),
        pytest.param('INV-000001', True, id="T-0267"),
        pytest.param('TXN-123456', True, id="T-0268"),
        pytest.param('ACCT-00000', False, id="T-0269"),
        pytest.param('ACCT-0000001', False, id="T-0270"),
        pytest.param('acct-000001', False, id="T-0271"),
        pytest.param('ACCT000001', False, id="T-0272"),
        pytest.param('ACCT-00000a', False, id="T-0273"),
        pytest.param('XXXX-000001', False, id="T-0274"),
        pytest.param(None, False, id="T-0275"),
    ],
)
def test_is_valid_id(value, expected):
    """Is valid id."""
    assert is_valid_id(value) is expected


@pytest.mark.parametrize(
    'values, expected',
    [
        pytest.param([], 1, id="T-0276"),
        pytest.param(['ACCT-000001'], 2, id="T-0277"),
        pytest.param(['ACCT-000009', 'ACCT-000003'], 10, id="T-0278"),
        pytest.param(['nonsense'], 1, id="T-0279"),
        pytest.param(['INV-000100', 'TXN-000050'], 101, id="T-0280"),
        pytest.param(['ACCT-999999'], 1000000, id="T-0281"),
        pytest.param(['ACCT-000001', 'nonsense', 'TXN-000002'], 3, id="T-0282"),
        pytest.param(['ACCT-00000'], 1, id="T-0283"),
        pytest.param(['ACCT-000020', 'INV-000019'], 21, id="T-0284"),
        pytest.param(['TXN-000042'], 43, id="T-0285"),
    ],
)
def test_next_sequence(values, expected):
    """Next sequence."""
    assert next_sequence(values) == expected


