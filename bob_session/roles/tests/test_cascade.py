"""Tests for the verification-gated cascade (deliverable B6).

These pin the properties the brief calls acceptance criteria:

  * escalation actually happens (tier 1 rejected -> tier 2);
  * the cap is two tiers, never three;
  * every rejection is recorded with its gate;
  * the safe direction is applied exactly where section 4 says;
  * no claim reaches an outcome without a verify call (asserted in code);
  * the falsifier runs last, alone, over the unselected rows only.
"""

from __future__ import annotations

import unittest

from bob_session.roles import cascade, envelope
from bob_session.roles.errors import (
    FalsifierInputError,
    FalsifierOrderError,
    KernelUnavailable,
    UnverifiedClaimError,
)
from bob_session.roles.testing import (
    DIFF,
    ScriptedProposer,
    StubGate,
    StubVerifier,
    UnavailableProposer,
    as_envelope,
    author_claim,
    author_unit,
    candidate_unit,
    intent_claim,
    missed_claim,
    scout_claim,
    scout_unit,
)

REPO = "/tmp/testscope-fixture"

SCOUT_REF = "scout:link_exists:T-0342"
SCOUT_REF_2 = "scout:link_exists:T-0187"
INTENT_REF = "cartographer:intent:app.services.cache_service.write_cache_entry"
MISSED_REF = "falsifier:missed:T-0404"


class CascadeAcceptanceTest(unittest.TestCase):
    def test_accepted_tier1_stops_escalation(self):
        proposer = ScriptedProposer([as_envelope(scout_claim())])
        verifier = StubVerifier(accept=[SCOUT_REF])
        outcome = cascade.run_cascade(scout_unit(), propose=proposer, verify=verifier, repo=REPO)

        self.assertEqual(outcome.status, "accepted")
        self.assertEqual(outcome.tiers_used, 1)
        self.assertEqual(proposer.call_count, 1)
        self.assertEqual(verifier.call_count, 1)
        self.assertEqual([c["claim_type"] for c in outcome.accepted], ["link_exists"])
        self.assertEqual(outcome.rejections, [])

    def test_rejection_escalates_to_tier2_and_is_recorded(self):
        proposer = ScriptedProposer([as_envelope(scout_claim()), as_envelope(intent_claim())])
        verifier = StubVerifier(accept=[INTENT_REF], default_gate="symbol_mismatch")
        outcome = cascade.run_cascade(candidate_unit(), propose=proposer, verify=verifier, repo=REPO)

        self.assertEqual(outcome.status, "escalated_accepted")
        self.assertEqual(outcome.tiers_used, 2)
        self.assertEqual([call["role"] for call in proposer.calls], ["scout", "cartographer"])
        self.assertEqual(len(outcome.rejections), 1)
        self.assertEqual(outcome.rejections[0].role, "scout")
        self.assertEqual(outcome.rejections[0].gate, "symbol_mismatch")
        self.assertEqual(verifier.call_count, 2)
        self.assertEqual([c["claim_type"] for c in outcome.accepted], ["intent"])

    def test_escalation_bundle_is_the_cartographer_view_of_the_same_unit(self):
        proposer = ScriptedProposer([as_envelope(scout_claim()), as_envelope(intent_claim())])
        verifier = StubVerifier(accept=[INTENT_REF])
        cascade.run_cascade(candidate_unit(), propose=proposer, verify=verifier, repo=REPO)

        tier1, tier2 = proposer.calls
        self.assertIn("producer_call_site", tier1["bundle"])
        self.assertIn("intent_artefacts", tier2["bundle"])
        self.assertEqual(tier1["bundle"]["changed_symbol"], tier2["bundle"]["changed_symbol"])

    def test_two_tier_cap_takes_the_safe_direction(self):
        proposer = ScriptedProposer([as_envelope(scout_claim()), as_envelope(intent_claim())])
        verifier = StubVerifier()  # rejects everything
        outcome = cascade.run_cascade(candidate_unit(), propose=proposer, verify=verifier, repo=REPO)

        self.assertEqual(outcome.status, "unconfirmed")
        self.assertEqual(proposer.call_count, 2, "a third tier must never be asked")
        self.assertEqual(len(outcome.rejections), 2)
        self.assertEqual(outcome.safe_direction_ids, ["T-0342"])
        self.assertEqual(outcome.selection_additions(), [])
        self.assertIn("safe direction", outcome.notes[-1])

    def test_insufficient_unit_costs_zero_model_calls(self):
        proposer = ScriptedProposer([])
        verifier = StubVerifier()
        outcome = cascade.run_cascade(
            scout_unit(consumer_call_site=""), propose=proposer, verify=verifier, repo=REPO
        )

        self.assertEqual(outcome.status, "skipped_insufficient")
        self.assertEqual(proposer.call_count, 0)
        self.assertEqual(verifier.call_count, 0)
        self.assertEqual(outcome.missing, ["consumer_call_site"])
        self.assertEqual(outcome.tiers_used, 0)
        self.assertEqual(outcome.safe_direction_ids, ["T-0342"])

    def test_honest_silence_adds_nothing(self):
        proposer = ScriptedProposer([as_envelope(), as_envelope()])
        verifier = StubVerifier()
        outcome = cascade.run_cascade(candidate_unit(), propose=proposer, verify=verifier, repo=REPO)

        self.assertEqual(outcome.status, "no_claims")
        self.assertEqual(outcome.rejections, [])
        self.assertEqual(outcome.safe_direction_ids, [])
        self.assertEqual(verifier.call_count, 0)


