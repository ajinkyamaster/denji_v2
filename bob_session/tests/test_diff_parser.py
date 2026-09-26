"""The diff parser and rho(D).

The inertness rules are the second soundness lever, so each clause gets a test
that fails if the clause is removed:

  * a log reword is inert (or 75 control tests come back, which T12 pins);
  * a separator change is NOT inert (or the hero catch disappears);
  * a numeric change is NOT inert (or a behavioural change is silently skipped);
  * a docs-only change is inert and selects nothing (the reachability control).
"""

import pytest

from bob_session.pipeline.diff_parser import (
    DiffError,
    parse_diff,
    previous_source,
    representations,
    skeleton,
)

from .conftest import BEHAVIOURAL_CONTROL, CHANGE, DOCS_ONLY

REWORD = """diff --git a/app/services/billing_service.py b/app/services/billing_service.py
--- a/app/services/billing_service.py
+++ b/app/services/billing_service.py
@@ -10,4 +10,4 @@ def settle(account_id, amount_cents):
     receipt = build_receipt(account_id, amount_cents)
-    logger.info("settled account %s", account_id)
+    logger.info("settlement complete for %s", account_id)
     return receipt
"""

NUMERIC = """diff --git a/app/services/billing_service.py b/app/services/billing_service.py
--- a/app/services/billing_service.py
+++ b/app/services/billing_service.py
@@ -6,3 +6,3 @@
-FEE_BPS = 25
+FEE_BPS = 30
"""

SEPARATOR = """diff --git a/app/services/cache_service.py b/app/services/cache_service.py
--- a/app/services/cache_service.py
+++ b/app/services/cache_service.py
@@ -16,3 +16,3 @@ def write_cache_entry(key, status, count, sink=None):
-    payload = f"{key}|{status}|{count}"
+    payload = f"{key}:{status}:{count}"
     if sink is not None:
"""

MALFORMED = """diff --git a/app/x.py b/app/x.py
--- a/app/x.py
+++ b/app/x.py
@@ not a hunk header @@
"""


def test_demo_change_parses_and_names_three_files(change_diff):
    diff = parse_diff(CHANGE.read_text(encoding="utf-8"))
    assert sorted(diff.paths) == [
        "README.md",
        "app/services/billing_service.py",
        "app/services/cache_service.py",
    ]
    assert diff.changed_modules == ["app.services.cache_service"]
    assert diff.inert_modules == ["app.services.billing_service"]


def test_log_reword_is_proven_inert(change_diff):
    diff = parse_diff(CHANGE.read_text(encoding="utf-8"))
    billing = next(parsed for parsed in diff.files if parsed.path.endswith("billing_service.py"))
    assert billing.inert is True
    assert billing.inert_reason == "string_content_in_unobservable_position"


def test_billing_reword_really_is_inert():
    diff = parse_diff(REWORD)
    billing = diff.files[0]
    assert billing.inert is True, "a reworded log message must not license re-running tests"


def test_numeric_constant_change_is_not_inert():
    diff = parse_diff(NUMERIC)
    assert diff.files[0].inert is False, "a changed constant is a behavioural change"


def test_separator_change_is_not_inert():
    diff = parse_diff(SEPARATOR)
    parsed = diff.files[0]
    assert parsed.inert is False
    assert 'separator "|"' in parsed.removed_representations
    assert 'separator ":"' in parsed.added_representations


def test_docs_only_change_is_inert_and_selects_nothing():
    diff = parse_diff(DOCS_ONLY.read_text(encoding="utf-8"))
    assert diff.changed_modules == []
    assert all(parsed.inert for parsed in diff.files)


def test_malformed_hunk_header_raises_and_names_the_line():
    with pytest.raises(DiffError) as error:
        parse_diff(MALFORMED, source="scratch.diff")
    assert "line 4" in str(error.value)


def test_unexpected_line_raises():
    with pytest.raises(DiffError, match="unexpected diff line"):
        parse_diff("diff --git a/x b/x\n--- a/x\n+++ b/x\nnonsense\n", source="scratch.diff")


def test_rename_is_detected_not_reported_as_delete_plus_add():
    text = (
        "diff --git a/app/old.py b/app/new.py\n"
        "similarity index 100%\n"
        "rename from app/old.py\n"
        "rename to app/new.py\n"
    )
    diff = parse_diff(text)
    assert diff.files[0].status == "renamed"
    assert diff.files[0].path == "app/new.py"
    assert diff.files[0].inert is False, "a rename must never be treated as an inert no-op"


def test_binary_and_non_python_files_are_declared_not_ignored():
    text = (
        "diff --git a/assets/logo.png b/assets/logo.png\n"
        "Binary files a/assets/logo.png and b/assets/logo.png differ\n"
        "diff --git a/docs/guide.md b/docs/guide.md\n"
        "--- a/docs/guide.md\n"
        "+++ b/docs/guide.md\n"
        "@@ -1 +1 @@\n-old\n+new\n"
    )
    diff = parse_diff(text)
    binary = diff.files[0]
    assert binary.is_binary is True and binary.inert is True
    markdown = diff.files[1]
    assert markdown.unsupported == "unsupported_file_type"
    assert markdown.inert is True


def test_skeleton_blanks_string_content():
    assert skeleton('logger.info("a", x)') == skeleton('logger.info("b", x)')
    assert skeleton("payload = 1") != skeleton("payload = 2")


def test_representations_find_separators_and_serializers():
    separators, serializers = representations('entry.split("|")')
    assert separators == {"|"}
    assert serializers == set()
    separators, serializers = representations('return json.dumps({"a": 1})')
    assert serializers == {"json.dumps"}
    separators, serializers = representations('payload = f"{key}|{status}"')
    assert separators == {"|"}


def test_rho_reports_what_the_change_removed(change_diff):
    diff = parse_diff(CHANGE.read_text(encoding="utf-8"))
    rho = diff.rho()
    assert rho["removed_representations"] == ['separator "|"']
    assert rho["added_representations"] == ["serializer json.dumps(...)"]
    assert rho["semantics_modifying"] == ["app.services.cache_service"]
    assert rho["inert_modules"] == ["app.services.billing_service"]
    assert rho["removed_symbols"] == []


def test_previous_source_reconstruction_is_exact(scratch_repo, project):
    """Rebuilding revision A from the diff alone must equal the checked-in revision A."""
    diff = parse_diff(CHANGE.read_text(encoding="utf-8"))
    cache = next(parsed for parsed in diff.files if parsed.path == "app/services/cache_service.py")
    rebuilt = previous_source(cache, (scratch_repo / cache.path).read_text(encoding="utf-8"))
    expected = (project / "fixtures" / "rev_a" / "app" / "services" / "cache_service.py").read_text(encoding="utf-8")
    assert rebuilt == expected


def test_previous_source_of_a_new_file_is_none():
    text = (
        "diff --git a/app/new.py b/app/new.py\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/app/new.py\n"
        "@@ -0,0 +1,1 @@\n+x = 1\n"
    )
    diff = parse_diff(text)
    assert previous_source(diff.files[0], "x = 1\n") is None
