"""Event ingestion. Payloads are asserted by shape only, never by wire
format, so these tests stay green across format changes."""

import pytest

from app.workers.ingest_worker import ingest_batch, normalise_status, summarise_batch


@pytest.mark.parametrize(
    'raw',
    [
        pytest.param('', id="T-0472"),
    ],
)
def test_normalise_status(raw):
    """Normalise status."""
    assert normalise_status(raw) == 'retry'


@pytest.mark.parametrize(
    'events',
    [
        pytest.param([{'key': 'k1', 'status': 'ok'}, {'key': 'k2', 'status': 'nope'}], id="T-0473"),
    ],
)
def test_ingest_batch(events):
    """Ingest batch."""
    payloads = ingest_batch(events)
    assert len(payloads) == 2
    assert all(isinstance(payload, str) and payload for payload in payloads)


@pytest.mark.parametrize(
    'events',
    [
        pytest.param([{'key': 'a', 'status': 'ok'}, {'key': 'b', 'status': 'weird'}], id="T-0474"),
    ],
)
def test_summarise_batch(events):
    """Summarise batch."""
    assert summarise_batch(events) == {'ok': 1, 'retry': 1}


