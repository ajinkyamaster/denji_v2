#!/usr/bin/env bash
# TestScope acceptance check (Person A).
#
# Prints one line per gate, then a single tally line:  N/N PASS
#
#   V01..V16  v1's numbers, re-derived from source in THIS run. Nothing in this
#             block is taken on the committed artefact's word: a check that reads
#             the very thing it is checking is a tautology with a green light.
#   N01..N21  the new layer's gates (T1..T13, G1..G5, artefact invariants, the
#             MCP surface, the trust-boundary sweep), each mapped to NAMED tests
#             observed in one pytest run. A gate whose tests are missing from the
#             run reports FAIL, never "skipped": a check that has never been
#             observed to fail is not a check.
#
# Usage: ./verify.sh [extra pytest args...]
set -uo pipefail

cd "$(dirname "$0")" || exit 2
ROOT="$PWD"
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

STAMP="2026-09-27T04:12:00Z"
ORACLE="bob_session/testscope_oracle.json"
REPORT="bob_session/testscope_report.json"
DIFF="demo_repo/revisions/post_change.diff"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ---------------------------------------------------------------- block V ----
V_OUT="$("$PY" - "$STAMP" "$ORACLE" "$REPORT" "$DIFF" "$TMP" <<'PY'
import csv, hashlib, json, pathlib, re, subprocess, sys

STAMP, ORACLE, REPORT, DIFF, TMP = sys.argv[1:6]
TMP = pathlib.Path(TMP)
PY = sys.executable
rows = []

def gate(code, description, ok, detail=""):
    rows.append((code, description, bool(ok), str(detail)))

def sh(*args, cwd="."):
    return subprocess.run(list(args), cwd=cwd, capture_output=True, text=True, timeout=600)

def artefact(diff, out, *, oracle=None, extra=()):
    cmd = [PY, "bob_session/run_analysis.py", "--repo", "demo_repo", "--diff", diff,
           "--inventory", "inventory.csv", "--generated-at", STAMP,
           "--model-layer", "disabled", "--no-cache", "--out", str(out), *extra]
    if oracle:
        cmd += ["--oracle", oracle]
    done = sh(*cmd)
    if done.returncode != 0:
        raise SystemExit(f"run_analysis failed for {diff}\n{done.stdout[-2000:]}\n{done.stderr[-2000:]}")
    return json.loads(pathlib.Path(out).read_text())

