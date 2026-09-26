#!/usr/bin/env python3
"""Does a candidate kernel server speak the frozen four-tool contract? (Person B.)

This is the check that stops the integration from getting stuck between two owners.
It is run against the SERVER, by whoever has one:

    python3 bob_session/roles/kernel_conformance.py --reference      # the bundled stub
    python3 bob_session/roles/kernel_conformance.py                  # Person A's server
    python3 bob_session/roles/kernel_conformance.py --server /path/to/server.py

WHAT IT DOES NOT CHECK. It says nothing about whether the kernel is correct: not
whether the ledger's classification is right, not whether the oracle measured the
right thing, not whether the gate's sandbox is sound. Those are Person A's claims and
Person A's tests. This suite tests THE SEAM -- the things that silently break the
cognitive layer while looking fine on both sides.

Above all it tests THE ECHO RULE. `cascade._apply_verdict` compares the claim the
kernel returns against the claim that was submitted, and raises `UnverifiedClaimError`
-- voiding the run -- when they differ. A kernel that re-serialises, normalises,
reorders or annotates the claim it echoes will pass every one of Person A's own tests
and fail the cascade on the first live call. That failure mode is the reason this file
exists, and it is the first thing to check when a live run dies.

Exit codes: 0 = every FAIL-level check passed (printed WARNs are tolerated),
1 = at least one FAIL, 2 = there was no server to test.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bob_session.roles import envelope  # noqa: E402
from bob_session.roles.cascade import _canonical  # noqa: E402 - the real comparison
from bob_session.roles.errors import KernelUnavailable  # noqa: E402
from bob_session.roles.kernel_client import McpToolClient  # noqa: E402

ROLES_DIR = Path(__file__).resolve().parent
REFERENCE_STUB = ROLES_DIR / "kernel_reference_stub.py"
DEFAULT_SERVER = ROOT / "bob_session" / "mcp_server.py"

LEDGER_ARTEFACT_KEYS = (
    "classification",
    "ledger",
    "uncovered_worklist",
    "measurement",
    "triage",
    "priority_order",
)
GATE_BOOLEAN_KEYS = ("g1_buildable", "g2_passes_5x", "g3_assertion_fires_at_a", "g5_spec_anchored")


@dataclass
class Result:
    status: str  # PASS | FAIL | WARN
    label: str
    detail: str = ""


def _claim(index: int, *, path: str, symbol: str, rationale: str) -> dict:
    """A valid claim envelope, built through the layer's own validator."""
    return envelope.validate_claim(
        "scout",
        {
            "claim_type": "link_exists",
            "role": "scout",
            "targets": {"test_id": f"T-900{index}", "changed_symbol": "stub.symbol"},
            "citations": [{"path": path, "symbol": symbol, "line": 1}],
            "confidence": "med",
            "rationale": rationale,
        },
        index=index,
    )