class TrustBoundaryTest(unittest.TestCase):
    def test_every_claim_is_submitted_to_the_verifier(self):
        proposer = ScriptedProposer([as_envelope(scout_claim(), scout_claim(test_id="T-0187"))])
        verifier = StubVerifier(accept=[SCOUT_REF, SCOUT_REF_2])
        outcome = cascade.run_cascade(scout_unit(), propose=proposer, verify=verifier, repo=REPO)

        self.assertEqual(verifier.call_count, 1)
        submitted = verifier.calls[0]["claims"]
        self.assertEqual(len(submitted), 2)
        self.assertEqual(verifier.calls[0]["repo"], REPO)
        self.assertEqual(len(outcome.accepted), 2)

    def test_a_claim_the_kernel_never_saw_can_never_be_accepted(self):
        class HostileVerifier:
            def __call__(self, claims, repo):
                return {
                    "accepted": [{"claim": scout_claim(test_id="T-9999"), "obligation": "forged"}],
                    "rejected": [],
                    "unconfirmed": [],
                }

        proposer = ScriptedProposer([as_envelope(scout_claim())])
        with self.assertRaises(UnverifiedClaimError):
            cascade.run_cascade(scout_unit(), propose=proposer, verify=HostileVerifier(), repo=REPO)

    def test_schema_violation_is_rejected_not_salvaged(self):
        prose = "I think T-0342 is affected. Here is my JSON:\n{}"
        proposer = ScriptedProposer([prose, prose])
        verifier = StubVerifier()
        outcome = cascade.run_cascade(candidate_unit(), propose=proposer, verify=verifier, repo=REPO)

        self.assertEqual(verifier.call_count, 0, "an unparsed proposal must never be sent to the kernel")
        self.assertEqual(outcome.accepted, [])
        self.assertEqual([r.gate for r in outcome.rejections], ["schema_violation", "schema_violation"])
        self.assertEqual(outcome.status, "unconfirmed")

    def test_kernel_unavailable_accepts_nothing(self):
        proposer = ScriptedProposer([as_envelope(scout_claim())])
        verifier = StubVerifier(raises=KernelUnavailable("server down"))
        outcome = cascade.run_cascade(scout_unit(), propose=proposer, verify=verifier, repo=REPO)

        self.assertEqual(outcome.status, "kernel_unavailable")
        self.assertEqual(outcome.accepted, [])
        self.assertEqual(outcome.safe_direction_ids, [])
        self.assertEqual(outcome.selection_additions(), [])

    def test_unconfirmed_claim_takes_the_safe_direction(self):
        proposer = ScriptedProposer([as_envelope(scout_claim()), as_envelope(intent_claim())])
        verifier = StubVerifier(unconfirmed=[SCOUT_REF, INTENT_REF])
        outcome = cascade.run_cascade(candidate_unit(), propose=proposer, verify=verifier, repo=REPO)

        self.assertEqual(outcome.accepted, [])
        self.assertEqual(outcome.status, "unconfirmed")
        self.assertEqual(len(outcome.unconfirmed), 2)
        self.assertIn("T-0342", outcome.safe_direction_ids)


class LayerDeterminismTest(unittest.TestCase):
    def test_cascade_outcome_is_identical_across_runs(self):
        def run():
            proposer = ScriptedProposer(
                [as_envelope(scout_claim()), as_envelope(intent_claim())]
            )
            verifier = StubVerifier(accept=[INTENT_REF], default_gate="symbol_mismatch")
            return cascade.run_cascade(
                candidate_unit(), propose=proposer, verify=verifier, repo=REPO
            )

        self.assertEqual(run(), run())


