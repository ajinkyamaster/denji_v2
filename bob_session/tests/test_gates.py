"""G1..G5: the gates that decide whether an authored test is admissible.

The G3-rejects-a-collection-error test is the important one. Without C14's
qualification, a test that fails at the previous revision merely because the
symbol does not exist yet would pass G3 - "all 400 pass, none catch the bug".
"""

import pathlib

import pytest

from bob_session import gates

from .conftest import AUTHORED_PATCH, CHANGE, DEMO

COLLECTION_FAILURE = """diff --git a/tests/test_invented.py b/tests/test_invented.py
new file mode 100644
--- /dev/null
+++ b/tests/test_invented.py
@@ -0,0 +1,6 @@
+import pytest
+
+
+def test_symbol_that_never_existed():
+    from app.services.cache_service import build_cache_payload
+
+    assert build_cache_payload("k", "ok", 1)
"""

BROKEN_SYNTAX = """diff --git a/tests/test_broken.py b/tests/test_broken.py
new file mode 100644
--- /dev/null
+++ b/tests/test_broken.py
@@ -0,0 +1,3 @@
+import pytest
+
+def test_broken(:
"""

NOOP_ASSERTION = """diff --git a/tests/test_noop.py b/tests/test_noop.py
new file mode 100644
--- /dev/null
+++ b/tests/test_noop.py
@@ -0,0 +1,5 @@
+import pytest
+
+
+def test_nothing_in_particular():
+    assert True
"""

# A deliberately flaky test: it keeps a run counter next to itself and alternates
# pass/fail. Construction notes, because the hunk counts must be exact for
# `git apply` and because the state must survive across the five G2 runs:
#   * G2 runs all five times inside ONE sandbox copy, so the counter persists;
#   * --collect-only never executes the body, so collection does not move the
#     counter and G1 still passes - which is what isolates G2 as the rejecting gate.
INTERMITTENT = """diff --git a/tests/test_intermittent.py b/tests/test_intermittent.py
new file mode 100644
--- /dev/null
+++ b/tests/test_intermittent.py
@@ -0,0 +1,8 @@
+import pathlib
+
+
+def test_passes_only_some_of_the_time():
+    state = pathlib.Path(__file__).with_name("intermittent.state")
+    count = int(state.read_text(encoding="utf-8")) if state.exists() else 0
+    state.write_text(str(count + 1), encoding="utf-8")
+    assert count % 2 == 0, "flaky by construction: fails every second run"
"""


def test_g2_rejects_a_test_that_passes_only_some_of_the_time():
    """G2 observed to fail: a test that passes sometimes is flaky, and flaky is discarded.

    Without this gate the suite would admit an intermittent test and G2 would be a
    claim rather than a check - a check that has never been observed to fail is not
    a check.
    """
    result = gates.run_gates(
        repo=DEMO,
        test_patch=INTERMITTENT,
        symbol="app.services.cache_service.write_cache_entry",
        change_patch=None,
        test_path="tests/test_intermittent.py",
        timeout=120,
    )
    assert result["g1_buildable"] is True, "G1 passes: the rejection must come from G2"
    assert len(result["g2_runs"]) == gates.G2_RUNS
    assert set(result["g2_runs"]) == {True, False}, "the test must pass on some runs and fail on others"
    assert result["g2_passes_5x"] is False
    assert result["accepted"] is False


def test_g3_rejects_a_failure_whose_origin_is_collection_or_import():
    """A failing import proves the symbol is ABSENT, not that behaviour changed."""
    result = gates.run_gates(
        repo=DEMO,
        test_patch=COLLECTION_FAILURE,
        symbol="app.services.cache_service.build_cache_payload",
        change_patch=None,
        test_path="tests/test_invented.py",
        timeout=120,
    )
    assert result["g3_failure_origin"] in (None, "collection")
    assert result["g3_assertion_fires_at_a"] is False
    assert result["accepted"] is False


def test_g1_fails_loudly_on_an_uncollectable_test_file():
    result = gates.run_gates(
        repo=DEMO,
        test_patch=BROKEN_SYNTAX,
        symbol="anything",
        change_patch=None,
        test_path="tests/test_broken.py",
        timeout=120,
    )
    assert result["g1_buildable"] is False
    assert result["accepted"] is False


def test_g4_refuses_a_test_that_survives_every_perturbation():
    """A test that notices nothing about the changed lines is not pinning them."""
    result = gates.run_gates(
        repo=DEMO,
        test_patch=NOOP_ASSERTION,
        symbol="app.services.cache_service.write_cache_entry",
        change_patch=CHANGE,
        test_path="tests/test_noop.py",
        timeout=120,
    )
    assert result["g4_mutation_strength"] == 0.0
    assert result["accepted"] is False


def test_g5_is_null_without_an_intent_artefact():
    result = gates.run_gates(
        repo=DEMO,
        test_patch=NOOP_ASSERTION,
        symbol="app.services.cache_service.write_cache_entry",
        change_patch=None,
        test_path="tests/test_noop.py",
        timeout=120,
    )
    assert result["g5_spec_anchored"] is None, "the gate must never invent an anchor"


def test_g5_anchors_when_the_assertion_encodes_the_specification():
    patch = """diff --git a/tests/test_spec_anchor.py b/tests/test_spec_anchor.py
new file mode 100644
--- /dev/null
+++ b/tests/test_spec_anchor.py
@@ -0,0 +1,8 @@
+import pathlib
+
+import pytest
+
+
+def test_documented_format():
+    text = (pathlib.Path(__file__).resolve().parents[1] / "app/workers/report_worker.py").read_text()
+    assert "pipe-delimited" in text
"""
    result = gates.run_gates(
        repo=DEMO,
        test_patch=patch,
        symbol="app.workers.report_worker.parse_recent_cache_entries",
        change_patch=None,
        test_path="tests/test_spec_anchor.py",
        intent={
            "path": "app/workers/report_worker.py",
            "line": 4,
            "quote": "cache entries are pipe-delimited records",
        },
        timeout=120,
    )
    assert result["g5_spec_anchored"] is True


def test_the_authored_patch_clears_every_gate():
    """The end-to-end acceptance path, on the repository's own fixture."""
    result = gates.run_gates(
        repo=DEMO,
        test_patch=AUTHORED_PATCH,
        symbol="app.services.cache_service.build_cache_payload",
        change_patch=CHANGE,
        test_path="tests/test_cache_service.py",
        timeout=180,
    )
    assert result["g1_buildable"] is True
    assert result["g2_passes_5x"] is True
    assert result["g2_runs"] == [True] * 5
    assert result["g3_assertion_fires_at_a"] is True
    assert result["g3_failure_origin"] == "assertion"
    assert result["g4_mutation_strength"] > 0
    assert result["accepted"] is True


def test_the_sandbox_never_writes_into_the_analysed_repository():
    before = _tree_digest(pathlib.Path(DEMO))
    gates.run_gates(
        repo=DEMO,
        test_patch=NOOP_ASSERTION,
        symbol="app.services.cache_service.write_cache_entry",
        change_patch=CHANGE,
        test_path="tests/test_noop.py",
        timeout=120,
    )
    assert _tree_digest(pathlib.Path(DEMO)) == before


def _tree_digest(root):
    import hashlib

    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and ".pytest_cache" not in path.parts:
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()
