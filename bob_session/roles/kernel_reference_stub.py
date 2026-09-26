#!/usr/bin/env python3
"""Reference implementation of the four-tool wire contract (Person B, for Person A).

THIS IS NOT THE KERNEL. Person A owns `bob_session/mcp_server.py`, and nothing here
replaces, pre-empts or duplicates it. This file exists so that neither side is
blocked on the other:

  * Person A gets a worked example of the framing, the response envelope and the
    verdict buckets, and can diff their server's behaviour against it.
  * Person B can exercise the whole cascade -- including the rejection -> escalation
    path and the author's gate -- before the real kernel exists, via
    `python3 bob_session/roles/kernel_conformance.py --reference`.

It computes NOTHING real. Every response carries `"stub": true`, and the verdicts are
derived from the request by the four deterministic rules below so that both the
accept path and the reject path are reachable in a test. Wiring this in place of the
real kernel would be a lie; the flag is there so that lie cannot be told by accident.

WIRE CONTRACT (frozen, identical for all four tools):

    stdin    one JSON request  : {"tool": "<name>", "input": {...}}
    stdout   one JSON response : {"ok": true, "output": {...}}
    refusals : {"ok": false, "error": "..."} with exit 0 -- an expected refusal is
               data, not a crash
    exit     non-zero only when the server itself broke; Person B reports that as
             KernelUnavailable together with the stderr tail

Nothing else may be written to stdout. A stray `print` corrupts the response, because
the client parses stdout as exactly one JSON document and rejects trailing content.

VERDICT RULES used by `testscope_verify` (deterministic, and nothing more):

    a cited path does not exist under repo      -> rejected   gate=citation_invalid
    a cited symbol contains "__absent__"        -> rejected   gate=symbol_mismatch
    the rationale contains "unconfirmed"        -> unconfirmed
    otherwise                                   -> accepted

EVERY SUBMITTED CLAIM IS ECHOED UNCHANGED into whichever bucket it lands: no
re-serialisation, no added keys, no reordering, no normalisation. Person B's cascade
compares the echo against the claim it submitted and VOIDS THE ENTIRE RUN if the two
differ (`UnverifiedClaimError`). See `cascade._apply_verdict`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

TOOLS = ("testscope_ledger", "testscope_verify", "testscope_oracle", "testscope_gate")

LEDGER_ARTEFACT_KEYS = (
    "classification",
    "ledger",
    "uncovered_worklist",
    "measurement",
    "triage",
    "priority_order",
)


def respond(tool: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Dispatch one request. Unknown tools refuse cleanly with `ok: false`."""
    handlers = {
        "testscope_ledger": _ledger,
        "testscope_verify": _verify,
        "testscope_oracle": _oracle,
        "testscope_gate": _gate,
    }
    handler = handlers.get(tool)
    if handler is None:
        return {"ok": False, "error": f"unknown tool {tool!r}; tools: {', '.join(TOOLS)}"}
    if not isinstance(payload, dict):
        return {"ok": False, "error": f"{tool} requires input to be an object"}
    return handler(payload)


# --------------------------------------------------------------------------- #
# the four tools
# --------------------------------------------------------------------------- #


