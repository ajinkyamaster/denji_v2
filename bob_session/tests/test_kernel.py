"""The kernel: citations are obligations, and confidence buys nothing.

T5 shows a fabricated citation cannot be smuggled through; T6 shows line drift is
*defined* behaviour, because moving code is not lying. Both directions matter: a
verifier that rejects everything is as useless as one that accepts everything, and
a verifier that reads `confidence` would let a persuasive model promote itself.
"""

import pytest

from bob_session.pipeline.diff_parser import parse_diff
from bob_session.pipeline.inventory import load_inventory
from bob_session.verify import verify_claims

from .conftest import CHANGE, DEMO, INVENTORY

REPO = str(DEMO)


@pytest.fixture(scope="module")
def inventory():
    return load_inventory(INVENTORY)


@pytest.fixture(scope="module")
def diff():
    return parse_diff(CHANGE.read_text(encoding="utf-8"), source=str(CHANGE))


def _claim(**overrides):
    claim = {
        "claim_type": "link_exists",
        "role": "scout",
        "targets": {"test_id": "T-0342", "consumer_symbol": "parse_recent_cache_entries"},
        "citations": [
            {"path": "app/workers/report_worker.py", "symbol": "parse_recent_cache_entries", "line": 27}
        ],
        "confidence": "high",
        "rationale": "the report worker parses a format the cache service produces",
    }
    claim.update(overrides)
    return claim


def test_T5_kernel_rejects_a_fabricated_citation(inventory):
    result = verify_claims(
        [_claim(citations=[{"path": "app/services/does_not_exist.py", "symbol": "ghost", "line": 1}])],
        repo=REPO,
        inventory=inventory,
    )
    assert len(result["rejected"]) == 1
    assert result["rejected"][0]["gate"] == "citation_invalid"
    assert result["accepted"] == []


def test_T6_kernel_accepts_a_drifting_line_if_the_symbol_resolves(inventory):
    result = verify_claims(
        [_claim(citations=[{"path": "app/workers/report_worker.py", "symbol": "parse_recent_cache_entries", "line": 999}])],
        repo=REPO,
        inventory=inventory,
    )
    assert len(result["accepted"]) == 1
    assert "line_drift" in result["accepted"][0]["obligation"]


def test_symbol_mismatch_rejects_even_when_the_file_exists(inventory):
    result = verify_claims(
        [_claim(citations=[{"path": "app/workers/report_worker.py", "symbol": "invented_symbol", "line": 1}])],
        repo=REPO,
        inventory=inventory,
    )
    assert result["rejected"][0]["gate"] == "symbol_mismatch"


def test_confidence_never_affects_acceptance(inventory):
    for confidence in ("low", "med", "high"):
        result = verify_claims([_claim(confidence=confidence)], repo=REPO, inventory=inventory)
        assert len(result["accepted"]) == 1, "confidence must not gate acceptance"


def test_unknown_test_id_is_rejected(inventory):
    result = verify_claims(
        [_claim(targets={"test_id": "T-9999", "consumer_symbol": "parse_recent_cache_entries"})],
        repo=REPO,
        inventory=inventory,
    )
    assert result["rejected"][0]["gate"] == "citation_invalid"


def test_schema_violations_are_named(inventory):
    cases = [
        _claim(claim_type="invented"),
        _claim(role="wizard"),
        _claim(rationale="x" * 300),
        _claim(citations=[]),
    ]
    for claim in cases:
        result = verify_claims([claim], repo=REPO, inventory=inventory)
        assert result["rejected"][0]["gate"] == "schema_violation"


def test_missed_claim_on_an_already_selected_test_contradicts_the_symbolic_layer(inventory, diff):
    result = verify_claims(
        [
            {
                "claim_type": "missed",
                "role": "falsifier",
                "targets": {"test_id": "T-0342"},
                "citations": [
                    {"path": "app/services/cache_service.py", "symbol": "write_cache_entry", "line": 19}
                ],
                "confidence": "med",
                "rationale": "maybe this one should run",
            }
        ],
        repo=REPO,
        inventory=inventory,
        diff=diff,
        selected_ids={"T-0342"},
    )
    assert result["rejected"][0]["gate"] == "contradicts_symbolic"


def test_missed_claim_whose_path_re_derives_is_accepted(inventory, diff):
    result = verify_claims(
        [
            {
                "claim_type": "missed",
                "role": "falsifier",
                "targets": {"test_id": "T-0460"},
                "citations": [
                    {"path": "tests/test_cache_service.py", "symbol": "write_cache_entry", "line": 9},
                    {"path": "app/services/cache_service.py", "symbol": "write_cache_entry", "line": 19},
                ],
                "confidence": "med",
                "rationale": "the cache test file reaches the changed symbol",
            }
        ],
        repo=REPO,
        inventory=inventory,
        diff=diff,
        selected_ids={"T-0342"},
    )
    assert result["accepted"], result["rejected"]


def test_missed_claim_ending_outside_the_change_is_rejected(inventory, diff):
    result = verify_claims(
        [
            {
                "claim_type": "missed",
                "role": "falsifier",
                "targets": {"test_id": "T-0460"},
                "citations": [{"path": "app/utils/text.py", "symbol": "normalise_slug", "line": 12}],
                "confidence": "med",
                "rationale": "claims a dependency the change does not touch",
            }
        ],
        repo=REPO,
        inventory=inventory,
        diff=diff,
        selected_ids=set(),
    )
    assert result["rejected"][0]["gate"] == "contradicts_symbolic"


