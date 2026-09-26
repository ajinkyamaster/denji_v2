"""Batch splitting for export jobs."""

import pytest

from app.workers.export_worker import batch, batch_count, flatten


@pytest.mark.parametrize(
    'items, size, expected',
    [
        pytest.param([], 3, [], id="T-0430"),
        pytest.param([1], 3, [[1]], id="T-0431"),
        pytest.param([1, 2, 3], 3, [[1, 2, 3]], id="T-0432"),
        pytest.param([1, 2, 3, 4], 3, [[1, 2, 3], [4]], id="T-0433"),
        pytest.param([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], 4, [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9]], id="T-0434"),
        pytest.param([1, 2], 1, [[1], [2]], id="T-0435"),
        pytest.param([], 1, [], id="T-0436"),
        pytest.param([0, 1, 2, 3, 4, 5], 2, [[0, 1], [2, 3], [4, 5]], id="T-0437"),
        pytest.param([1, 2, 3], 10, [[1, 2, 3]], id="T-0438"),
        pytest.param([0, 1, 2, 3, 4], 5, [[0, 1, 2, 3, 4]], id="T-0439"),
    ],
)
def test_batch(items, size, expected):
    """Batch."""
    assert batch(items, size) == expected


@pytest.mark.parametrize(
    'total, size, expected',
    [
        pytest.param(0, 10, 0, id="T-0440"),
        pytest.param(1, 10, 1, id="T-0441"),
        pytest.param(10, 10, 1, id="T-0442"),
        pytest.param(11, 10, 2, id="T-0443"),
        pytest.param(100, 100, 1, id="T-0444"),
        pytest.param(101, 100, 2, id="T-0445"),
        pytest.param(7, 3, 3, id="T-0446"),
        pytest.param(9, 3, 3, id="T-0447"),
        pytest.param(10, 3, 4, id="T-0448"),
        pytest.param(1000, 7, 143, id="T-0449"),
    ],
)
def test_batch_count(total, size, expected):
    """Batch count."""
    assert batch_count(total, size) == expected


@pytest.mark.parametrize(
    'batches, expected',
    [
        pytest.param([], [], id="T-0450"),
        pytest.param([[1]], [1], id="T-0451"),
        pytest.param([[1, 2], [3]], [1, 2, 3], id="T-0452"),
        pytest.param([[], [1]], [1], id="T-0453"),
        pytest.param([[1], [], [2]], [1, 2], id="T-0454"),
        pytest.param([[0, 1, 2], [3, 4]], [0, 1, 2, 3, 4], id="T-0455"),
        pytest.param([['a'], ['b', 'c']], ['a', 'b', 'c'], id="T-0456"),
        pytest.param([[1, 2, 3]], [1, 2, 3], id="T-0457"),
        pytest.param([[1], [2], [3], [4]], [1, 2, 3, 4], id="T-0458"),
        pytest.param([[], []], [], id="T-0459"),
    ],
)
def test_flatten(batches, expected):
    """Flatten."""
    assert flatten(batches) == expected


