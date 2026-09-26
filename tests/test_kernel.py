"""The kernel is the trust boundary: it accepts, rejects and downgrades."""
import json
import pathlib

import pytest

from bob_session import gate as gate_mod
from bob_session import verify
from bob_session.pipeline import artefact as artefact_mod
from bob_session.pipeline.index import RepoIndex
from bob_session.proposal_cache import ProposalCache, bundle_digest, cache_key
from bob_session.pipeline import context as context_loader

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"


@pytest.fixture(scope="module")
def ctx():
    return context_loader.load(str(DEMO), str(ROOT / "diffs/change_b.patch"), str(DEMO / "inventory.csv"))


def _claim(**overrides):
    claim = {
        "claim_type": "link_exists",
        "role": "scout",
        "targets": {
            "test_id": "T-0342",
            "test_node": "tests/test_report_worker.py::test_cache_roundtrip_contract",
            "consumer": "app.workers.report_worker.parse_recent_cache_entries",
        },
        "citations": [
            {"path": "tests/test_report_worker.py", "symbol": "test_cache_roundtrip_contract", "line": 9},
            {"path": "app/workers/report_worker.py", "symbol": "parse_recent_cache_entries", "line": 16},
        ],
        "confidence": "high",
        "rationale": "test",
    }
    claim["targets"].update(overrides.pop("targets", {}))
    claim.update(overrides)
    return claim


def test_a_valid_claim_is_accepted(ctx):
    result = verify.verify_claims([_claim()], repo_root=ctx.repo_path, index=ctx.index, symbolic_selection=set())
    assert len(result["accepted"]) == 1 and not result["rejected"]
    assert "referenced by" in result["accepted"][0]["obligation"]


def test_a_fabricated_symbol_is_rejected(ctx):
    claim = _claim()
    claim["citations"][1]["symbol"] = "parse_recent_cache_entries_v2"
    result = verify.verify_claims([claim], repo_root=ctx.repo_path, index=ctx.index, symbolic_selection=set())
    assert result["rejected"][0]["gate"] == "symbol_mismatch"


def test_a_fabricated_path_is_rejected(ctx):
    claim = _claim()
    claim["citations"][1]["path"] = "app/workers/report_parser.py"
    result = verify.verify_claims([claim], repo_root=ctx.repo_path, index=ctx.index, symbolic_selection=set())
    assert result["rejected"][0]["gate"] == "citation_invalid"


def test_a_claim_without_citations_is_rejected(ctx):
    claim = _claim(citations=[])
    result = verify.verify_claims([claim], repo_root=ctx.repo_path, index=ctx.index, symbolic_selection=set())
    assert result["rejected"][0]["gate"] == "citation_invalid"


def test_a_claim_contradicting_the_symbolic_layer_is_rejected(ctx):
    claim = _claim(targets={"test_id": "T-0343", "asserts": "no_link"})
    result = verify.verify_claims([claim], repo_root=ctx.repo_path, index=ctx.index, symbolic_selection={"T-0343"})
    assert result["rejected"][0]["gate"] == "contradicts_symbolic"


def test_a_plausible_but_unwitnessed_claim_is_unconfirmed(ctx):
    claim = _claim(targets={"consumer": "app.models.Report"})
    result = verify.verify_claims([claim], repo_root=ctx.repo_path, index=ctx.index, symbolic_selection=set())
    assert result["unconfirmed"] and not result["accepted"]


def test_coverage_is_admissible_as_a_positive_witness(ctx):
    coverage = verify.coverage_from_evidence(ROOT / "bob_session/evidence/coverage_b.json")
    claim = _claim(targets={"consumer": "app.models.Report"})
    claim["citations"][1] = {"path": "app/workers/report_worker.py", "symbol": "parse_recent_cache_entries", "line": 23}
    result = verify.verify_claims(
        [claim], repo_root=ctx.repo_path, index=ctx.index, symbolic_selection=set(), coverage=coverage
    )
    assert result["accepted"] and "coverage witness" in result["accepted"][0]["obligation"]


def test_intent_quote_must_be_byte_present(ctx):
    claim = {
        "claim_type": "intent",
        "role": "cartographer",
        "targets": {
            "symbol": "app.services.cache_service.write_cache_entry",
            "quote": "Entries are stored in a compact binary format",
            "violated_tag": "sep:|",
        },
        "citations": [{"path": "app/services/cache_service.py", "symbol": "write_cache_entry", "line": 40}],
        "confidence": "low",
        "rationale": "fabricated quote",
    }
    result = verify.verify_claims([claim], repo_root=ctx.repo_path, index=ctx.index, symbolic_selection=set())
    assert result["rejected"][0]["gate"] == "citation_invalid"


def test_intent_claim_is_accepted_when_the_code_no_longer_satisfies_it(ctx):
    claim = {
        "claim_type": "intent",
        "role": "cartographer",
        "targets": {
            "symbol": "app.services.cache_service.write_cache_entry",
            "quote": "Entries are serialised as pipe-delimited text before they are handed to the",
            "violated_tag": "sep:|",
        },
        "citations": [{"path": "app/services/cache_service.py", "symbol": "write_cache_entry", "line": 40}],
        "confidence": "high",
        "rationale": "anchored",
    }
    from bob_session.pipeline.coupling import text_tags
    from bob_session.pipeline.dispositions import document_symbol

    intent_lines = {
        document_symbol(change.module, change.symbol): sorted(text_tags(text for text, _ in change.removed))
        for change in ctx.semantic
    }
    result = verify.verify_claims(
        [claim], repo_root=ctx.repo_path, index=ctx.index, symbolic_selection=set(), intent_lines=intent_lines
    )
    assert result["accepted"]


