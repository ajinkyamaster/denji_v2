"""Cache writing: asserts shape only, never the wire format.
The format itself is pinned end-to-end by tests/test_report_worker.py."""

import json

import pytest

from app.services.cache_service import read_cache_entries, write_cache_entry


@pytest.mark.parametrize(
    'key, status, count',
    [
        pytest.param('key-0', 'ok', 0, id="T-0460"),
    ],
)
def test_write_cache_entry_returns_a_payload(key, status, count):
    """Write cache entry returns a payload."""
    sink = []
    payload = write_cache_entry(key, status, count, sink=sink)
    assert isinstance(payload, str) and payload
    assert sink == [payload]


@pytest.mark.parametrize(
    'blank',
    [
        pytest.param(None, id="T-0461"),
    ],
)
def test_read_cache_entries(blank, tmp_path):
    """Read cache entries."""
    path = tmp_path / 'cache.txt'
    path.write_text('a\n\n b \n', encoding='utf-8')
    assert read_cache_entries(path) == ['a', ' b ']


@pytest.mark.parametrize(
    "case",
    [
        pytest.param("json-object", id="T-A001"),
    ],
)
def test_cache_entry_is_a_json_object(case):
    """An authored test added by the Author role, gated G1..G5.

    It is a patch test on purpose: it asserts the *serialised shape* and then
    parses it, so at the previous revision (a pipe-delimited record) the first
    assertion fires - an assertion failure, not an import error, which is exactly
    what G3 demands.
    """
    payload = write_cache_entry("k", "ok", 1)
    assert payload.startswith("{")
    assert json.loads(payload) == {"count": 1, "key": "k", "status": "ok"}
