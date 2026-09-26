"""Tests for the subagent dispatch rules (person_b.txt section 7).

  RULE 3  NEVER let two subagents write the same file.
  RULE 4  Complete context per unit; a subagent returns ONLY a claim envelope.

Both are enforced in code (`dispatch.py`), not merely documented.
"""

from __future__ import annotations

import unittest

from bob_session.roles import context, dispatch, envelope
from bob_session.roles.errors import (
    EnvelopeError,
    SequentialRoleInParallel,
    TwoWritersOneFile,
)
from bob_session.roles.testing import as_envelope, as_json, scout_claim, scout_unit


class OneWriterOneFileTest(unittest.TestCase):
    def test_second_writer_of_one_file_is_refused(self):
        registry = dispatch.WriterRegistry()
        registry.claim_file("tests/test_a.py", role="author", unit_id="u1")
        with self.assertRaises(TwoWritersOneFile):
            registry.claim_file("tests/test_a.py", role="author", unit_id="u2")

    def test_the_same_unit_may_reclaim_its_file(self):
        registry = dispatch.WriterRegistry()
        registry.claim_file("tests/test_a.py", role="author", unit_id="u1")
        registry.claim_file("tests/test_a.py", role="author", unit_id="u1")
        self.assertEqual(registry.owner_of("tests/test_a.py"), ("author", "u1"))

    def test_a_parallel_wave_with_two_writers_is_refused(self):
        wave = [
            {"unit_id": "u1", "target_file": "t.py"},
            {"unit_id": "u2", "target_file": "t.py"},
        ]
        with self.assertRaises(TwoWritersOneFile):
            dispatch.assert_no_parallel_writers(wave)


class WavePlanningTest(unittest.TestCase):
    UNITS = [
        {"unit_id": "u1", "target_file": "tests/test_a.py"},
        {"unit_id": "u2", "target_file": "tests/test_a.py"},
        {"unit_id": "u3", "target_file": "tests/test_b.py"},
    ]

    def test_same_file_units_are_serialised(self):
        waves = dispatch.plan_waves(self.UNITS)
        self.assertEqual(len(waves), 2)
        self.assertEqual({u["unit_id"] for u in waves[0]}, {"u1", "u3"})
        self.assertEqual({u["unit_id"] for u in waves[1]}, {"u2"})

    def test_disjoint_files_share_a_wave(self):
        units = [
            {"unit_id": "u1", "target_file": "a.py"},
            {"unit_id": "u2", "target_file": "b.py"},
        ]
        waves = dispatch.plan_waves(units)
        self.assertEqual(len(waves), 1)
        self.assertEqual({u["unit_id"] for u in waves[0]}, {"u1", "u2"})

    def test_no_wave_ever_contains_two_writers_of_one_file(self):
        waves = dispatch.plan_waves(self.UNITS)
        for wave in waves:
            files = [u["target_file"] for u in wave]
            self.assertEqual(len(files), len(set(files)))

    def test_same_inputs_produce_the_same_schedule(self):
        self.assertEqual(dispatch.plan_waves(self.UNITS), dispatch.plan_waves(self.UNITS))

    def test_planning_releases_each_claim_when_the_wave_finishes(self):
        registry = dispatch.WriterRegistry()
        dispatch.plan_waves(self.UNITS, writers=registry)
        self.assertEqual(registry.owners, {}, "a wave must release its claims when it completes")

    def test_planning_refuses_a_file_already_held_by_another_writer(self):
        registry = dispatch.WriterRegistry()
        registry.claim_file("tests/test_a.py", role="author", unit_id="running-now")
        with self.assertRaises(TwoWritersOneFile):
            dispatch.plan_waves([{"unit_id": "u1", "target_file": "tests/test_a.py"}], writers=registry)

    def test_falsifier_may_not_join_a_parallel_wave(self):
        with self.assertRaises(SequentialRoleInParallel):
            dispatch.assert_parallelisable("falsifier")
        with self.assertRaises(SequentialRoleInParallel):
            dispatch.plan_waves([{"unit_id": "u1", "target_file": "x.py"}], role="falsifier")

    def test_parallelisable_roles_pass(self):
        for role in dispatch.PARALLEL_ROLES:
            with self.subTest(role=role):
                dispatch.assert_parallelisable(role)


class SubagentBoundaryTest(unittest.TestCase):
    def test_subagent_returns_only_the_claim_envelope(self):
        bundle = context.assemble_scout(scout_unit()).bundle

        def model(prompt: str) -> str:
            return as_json(as_envelope(scout_claim()))

        claims = dispatch.invoke_subagent("scout", bundle, model)
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["claim_type"], "link_exists")
        self.assertEqual(list(claims[0]), list(envelope.ENVELOPE_KEYS))

    def test_reasoning_prose_instead_of_an_envelope_is_rejected(self):
        bundle = context.assemble_scout(scout_unit()).bundle

        def model(prompt: str) -> str:
            return "I would need to see the whole file before I can decide."

        with self.assertRaises(EnvelopeError):
            dispatch.invoke_subagent("scout", bundle, model)

    def test_subagent_receives_only_its_own_bundle(self):
        bundle = context.assemble_scout(scout_unit()).bundle
        seen: dict[str, str] = {}

        def model(prompt: str) -> str:
            seen["prompt"] = prompt
            return as_json(as_envelope(scout_claim()))

        dispatch.invoke_subagent("scout", bundle, model)
        self.assertIn("T-0342", seen["prompt"])
        self.assertNotIn("T-9999", seen["prompt"])
        self.assertIn("--- RUN ENVELOPE ---", seen["prompt"])


if __name__ == "__main__":
    unittest.main()
