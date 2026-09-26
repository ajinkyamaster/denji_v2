"""Tests for the strict claim envelope (person_b.txt section 2.2).

The envelope is the only language the models may speak. These tests pin the two
properties that matter: malformed output is REJECTED (never salvaged), and the
per-role contract is exact.
"""

from __future__ import annotations

import json
import unittest

from bob_session.roles import envelope
from bob_session.roles.errors import EnvelopeError
from bob_session.roles.testing import (
    as_envelope,
    as_json,
    author_claim,
    intent_claim,
    missed_claim,
    scout_claim,
)


class StrictJsonTest(unittest.TestCase):
    def test_valid_envelope_parses(self):
        claims = envelope.parse_claims("scout", as_envelope(scout_claim()))
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["claim_type"], "link_exists")

    def test_valid_envelope_parses_from_raw_json_text(self):
        raw = as_json(as_envelope(scout_claim()))
        claims = envelope.parse_claims("scout", raw)
        self.assertEqual(claims[0]["role"], "scout")

    def test_prose_around_the_json_is_rejected_not_salvaged(self):
        raw = "Here is the JSON you asked for:\n" + as_json(as_envelope(scout_claim()))
        with self.assertRaises(EnvelopeError):
            envelope.parse_claims("scout", raw)

    def test_markdown_fences_are_rejected(self):
        raw = "```json\n" + as_json(as_envelope(scout_claim())) + "\n```"
        with self.assertRaises(EnvelopeError):
            envelope.parse_claims("scout", raw)

    def test_empty_response_is_rejected(self):
        with self.assertRaises(EnvelopeError):
            envelope.parse_claims("scout", "   ")

    def test_top_level_shape_is_exact(self):
        with self.assertRaises(EnvelopeError):
            envelope.parse_claims("scout", {"claims": [], "notes": "extra"})
        with self.assertRaises(EnvelopeError):
            envelope.parse_claims("scout", [scout_claim()])

    def test_unknown_role_is_rejected(self):
        with self.assertRaises(EnvelopeError):
            envelope.parse_claims("referee", as_envelope(scout_claim()))


class ClaimValidationTest(unittest.TestCase):
    def test_role_must_match(self):
        claim = scout_claim()
        claim["role"] = "cartographer"
        with self.assertRaises(EnvelopeError):
            envelope.parse_claims("scout", as_envelope(claim))

    def test_claim_type_must_match_the_role(self):
        claim = scout_claim()
        claim["claim_type"] = "intent"
        with self.assertRaises(EnvelopeError):
            envelope.parse_claims("scout", as_envelope(claim))

    def test_extra_key_is_rejected(self):
        claim = scout_claim()
        claim["obviously_true"] = True
        with self.assertRaises(EnvelopeError):
            envelope.parse_claims("scout", as_envelope(claim))

    def test_missing_key_is_rejected(self):
        claim = scout_claim()
        del claim["rationale"]
        with self.assertRaises(EnvelopeError):
            envelope.parse_claims("scout", as_envelope(claim))

    def test_confidence_must_be_an_enum(self):
        claim = scout_claim(confidence="certain")
        with self.assertRaises(EnvelopeError):
            envelope.parse_claims("scout", as_envelope(claim))

    def test_rationale_is_bounded_at_200_chars(self):
        claim = scout_claim()
        claim["rationale"] = "x" * 201
        with self.assertRaises(EnvelopeError):
            envelope.parse_claims("scout", as_envelope(claim))

    def test_rationale_must_not_be_empty(self):
        claim = scout_claim()
        claim["rationale"] = "  "
        with self.assertRaises(EnvelopeError):
            envelope.parse_claims("scout", as_envelope(claim))

    def test_citations_must_not_be_empty(self):
        claim = scout_claim(citations=[])
        with self.assertRaises(EnvelopeError):
            envelope.parse_claims("scout", as_envelope(claim))

    def test_citation_shape_is_exact(self):
        claim = scout_claim(citations=[{"path": "a.py", "symbol": "f"}])
        with self.assertRaises(EnvelopeError):
            envelope.parse_claims("scout", as_envelope(claim))

    def test_citation_line_must_be_a_positive_integer(self):
        claim = scout_claim(citations=[{"path": "a.py", "symbol": "f", "line": 0}])
        with self.assertRaises(EnvelopeError):
            envelope.parse_claims("scout", as_envelope(claim))

    def test_targets_keys_are_role_specific(self):
        claim = scout_claim()
        claim["targets"] = {"test_id": "T-1"}  # changed_symbol missing
        with self.assertRaises(EnvelopeError):
            envelope.parse_claims("scout", as_envelope(claim))

    def test_author_claim_requires_the_patch(self):
        claim = author_claim()
        del claim["targets"]["patch"]
        with self.assertRaises(EnvelopeError):
            envelope.parse_claims("author", as_envelope(claim))

    def test_valid_claims_for_all_four_roles(self):
        cases = [
            ("scout", scout_claim()),
            ("cartographer", intent_claim()),
            ("author", author_claim()),
            ("falsifier", missed_claim()),
        ]
        for role, claim in cases:
            with self.subTest(role=role):
                parsed = envelope.parse_claims(role, as_envelope(claim))
                self.assertEqual(parsed[0]["role"], role)

    def test_validated_claim_is_in_canonical_key_order(self):
        claim = scout_claim()
        parsed = envelope.parse_claims("scout", as_envelope(claim))[0]
        self.assertEqual(list(parsed), list(envelope.ENVELOPE_KEYS))

    def test_claim_ref_is_stable(self):
        self.assertEqual(envelope.claim_ref(scout_claim()), "scout:link_exists:T-0342")
        self.assertEqual(envelope.claim_ref(missed_claim("T-0404")), "falsifier:missed:T-0404")
        self.assertEqual(
            envelope.claim_ref(intent_claim()),
            "cartographer:intent:app.services.cache_service.write_cache_entry",
        )

    def test_round_trip_through_json_is_lossless(self):
        claims = envelope.parse_claims("scout", as_envelope(scout_claim()))
        self.assertEqual(json.loads(json.dumps(claims)), claims)


if __name__ == "__main__":
    unittest.main()
