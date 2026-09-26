#!/usr/bin/env bash
# Build the demo repository history and the diff fixtures.
#
#   rev-a  base revision
#   rev-b  the change under analysis (revision B, the checked-out tree)
#   rev-c  the change with the consumer fixed        (necessity control)
#   rev-d  the inert edit made behavioural           (sensitivity control)
#
# Also writes:
#   diffs/change_b.patch        rev-a -> rev-b
#   diffs/consumer_fixed.patch  rev-a -> rev-c
#   diffs/sensitivity.patch     rev-a -> rev-d
#   diffs/docs_only.patch       rev-a -> rev-b, README only
#   bob_session/evidence/revisions.json
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
demo="$here/demo"
cd "$demo"

rm -rf .git
git init -q
git config user.email "testscope@example.invalid"
git config user.name "TestScope Fixture"
git add -A
git commit -q -m "revision B: the change under analysis"
git branch -f rev-b HEAD

# --- revision A: the base revision -----------------------------------------
git checkout -q -b rev-a HEAD
cp "$here/tools/rev_a/app/services/cache_service.py" app/services/cache_service.py
cp "$here/tools/rev_a/app/services/billing_service.py" app/services/billing_service.py
cp "$here/tools/rev_a/README.md" README.md
git add -A
git commit -q -m "revision A: base revision"

# --- revision C: the change, with the consumer fixed ------------------------
git checkout -q -b rev-c rev-a
git checkout -q rev-b -- app/services/cache_service.py
cp "$here/tools/rev_c/app/workers/report_worker.py" app/workers/report_worker.py
git add -A
git commit -q -m "revision C: the change with the consumer fixed"

# --- revision D: the inert edit made behavioural ---------------------------
git checkout -q -b rev-d rev-a
git checkout -q rev-b -- app/services/cache_service.py
cp "$here/tools/rev_d/app/services/billing_service.py" app/services/billing_service.py
git add -A
git commit -q -m "revision D: the inert edit made behavioural"

git checkout -q rev-b

# --- diff fixtures ----------------------------------------------------------
mkdir -p "$here/diffs"
git diff rev-a rev-b > "$here/diffs/change_b.patch"
git diff rev-a rev-c > "$here/diffs/consumer_fixed.patch"
git diff rev-a rev-d > "$here/diffs/sensitivity.patch"
git diff rev-a rev-b -- README.md > "$here/diffs/docs_only.patch"

# --- revision evidence ------------------------------------------------------
mkdir -p "$here/bob_session/evidence"
cat > "$here/bob_session/evidence/revisions.json" <<EOF
{
  "rev_a": "$(git rev-parse rev-a)",
  "rev_b": "$(git rev-parse rev-b)",
  "rev_c": "$(git rev-parse rev-c)",
  "rev_d": "$(git rev-parse rev-d)"
}
EOF

echo "revisions built:"
git log --oneline --all --decorate | sed 's/^/  /'
wc -l "$here"/diffs/*.patch | sed 's/^/  /'