def _ledger(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("repo", "diff", "inventory", "generated_at"):
        if key not in payload:
            return {"ok": False, "error": f"ledger requires input.{key}"}
    # The artefact's SHAPE is Person A's; the cognitive layer treats it opaquely and
    # only requires it to be a JSON object. The keys below are the documented
    # top-level ones, so the stub stays shaped like the real thing for the demo.
    artefact: dict[str, Any] = {
        "schema": "testscope.ledger.v1",
        "generated_at": payload["generated_at"],
        "repo": payload["repo"],
        "stub": True,
    }
    for key in LEDGER_ARTEFACT_KEYS:
        artefact[key] = {}
    return {"ok": True, "output": artefact}


def _verify(payload: dict[str, Any]) -> dict[str, Any]:
    claims = payload.get("claims")
    repo = payload.get("repo")
    if not isinstance(claims, list):
        return {"ok": False, "error": "verify requires input.claims to be a list"}
    if not isinstance(repo, str) or not repo.strip():
        return {"ok": False, "error": "verify requires input.repo to be a non-empty string"}

    root = Path(repo).expanduser()
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    unconfirmed: list[dict[str, Any]] = []

    for claim in claims:
        gate, detail = _judge(claim, root)
        # `claim` is echoed by reference, exactly as received.
        if gate is None:
            accepted.append({"claim": claim})
        elif gate == "unconfirmed":
            unconfirmed.append(
                {"claim": claim, "reason": "the rationale asked to be left unconfirmed"}
            )
        else:
            rejected.append({"claim": claim, "gate": gate, "detail": detail})

    return {
        "ok": True,
        "output": {
            "accepted": accepted,
            "rejected": rejected,
            "unconfirmed": unconfirmed,
            "stub": True,
        },
    }


def _oracle(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("repo", "rev_a", "rev_b", "run_cmd"):
        if key not in payload:
            return {"ok": False, "error": f"oracle requires input.{key}"}
    # A stub measurement is NOT a measurement. It reports an empty, complete run
    # rather than an invented one, and says so.
    return {
        "ok": True,
        "output": {
            "collected": 0,
            "inventory_total": 0,
            "complete": True,
            "changed": [],
            "outcome": {},
            "stub": True,
        },
    }


def _gate(payload: dict[str, Any]) -> dict[str, Any]:
    symbol = payload.get("symbol")
    patch = payload.get("test_patch")
    for key, value in (("repo", payload.get("repo")), ("test_patch", patch), ("symbol", symbol)):
        if not isinstance(value, str) or not value.strip():
            return {"ok": False, "error": f"gate requires input.{key} to be a non-empty string"}

    # An empty patch must never be accepted: nothing authored enters the suite
    # unverified, and "nothing was authored" is not a pass.
    fires = "__absent__" not in str(symbol)
    output: dict[str, Any] = {
        "accepted": fires,
        "g1_buildable": True,
        "g2_passes_5x": True,
        "g3_assertion_fires_at_a": fires,
        "g4_mutation_strength": 1.0 if fires else 0.0,
        # G5 is null when no intent artefact exists -- null, not false.
        "g5_spec_anchored": None,
        "stub": True,
    }
    return {"ok": True, "output": output}


def _judge(claim: Any, root: Path) -> tuple[str | None, str]:
    """(gate, detail); gate None means accept. Deterministic, and nothing more."""
    if not isinstance(claim, dict):
        return "citation_invalid", f"claim is not an object: {type(claim).__name__}"
    rationale = str(claim.get("rationale") or "")
    if "unconfirmed" in rationale.lower():
        return "unconfirmed", ""
    citations = claim.get("citations")
    if not isinstance(citations, list) or not citations:
        return "citation_invalid", "the claim carries no citation (cite or abstain)"
    for citation in citations:
        if not isinstance(citation, dict):
            return "citation_invalid", "a citation is not an object"
        path = str(citation.get("path") or "")
        if not path or not (root / path).exists():
            return "citation_invalid", f"no such file under repo: {path!r}"
        if "__absent__" in str(citation.get("symbol") or ""):
            return "symbol_mismatch", f"symbol not found at the cited location: {citation['symbol']!r}"
    return None, ""


# --------------------------------------------------------------------------- #
# transport
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    raw = sys.stdin.read()
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as exc:
        response: dict[str, Any] = {"ok": False, "error": f"request is not JSON: {exc.msg}"}
    else:
        if not isinstance(request, dict):
            response = {"ok": False, "error": "request must be a JSON object"}
        else:
            response = respond(str(request.get("tool") or ""), request.get("input") or {})
    sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
