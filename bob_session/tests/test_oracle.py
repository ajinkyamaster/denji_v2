"""The oracle: T4 pins the defect that blinded the first instrument.

The defect, restated so it cannot creep back: the demo repository's ``pytest.ini``
sets ``addopts = -m "not contract"``. A default run therefore collects 497 tests
instead of 500, and the three it drops are the only tests that discriminate the
change. The first oracle reported "no regression" with complete confidence. An
instrument must be able to report its own blindness.
"""

import hashlib
import json
import subprocess
import sys

import pytest

from bob_session.oracle import run_oracle

from .conftest import DEMO, INVENTORY, INVENTORY_XLSX
from bob_session.pipeline.inventory import load_inventory

CHANGE = DEMO / "revisions" / "post_change.diff"


@pytest.fixture(scope="module")
def oracle():
    return run_oracle(
        repo=DEMO,
        patch=CHANGE,
        inventory_total=500,
        timeout=300,
    )


def test_T4_default_marker_run_is_incomplete_and_the_full_run_is_complete(oracle):
    assert oracle["complete"] is True
    assert oracle["collected"] == 500
    assert oracle["collected_a"] == oracle["collected_b"] == 500
    assert oracle["default_marker_collected"] == 497, (
        "the default-marker control must show the instrument is narrower than the population"
    )
    # The defect itself, enacted rather than quoted: run the SAME instrument under
    # the marker set the demo repository defaults to (addopts = -m "not contract").
    # It must report complete:false and say why - an instrument that is narrower
    # than the population it measures and still reports confidence is the bug this
    # project exists not to have (O1).
    under_default_markers = run_oracle(
        repo=DEMO,
        patch=CHANGE,
        inventory_total=500,
        timeout=300,
        run_cmd=["-m", "pytest", "-q", "-p", "no:cacheprovider"],
    )
    assert under_default_markers["collected"] == 497
    assert under_default_markers["complete"] is False, "a partial instrument must never report complete"
    assert "VOID" in under_default_markers["note"], "the measurement must be marked void, with the reason"


def test_oracle_returns_a_small_specific_non_empty_changed_list(oracle):
    assert len(oracle["changed"]) == 3
    assert all("test_report_worker" in node for node in oracle["changed"])
    assert {node.split("[")[-1].rstrip("]") for node in oracle["changed"]} == {"T-0340", "T-0341", "T-0342"}


def test_oracle_excludes_nothing_it_should_not(oracle):
    assert oracle["flaky_excluded"] == []
    assert oracle["already_red"] == []
    assert oracle["mode"] == "patch"


def test_oracle_output_is_deterministic(oracle):
    assert oracle["outcome"] == dict(sorted(oracle["outcome"].items()))


def test_completeness_fails_when_the_inventory_exceeds_the_suite(tmp_path):
    """A partial instrument must report complete:false rather than confidence."""
    result = run_oracle(repo=DEMO, patch=CHANGE, inventory_total=501, timeout=300)
    assert result["complete"] is False
    assert "VOID" in result["note"]


def test_oracle_never_mutates_the_input_repository():
    before = _tree_digest(DEMO)
    run_oracle(repo=DEMO, patch=CHANGE, inventory_total=500, timeout=300)
    assert _tree_digest(DEMO) == before


def test_oracle_refuses_a_patch_that_does_not_reverse_apply():
    with pytest.raises(RuntimeError, match="could not reconstruct"):
        run_oracle(repo=DEMO, patch=str(INVENTORY), inventory_total=500, timeout=120)


def test_T11_a_test_that_flips_between_repeats_is_excluded_from_ground_truth(tmp_path):
    """T11: an intermittent node is excluded from ground truth AND counted.

    Why this is measurement validity rather than a nicety: ``recall`` is measured
    against ``changed``. A test that fails on one repeat and passes on the next is
    a coin flip, so allowing it into that set means publishing a recall number
    against noise - the instrument would report a regression that a rerun denies.
    ``flaky_excluded`` therefore has to be both a subtraction and a visible count,
    never a silent drop.

    The scratch repository carries both cases side by side:

      * ``test_stable_regression`` passes at A (value.txt is ``1``) and fails at B
        (value.txt is ``2``) - a genuine discriminator;
      * ``test_flips_between_repeats`` keeps a run counter and alternates pass/fail
        - flaky by construction, whatever the revision says.
    """
    (tmp_path / "value.txt").write_text("2\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_stable.py").write_text(
        "import pathlib\n\n\n"
        "def test_stable_regression():\n"
        "    value = pathlib.Path(__file__).resolve().parents[1] / 'value.txt'\n"
        "    assert value.read_text(encoding='utf-8').strip() == '1'\n",
        encoding="utf-8",
    )
    (tests / "test_flippy.py").write_text(
        "import pathlib\n\n\n"
        "def test_flips_between_repeats():\n"
        "    state = pathlib.Path(__file__).with_name('flippy.state')\n"
        "    count = int(state.read_text(encoding='utf-8')) if state.exists() else 0\n"
        "    state.write_text(str(count + 1), encoding='utf-8')\n"
        "    assert count % 2 == 0, 'flaky by construction'\n",
        encoding="utf-8",
    )
    patch = tmp_path / "change.diff"
    patch.write_text(
        "diff --git a/value.txt b/value.txt\n"
        "--- a/value.txt\n"
        "+++ b/value.txt\n"
        "@@ -1 +1 @@\n"
        "-1\n"
        "+2\n",
        encoding="utf-8",
    )
    result = run_oracle(repo=tmp_path, patch=patch, inventory_total=2, repeat=2, timeout=300)
    assert result["repeat"] == 2
    assert result["complete"] is True
    assert result["flaky_excluded"], "the flipping node must be excluded AND counted"
    assert all("flips" in node for node in result["flaky_excluded"]), "exactly the intermittent node is excluded"
    assert not any("flips" in node for node in result["changed"]), "ground truth may not contain a coin flip"
    assert any("stable" in node for node in result["changed"]), "the genuine discriminator still counts"


def test_T11_the_exclusion_is_empty_when_flakiness_was_never_looked_for():
    """``repeat=1`` cannot detect flakiness, so it must SAY so rather than imply it.

    The control half of T11: a run that never repeats anything reports
    ``flaky_excluded: []`` - which would be indistinguishable from "looked and
    found none" if the note did not state that detection requires ``repeat>1``.
    """
    result = run_oracle(repo=DEMO, patch=CHANGE, inventory_total=500, timeout=300, repeat=1)
    assert result["flaky_excluded"] == []
    assert "repeat>1" in result["note"]


def _tree_digest(root):
    import pathlib

    digest = hashlib.sha256()
    for path in sorted(pathlib.Path(root).rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and ".pytest_cache" not in path.parts:
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()
