"""The seam, exercised against a REAL subprocess (Person B).

Every other test in this directory fakes the kernel in-process --
`testing.StubVerifier` and `testing.StubGate` are Python callables. None of them
crosses a process boundary, so none of them can catch: a mis-framed request, extra
output on stdout, a response wrapped differently than expected, or a kernel that
returns the claim it was sent in a different form.

These tests drive the cascade through `kernel_reference_stub.py` -- a real
subprocess speaking the frozen contract -- which is the closest available stand-in
for `bob_session/mcp_server.py` until Person A's server lands. The same seam is
checked end to end, against the real server, by
`python3 bob_session/roles/kernel_conformance.py`.

The ECHO RULE gets its own test here, against a deliberately hostile server: a kernel
that "improves" the claim it echoes must VOID the run rather than have its verdict
accepted. That is the guarantee `cascade._apply_verdict` exists to provide, and it is
the first thing to check when a live run dies.

Nothing here asserts that the reference stub is CORRECT. It is not the kernel and
computes nothing real. These tests assert that the layer works over a process
boundary, which is the part that cannot be faked in-process.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bob_session.roles import testing
from bob_session.roles.cascade import run_author, run_cascade
from bob_session.roles.errors import UnverifiedClaimError
from bob_session.roles.kernel_client import McpToolClient

ROOT = Path(__file__).resolve().parents[3]
REFERENCE_STUB = Path(__file__).resolve().parents[1] / "kernel_reference_stub.py"

# Citations that resolve: the stub accepts a claim only when every cited path exists.
RESOLVING = {"path": "AGENTS.md", "symbol": "stub.probe", "line": 1}
FABRICATED = {"path": "no/such/file.py", "symbol": "stub.probe", "line": 1}

# A kernel that does NOT honour the echo rule: it re-serialises each claim, adding a
# key it decided was worth having. B's cascade must refuse the verdict entirely.
MANGLING_SERVER = """
import json, sys