class MonotonicityTest(unittest.TestCase):
    def test_model_unavailable_degrades_to_the_baseline(self):
        proposer = UnavailableProposer()
        verifier = StubVerifier()
        outcome = cascade.run_cascade(candidate_unit(), propose=proposer, verify=verifier, repo=REPO)

        self.assertEqual(outcome.status, "no_claims")
        self.assertEqual(outcome.selection_additions(), [])
        self.assertEqual(outcome.safe_direction_ids, [])
        self.assertEqual(proposer.calls, 4, "one retry per tier, then baseline")
        self.assertEqual(outcome.model_calls, 4)

    def test_verified_additions_only_ever_grow_the_baseline(self):
        proposer = ScriptedProposer([as_envelope(scout_claim())])
        verifier = StubVerifier(accept=[SCOUT_REF])
        outcome = cascade.run_cascade(scout_unit(), propose=proposer, verify=verifier, repo=REPO)

        selected = ["T-0001"]
        additions = [c["targets"]["test_id"] for c in outcome.selection_additions()]
        self.assertEqual(sorted(set(selected) | set(additions)), ["T-0001", "T-0342"])

    def test_unmapped_finding_is_never_dropped(self):
        proposer = ScriptedProposer([as_envelope(scout_claim())])
        verifier = StubVerifier(accept=[SCOUT_REF])
        outcome = cascade.run_cascade(
            scout_unit(), propose=proposer, verify=verifier, repo=REPO, inventory_ids=["T-0001"]
        )

        self.assertEqual(len(outcome.accepted), 1, "the finding is kept, not dropped")
        self.assertEqual(len(outcome.unmapped_findings), 1)
        self.assertIn("T-0342", outcome.unmapped_findings[0]["reason"])


class AuthorTest(unittest.TestCase):
    def test_author_output_clears_the_gate(self):
        proposer = ScriptedProposer([as_envelope(author_claim())])
        gate = StubGate()
        outcome = cascade.run_author(author_unit(), propose=proposer, gate=gate, repo=REPO)

        self.assertEqual(outcome.status, "authored_accepted")
        self.assertEqual(len(outcome.accepted), 1)
        self.assertEqual(gate.calls[0]["symbol"], "app.services.cache_service.write_cache_entry")
        self.assertIn("pipe_delimited_contract", gate.calls[0]["test_patch"])
        self.assertIn("G1..G5", outcome.notes[-1])

    def test_author_gate_failure_is_recorded_with_the_failing_gate(self):
        result = dict(StubGate.DEFAULT_RESULT, g3_assertion_fires_at_a=False, accepted=False)
        proposer = ScriptedProposer([as_envelope(author_claim())])
        gate = StubGate(result=result)
        outcome = cascade.run_author(author_unit(), propose=proposer, gate=gate, repo=REPO)

        self.assertEqual(outcome.status, "authored_discarded")
        self.assertEqual(outcome.accepted, [])
        self.assertEqual(outcome.rejections[0].gate, "gate_failed")
        self.assertIn("g3_assertion_fires_at_a", outcome.rejections[0].detail)

    def test_a_g4_only_refusal_names_g4_instead_of_going_unattributed(self):
        """G4 is a strength, not a boolean: a refusal it alone caused must say so."""
        result = dict(StubGate.DEFAULT_RESULT, g4_mutation_strength=0.25, accepted=False)
        proposer = ScriptedProposer([as_envelope(author_claim())])
        outcome = cascade.run_author(
            author_unit(), propose=proposer, gate=StubGate(result=result), repo=REPO
        )

        self.assertEqual(outcome.status, "authored_discarded")
        self.assertIn("g4_mutation_strength=0.25", outcome.rejections[0].detail)

    def test_author_must_extend_the_existing_file(self):
        proposer = ScriptedProposer(
            [as_envelope(author_claim(file="demo_repo/tests/services/test_something_else.py"))]
        )
        gate = StubGate()
        outcome = cascade.run_author(author_unit(), propose=proposer, gate=gate, repo=REPO)

        self.assertEqual(outcome.status, "discarded")
        self.assertEqual(outcome.rejections[0].gate, "target_file_mismatch")
        self.assertEqual(gate.calls, [], "a new-file proposal never reaches the gate")

    def test_author_proposes_at_most_one_test(self):
        proposer = ScriptedProposer([as_envelope(author_claim(), author_claim())])
        gate = StubGate()
        outcome = cascade.run_author(author_unit(), propose=proposer, gate=gate, repo=REPO)

        self.assertEqual(outcome.status, "discarded")
        self.assertEqual(outcome.rejections[0].gate, "too_many_claims")
        self.assertEqual(gate.calls, [])

    def test_author_insufficient_unit_makes_no_model_call(self):
        proposer = ScriptedProposer([])
        outcome = cascade.run_author(
            author_unit(pre_change_body=""), propose=proposer, gate=StubGate(), repo=REPO
        )

        self.assertEqual(outcome.status, "skipped_insufficient")
        self.assertEqual(proposer.call_count, 0)
        self.assertIn("pre_change_body", outcome.missing)

    def test_author_gate_unavailable_accepts_nothing(self):
        proposer = ScriptedProposer([as_envelope(author_claim())])
        gate = StubGate(raises=KernelUnavailable("sandbox exploded"))
        outcome = cascade.run_author(author_unit(), propose=proposer, gate=gate, repo=REPO)

        self.assertEqual(outcome.status, "kernel_unavailable")
        self.assertEqual(outcome.accepted, [])


