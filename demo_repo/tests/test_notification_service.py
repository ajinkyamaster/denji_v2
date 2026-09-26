"""Notification channel selection and rendering."""

import pytest

from app.services.notification_service import body_length, channels_for, render_message, should_notify


@pytest.mark.parametrize(
    'account, expected',
    [
        pytest.param({'state': 'open'}, ['email', 'push'], id="T-0478"),
        pytest.param({'state': 'closed'}, ['email'], id="T-0479"),
        pytest.param({'state': 'frozen'}, ['email'], id="T-0480"),
        pytest.param({}, ['email'], id="T-0481"),
        pytest.param({'state': 'open', 'id': 'ACCT-1'}, ['email', 'push'], id="T-0482"),
    ],
)
def test_channels_for(account, expected):
    """Channels for."""
    assert channels_for(account) == expected


@pytest.mark.parametrize(
    'template, values, expected',
    [
        pytest.param('hello {name}', {'name': 'world'}, 'hello world', id="T-0483"),
        pytest.param('{a}-{b}', {'a': '1', 'b': '2'}, '1-2', id="T-0484"),
        pytest.param('no placeholders', {}, 'no placeholders', id="T-0485"),
        pytest.param('{x}{x}', {'x': 'ab'}, 'abab', id="T-0486"),
        pytest.param('total {amount} cents', {'amount': 250}, 'total 250 cents', id="T-0487"),
    ],
)
def test_render_message(template, values, expected):
    """Render message."""
    assert render_message(template, values) == expected


@pytest.mark.parametrize(
    'account, event, expected',
    [
        pytest.param({'state': 'open'}, 'settled', True, id="T-0488"),
        pytest.param({'state': 'closed'}, 'settled', True, id="T-0489"),
        pytest.param({'state': 'open'}, 'opened', True, id="T-0490"),
        pytest.param({'state': 'closed'}, 'opened', False, id="T-0491"),
        pytest.param({'state': 'open'}, 'ignored', False, id="T-0492"),
    ],
)
def test_should_notify(account, event, expected):
    """Should notify."""
    assert should_notify(account, event) is expected


@pytest.mark.parametrize(
    'message, expected',
    [
        pytest.param('', 0, id="T-0493"),
        pytest.param('abc', 3, id="T-0494"),
        pytest.param('xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', 239, id="T-0495"),
        pytest.param('xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', 240, id="T-0496"),
        pytest.param('xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', 240, id="T-0497"),
    ],
)
def test_body_length(message, expected):
    """Body length."""
    assert body_length(message) == expected


