"""Recent-cache reporting.

This module is the consumer side of the cache wire format. It imports nothing
from the cache service, and the cache service imports nothing from it: the two
are bound only by the record format they exchange.

Three tests here are marked ``contract`` and are excluded by the repository's
default marker filter (see ``pytest.ini``). That exclusion is the blind spot
invariant O1 exists to catch: a default run collects 497 tests, not 500, and the
three tests it drops are the only ones that observe the format end to end. A
measurement from that instrument is VOID, not reassuring.

The contract tests drive the producer through its command-line job in a child
process, so the test process never imports the producer. The dependency is real
and travels through a file; the import graph cannot see it.
"""

import pathlib
import subprocess
import sys

import pytest

from app.workers.report_worker import (
    parse_recent_cache_entries,
    read_cache_file,
    summarise_entries,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_cache.py"


def build_cache_file(destination):
    """Run the cache builder in a child process and return the destination path.

    A child process on purpose: the test process must not import the producer,
    because the dependency under test travels through a *file*, not through the
    import graph. That is also why the coverage instrument is blind here, which
    is the live instance of the triage refinement in this repository.
    """
    result = subprocess.run(
        [sys.executable, str(BUILD_SCRIPT), "--out", str(destination)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return destination


# --------------------------------------------------------------------------- #
# parsing, in isolation: these do not depend on what the producer writes       #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "payloads,expected",
    [
        pytest.param(
            ["k|ok|2", "junk"],
            [{"key": "k", "status": "ok", "count": 2}, {"raw": "junk"}],
            id="T-0338",
        ),
    ],
)
def test_parse_keeps_unknown_payloads(payloads, expected):
    """A payload that is not three fields is kept, not dropped."""
    assert parse_recent_cache_entries(payloads) == expected


@pytest.mark.parametrize(
    "payloads,expected",
    [
        pytest.param(
            ["k|ok|2"],
            [{"key": "k", "status": "ok", "count": 2}],
            id="T-0339",
        ),
    ],
)
def test_parse_pipe_records(payloads, expected):
    """A well-formed record parses field by field."""
    assert parse_recent_cache_entries(payloads) == expected


@pytest.mark.parametrize(
    "payloads,expected",
    [
        pytest.param(["a|ok|2", "b|ok|3"], 5, id="T-0343"),
    ],
)
def test_summarise_entries_totals_counts(payloads, expected):
    """Counts add up across records."""
    assert summarise_entries(payloads) == expected


# --------------------------------------------------------------------------- #
# the contract: what the producer writes must be what the consumer reads       #
# --------------------------------------------------------------------------- #
@pytest.mark.contract
@pytest.mark.parametrize("case", [pytest.param("default-rows", id="T-0340")])
def test_recent_entries_round_trip_contract(case, tmp_path):
    """Every field written by the cache job survives the round trip."""
    cache_path = build_cache_file(tmp_path / "recent.cache")
    parsed = parse_recent_cache_entries(read_cache_file(cache_path))
    assert parsed == [
        {"key": "acct-1", "status": "ok", "count": 2},
        {"key": "acct-2", "status": "retry", "count": 1},
        {"key": "acct-3", "status": "failed", "count": 4},
    ]


@pytest.mark.contract
@pytest.mark.parametrize("case", [pytest.param("statuses", id="T-0341")])
def test_recent_entries_round_trip_statuses(case, tmp_path):
    """The status field survives the round trip, in order."""
    cache_path = build_cache_file(tmp_path / "recent.cache")
    parsed = parse_recent_cache_entries(read_cache_file(cache_path))
    assert [record.get("status") for record in parsed] == ["ok", "retry", "failed"]


@pytest.mark.contract
@pytest.mark.parametrize("case", [pytest.param("totals", id="T-0342")])
def test_recent_entries_round_trip_totals(case, tmp_path):
    """The counts written by the job are the counts the report reads."""
    cache_path = build_cache_file(tmp_path / "recent.cache")
    assert summarise_entries(read_cache_file(cache_path)) == 7