request = json.loads(sys.stdin.read())
claims = request["input"]["claims"]
mangled = [{**claim, "normalised_by": "hostile-server"} for claim in claims]
output = {
    "accepted": [{"claim": claim, "obligation": "re-serialised"} for claim in mangled],
    "rejected": [],
    "unconfirmed": [],
}
sys.stdout.write(json.dumps({"ok": True, "output": output}) + "\\n")
"""


def _client(**kwargs) -> McpToolClient:
    return McpToolClient(server=REFERENCE_STUB, cwd=ROOT, timeout=120.0, **kwargs)


class SeamAcceptPath(unittest.TestCase):
    def test_cascade_accepts_over_a_real_process_boundary(self):
        claim = testing.scout_claim(citations=[RESOLVING])
        proposer = testing.ScriptedProposer([testing.as_json(testing.as_envelope(claim))])
        outcome = run_cascade(
            testing.candidate_unit(),
            propose=proposer,
            verify=_client().verify,
            repo=str(ROOT),
            inventory_ids=["T-0342"],
        )
        self.assertEqual(outcome.status, "accepted")
        self.assertEqual(outcome.tiers_used, 1)
        self.assertEqual(proposer.call_count, 1, "an accepted tier-1 claim must stop the cascade")
        self.assertEqual(len(outcome.accepted), 1)
        self.assertEqual(outcome.accepted[0]["targets"]["test_id"], "T-0342")
        self.assertEqual(outcome.unmapped_findings, [])

    def test_unmapped_test_id_is_kept_never_dropped(self):
        """The kernel accepted a test_id with no inventory row: keep it, mark it."""
        claim = testing.scout_claim(test_id="T-9999", citations=[RESOLVING])
        proposer = testing.ScriptedProposer([testing.as_json(testing.as_envelope(claim))])
        outcome = run_cascade(
            testing.candidate_unit(),
            propose=proposer,
            verify=_client().verify,
            repo=str(ROOT),
            inventory_ids=["T-0342"],
        )
        self.assertEqual(outcome.status, "accepted")
        self.assertEqual(len(outcome.unmapped_findings), 1)
        self.assertIn("T-9999", outcome.unmapped_findings[0]["reason"])


class SeamRejectionPath(unittest.TestCase):
    def test_a_fabricated_citation_is_rejected_then_escalated_then_unconfirmed(self):
        """The live failure path: tier 1 rejected, tier 2 rejected, safe direction."""
        scout = testing.scout_claim(citations=[FABRICATED])
        intent = testing.intent_claim()
        # Tier 2 fails differently on purpose: the ledger must record WHICH gate fired
        # per rejection, not merely that something was rejected.
        intent["citations"] = [{"path": "AGENTS.md", "symbol": "stub.__absent__", "line": 1}]
        proposer = testing.ScriptedProposer(
            [testing.as_json(testing.as_envelope(scout)), testing.as_json(testing.as_envelope(intent))]
        )
        outcome = run_cascade(
            testing.candidate_unit(),
            propose=proposer,
            verify=_client().verify,
            repo=str(ROOT),
            inventory_ids=["T-0342"],
        )
        self.assertEqual(outcome.status, "unconfirmed")
        self.assertEqual(outcome.tiers_used, 2, "a rejection must escalate, not stop")
        self.assertEqual(proposer.call_count, 2)
        self.assertEqual(outcome.accepted, [], "nothing unverified may be accepted")
        self.assertEqual(
            [entry["gate"] for entry in outcome.rejection_ledger()],
            ["citation_invalid", "symbol_mismatch"],
            "the ledger records the gate per rejection: a published path, then a missing symbol",
        )
        self.assertEqual(outcome.safe_direction_ids, ["T-0342"])

    def test_a_mangled_echo_voids_the_run(self):
        """A kernel that rewrites the claim it echoes is refused, not trusted."""
        with tempfile.TemporaryDirectory() as tmp:
            server = Path(tmp) / "mangling_server.py"
            server.write_text(MANGLING_SERVER, encoding="utf-8")
            claim = testing.scout_claim(citations=[RESOLVING])
            proposer = testing.ScriptedProposer([testing.as_json(testing.as_envelope(claim))])
            with self.assertRaises(UnverifiedClaimError):
                run_cascade(
                    testing.candidate_unit(),
                    propose=proposer,
                    verify=McpToolClient(server=server, cwd=ROOT, timeout=120.0).verify,
                    repo=str(ROOT),
                    inventory_ids=["T-0342"],
                )

    def test_a_missing_kernel_accepts_nothing_and_keeps_the_baseline(self):
        absent = McpToolClient(server=ROOT / "bob_session" / "mcp_server.py", cwd=ROOT)
        claim = testing.scout_claim(citations=[RESOLVING])
        proposer = testing.ScriptedProposer([testing.as_json(testing.as_envelope(claim))])
        outcome = run_cascade(
            testing.candidate_unit(),
            propose=proposer,
            verify=absent.verify,
            repo=str(ROOT),
            inventory_ids=["T-0342"],
        )
        self.assertEqual(outcome.status, "kernel_unavailable")
        self.assertEqual(outcome.accepted, [])
        self.assertEqual(outcome.selection_additions(), [], "selection stays equal to the baseline")


class SeamAuthorPath(unittest.TestCase):
    def test_author_output_is_adjudicated_over_a_real_process_boundary(self):
        proposer = testing.ScriptedProposer(
            [testing.as_json(testing.as_envelope(testing.author_claim()))]
        )
        outcome = run_author(
            testing.author_unit(),
            propose=proposer,
            gate=_client().gate,
            repo=str(ROOT),
        )
        self.assertEqual(outcome.status, "authored_accepted")
        self.assertEqual(len(outcome.accepted), 1)

    def test_an_unauthorable_symbol_fails_its_gate_and_is_discarded(self):
        """The stub fails G3 for a symbol that cannot have fired; nothing is admitted."""
        claim = testing.author_claim()
        claim["targets"]["symbol"] = "stub.__absent__"
        proposer = testing.ScriptedProposer([testing.as_json(testing.as_envelope(claim))])
        outcome = run_author(
            testing.author_unit(),
            propose=proposer,
            gate=_client().gate,
            repo=str(ROOT),
        )
        self.assertEqual(outcome.status, "authored_discarded")
        self.assertEqual(outcome.accepted, [])
        self.assertEqual([entry["gate"] for entry in outcome.rejection_ledger()], ["gate_failed"])
        self.assertIn("g3_assertion_fires_at_a", outcome.rejection_ledger()[0]["detail"])

    def test_a_missing_gate_admits_nothing(self):
        absent = McpToolClient(server=ROOT / "bob_session" / "mcp_server.py", cwd=ROOT)
        proposer = testing.ScriptedProposer(
            [testing.as_json(testing.as_envelope(testing.author_claim()))]
        )
        outcome = run_author(
            testing.author_unit(),
            propose=proposer,
            gate=absent.gate,
            repo=str(ROOT),
        )
        self.assertEqual(outcome.status, "kernel_unavailable")
        self.assertEqual(outcome.accepted, [])


class ReferenceStubContract(unittest.TestCase):
    """The stub itself must speak the framing Person A is asked to implement."""

    def test_stub_refuses_an_unknown_tool_with_data_not_a_crash(self):
        response = _client().call_raw("testscope_nonexistent", {})
        self.assertIs(response.get("ok"), False)
        self.assertIn("unknown tool", response.get("error", ""))

    def test_stub_writes_exactly_one_json_document_to_stdout(self):
        response = _client().call_raw(
            "testscope_ledger",
            {"repo": str(ROOT), "diff": "", "inventory": "", "generated_at": "1970-01-01T00:00:00Z"},
        )
        self.assertIs(response.get("ok"), True)
        self.assertIsInstance(response.get("output"), dict)

    def test_every_stub_response_is_marked_as_a_stub(self):
        """A stub measurement must never be mistakable for a measurement."""
        ledger = _client().ledger(repo=str(ROOT), diff="", inventory="", generated_at="1970-01-01T00:00:00Z")
        oracle = _client().oracle(repo=str(ROOT), rev_a="HEAD", rev_b="HEAD", run_cmd="pytest -q")
        gate = _client().gate({"repo": str(ROOT), "test_patch": "--- x ---\n", "symbol": "s"})
        for name, payload in (("ledger", ledger), ("oracle", oracle), ("gate", gate)):
            self.assertIs(payload.get("stub"), True, f"{name} output is not flagged as a stub")

    def test_stdout_is_the_only_channel_the_client_reads(self):
        """json.loads rejects trailing content, so noise on stdout cannot pass."""
        import subprocess
        import sys

        completed = subprocess.run(
            [sys.executable, str(REFERENCE_STUB)],
            input=json.dumps({"tool": "testscope_ledger", "input": {}}),
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=60,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(len(completed.stdout.strip().splitlines()), 1)
        self.assertTrue(json.loads(completed.stdout.strip())["ok"] is False)


if __name__ == "__main__":
    unittest.main()