def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def collect_count(cwd, marker):
    done = sh(PY, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", "-m", marker, cwd=cwd)
    for line in reversed((done.stdout or "").splitlines()):
        if "collected" in line:
            digits = "".join(ch if ch.isdigit() else " " for ch in line).split()
            if digits:
                return int(digits[0])
    return None

# V15 + V16 first: eight COLD runs (--no-cache) of the real invocation. The first
# is also the artefact every numeric gate below is read from, so the numbers and
# the determinism claim come from the same run.
digests = []
for index in range(8):
    out = TMP / f"det-{index}.json"
    artefact(DIFF, out, oracle=ORACLE)
    digests.append(sha(out))
main = json.loads((TMP / "det-0.json").read_text())
gate("V16", "eight cold runs of the engine produce ONE distinct sha256",
     len(set(digests)) == 1, f"{len(set(digests))} distinct digests")
gate("V15", "the committed artefact is byte-reproducible from source (I4)",
     sha(REPORT) == digests[0], f"committed {sha(REPORT)[:16]} vs fresh {digests[0][:16]}")

with open("inventory.csv", newline="", encoding="utf-8") as handle:
    inventory_rows = [row for row in csv.DictReader(handle) if any((value or "").strip() for value in row.values())]
summary, meta, measure = main["summary"], main["run_metadata"], main["measurement"]

gate("V01", "inventory.csv carries exactly 500 test rows", len(inventory_rows) == 500, len(inventory_rows))
gate("V02", "47 tests are selected for the run", summary["selected_for_run"] == 47, summary["selected_for_run"])
gate("V03", "41 are definitely affected (syntactic)", summary["definitely_affected_count"] == 41,
     summary["definitely_affected_count"])
gate("V04", "6 are semantically affected", summary["semantically_affected_count"] == 6,
     summary["semantically_affected_count"])
gate("V05", "reduction is 90.6%", summary["reduction_pct"] == 90.6, summary["reduction_pct"])

closure = meta["import_closure"]
gate("V06", "reverse import closure spans 11 modules", closure["modules"] == 11, closure["modules"])
gate("V07", "depth histogram is {0:1, 1:8, 2:1, 3:1}",
     closure["depth_histogram"] == {"0": 1, "1": 8, "2": 1, "3": 1}, closure["depth_histogram"])
gate("V08", "closure covers 41 inventory rows (18 direct + 23 transitive)",
     (closure["inventory_rows"], closure["direct_rows"], closure["transitive_rows"]) == (41, 18, 23),
     f"{closure['inventory_rows']} = {closure['direct_rows']} + {closure['transitive_rows']}")
gate("V09", "price of safety is 6", measure["price_of_safety"] == 6, measure["price_of_safety"])

hero = next((e for e in main["classification"]["semantically_affected"] if e["test_id"] == "T-0342"), None)
gate("V10", "hero T-0342 is selected by representation coupling, never by an import edge",
     hero is not None and hero["reason"] == "representation_coupling"
     and main["priority_order"][0] == "T-0342",
     hero["reason"] if hero else "T-0342 absent")

default_collect = collect_count("demo_repo", "not contract")
full_collect = collect_count("demo_repo", "")
gate("V11", "the marker defect is real: a default run collects 497, -m '' collects 500",
     default_collect == 497 and full_collect == 500, f"default {default_collect} / full {full_collect}")

docs = artefact("demo_repo/revisions/docs_only.diff", TMP / "docs.json")
gate("V12", "a docs-only change selects nothing (reachability control)",
     docs["summary"]["selected_for_run"] == 0, docs["summary"]["selected_for_run"])

control = artefact("demo_repo/revisions/post_change_behavioural_billing.diff", TMP / "control.json")
cs = control["summary"]
gate("V13", "the inertness control returns the 75 tests (47 -> 122, reduction 75.6%)",
     (cs["selected_for_run"], cs["definitely_affected_count"], cs["reduction_pct"]) == (122, 116, 75.6),
     f"selected {cs['selected_for_run']}, definite {cs['definitely_affected_count']}, reduction {cs['reduction_pct']}")

correction = next((c for c in meta["link_corrections"] if c["test_id"] == "T-0146"), None)
gate("V14", "the inventory's wrong link for T-0146 is corrected, and the correction is recorded",
     correction is not None and correction["declared_module"] == "app.utils.ids"
     and correction["derived_module"] == "app.utils.text",
     correction)

for code, description, ok, detail in rows:
    print(f"{'PASS' if ok else 'FAIL'}|{code}|{description}|{detail}")
print(f"SUMMARY|{sum(1 for r in rows if r[2])}|{len(rows)}")
PY
)"

# ------------------------------------- block S (the sabotage matrix) --------
# §9: "every gate T1..T13 and G1..G5 has been OBSERVED TO FAIL at least once,
# when deliberately broken. A check that has never failed is not a check."
#
# Each row breaks exactly ONE mechanism, runs that gate's own test and REQUIRES
# it to go red, then restores the file byte-for-byte. The three-state test of
# C26 is completed by block N below: every node used here also runs (and passes)
# in block N, which executes on the restored tree - probe present -> FAIL,
# probe removed -> PASS, and the restore is checked byte-for-byte in between.
# Nothing in this block echoes the injected text into any log (C26: never echo
# the literal), and the probes live only inside files the scanners read last.
S_OUT="$("$PY" - "$TMP" <<'PY'
import pathlib, subprocess, sys, xml.etree.ElementTree as ET

TMP = pathlib.Path(sys.argv[1])
PY = sys.executable

