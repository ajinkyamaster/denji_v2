#!/usr/bin/env bash
# Build the Author's test patch for the uncovered symbol _should_drop.
#
# The patch appends one test to the existing test file. It is a real unified
# diff produced by diff -u, so the gate applies exactly what a developer
# would review, and the patch is regenerated from the live test file rather
# than being hand-maintained.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
src="$here/demo/tests/test_cache_service.py"
out="$here/bob_session/roles/patches/author_should_drop.patch"
mkdir -p "$(dirname "$out")"

tmp="$(mktemp -d)"
cp "$src" "$tmp/before.py"
cp "$src" "$tmp/after.py"
cat >> "$tmp/after.py" <<'PY'


def test_evict_expired_drops_status_expired():
    '''Pin the behaviour the diff added: an entry marked expired is dropped.'''
    service = cache_service.CacheService()
    service.write_cache_entry('a', {'id': 1, 'status': 'expired', 'amount': 0, 'expires_at': 10 ** 13})
    assert service.evict_expired(10 ** 12) == 1
    assert service.entry_count() == 0
PY

diff -u --label a/tests/test_cache_service.py --label b/tests/test_cache_service.py \
    "$tmp/before.py" "$tmp/after.py" > "$out" || true
rm -rf "$tmp"
echo "wrote $out"
tail -9 "$out"
