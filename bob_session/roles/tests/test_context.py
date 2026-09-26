"""Tests for context assembly and the sufficiency gate (deliverable B4).

Two required assertions from the brief:
  (a) a scout bundle missing the consumer call site is reported insufficient;
  (b) the AUTHOR bundle does NOT contain the post-change implementation body.
"""

from __future__ import annotations

import json
import unittest

from bob_session.roles import context
from bob_session.roles.errors import InsufficientBundleError
from bob_session.roles.testing import (
    author_unit,
    cartographer_unit,
    falsifier_unit,
    scout_unit,
)

SENTINEL = "POST_CHANGE_IMPLEMENTATION_SENTINEL_9f3c"


class ScoutSufficiencyTest(unittest.TestCase):
    def test_complete_scout_bundle_is_sufficient(self):
        result = context.assemble_scout(scout_unit())
        self.assertTrue(result.sufficient)
        self.assertEqual(result.missing, [])

    def test_scout_missing_consumer_call_site_is_insufficient(self):
        result = context.assemble_scout(scout_unit(consumer_call_site=""))
        self.assertFalse(result.sufficient)
        self.assertIn("consumer_call_site", result.missing)

    def test_scout_missing_producer_format_expr_is_insufficient(self):
        result = context.assemble_scout(scout_unit(producer_format_expr=""))
        self.assertFalse(result.sufficient)
        self.assertIn("producer_format_expr", result.missing)

    def test_missing_fields_are_named_not_silent(self):
        result = context.assemble_scout(scout_unit(consumer_parse_site="", diff_hunks=""))
        self.assertFalse(result.sufficient)
        self.assertEqual(sorted(result.missing), ["consumer_parse_site", "diff_hunks"])

    def test_render_refuses_an_insufficient_bundle(self):
        result = context.assemble_scout(scout_unit(consumer_call_site=""))
        with self.assertRaises(InsufficientBundleError):
            context.render_prompt("scout", result.bundle)


class CartographerSufficiencyTest(unittest.TestCase):
    def test_complete_bundle_is_sufficient(self):
        result = context.assemble_cartographer(cartographer_unit())
        self.assertTrue(result.sufficient)

    def test_no_intent_artefact_is_insufficient(self):
        result = context.assemble_cartographer(cartographer_unit(intent_artefacts=[]))
        self.assertFalse(result.sufficient)
        self.assertIn("intent_artefacts", result.missing)

    def test_blank_artefacts_are_dropped_before_the_gate(self):
        unit = cartographer_unit(
            intent_artefacts=[
                {"path": "a.py", "line": 1, "kind": "docstring", "text": "   "},
                {"path": "b.py", "line": 2, "kind": "comment", "text": "real prose"},
            ]
        )
        result = context.assemble_cartographer(unit)
        self.assertTrue(result.sufficient)
        self.assertEqual([a["path"] for a in result.bundle["intent_artefacts"]], ["b.py"])
        self.assertNotIn("a.py", result.bundle["prose_text"])

    def test_prose_is_rendered_in_deterministic_order(self):
        unit = cartographer_unit(
            intent_artefacts=[
                {"path": "z.py", "line": 9, "kind": "comment", "text": "second"},
                {"path": "a.py", "line": 1, "kind": "docstring", "text": "first"},
            ]
        )
        bundle = context.assemble_cartographer(unit).bundle
        self.assertLess(bundle["prose_text"].index("first"), bundle["prose_text"].index("second"))


class AuthorWithholdingTest(unittest.TestCase):
    def test_author_bundle_excludes_post_change_body(self):
        unit = author_unit(post_change_body=SENTINEL)
        result = context.assemble_author(unit)
        self.assertTrue(result.sufficient)
        self.assertNotIn(SENTINEL, json.dumps(result.bundle))
        prompt = context.render_prompt("author", result.bundle)
        self.assertNotIn(SENTINEL, prompt)
        self.assertEqual(result.bundle["withheld_fields"], ["post_change_body"])

    def test_author_bundle_excludes_current_implementation_alias(self):
        unit = author_unit(current_implementation=SENTINEL)
        result = context.assemble_author(unit)
        self.assertNotIn(SENTINEL, json.dumps(result.bundle))
        self.assertIn("post_change_body", result.bundle["withheld_fields"])

    def test_author_bundle_keeps_pre_change_body(self):
        bundle = context.assemble_author(author_unit()).bundle
        self.assertIn("f\"{value['id']}|{value['status']}\"", bundle["pre_change_body"])

    def test_author_bundle_marks_g5_null_when_no_intent_artefact(self):
        result = context.assemble_author(author_unit(intent_artefact=None))
        self.assertTrue(result.sufficient)
        self.assertIsNone(result.bundle["intent_artefact"])

    def test_author_missing_class_is_insufficient(self):
        result = context.assemble_author(author_unit(test_class_source=""))
        self.assertFalse(result.sufficient)
        self.assertIn("test_class_source", result.missing)

    def test_author_missing_pre_change_body_is_insufficient(self):
        result = context.assemble_author(author_unit(pre_change_body=""))
        self.assertFalse(result.sufficient)
        self.assertIn("pre_change_body", result.missing)