# (gate, what is broken, file, anchor, sabotage replacement, the gate's own node)
MUTATIONS = [
    ("S01", "T1  STALE fires on an orphan (break: orphan detection disabled)",
     "bob_session/pipeline/dispositions.py",
     "        if effective_module and index.module_named(effective_module) is None and verdict.derived_module is None:",
     "        if False and effective_module and index.module_named(effective_module) is None and verdict.derived_module is None:",
     "bob_session/tests/test_dispositions.py::test_T1_stale_fires_on_an_orphan_module"),
    ("S02", "T2  STALE stays silent on preserved behaviour (break: every change declared stale)",
     "bob_session/pipeline/dispositions.py",
     "            evidence = _stale_by_assertion(index, test_module, rho)",
     "            evidence = [(0, 'sabotage: stale without evidence', 0)]",
     "bob_session/tests/test_dispositions.py::test_T2_stale_does_not_fire_on_the_demo_change"),
    ("S03", "T3  UNCOVERED is non-empty for the added symbol (break: uncovered always empty)",
     "bob_session/pipeline/dispositions.py",
     "    in_scope = set()",
     "    return [], {'uncovered_symbols_excluded': 0, 'private_symbols_excluded': 0, 'changed_symbols_considered': 0}  # sabotage\n    in_scope = set()",
     "bob_session/tests/test_dispositions.py::test_T3_uncovered_is_non_empty_for_the_added_symbol_and_empty_for_docs_only"),
    ("S04", "T4  the oracle reports its own blindness (break: complete is always true)",
     "bob_session/oracle.py",
     "        complete = bool(collected_a == collected_b and inventory_total is not None and collected_a >= inventory_total)",
     "        complete = True  # sabotage: confidence regardless of population",
     "bob_session/tests/test_oracle.py::test_T4_default_marker_run_is_incomplete_and_the_full_run_is_complete"),
    ("S05", "T5  a fabricated citation is rejected (break: citation resolution always resolves)",
     "bob_session/verify.py",
     "    path = citation.get(\"path\") or \"\"",
     "    path = citation.get(\"path\") or \"\"\n    if True:\n        return True, None, None, {\"path\": path, \"symbol\": \"\", \"line\": None, \"defined_at\": None, \"text\": \"\"}",
     "bob_session/tests/test_kernel.py::test_T5_kernel_rejects_a_fabricated_citation"),
    ("S06", "T6  line drift still accepts (break: drift becomes a rejection)",
     "bob_session/verify.py",
     "        drift = bool(match is not None and line is not None and match.line != line)",
     "        drift = bool(match is not None and line is not None and match.line != line)\n        if drift:\n            return False, \"symbol_mismatch\", \"line drifted\", None",
     "bob_session/tests/test_kernel.py::test_T6_kernel_accepts_a_drifting_line_if_the_symbol_resolves"),
    ("S07", "T7  eight runs produce one digest (break: serialisation reads randomness)",
     "bob_session/pipeline/report.py",
     "    return json.dumps(artifact, indent=2, sort_keys=True, ensure_ascii=True) + \"\\n\"",
     "    import os\n    return json.dumps(artifact, indent=2, sort_keys=True, ensure_ascii=True) + os.urandom(4).hex() + \"\\n\"",
     "bob_session/tests/test_determinism.py::test_T7_eight_runs_produce_one_digest"),
    ("S08", "T8  monotonicity: disabled means ignored (break: claims ingested while disabled)",
     "bob_session/run_analysis.py",
     "        claims_in = []\n        claims_ignored = True",
     "        claims_ignored = True  # sabotage: claims ingested with the model layer disabled",
     "bob_session/tests/test_determinism.py::test_T8_model_layer_disabled_equals_the_baseline_exactly"),
    ("S09", "T9  the committed artefact is byte-reproducible (break: serialisation format)",
     "bob_session/pipeline/report.py",
     "    return json.dumps(artifact, indent=2, sort_keys=True, ensure_ascii=True) + \"\\n\"",
     "    return json.dumps(artifact, indent=4, sort_keys=True, ensure_ascii=True) + \"\\n\"",
     "bob_session/tests/test_determinism.py::test_T9_the_committed_artefact_is_reproducible_from_source"),
    ("S10", "T10 no dynamic exec/import in the pipeline (break: forbidden token injected)",
     "bob_session/pipeline/cache.py",
     "DECLARED_ASSUMPTIONS = [",
     "if False:  # sabotage probe for S10, never executed\n    eval(\"1\")\nDECLARED_ASSUMPTIONS = [",
     "bob_session/tests/test_security.py::test_T10_pipeline_never_executes_or_imports_the_analysed_code"),
    ("S11", "T11 a flipping test is excluded and counted (break: flakiness never recorded)",
     "bob_session/oracle.py",
     "                        flaky.add(node)",
     "                        pass  # sabotage: flakiness never recorded",
     "bob_session/tests/test_oracle.py::test_T11_a_test_that_flips_between_repeats_is_excluded_from_ground_truth"),
    ("S12", "T12 the inertness control fires (break: every change declared inert)",
     "bob_session/pipeline/diff_parser.py",
     "        if not self.confined:",
     "        if True:  # sabotage: every change is inert\n            self.inert = True\n            self.inert_reason = \"sabotage\"\n            return\n        if not self.confined:",
     "bob_session/tests/test_controls.py::test_T12_the_inertness_control_still_fires"),
    ("S13", "T13 the cache's assumptions are declared (break: assumption list emptied)",
     "bob_session/pipeline/cache.py",
     "DECLARED_ASSUMPTIONS = [",
     "DECLARED_ASSUMPTIONS = []  # sabotage\n_LEGACY_DECLARED_ASSUMPTIONS = [",
     "bob_session/tests/test_controls.py::test_T13_environment_fingerprint_and_cache_report_are_present_and_non_empty"),
    ("S14", "G1  an uncollectable file is refused (break: G1 always buildable)",
     "bob_session/gates.py",
     "        result[\"g1_buildable\"] = bool(buildable)",
     "        result[\"g1_buildable\"] = True  # sabotage",
     "bob_session/tests/test_gates.py::test_g1_fails_loudly_on_an_uncollectable_test_file"),
    ("S15", "G2  a flaky test is discarded (break: G2 always passes)",
     "bob_session/gates.py",
     "        result[\"g2_passes_5x\"] = all(runs) and bool(runs)",
     "        result[\"g2_passes_5x\"] = True  # sabotage",
     "bob_session/tests/test_gates.py::test_g2_rejects_a_test_that_passes_only_some_of_the_time"),
    ("S16", "G3  a collection error does not satisfy the patch test (break: G3 defaults to true)",
     "bob_session/gates.py",
     "        \"g3_assertion_fires_at_a\": False,",
     "        \"g3_assertion_fires_at_a\": True,  # sabotage",
     "bob_session/tests/test_gates.py::test_g3_rejects_a_failure_whose_origin_is_collection_or_import"),
    ("S17", "G4  a test that survives every perturbation is refused (break: strength without mutation)",
     "bob_session/gates.py",
     "                result[\"g4_mutation_strength\"] = _mutation_strength(\n                    repo, change_patch, test_patch, target, timeout, temporary\n                )",
     "                result[\"g4_mutation_strength\"] = 1.0  # sabotage: strength claimed without running any mutant",
     "bob_session/tests/test_gates.py::test_g4_refuses_a_test_that_survives_every_perturbation"),
    ("S18", "G5  no intent artefact means no invented anchor (break: G5 defaults to true)",
     "bob_session/gates.py",
     "        \"g5_spec_anchored\": None,",
     "        \"g5_spec_anchored\": True,  # sabotage",
     "bob_session/tests/test_gates.py::test_g5_is_null_without_an_intent_artefact"),
]

