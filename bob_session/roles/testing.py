"""Test doubles and unit builders for the cognitive layer.

These are NOT the kernel and NOT part of the production path. `StubVerifier` is a
configurable FAKE of `testscope_verify`; the real kernel is Person A's tool. The
layer's tests use these so they never depend on the server being present, and the
acceptance check can exercise the control flow end to end with zero coins.

`ScriptedProposer` stands in for a subagent: it returns pre-recorded model output,
in order, and records what it was asked. That is exactly the seam the cascade needs
to prove its properties (escalation, the two-tier cap, the safe direction) without
a live model.
"""

from __future__ import annotations

import json
from typing import Any

from . import envelope
from .errors import ModelUnavailable

# --------------------------------------------------------------------------- #
# unit builders -- shaped after the demo repository's counterexample
# --------------------------------------------------------------------------- #

DIFF = (
    "--- a/app/services/cache_service.py\n"
    "+++ b/app/services/cache_service.py\n"
    "@@ -28,7 +28,7 @@ def write_cache_entry(value):\n"
    '-    payload = f"{value[\'id\']}|{value[\'status\']}"\n'
    "+    payload = json.dumps(value)\n"
)


def scout_unit(**overrides: Any) -> dict:
    unit = {
        "unit_id": "pair:T-0342:write_cache_entry",
        "run_id": "run-fixture",
        "changed_symbol": "app.services.cache_service.write_cache_entry",
        "producer_call_site": "app/services/cache_service.py:31 (write_cache_entry)",
        "producer_format_expr": 'f"{value[\'id\']}|{value[\'status\']}" -> json.dumps(value)',
        "consumer_call_site": "app/workers/report_worker.py:44 (parse_recent_cache_entries)",
        "consumer_parse_site": 'entry.split("|")',
        "test_row": {
            "test_id": "T-0342",
            "test_name": "test_parse_recent_cache_entries_round_trip",
            "module": "app/workers/report_worker.py",
            "description": "cache entries round-trip through the report worker",
        },
        "diff_hunks": DIFF,
    }
    unit.update(overrides)
    return unit


def candidate_unit(**overrides: Any) -> dict:
    """One cascade unit: the scout's pair sites AND the cartographer's prose.

    A real unit carries both views, which is why the cascade can escalate from
    scout to cartographer without asking for new evidence from the orchestrator.
    """
    unit = scout_unit()
    prose = cartographer_unit()
    for key in ("changed_symbol_body", "intent_artefacts"):
        unit[key] = prose[key]
    unit.update(overrides)
    return unit


def cartographer_unit(**overrides: Any) -> dict:
    unit = {
        "unit_id": "file:app/workers/report_worker.py",
        "run_id": "run-fixture",
        "changed_symbol_body": (
            "def write_cache_entry(value):\n"
            '    payload = json.dumps(value)\n'
            "    _write(payload)\n"
        ),
        "intent_artefacts": [
            {
                "path": "app/workers/report_worker.py",
                "line": 7,
                "kind": "docstring",
                "text": (
                    "The exact shape of the string is still part of the service's "
                    "public contract: entries are pipe-delimited."
                ),
            }
        ],
        "diff_hunks": DIFF,
    }
    unit.update(overrides)
    return unit


def author_unit(**overrides: Any) -> dict:
    unit = {
        "unit_id": "uncovered:write_cache_entry",
        "run_id": "run-fixture",
        "symbol": "app.services.cache_service.write_cache_entry",
        "symbol_signature": "def write_cache_entry(value: dict) -> None",
        "test_class_file": "demo_repo/tests/services/test_cache_service.py",
        "test_class": "TestCacheService",
        "test_class_source": (
            "import json\n\n"
            "from app.services.cache_service import write_cache_entry\n\n\n"
            "class TestCacheService:\n"
            "    def test_write_then_read(self):\n"
            "        write_cache_entry({'id': 1, 'status': 'ok'})\n"
        ),
        "intent_artefact": {
            "path": "app/services/cache_service.py",
            "line": 12,
            "kind": "docstring",
            "text": "Entries are stored as pipe-delimited strings for downstream readers.",
        },
        "pre_change_body": (
            "def write_cache_entry(value):\n"
            '    payload = f"{value[\'id\']}|{value[\'status\']}"\n'
            "    _write(payload)\n"
        ),
    }
    unit.update(overrides)
    return unit


def falsifier_unit(**overrides: Any) -> dict:
    unit = {
        "unit_id": "falsifier",
        "run_id": "run-fixture",
        "final_ledger": {"selected": ["T-0342", "T-0187"], "stale": [], "unknown": []},
        "diff_hunks": DIFF,
        "unselected_rows": [
            {"test_id": "T-0404", "test_name": "test_roundtrip_cache_encoding"},
            {"test_id": "T-0405", "test_name": "test_cache_entry_serialisation"},
        ],
        "selected_ids": ["T-0342", "T-0187"],
    }
    unit.update(overrides)
    return unit


# --------------------------------------------------------------------------- #
# envelope builders
# --------------------------------------------------------------------------- #

CITATION_PRODUCER = {"path": "app/services/cache_service.py", "symbol": "write_cache_entry", "line": 31}
CITATION_CONSUMER = {"path": "app/workers/report_worker.py", "symbol": "parse_recent_cache_entries", "line": 44}


def scout_claim(
    test_id: str = "T-0342",
    changed_symbol: str = "app.services.cache_service.write_cache_entry",
    confidence: str = "high",
    citations: list | None = None,
) -> dict:
    return {
        "claim_type": "link_exists",
        "role": "scout",
        "targets": {"test_id": test_id, "changed_symbol": changed_symbol},
        "citations": list(citations if citations is not None else [CITATION_CONSUMER, CITATION_PRODUCER]),
        "confidence": confidence,
        "rationale": "consumer parses the wire format the producer changed",
    }