def test_author_claim_needs_gate_evidence(ctx):
    claim = {
        "claim_type": "test",
        "role": "author",
        "targets": {"symbol": "app.services.cache_service._should_drop"},
        "citations": [{"path": "app/services/cache_service.py", "symbol": "_should_drop", "line": 20}],
        "confidence": "med",
        "rationale": "patch",
    }
    without = verify.verify_claims([claim], repo_root=ctx.repo_path, index=ctx.index, symbolic_selection=set())
    assert without["unconfirmed"][0]["reason"].startswith("no gate evidence")
    with_evidence = verify.verify_claims(
        [claim], repo_root=ctx.repo_path, index=ctx.index, symbolic_selection=set(),
        gate_evidence={"accepted": True},
    )
    assert with_evidence["accepted"]


def test_gate_evidence_rejects_a_bad_authored_test(ctx):
    claim = {
        "claim_type": "test",
        "role": "author",
        "targets": {"symbol": "app.services.cache_service._should_drop"},
        "citations": [{"path": "app/services/cache_service.py", "symbol": "_should_drop", "line": 20}],
        "confidence": "med",
        "rationale": "patch",
    }
    result = verify.verify_claims(
        [claim], repo_root=ctx.repo_path, index=ctx.index, symbolic_selection=set(),
        gate_evidence={"accepted": False, "detail": "G3 failed"},
    )
    assert result["rejected"][0]["gate"] == "contradicts_symbolic"


def test_failure_origin_distinguishes_errors_from_assertions():
    assert gate_mod.failure_origin("E   AssertionError: nope") == "assertion"
    assert gate_mod.failure_origin("E       assert 0 == 1") == "assertion"
    assert gate_mod.failure_origin("E   AttributeError: module has no attribute") == "error"
    assert gate_mod.failure_origin("ERROR collecting tests/test_x.py") == "collection"


def test_mutant_lines_are_restricted_to_the_changed_lines():
    mutants = gate_mod.mutant_lines(
        [('        return is_expired(int(value.get("expires_at", 0)), moment) or value.get("status") == "expired"', 79)]
    )
    assert len(mutants) >= 3
    assert all(number == 79 for _, number, _ in mutants)
    assert any("and" in mutated for _, _, mutated in mutants)


def test_mutant_lines_skip_comments_and_blanks():
    assert gate_mod.mutant_lines([("# a comment", 1), ("", 2)]) == []


def test_gate_evidence_is_accepted_for_the_recorded_author_patch():
    evidence = json.loads((ROOT / "bob_session/evidence/gate_author.json").read_text(encoding="utf-8"))
    assert evidence["accepted"] is True
    assert evidence["g1_buildable"] and evidence["g2_passes_5x"]
    assert evidence["g3_assertion_fires_at_a"] and evidence["g3_failure_origin"] == "assertion"
    assert evidence["g4_mutation_strength"] >= gate_mod.MUTATION_THRESHOLD
    assert evidence["g5_spec_anchored"] is None and evidence["capability"] == "PINS"


def test_proposal_cache_keys_are_content_addressed(tmp_path):
    cache = ProposalCache(tmp_path)
    digest = bundle_digest("scout", {"a": 1})
    assert cache.lookup("scout", "v2.0.0", digest) is None
    cache.store("scout", "v2.0.0", digest, {"coins": 3, "claims": [{"claim_type": "link_exists"}]})
    entry = cache.lookup("scout", "v2.0.0", digest)
    assert entry["coins"] == 3 and len(entry["claims"]) == 1
    assert cache_key("scout", "v2.0.0", digest).startswith("scout-v2.0.0-")


def test_bundle_digest_changes_with_the_bundle():
    assert bundle_digest("scout", {"a": 1}) != bundle_digest("scout", {"a": 2})
    assert bundle_digest("scout", {"a": 1}) == bundle_digest("scout", {"a": 1})


def test_artefact_validator_accepts_the_committed_artefact():
    artefact = json.loads((ROOT / "bob_session/testscope_report.json").read_text(encoding="utf-8"))
    assert artefact_mod.validate(artefact) == []


def test_artefact_validator_catches_a_double_count():
    artefact = json.loads((ROOT / "bob_session/testscope_report.json").read_text(encoding="utf-8"))
    artefact["classification"]["semantically_affected"].append(artefact["classification"]["definitely_affected"][0])
    problems = artefact_mod.validate(artefact)
    assert any(problem.startswith("I1") for problem in problems)


def test_artefact_validator_catches_a_rejection_ledger_mismatch():
    artefact = json.loads((ROOT / "bob_session/testscope_report.json").read_text(encoding="utf-8"))
    artefact["rejection_ledger"].pop()
    assert any(problem.startswith("I16") for problem in artefact_mod.validate(artefact))


def test_artefact_validator_catches_a_wrong_summary_count():
    artefact = json.loads((ROOT / "bob_session/testscope_report.json").read_text(encoding="utf-8"))
    artefact["summary"]["stale_count"] += 1
    assert any(problem.startswith("I13") for problem in artefact_mod.validate(artefact))


def test_artefact_serialisation_is_canonical():
    artefact = json.loads((ROOT / "bob_session/testscope_report.json").read_text(encoding="utf-8"))
    first = artefact_mod.dumps(artefact)
    second = artefact_mod.dumps(json.loads(first))
    assert first == second
    assert artefact_mod.digest(artefact) == artefact_mod.digest(json.loads(first))