def node_state(node):
    """Run one gate node and return the observed state of that single test case."""
    xml = TMP / "sabotage.xml"
    if xml.exists():
        xml.unlink()
    done = subprocess.run(
        [PY, "-m", "pytest", "-p", "no:cacheprovider", "-q", node, f"--junitxml={xml}"],
        capture_output=True, text=True, timeout=600,
    )
    if not xml.exists():
        return "absent", f"pytest produced no report (rc={done.returncode})"
    states = []
    for case in ET.parse(xml).getroot().iter("testcase"):
        if case.find("failure") is not None:
            states.append("failed")
        elif case.find("error") is not None:
            states.append("error")
        elif case.find("skipped") is not None:
            states.append("skipped")
        else:
            states.append("passed")
    if len(states) != 1:
        return "absent", f"{len(states)} test cases recorded for one node"
    return states[0], ""

rows = []
for code, description, rel, anchor, replacement, node in MUTATIONS:
    path = pathlib.Path(rel)
    original = path.read_bytes()
    ok = False
    detail = ""
    try:
        text = original.decode("utf-8")
        occurrences = text.count(anchor)
        if occurrences != 1:
            detail = f"anchor occurs {occurrences}x in {rel} (must be exactly once)"
        else:
            mutated = text.replace(anchor, replacement, 1)
            try:
                compile(mutated, rel, "exec")
            except SyntaxError as error:
                detail = f"the mutation itself is not valid Python: {error}"
            else:
                path.write_text(mutated, encoding="utf-8")
                state, why = node_state(node)
                ok = state in ("failed", "error")
                detail = (f"gate observed RED while broken ({state}); restored byte-identical"
                          if ok else f"gate observed {state} while broken - a check that cannot fail is not a check"
                          + (f" ({why})" if why else ""))
    except Exception as error:  # noqa: BLE001 - a harness error must fail the gate, never hide it
        detail = f"sabotage harness error: {type(error).__name__}: {error}"
    finally:
        path.write_bytes(original)
    if path.read_bytes() != original:
        ok = False
        detail = "RESTORE FAILED: source left mutated"
    rows.append((code, description, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}|{code}|{description}|{detail}")

print(f"SUMMARY|{sum(1 for r in rows if r[2])}|{len(rows)}")
PY
)"