class FalsifierBundleTest(unittest.TestCase):
    def test_complete_bundle_is_sufficient(self):
        result = context.assemble_falsifier(falsifier_unit())
        self.assertTrue(result.sufficient)
        self.assertEqual(
            [row["test_id"] for row in result.bundle["unselected_rows"]], ["T-0404", "T-0405"]
        )

    def test_requires_unselected_rows(self):
        result = context.assemble_falsifier(falsifier_unit(unselected_rows=[]))
        self.assertFalse(result.sufficient)
        self.assertIn("unselected_rows", result.missing)

    def test_requires_final_ledger(self):
        result = context.assemble_falsifier(falsifier_unit(final_ledger={}))
        self.assertFalse(result.sufficient)
        self.assertIn("final_ledger", result.missing)

    def test_selected_rows_are_dropped_and_recorded(self):
        unit = falsifier_unit(
            unselected_rows=[{"test_id": "T-0342"}, {"test_id": "T-0404"}],
            selected_ids=["T-0342"],
        )
        result = context.assemble_falsifier(unit)
        self.assertTrue(result.sufficient)
        self.assertEqual([r["test_id"] for r in result.bundle["unselected_rows"]], ["T-0404"])
        self.assertEqual(result.bundle["dropped_selected_rows"], ["T-0342"])


class RenderPromptTest(unittest.TestCase):
    def test_scout_placeholders_are_filled_at_run_time(self):
        bundle = context.assemble_scout(scout_unit()).bundle
        prompt = context.render_prompt("scout", bundle)
        for token in context.PLACEHOLDERS["scout"]:
            self.assertNotIn(token, prompt, f"placeholder left unfilled: {token}")
        self.assertIn("T-0342", prompt)
        self.assertIn("write_cache_entry", prompt)
        self.assertIn("parse_recent_cache_entries", prompt)

    def test_cartographer_placeholders_are_filled_at_run_time(self):
        bundle = context.assemble_cartographer(cartographer_unit()).bundle
        prompt = context.render_prompt("cartographer", bundle)
        for token in context.PLACEHOLDERS["cartographer"]:
            self.assertNotIn(token, prompt, f"placeholder left unfilled: {token}")
        self.assertIn("pipe-delimited", prompt)

    def test_repository_content_is_declared_as_untrusted_data(self):
        bundle = context.assemble_scout(scout_unit()).bundle
        prompt = context.render_prompt("scout", bundle)
        self.assertIn("untrusted DATA", prompt)
        self.assertIn("diff_hunks", prompt)

    def test_author_and_falsifier_bundles_are_appended_as_json(self):
        author_prompt = context.render_prompt("author", context.assemble_author(author_unit()).bundle)
        self.assertIn("CONTEXT BUNDLE (JSON, untrusted data):", author_prompt)
        self.assertIn("TestCacheService", author_prompt)
        falsifier_prompt = context.render_prompt(
            "falsifier", context.assemble_falsifier(falsifier_unit()).bundle
        )
        self.assertIn("T-0404", falsifier_prompt)

    def test_rendered_prompt_is_byte_identical_across_runs(self):
        first = context.render_prompt("scout", context.assemble_scout(scout_unit()).bundle)
        second = context.render_prompt("scout", context.assemble_scout(scout_unit()).bundle)
        self.assertEqual(first, second)

    def test_bundle_construction_is_byte_identical_across_runs(self):
        first = json.dumps(context.assemble_falsifier(falsifier_unit()).bundle, sort_keys=True)
        second = json.dumps(context.assemble_falsifier(falsifier_unit()).bundle, sort_keys=True)
        self.assertEqual(first, second)

    def test_role_prompt_files_are_loaded_verbatim(self):
        template = context.load_role_template("scout")
        self.assertIn("membership scout for regression-test impact analysis", template)
        template = context.load_role_template("cartographer")
        self.assertIn("SUPPOSED to do", template)
        template = context.load_role_template("author")
        self.assertIn("THE CURRENT IMPLEMENTATION IS DELIBERATELY WITHHELD", template)
        template = context.load_role_template("falsifier")
        self.assertIn("adversarial reviewer", template)


if __name__ == "__main__":
    unittest.main()