def test_intent_claim_verifies_a_specification_the_change_removed(inventory, diff):
    result = verify_claims(
        [
            {
                "claim_type": "intent",
                "role": "cartographer",
                "targets": {"quote": "Entries are serialised as pipe-delimited records"},
                "citations": [
                    {"path": "app/services/cache_service.py", "symbol": "write_cache_entry", "line": 1}
                ],
                "confidence": "med",
                "rationale": "the module docstring declared the format the change removed",
            }
        ],
        repo=REPO,
        inventory=inventory,
        diff=diff,
    )
    assert result["accepted"], result["rejected"]


def test_intent_claim_is_rejected_when_the_quote_is_not_byte_present(inventory, diff):
    result = verify_claims(
        [
            {
                "claim_type": "intent",
                "role": "cartographer",
                "targets": {"quote": "the cache is written as CSV rows"},
                "citations": [
                    {"path": "app/services/cache_service.py", "symbol": "write_cache_entry", "line": 1}
                ],
                "confidence": "high",
                "rationale": "invented specification",
            }
        ],
        repo=REPO,
        inventory=inventory,
        diff=diff,
    )
    assert result["rejected"][0]["gate"] == "quote_not_present"


def test_intent_claim_on_a_live_spec_without_a_removed_representation_is_rejected(inventory, diff):
    result = verify_claims(
        [
            {
                "claim_type": "intent",
                "role": "cartographer",
                "targets": {"quote": "Recent-activity reporting."},
                "citations": [
                    {"path": "app/workers/report_worker.py", "symbol": "parse_recent_cache_entries", "line": 1}
                ],
                "confidence": "high",
                "rationale": "still true after the change",
            }
        ],
        repo=REPO,
        inventory=inventory,
        diff=diff,
    )
    assert result["rejected"][0]["gate"] == "contradicts_symbolic"


def test_coverage_is_accepted_only_as_a_positive_witness(inventory):
    """Absence of coverage must never reject a link: coverage is one-sided (A1).

    The symbol is ``recent_keys``: defined in the cited file, but *not* referenced
    by ``tests/test_report_worker.py``. That matters - if the test file referenced
    it, the reference mechanism would accept before coverage was ever consulted and
    this test would prove nothing about the coverage path it is named after.
    """
    claim = _claim(
        targets={"test_id": "T-0342", "consumer_symbol": "recent_keys"},
        citations=[{"path": "app/workers/report_worker.py", "symbol": "recent_keys", "line": 41}],
    )
    without = verify_claims([claim], repo=REPO, inventory=inventory)
    assert without["accepted"] == [] and without["unconfirmed"], "silence is not rejection"
    assert without["rejected"] == [], "absence of coverage may never become a rejection (A1)"
    with_witness = verify_claims(
        [claim],
        repo=REPO,
        inventory=inventory,
        coverage={"app/workers/report_worker.py": {"41": True}},
    )
    assert with_witness["accepted"], "a coverage witness must be admissible in the positive direction"
    assert "coverage" in with_witness["accepted"][0]["obligation"]


def test_a_coverage_witness_must_attest_the_cited_site_not_some_other_line(inventory):
    """The witness is anchored to the citation, because the citation is the obligation.

    If a model could aim the witness at a line its citation never named, it would
    be attesting a site the claim never asserted - an unsound accept by indirection.
    Two variants: a witness aimed at a different line accepts nothing, and a claim
    whose ``targets`` contradict its own citation is rejected outright rather than
    guessed at.
    """
    claim = _claim(
        targets={"test_id": "T-0342", "consumer_symbol": "recent_keys"},
        citations=[{"path": "app/workers/report_worker.py", "symbol": "recent_keys", "line": 41}],
    )
    wrong_line = verify_claims(
        [claim], repo=REPO, inventory=inventory, coverage={"app/workers/report_worker.py": {"19": True}}
    )
    assert wrong_line["accepted"] == [], "a witness at an uncited line proves nothing"
    contradictory = _claim(
        targets={
            "test_id": "T-0342",
            "consumer_symbol": "recent_keys",
            "consumer_path": "app/workers/report_worker.py",
            "consumer_line": 19,
        },
        citations=[{"path": "app/workers/report_worker.py", "symbol": "recent_keys", "line": 41}],
    )
    result = verify_claims(
        [contradictory],
        repo=REPO,
        inventory=inventory,
        coverage={"app/workers/report_worker.py": {"19": True}},
    )
    assert result["accepted"] == [] and result["rejected"]
    assert result["rejected"][0]["gate"] == "contradicts_symbolic", (
        "a claim that points its witness away from its own citation is internally contradictory; "
        "the kernel refuses to pick a side"
    )


def test_a_test_claim_without_the_gate_is_unconfirmed_not_accepted(inventory):
    result = verify_claims(
        [
            {
                "claim_type": "test",
                "role": "author",
                "targets": {"symbol": "app.services.cache_service.purge_stale_entries"},
                "citations": [],
                "confidence": "med",
                "rationale": "a test for the new purge helper",
            }
        ],
        repo=REPO,
        inventory=inventory,
    )
    assert result["unconfirmed"], "G1..G5 are decided by execution, never by the kernel's opinion"
    assert result["accepted"] == []