# -------------------------------------------------------- block N (pytest) ----
N_OUT="$("$PY" - "$TMP/junit.xml" "$@" <<'PY'
import pathlib, sys, xml.etree.ElementTree as ET

import subprocess

junit = pathlib.Path(sys.argv[1])
extra = sys.argv[2:]
# One run for every gate below: the gates read NAMED outcomes from this single
# observed execution, so they cannot drift apart from each other.
done = subprocess.run(
    [sys.executable, "-m", "pytest", "bob_session/tests", "-p", "no:cacheprovider",
     f"--junitxml={junit}", "-q", *extra]
)

cases = {}
if junit.exists():
    for case in ET.parse(junit).getroot().iter("testcase"):
        name = case.get("name", "")
        cls = case.get("classname", "")
        state = "passed"
        if case.find("failure") is not None:
            state = "failed"
        elif case.find("error") is not None:
            state = "error"
        elif case.find("skipped") is not None:
            state = "skipped"
        cases[(cls, name)] = state

# (code, description, [patterns], [excluded patterns]);  pattern = module::testname
GATES = [
    ("N01", "T1  STALE fires on an orphaned module", ["test_dispositions::test_T1_stale_fires_on_an_orphan_module"], []),
    ("N02", "T2  STALE does not fire on preserved behaviour (false-positive control)",
     ["test_dispositions::test_T2_stale_does_not_fire_on_the_demo_change"], []),
    ("N03", "T3  UNCOVERED is non-empty for the added symbol and empty for docs-only",
     ["test_dispositions::test_T3_uncovered_is_non_empty_for_the_added_symbol_and_empty_for_docs_only"], []),
    ("N04", "T4  the oracle reports its own blindness (default markers incomplete, -m '' complete)",
     ["test_oracle::test_T4_default_marker_run_is_incomplete_and_the_full_run_is_complete"], []),
    ("N05", "T5  the kernel rejects a fabricated citation",
     ["test_kernel::test_T5_kernel_rejects_a_fabricated_citation"], []),
    ("N06", "T6  the kernel accepts a drifting line when the symbol resolves",
     ["test_kernel::test_T6_kernel_accepts_a_drifting_line_if_the_symbol_resolves"], []),
    ("N07", "T7  eight runs produce one digest",
     ["test_determinism::test_T7_eight_runs_produce_one_digest"], []),
    ("N08", "T8  monotonicity: the model layer can only add, never remove",
     ["test_determinism::test_T8_model_layer_disabled_equals_the_baseline_exactly",
      "test_determinism::test_T8_unverifiable_claims_cannot_reduce_the_selection",
      "test_determinism::test_supplying_claims_with_the_model_layer_disabled_ignores_them"], []),
    ("N09", "T9  the committed artefact is byte-reproducible from source",
     ["test_determinism::test_T9_the_committed_artefact_is_reproducible_from_source"], []),
    ("N10", "T10 nothing in the pipeline imports or executes the analysed code",
     ["test_security::test_T10_pipeline_never_executes_or_imports_the_analysed_code",
      "test_security::test_T10_holds_for_the_whole_server_side_surface"], []),
    ("N11", "T11 a flipping test is excluded from ground truth and counted",
     ["test_oracle::test_T11_a_test_that_flips_between_repeats_is_excluded_from_ground_truth",
      "test_oracle::test_T11_the_exclusion_is_empty_when_flakiness_was_never_looked_for",
      "test_oracle::test_oracle_excludes_nothing_it_should_not",
      "test_dispositions::test_triage_refinement_does_not_write_off_the_hero_case"], []),
    ("N12", "T12 the inertness control fires (47 -> 122) and only the billing hunk differs",
     ["test_controls::test_T12_the_inertness_control_still_fires",
      "test_controls::test_T12_the_two_runs_differ_only_in_the_billing_hunk",
      "test_controls::test_docs_only_reachability_control_selects_nothing"], []),
    ("N13", "T13 the cache's assumptions are declared and visible",
     ["test_controls::test_T13_environment_fingerprint_and_cache_report_are_present_and_non_empty",
      "test_controls::test_T13_the_cache_records_its_state_and_what_invalidated_it",
      "test_controls::test_the_cache_is_atomic_and_leaves_no_temp_files"], []),
    ("N14", "G1  observed to fail: an uncollectable test file is refused",
     ["test_gates::test_g1_fails_loudly_on_an_uncollectable_test_file"], []),
    ("N15", "G2  observed to fail: a test that passes only sometimes is discarded",
     ["test_gates::test_g2_rejects_a_test_that_passes_only_some_of_the_time"], []),
    ("N16", "G3  observed to fail: a collection error does not satisfy the patch test",
     ["test_gates::test_g3_rejects_a_failure_whose_origin_is_collection_or_import"], []),
    ("N17", "G4  observed to fail: a test that survives every perturbation is refused",
     ["test_gates::test_g4_refuses_a_test_that_survives_every_perturbation"], []),
    ("N18", "G5  observed to fail: no intent artefact means no invented anchor (null)",
     ["test_gates::test_g5_is_null_without_an_intent_artefact",
      "test_gates::test_g5_anchors_when_the_assertion_encodes_the_specification"], []),
    ("N19", "artefact invariants I13..I17 hold and are sabotaged to prove they fire",
     ["test_report_invariants::*"], []),
    ("N20", "the MCP surface: four tools, protocol-clean stdio, approval split",
     ["test_mcp::*", "test_security::test_always_allow_covers_exactly_the_three_pure_tools"], []),
    ("N21", "the trust-boundary sweep: traversal, symlinks, secrets, sandbox, hostile diff",
     ["test_security::*"], ["test_security::test_always_allow_covers_exactly_the_three_pure_tools"]),
]

