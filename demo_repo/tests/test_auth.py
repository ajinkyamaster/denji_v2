"""Token hashing and role scopes."""

import pytest

from app.api.auth import hash_token, is_allowed, scopes_for, verify_token


@pytest.mark.parametrize(
    'token, expected',
    [
        pytest.param('', 'e3b0c44298fc1c14', id="T-0286"),
        pytest.param('a', 'ca978112ca1bbdca', id="T-0287"),
        pytest.param('token-1', '3f08aace122ee236', id="T-0288"),
        pytest.param('1111111111111111111111111111111111111111111111111111111111111111', '3138bb9bc78df27c', id="T-0289"),
        pytest.param('üñïçø∂é', '66b47e2f6fe3e06b', id="T-0290"),
    ],
)
def test_hash_token(token, expected):
    """Hash token."""
    assert hash_token(token) == expected


@pytest.mark.parametrize(
    'token, digest, expected',
    [
        pytest.param('', 'e3b0c44298fc1c14', True, id="T-0291"),
        pytest.param('a', 'ca978112ca1bbdca', True, id="T-0292"),
        pytest.param('token-1', '3f08aace122ee236', True, id="T-0293"),
        pytest.param('1111111111111111111111111111111111111111111111111111111111111111', '3138bb9bc78df27c', True, id="T-0294"),
        pytest.param('üñïçø∂é', 'a21f0a021a9de5eb', False, id="T-0295"),
    ],
)
def test_verify_token(token, digest, expected):
    """Verify token."""
    assert verify_token(token, digest) is expected


@pytest.mark.parametrize(
    'role, expected',
    [
        pytest.param('viewer', ['read'], id="T-0296"),
        pytest.param('operator', ['read', 'write'], id="T-0297"),
        pytest.param('admin', ['delete', 'read', 'write'], id="T-0298"),
        pytest.param('auditor', [], id="T-0299"),
        pytest.param('ADMIN', [], id="T-0300"),
    ],
)
def test_scopes_for(role, expected):
    """Scopes for."""
    assert scopes_for(role) == expected


@pytest.mark.parametrize(
    'role, scope, expected',
    [
        pytest.param('viewer', 'read', True, id="T-0301"),
        pytest.param('viewer', 'write', False, id="T-0302"),
        pytest.param('operator', 'write', True, id="T-0303"),
        pytest.param('admin', 'delete', True, id="T-0304"),
        pytest.param('auditor', 'read', False, id="T-0305"),
    ],
)
def test_is_allowed(role, scope, expected):
    """Is allowed."""
    assert is_allowed(role, scope) is expected


