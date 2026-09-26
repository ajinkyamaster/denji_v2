#!/usr/bin/env bash
# One command: regenerate every artefact and run every gate.
#
#   PYTHON=/path/to/python ./verify.sh
#
# Order matters and mirrors the workflow: the oracle produces the ground
# truth, the engine produces the baseline then the ledger, the gate adjudicates
# the authored test, the harness measures, the scorecard falsifies every gate.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${PYTHON:-python3}"
cd "$here"

echo "== preflight =="
$PYTHON - <<'PY'
import importlib.util, sys
missing = [name for name in ("pytest", "coverage", "jsonschema") if importlib.util.find_spec(name) is None]
if missing:
    print(f"missing dependencies: {', '.join(missing)}")
    print(f"install them with: {sys.executable} -m pip install -r requirements.txt")
    raise SystemExit(2)
print("dependencies present")
PY

echo "== 1/8 revisions =="
bash tools/make_revisions.sh > /dev/null
$PYTHON -c "import json; print('  revisions:', json.load(open('bob_session/evidence/revisions.json')))"

echo "== 2/8 oracle (executed ground truth) =="
$PYTHON -m bob_session.oracle | sed 's/^/  /'

echo "== 3/8 proposal cache (recorded role outputs) =="
$PYTHON -m bob_session.roles.record_proposals | sed 's/^/  /'

echo "== 4/8 ledger, model layer disabled (the baseline) =="
$PYTHON -m bob_session.pipeline.run_analysis --model-layer disabled --out submissions/ablation/disabled.json --quiet
echo "  wrote submissions/ablation/disabled.json"

echo "== 5/8 ledger, model layer enabled (the committed artefact) =="
$PYTHON -m bob_session.pipeline.run_analysis --model-layer enabled \
    --out bob_session/testscope_report.json --ablation-baseline submissions/ablation/disabled.json | sed 's/^/  /'

echo "== 6/8 gate G1..G5 on the authored test =="
$PYTHON -m bob_session.gate | sed 's/^/  /'

echo "== 7/8 measurement =="
$PYTHON bob_session/measure.py | sed 's/^/  /'

echo "== 8/8 scorecard (each gate falsified) =="
$PYTHON bob_session/reliability_check.py | sed 's/^/  /'

echo "== engine suite =="
$PYTHON -m pytest tests -q | tail -2 | sed 's/^/  /'

echo "== verification record =="
$PYTHON tools/write_verification.py | sed 's/^/  /'

echo "== done =="