def matches(entry_cls, entry_name, pattern):
    module, _, want = pattern.partition("::")
    if not entry_cls.endswith("." + module):
        return False
    if want == "*":
        return True
    return entry_name == want or entry_name.startswith(want + "[")

rows = []
for code, description, patterns, excluded in GATES:
    matched = [(cls, name) for (cls, name) in cases
               if any(matches(cls, name, p) for p in patterns)
               and not any(matches(cls, name, x) for x in excluded)]
    bad = [f"{name}:{state}" for (cls, name), state in sorted(cases.items())
           if (cls, name) in matched and state != "passed"]
    ok = bool(matched) and not bad
    detail = f"{len(matched)} observed" if ok else (f"MISSING TEST for gate" if not matched else "; ".join(bad[:3]))
    rows.append((code, description, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}|{code}|{description}|{detail}")

failed_tests = sorted((cls, name) for (cls, name), state in cases.items() if state != "passed")
print(f"PYTEST|{len(cases) - len(failed_tests)}|{len(cases)}")
print(f"SUMMARY|{sum(1 for r in rows if r[2])}|{len(rows)}")
if done.returncode not in (0, 1):
    print(f"PYTEST_RC|{done.returncode}")
PY
)"

# ------------------------------------------------------------------ report ----
print_block() {
  while IFS='|' read -r verdict code description detail; do
    case "$verdict" in
      PASS) printf 'PASS  %-4s %s\n' "$code" "$description" ;;
      FAIL) printf 'FAIL  %-4s %s  [%s]\n' "$code" "$description" "$detail" ;;
    esac
  done <<< "$1"
}