def check_verify(client: McpToolClient) -> list[Result]:
    """The seam that matters: payloads accepted, buckets well formed, echo exact."""
    results: list[Result] = []
    fabricated = "no/such/file.py"
    submitted = [
        _claim(0, path="AGENTS.md", symbol="stub.probe", rationale="conformance probe"),
        _claim(1, path=".bobignore", symbol="stub.probe", rationale="conformance probe"),
        # A citation that cannot resolve. The kernel must never accept this: it is
        # the whole trust boundary, and the demo's money shot.
        _claim(2, path=fabricated, symbol="stub.probe", rationale="fabricated citation probe"),
        _claim(3, path="AGENTS.md", symbol="stub.__absent__", rationale="symbol probe"),
    ]
    try:
        verdict = client.verify(submitted, str(ROOT))
    except KernelUnavailable as exc:
        return [Result("FAIL", "verify accepts a valid {claims, repo} request", str(exc))]

    buckets = {name: verdict.get(name) for name in ("accepted", "rejected", "unconfirmed")}
    missing = [name for name, value in buckets.items() if not isinstance(value, list)]
    if missing:
        results.append(
            Result(
                "FAIL",
                "verify returns accepted / rejected / unconfirmed as lists",
                f"missing or non-list: {missing}; got keys {sorted(verdict)}",
            )
        )
        return results
    results.append(
        Result(
            "PASS",
            "verify returns accepted / rejected / unconfirmed as lists",
            " + ".join(f"{name}={len(buckets[name])}" for name in buckets),
        )
    )

    entries = [entry for name in buckets for entry in buckets[name]]
    if len(entries) != len(submitted):
        results.append(
            Result(
                "FAIL",
                "verify adjudicates every submitted claim exactly once",
                f"submitted {len(submitted)}, adjudicated {len(entries)}: a claim with no "
                "verdict is silently ignored, which the layer cannot detect",
            )
        )
    else:
        results.append(
            Result(
                "PASS",
                "verify adjudicates every submitted claim exactly once",
                f"{len(entries)}/{len(submitted)} adjudicated",
            )
        )

    submitted_forms = {_canonical(claim) for claim in submitted}
    mangled: list[str] = []
    for name in buckets:
        for entry in buckets[name]:
            echoed = entry.get("claim") if isinstance(entry, dict) else None
            if echoed is None and isinstance(entry, dict):
                echoed = entry  # a bare claim object is accepted too
            if _canonical(echoed) not in submitted_forms:
                mangled.append(f"{name}: {json.dumps(echoed, sort_keys=True)[:120]}")
    if mangled:
        results.append(
            Result(
                "FAIL",
                "verify ECHOES each claim unchanged (the echo rule)",
                "claim differs from the one submitted; the cascade would void the run "
                "with UnverifiedClaimError: " + "; ".join(mangled),
            )
        )
    else:
        results.append(
            Result(
                "PASS",
                "verify ECHOES each claim unchanged (the echo rule)",
                "no re-serialisation, no added keys, no reordering",
            )
        )

    ungated = [
        entry
        for entry in buckets["rejected"]
        if not isinstance(entry, dict) or not isinstance(entry.get("gate"), str) or not entry.get("gate")
    ]
    if buckets["rejected"] and ungated:
        results.append(
            Result(
                "FAIL",
                "every rejection names the gate that rejected it",
                f"{len(ungated)} rejection(s) carry no `gate` string; the rejection ledger "
                "must record which gate fired",
            )
        )
    else:
        results.append(
            Result(
                "PASS",
                "every rejection names the gate that rejected it",
                f"{len(buckets['rejected'])} rejection(s), all gated"
                if buckets["rejected"]
                else "no rejections in this probe",
            )
        )

    # The trust boundary itself: a citation that cannot resolve must never be
    # accepted. This is the behaviour the recorded session shows, so it is asserted
    # here rather than assumed.
    verdict_of = {}
    for name in buckets:
        for entry in buckets[name]:
            echoed = entry.get("claim") if isinstance(entry, dict) else None
            if isinstance(echoed, dict):
                verdict_of[_canonical(echoed)] = name
    fabricated_verdict = verdict_of.get(_canonical(submitted[2]))
    if fabricated_verdict == "accepted":
        results.append(
            Result(
                "FAIL",
                "verify REJECTS a claim citing a path that does not exist",
                f"{fabricated!r} does not exist under the repo, yet the claim was accepted: "
                "a model would be able to assert anything",
            )
        )
    elif fabricated_verdict is None:
        results.append(
            Result(
                "WARN",
                "verify REJECTS a claim citing a path that does not exist",
                "the probe claim was not adjudicated, so this is untested",
            )
        )
    else:
        results.append(
            Result(
                "PASS",
                "verify REJECTS a claim citing a path that does not exist",
                f"{fabricated!r} -> {fabricated_verdict}",
            )
        )
    return results


def check_ledger(client: McpToolClient) -> list[Result]:
    try:
        artefact = client.ledger(
            repo=str(ROOT),
            diff="--- conformance probe ---\n",
            inventory="test_id,test_name\nT-9000,probe\n",
            generated_at="1970-01-01T00:00:00Z",
        )
    except KernelUnavailable as exc:
        return [Result("FAIL", "ledger accepts {repo, diff, inventory, generated_at}", str(exc))]
    if not isinstance(artefact, dict):
        return [
            Result(
                "FAIL",
                "ledger accepts {repo, diff, inventory, generated_at}",
                f"returned {type(artefact).__name__}; the artefact must be a JSON object",
            )
        ]
    results = [
        Result(
            "PASS",
            "ledger accepts {repo, diff, inventory, generated_at}",
            f"{len(artefact)} top-level key(s)",
        )
    ]
    absent = [key for key in LEDGER_ARTEFACT_KEYS if key not in artefact]
    if absent:
        results.append(
            Result(
                "WARN",
                "ledger artefact carries the six documented sections",
                f"absent: {absent}. The cognitive layer treats the artefact opaquely, so "
                "this does not break the seam; it does mean the demo artefact is thinner "
                "than WORKFLOW.md describes",
            )
        )
    return results


def check_oracle(client: McpToolClient) -> list[Result]:
    try:
        measurement = client.oracle(
            repo=str(ROOT), rev_a="HEAD", rev_b="HEAD", run_cmd="python3 -m pytest -q"
        )
    except KernelUnavailable as exc:
        return [Result("FAIL", "oracle accepts {repo, rev_a, rev_b, run_cmd}", str(exc))]
    if not isinstance(measurement, dict):
        return [
            Result(
                "FAIL",
                "oracle accepts {repo, rev_a, rev_b, run_cmd}",
                f"returned {type(measurement).__name__}",
            )
        ]
    complete = measurement.get("complete")
    if not isinstance(complete, bool):
        return [
            Result(
                "FAIL",
                "oracle reports collection completeness as a boolean",
                f"`complete` is {complete!r}; an incomplete collection must be visible "
                "as false rather than absent",
            )
        ]
    return [
        Result(
            "PASS",
            "oracle accepts {repo, rev_a, rev_b, run_cmd}",
            f"complete={complete}, collected={measurement.get('collected')!r}",
        )
    ]


