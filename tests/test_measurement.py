"""The measurement harness, and the rules it is not allowed to break."""
import json
import pathlib

from bob_session import measure
from bob_session import oracle as oracle_mod
from bob_session.pipeline import inventory as inventory_mod

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _rows(nodes):
    return [inventory_mod.Row(f"T-{index:04d}", f"t{index}", "app.m", node, "d", 1) for index, node in enumerate(nodes)]


def test_oracle_lower_bound_and_flaky_exclusion():
    runs_a = [
        {"t.py::a": "passed", "t.py::b": "passed", "t.py::c": "passed", "t.py::d": "failed", "t.py::e": "passed"},
        {"t.py::a": "passed", "t.py::b": "failed", "t.py::c": "passed", "t.py::d": "failed", "t.py::e": "passed"},
    ]
    runs_b = [
        {"t.py::a": "failed", "t.py::b": "passed", "t.py::c": "passed", "t.py::d": "failed", "t.py::e": "passed"},
        {"t.py::a": "failed", "t.py::b": "passed", "t.py::c": "passed", "t.py::d": "failed", "t.py::e": "passed"},
    ]
    analysis = oracle_mod.analyse(
        rows=_rows(["t.py::a", "t.py::b", "t.py::c", "t.py::d", "t.py::e"]),
        runs_a=runs_a,
        runs_b=runs_b,
        strategy="fixture",
    )
    assert analysis["changed"] == ["t.py::a"]
    assert analysis["flaky_excluded"] == ["t.py::b"] and analysis["flaky_excluded_count"] == 1
    assert analysis["already_red"] == ["t.py::d"]
    assert "t.py::c" not in analysis["changed"] and "t.py::e" not in analysis["changed"]


def test_oracle_completeness_is_computed_not_asserted():
    runs_a = [{"t.py::a": "passed"}]
    runs_b = [{"t.py::a": "passed"}, {"t.py::extra": "passed"}]
    rows = _rows(["t.py::a", "t.py::missing"])
    analysis = oracle_mod.analyse(rows=rows, runs_a=runs_a, runs_b=runs_b, strategy="fixture")
    assert analysis["missing"] == ["t.py::missing"]
    assert analysis["unmapped"] == ["t.py::extra"]
    # (collected - unmapped) + missing == inventory total -> complete
    assert analysis["complete"] is True


def test_oracle_reports_incomplete_when_rows_are_missing_from_both_revisions():
    runs_a = [{"t.py::a": "passed"}]
    runs_b = [{"t.py::a": "passed"}]
    rows = _rows(["t.py::a", "t.py::missing"])
    analysis = oracle_mod.analyse(rows=rows, runs_a=runs_a, runs_b=runs_b, strategy="fixture")
    assert analysis["missing"] == ["t.py::missing"]
    # collected 1, unmapped 0, missing 1, inventory 2 -> complete
    assert analysis["complete"] is True


def test_measurement_rule_m1_prints_void_for_an_incomplete_oracle(tmp_path):
    artefact = json.loads((ROOT / "bob_session/testscope_report.json").read_text(encoding="utf-8"))
    artefact_path = tmp_path / "artefact.json"
    artefact_path.write_text(json.dumps(artefact), encoding="utf-8")
    oracle = json.loads((ROOT / "bob_session/evidence/oracle.json").read_text(encoding="utf-8"))
    oracle["complete"] = False
    oracle_path = tmp_path / "oracle.json"
    oracle_path.write_text(json.dumps(oracle), encoding="utf-8")
    result = measure.measure(
        artefact_path=str(artefact_path),
        oracle_path=str(oracle_path),
        inventory_path=str(ROOT / "demo/inventory.csv"),
        disabled_path=None,
    )
    assert result["recall"] == measure.VOID
    assert result["truth_size"] == measure.VOID
    assert result["missed"] == []


def test_measurement_always_publishes_missed(tmp_path):
    artefact = json.loads((ROOT / "bob_session/testscope_report.json").read_text(encoding="utf-8"))
    artefact["priority_order"] = [test_id for test_id in artefact["priority_order"] if test_id != "T-0342"]
    artefact_path = tmp_path / "artefact.json"
    artefact_path.write_text(json.dumps(artefact), encoding="utf-8")
    result = measure.measure(
        artefact_path=str(artefact_path),
        oracle_path=str(ROOT / "bob_session/evidence/oracle.json"),
        inventory_path=str(ROOT / "demo/inventory.csv"),
        disabled_path=None,
    )
    assert result["missed"] == ["T-0342"]
    assert result["recall"] < 1.0


def test_measurement_recall_cross_checks_the_engine(tmp_path):
    result = measure.measure(
        artefact_path=str(ROOT / "bob_session/testscope_report.json"),
        oracle_path=str(ROOT / "bob_session/evidence/oracle.json"),
        inventory_path=str(ROOT / "demo/inventory.csv"),
        disabled_path=str(ROOT / "submissions/ablation/disabled.json"),
    )
    assert result["recall"] == 1.0
    assert result["recall_cross_check"] == "agree"
    assert result["ablation"]["additional_true_positives"] == 1
    assert all(assertion["passed"] for assertion in result["ablation"]["assertions"])
    assert result["limits"]["recall_direction"] == "lower bound"


def test_measurement_states_the_direction_of_the_error():
    result = measure.measure(
        artefact_path=str(ROOT / "bob_session/testscope_report.json"),
        oracle_path=str(ROOT / "bob_session/evidence/oracle.json"),
        inventory_path=str(ROOT / "demo/inventory.csv"),
        disabled_path=None,
    )
    assert "over-selection is invisible" in result["limits"]["what_it_cannot_see"]
    assert result["limits"]["no_precision_claim"] is True