class FalsifierTest(unittest.TestCase):
    def test_falsifier_refuses_to_run_before_the_ledger_is_final(self):
        with self.assertRaises(FalsifierOrderError):
            cascade.run_falsifier(
                ledger={"selected": ["T-0342"]},
                diff_hunks=DIFF,
                unselected_rows=[{"test_id": "T-0404"}],
                selected_ids=["T-0342"],
                propose=ScriptedProposer([]),
                verify=StubVerifier(),
                repo=REPO,
                ledger_is_final=False,
            )

    def test_falsifier_refuses_to_see_selected_rows(self):
        with self.assertRaises(FalsifierInputError):
            cascade.run_falsifier(
                ledger={"selected": ["T-0342"]},
                diff_hunks=DIFF,
                unselected_rows=[{"test_id": "T-0342"}, {"test_id": "T-0404"}],
                selected_ids=["T-0342"],
                propose=ScriptedProposer([]),
                verify=StubVerifier(),
                repo=REPO,
                ledger_is_final=True,
            )

    def test_falsifier_runs_alone_over_unselected_rows_and_logs_rejections(self):
        proposer = ScriptedProposer([as_envelope(missed_claim())])
        verifier = StubVerifier(default_gate="citation_invalid")
        outcome = cascade.run_falsifier(
            ledger={"selected": ["T-0342"], "stale": [], "unknown": []},
            diff_hunks=DIFF,
            unselected_rows=[{"test_id": "T-0404"}, {"test_id": "T-0405"}],
            selected_ids=["T-0342"],
            propose=proposer,
            verify=verifier,
            repo=REPO,
            ledger_is_final=True,
        )

        self.assertEqual(outcome.status, "unconfirmed")
        self.assertEqual(outcome.safe_direction_ids, ["T-0404"])
        self.assertEqual(proposer.calls[0]["role"], "falsifier")
        bundle = proposer.calls[0]["bundle"]
        self.assertEqual([r["test_id"] for r in bundle["unselected_rows"]], ["T-0404", "T-0405"])
        self.assertEqual(bundle["selected_ids"], ["T-0342"])
        ledger_entry = outcome.rejection_ledger()[0]
        self.assertEqual(ledger_entry["role"], "falsifier")
        self.assertEqual(ledger_entry["gate"], "citation_invalid")
        self.assertEqual(ledger_entry["claim_ref"], MISSED_REF)

    def test_falsifier_hit_joins_the_selection(self):
        proposer = ScriptedProposer([as_envelope(missed_claim())])
        verifier = StubVerifier(accept=[MISSED_REF])
        outcome = cascade.run_falsifier(
            ledger={"selected": ["T-0342"]},
            diff_hunks=DIFF,
            unselected_rows=[{"test_id": "T-0404"}],
            selected_ids=["T-0342"],
            propose=proposer,
            verify=verifier,
            repo=REPO,
            ledger_is_final=True,
        )

        self.assertEqual(outcome.status, "accepted")
        self.assertEqual(outcome.accepted[0]["claim_type"], "missed")
        self.assertEqual(envelope.claim_ref(outcome.accepted[0]), MISSED_REF)


if __name__ == "__main__":
    unittest.main()