print_block "$V_OUT"
print_block "$S_OUT"
print_block "$N_OUT"

V_PASS=$(grep '^SUMMARY|' <<< "$V_OUT" | tail -1 | cut -d'|' -f2)
V_TOTAL=$(grep '^SUMMARY|' <<< "$V_OUT" | tail -1 | cut -d'|' -f3)
S_PASS=$(grep '^SUMMARY|' <<< "$S_OUT" | tail -1 | cut -d'|' -f2)
S_TOTAL=$(grep '^SUMMARY|' <<< "$S_OUT" | tail -1 | cut -d'|' -f3)
N_PASS=$(grep '^SUMMARY|' <<< "$N_OUT" | tail -1 | cut -d'|' -f2)
N_TOTAL=$(grep '^SUMMARY|' <<< "$N_OUT" | tail -1 | cut -d'|' -f3)

PY_PASS=$(grep '^PYTEST|' <<< "$N_OUT" | tail -1 | cut -d'|' -f2)
PY_TOTAL=$(grep '^PYTEST|' <<< "$N_OUT" | tail -1 | cut -d'|' -f3)

TOTAL_PASS=$(( ${V_PASS:-0} + ${S_PASS:-0} + ${N_PASS:-0} ))
TOTAL=$(( ${V_TOTAL:-0} + ${S_TOTAL:-0} + ${N_TOTAL:-0} ))

if [ -n "${PY_TOTAL:-}" ]; then
  echo "pytest: ${PY_PASS}/${PY_TOTAL} tests passed"
fi

if [ "$TOTAL_PASS" -eq "$TOTAL" ] && [ "$TOTAL" -gt 0 ]; then
  echo "$TOTAL_PASS/$TOTAL PASS  (v1 ${V_PASS}/${V_TOTAL} + sabotage ${S_PASS}/${S_TOTAL} + new ${N_PASS}/${N_TOTAL})"
  exit 0
fi

echo "$TOTAL_PASS/$TOTAL PASS  (v1 ${V_PASS:-0}/${V_TOTAL:-0} + sabotage ${S_PASS:-0}/${S_TOTAL:-0} + new ${N_PASS:-0}/${N_TOTAL:-0})  -- FAILURES ABOVE"
exit 1