def intent_claim(changed_symbol: str = "app.services.cache_service.write_cache_entry") -> dict:
    return {
        "claim_type": "intent",
        "role": "cartographer",
        "targets": {
            "changed_symbol": changed_symbol,
            "quote": "The exact shape of the string is still part of the service's public contract: entries are pipe-delimited.",
            "contradiction": "the change replaces the pipe-delimited shape with json.dumps",
        },
        "citations": [{"path": "app/workers/report_worker.py", "symbol": "parse_recent_cache_entries", "line": 7}],
        "confidence": "high",
        "rationale": "prose states a contract the change violates",
    }


def author_claim(
    file: str = "demo_repo/tests/services/test_cache_service.py",
    patch: str = (
        "--- a/demo_repo/tests/services/test_cache_service.py\n"
        "+++ b/demo_repo/tests/services/test_cache_service.py\n"
        "@@ -1,3 +1,8 @@\n"
        "+    def test_pipe_delimited_contract(self):\n"
        "+        write_cache_entry({'id': 1, 'status': 'ok'})\n"
        "+        assert _read() == '1|ok'\n"
    ),
) -> dict:
    return {
        "claim_type": "test",
        "role": "author",
        "targets": {
            "symbol": "app.services.cache_service.write_cache_entry",
            "file": file,
            "test_name": "test_pipe_delimited_contract",
            "behaviour_pinned": "cache entries stay pipe-delimited for downstream readers",
            "patch": patch,
        },
        "citations": [{"path": "app/services/cache_service.py", "symbol": "write_cache_entry", "line": 12}],
        "confidence": "med",
        "rationale": "pins the documented wire contract of the changed symbol",
    }


def missed_claim(test_id: str = "T-0404") -> dict:
    return {
        "claim_type": "missed",
        "role": "falsifier",
        "targets": {
            "test_id": test_id,
            "missing_reason": "the change alters the serialized shape this test asserts on",
        },
        "citations": [CITATION_CONSUMER, CITATION_PRODUCER],
        "confidence": "med",
        "rationale": "hidden representation coupling with no import edge",
    }


def as_envelope(*claims: dict, **kwargs: Any) -> dict:
    """The documented top-level shape: {"claims": [...]}."""
    return {"claims": list(claims), **kwargs}


def as_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True)


# --------------------------------------------------------------------------- #
# proposer / verifier / gate doubles
# --------------------------------------------------------------------------- #


class ScriptedProposer:
    """Feeds pre-recorded model outputs, in order, one per call."""

    def __init__(self, outputs: list[Any]):
        self._outputs = list(outputs)
        self.calls: list[dict] = []

    def __call__(self, role: str, bundle: dict) -> Any:
        self.calls.append({"role": role, "bundle": bundle})
        if not self._outputs:
            raise AssertionError("ScriptedProposer exhausted: the cascade called the model too many times")
        return self._outputs.pop(0)

    @property
    def call_count(self) -> int:
        return len(self.calls)


class UnavailableProposer:
    """Every call fails like a rate-limited model."""

    def __init__(self, reason: str = "all keys rate-limited (test double)"):
        self.reason = reason
        self.calls = 0

    def __call__(self, role: str, bundle: dict) -> Any:
        self.calls += 1
        raise ModelUnavailable(self.reason)


class StubVerifier:
    """Configurable FAKE of `testscope_verify`.

    Not the kernel. It records every call so tests can assert that no accepted
    claim exists without a verify call behind it.
    """

    def __init__(
        self,
        *,
        accept: list[str] | tuple[str, ...] = (),
        unconfirmed: list[str] | tuple[str, ...] = (),
        default_gate: str = "symbol_mismatch",
        raises: BaseException | None = None,
    ):
        self.accept_refs = set(accept)
        self.unconfirmed_refs = set(unconfirmed)
        self.default_gate = default_gate
        self.raises = raises
        self.calls: list[dict] = []

    def __call__(self, claims: list[dict], repo: str) -> dict:
        self.calls.append({"claims": list(claims), "repo": repo})
        if self.raises is not None:
            raise self.raises
        accepted, rejected, unconfirmed = [], [], []
        for claim in claims:
            ref = envelope.claim_ref(claim)
            if ref in self.accept_refs:
                accepted.append({"claim": claim, "obligation": "symbol resolves (test double)"})
            elif ref in self.unconfirmed_refs:
                unconfirmed.append(
                    {"claim": claim, "reason": "verifiable by neither mechanism (test double)"}
                )
            else:
                rejected.append(
                    {"claim": claim, "gate": self.default_gate, "detail": "test double rejection"}
                )
        return {"accepted": accepted, "rejected": rejected, "unconfirmed": unconfirmed}

    @property
    def call_count(self) -> int:
        return len(self.calls)


class StubGate:
    """FAKE of `testscope_gate` (the human-click tool). Records its payloads."""

    DEFAULT_RESULT = {
        "g1_buildable": True,
        "g2_passes_5x": True,
        "g2_runs": [True, True, True, True, True],
        "g3_assertion_fires_at_a": True,
        "g3_failure_origin": "assertion",
        "g4_mutation_strength": 0.8,
        "g5_spec_anchored": True,
        "accepted": True,
    }

    def __init__(self, result: dict | None = None, raises: BaseException | None = None):
        self.result = dict(result or self.DEFAULT_RESULT)
        self.raises = raises
        self.calls: list[dict] = []

    def __call__(self, payload: dict) -> dict:
        self.calls.append(payload)
        if self.raises is not None:
            raise self.raises
        return dict(self.result)