def check_gate(client: McpToolClient) -> list[Result]:
    results: list[Result] = []
    try:
        verdict = client.gate(
            {"repo": str(ROOT), "test_patch": "--- probe ---\n+def test_x():\n+    assert 1 == 1\n", "symbol": "stub.symbol"}
        )
    except KernelUnavailable as exc:
        return [Result("FAIL", "gate accepts {repo, test_patch, symbol}", str(exc))]
    if not isinstance(verdict, dict):
        return [
            Result(
                "FAIL",
                "gate accepts {repo, test_patch, symbol}",
                f"returned {type(verdict).__name__}",
            )
        ]
    results.append(Result("PASS", "gate accepts {repo, test_patch, symbol}", f"keys: {sorted(verdict)}"))

    absent = [key for key in GATE_BOOLEAN_KEYS if key not in verdict]
    if absent:
        results.append(
            Result(
                "FAIL",
                "gate reports the per-gate booleans by their documented names",
                f"absent: {absent}. `cascade.run_author` reads these names to build its "
                "rejection entry; a missing key reads as 'not a recorded failure'",
            )
        )
    else:
        results.append(
            Result(
                "PASS",
                "gate reports the per-gate booleans by their documented names",
                f"{', '.join(GATE_BOOLEAN_KEYS)}",
            )
        )
    if not isinstance(verdict.get("accepted"), bool):
        results.append(
            Result("FAIL", "gate reports `accepted` as a boolean", f"got {verdict.get('accepted')!r}")
        )

    # The safety property: an empty patch is nothing authored, and nothing authored
    # may never read as accepted. Either answer is conformant -- adjudicating it and
    # returning accepted=false, or refusing the request with ok=false -- so the probe
    # reads the raw response: "the gate refused" and "the gate never ran" must not be
    # reported as the same thing.
    try:
        response = client.call_raw("testscope_gate", {"repo": str(ROOT), "test_patch": "", "symbol": "stub.symbol"})
    except KernelUnavailable as exc:
        results.append(Result("FAIL", "gate never accepts an empty patch", str(exc)))
        return results

    if response.get("ok") is False:
        results.append(
            Result(
                "PASS",
                "gate never accepts an empty patch",
                f"refused as a malformed request: {response.get('error')}",
            )
        )
    else:
        output = response.get("output") if isinstance(response.get("output"), dict) else response
        accepted_empty = output.get("accepted")
        refused = accepted_empty is not True
        results.append(
            Result(
                "PASS" if refused else "FAIL",
                "gate never accepts an empty patch",
                f"adjudicated, accepted={accepted_empty!r}"
                if refused
                else "an empty patch returned accepted=true: nothing authored would enter "
                "the suite unverified",
            )
        )
    return results


# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--server", default=None, help=f"server to test (default: {DEFAULT_SERVER})")
    parser.add_argument(
        "--reference",
        action="store_true",
        help="test the bundled contract stub instead of a real server (proves the suite runs)",
    )
    parser.add_argument("--timeout", type=float, default=120.0, help="per-call timeout in seconds")
    args = parser.parse_args(argv)

    server = Path(args.server) if args.server else (REFERENCE_STUB if args.reference else DEFAULT_SERVER)
    target = f"{server}  (bundled contract stub)" if args.reference else str(server)

    print("TestScope — kernel conformance against the frozen four-tool contract")
    print("=" * 78)
    print(f"target: {target}")
    print()

    if not server.is_file():
        print(f"[FAIL] server present at {server}")
        print()
        print("-" * 78)
        print("VERDICT: NO SERVER — nothing to test (exit 2)")
        print("Person A owns `bob_session/mcp_server.py`. Until it exists, the seam can")
        print("still be exercised end to end with the bundled stub:")
        print()
        print("    python3 bob_session/roles/kernel_conformance.py --reference")
        return 2

    client = McpToolClient(server=server, timeout=args.timeout)
    results: list[Result] = [Result("PASS", f"server present at {server}", "")]
    for check in (check_ledger, check_verify, check_oracle, check_gate):
        results.extend(check(client))

    for result in results:
        print(f"[{result.status}] {result.label}")
        if result.detail:
            print(f"         {result.detail}")

    failed = [r for r in results if r.status == "FAIL"]
    warned = [r for r in results if r.status == "WARN"]
    passed = [r for r in results if r.status == "PASS"]

    print()
    print("-" * 78)
    if failed:
        print(f"VERDICT: FAIL — {len(failed)} contract violation(s); {len(passed)} passed, {len(warned)} warn")
        print("Fix the seam in `bob_session/mcp_server.py`. If the request never arrived, the")
        print("framing is the suspect: this client sends {\"tool\": ..., \"input\": ...} on")
        print("stdin, and `kernel_client._frame` is the one place that decides that.")
        return 1
    print(f"VERDICT: PASS — {len(passed)} checks passed, {len(warned)} warn, 0 failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
