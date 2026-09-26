#!/usr/bin/env python3
"""Generate the demo test suite and the 500-row inventory.

Deterministic by construction: the same tree is produced on every run, so
the inventory, the suite and the inventory-to-node mapping can be rebuilt
and diffed by anyone.  Run with:

    python3 tools/gen_demo_suite.py

Layout produced:

    demo/app/<filler modules>.py     generated fixture modules
    demo/tests/test_<module>.py      generated tests (templated + real)
    demo/inventory.csv               500 rows, one per inventory entry

Two deliberate defects are planted in the inventory (both are documented
oracle cases in ARCHITECTURE_V2.md section 13.1):

  * T-0342 is declared against ``app.workers.legacy_adapter`` although the
    test lives in ``tests/test_report_worker.py`` and exercises
    ``app.workers.report_worker``: a mis-declared link.
  * T-0499 names a node that does not exist (a renamed-away test); the real
    node it used to name is therefore unmapped.
"""
from __future__ import annotations

import hashlib
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo"
APP = DEMO / "app"
TESTS = DEMO / "tests"

PREAMBLE = '"""Generated demo tests. Do not edit: run tools/gen_demo_suite.py."""\n'

# ---------------------------------------------------------------------------
# Module layout.  The order defines inventory ids: the report_worker block
# must start at T-0342 (index 341).
# ---------------------------------------------------------------------------
# (dotted module, count, kind)
MODULES = [
    ("app.config", 2, "real"),
    ("app.logging_setup", 2, "real"),
    ("app.models", 2, "real"),
    ("app.storage.backends", 2, "real"),
    ("app.telemetry", 1, "real"),
    ("app.utils.hashing", 8, "real"),
    ("app.utils.encoding", 15, "real"),
    ("app.utils.text", 1, "real"),
    ("app.utils.timeutil", 1, "real"),
    ("app.services.cache_service", 6, "real"),
    ("app.validators", 1, "real"),
    ("app.services.billing_service", 20, "real"),
    ("app.services.order_service", 70, "templated"),
    ("app.workers.legacy_adapter", 14, "templated"),
    ("app.services.user_service", 25, "templated"),
    ("app.services.pricing_service", 25, "templated"),
    ("app.services.notification_service", 20, "templated"),
    ("app.services.inventory_service", 20, "templated"),
    ("app.workers.batch_worker", 22, "templated"),
    ("app.workers.sync_worker", 22, "templated"),
    ("app.workers.ingest_worker", 20, "templated"),
    ("app.utils.formatting", 22, "templated"),
    ("app.utils.metrics", 19, "templated"),
    ("app.workers.report_worker", 6, "real"),
    ("app.utils.paginate", 20, "templated"),
    ("app.api.handlers", 18, "templated"),
    ("app.api.routes", 12, "templated"),
    ("app.clients.http_client", 10, "templated"),
    ("app.clients.db_client", 10, "templated"),
    ("app.services.audit_service", 8, "templated"),
    ("app.workers.cleanup_worker", 8, "templated"),
    ("app.utils.cron", 10, "templated"),
    ("app.utils.redaction", 6, "templated"),
    ("app.api.serializers", 10, "templated"),
    ("app.services.currency_service", 10, "templated"),
    ("app.services.tax_service", 10, "templated"),
    ("app.services.receipt_service", 10, "templated"),
    ("app.workers.digest_worker", 11, "templated"),
]

# One extra test node that carries no inventory row (documented: unmapped).
EXTRA_NODES = [("tests/test_metrics_dashboard.py", "test_histogram_buckets_match_expected", "app.utils.metrics")]

# The hero row: declared module differs from the module the test exercises.
DECLARATION_OVERRIDES = {
    "tests/test_report_worker.py::test_cache_roundtrip_contract": "app.workers.legacy_adapter",
}

# Rows appended right after a module's own rows (keeps id alignment stable).
EXTRA_ROWS_AFTER = {
    "app.utils.metrics": [
        {
            "test_name": "test_ops_smoke_parses_cache_dump",
            "module": "app.utils.metrics",
            "node_id": "tests/test_ops_smoke.py::test_ops_smoke_parses_cache_dump",
            "description": "parses a raw cache dump line during the ops smoke check",
        }
    ]
}

# The inventory row that names a node which does not exist.
MISSING_ROW = {
    "test_name": "test_receipt_number_is_unique",
    "node_id": "tests/test_receipt_service.py::test_receipt_number_is_unique",
    "module": "app.services.receipt_service",
}


def module_path(dotted: str) -> pathlib.Path:
    return APP / (dotted[len("app."):].replace(".", "/") + ".py")


def test_path(dotted: str) -> pathlib.Path:
    return TESTS / ("test_" + dotted.rsplit(".", 1)[-1] + ".py")


def slug_of(dotted: str) -> str:
    return dotted.rsplit(".", 1)[-1]


def avg_runtime(test_id: str) -> int:
    """Deterministic pseudo-runtime in milliseconds."""
    digest = hashlib.sha256(test_id.encode()).hexdigest()
    return 2 + int(digest[:2], 16) % 39


# ---------------------------------------------------------------------------
# Real tests: hand-written against the hand-written modules.
# ---------------------------------------------------------------------------
REAL_TESTS: dict[str, list[tuple[str, str]]] = {
    "app.config": [
        ("test_default_cache_path_is_relative", ["assert config.cache_path().endswith('entries.dat')"]),
        ("test_service_name_uses_the_app_name", ["assert config.service_name() == 'demo-service-cache'"]),
    ],
    "app.logging_setup": [
        ("test_get_logger_returns_a_logger", ["assert logging_setup.get_logger('demo').name == 'demo'"]),
        ("test_log_level_name_is_canonical", ["assert logging_setup.log_level_name(20) == 'INFO'"]),
    ],
    "app.models": [
        (
            "test_report_add_folds_entries",
            [
                "report = models.Report()",
                "report.add(models.CacheEntry(id=1, status='ok', amount=5))",
                "report.add(models.CacheEntry(id=2, status='ok', amount=7))",
                "assert (report.entries, report.total_amount) == (2, 12)",
            ],
        ),
        (
            "test_entry_expiry_flag",
            [
                "entry = models.CacheEntry(id=1, expires_at=100)",
                "assert entry.is_expired(101) is True",
                "assert entry.is_expired(99) is False",
            ],
        ),
    ],
    "app.storage.backends": [
        (
            "test_set_get_roundtrip",
            ["backend = backends.MemoryBackend()", "backend.set('k', 'v')", "assert backend.get('k') == 'v'"],
        ),
        (
            "test_delete_reports_removal",
            [
                "backend = backends.MemoryBackend()",
                "backend.set('k', 'v')",
                "assert backend.delete('k') is True",
                "assert backend.get('k') is None",
            ],
        ),
    ],
    "app.telemetry": [
        (
            "test_record_increments_counters",
            [
                "telemetry.reset()",
                "telemetry.record('x', 2)",
                "telemetry.record('x')",
                "assert telemetry.snapshot() == {'x': 3}",
            ],
        )
    ],
    "app.utils.hashing": [
        (
            "test_sha256_matches_known_digest",
            [
                "assert hashing.sha256_hex(b'abc') == "
                "'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'"
            ],
        ),
        ("test_hash_text_encodes_utf8", ["assert hashing.hash_text('abc') == hashing.sha256_hex(b'abc')"]),
        ("test_short_hash_length", ["assert len(hashing.short_hash(b'payload', 8)) == 8"]),
        ("test_short_hash_default_length", ["assert len(hashing.short_hash(b'payload')) == 12"]),
        (
            "test_short_hash_rejects_zero_length",
            ["with pytest.raises(ValueError):", "    hashing.short_hash(b'payload', 0)"],
        ),
        (
            "test_short_hash_is_prefix_of_sha256",
            ["assert hashing.sha256_hex(b'payload').startswith(hashing.short_hash(b'payload', 16))"],
        ),
        (
            "test_sha256_is_stable_across_calls",
            ["assert hashing.sha256_hex(b'payload') == hashing.sha256_hex(b'payload')"],
        ),
        (
            "test_short_hash_rejects_negative_length",
            ["with pytest.raises(ValueError):", "    hashing.short_hash(b'payload', -1)"],
        ),
    ],
    "app.utils.encoding": [
        ("test_encode_decode_roundtrip", ["assert encoding.decode_blob(encoding.encode_blob(b'payload')) == b'payload'"]),
        (
            "test_encoded_form_has_hash_prefix",
            ["assert encoding.encode_blob(b'payload').split(':', 1)[0] == hashing.sha256_hex(b'payload')"],
        ),
        (
            "test_corrupt_blob_is_rejected",
            ["with pytest.raises(ValueError):", "    encoding.decode_blob('00' * 32 + ':QUFBQQ==')"],
        ),
        ("test_unchecked_decode_skips_hash_check", ["assert encoding.decode_blob_unchecked('00:QUFBQQ==') == b'AAAA'"]),
        ("test_empty_payload_roundtrip", ["assert encoding.decode_blob(encoding.encode_blob(b'')) == b''"]),
        ("test_encode_is_deterministic", ["assert encoding.encode_blob(b'x') == encoding.encode_blob(b'x')"]),
        ("test_encoded_is_ascii", ["assert encoding.encode_blob(b'\\xff\\xfe').isascii() is True"]),
        ("test_prefix_is_64_hex_chars", ["assert len(encoding.encode_blob(b'x').split(':', 1)[0]) == 64"]),
        (
            "test_binary_payload_roundtrip",
            ["assert encoding.decode_blob(encoding.encode_blob(bytes(range(256)))) == bytes(range(256))"],
        ),
        (
            "test_encoded_length_grows_with_payload",
            ["assert len(encoding.encode_blob(b'a' * 12)) > len(encoding.encode_blob(b'a'))"],
        ),
        ("test_manually_built_blob_decodes", ["assert encoding.decode_blob(encoding.encode_blob(b'z')) == b'z'"]),
        ("test_unchecked_decode_of_empty_text", ["assert encoding.decode_blob_unchecked(':') == b''"]),
        ("test_two_payloads_have_distinct_encodings", ["assert encoding.encode_blob(b'a') != encoding.encode_blob(b'b')"]),
        (
            "test_partition_ignores_extra_colons",
            ["assert encoding.decode_blob_unchecked('deadbeef:QUFBQQ==:tail') == b'AAAA'"],
        ),
        ("test_encode_returns_text", ["assert isinstance(encoding.encode_blob(b'payload'), str)"]),
    ],
    "app.utils.text": [
        ("test_slugify_collapses_separators", ["assert text.slugify('Hello  World!') == 'hello-world'"]),
    ],
    "app.utils.timeutil": [
        (
            "test_expiry_semantics",
            [
                "assert timeutil.is_expired(0, 10 ** 12) is False",
                "assert timeutil.is_expired(5, 5) is True",
                "assert timeutil.is_expired(5, 4) is False",
            ],
        )
    ],
    "app.services.cache_service": [
        (
            "test_write_returns_serialised_text",
            [
                "service = cache_service.CacheService()",
                "entry = service.write_cache_entry('a', {'id': 1, 'status': 'ok', 'amount': 5})",
                "assert isinstance(entry, str) and entry",
            ],
        ),
        (
            "test_read_returns_the_written_mapping",
            [
                "service = cache_service.CacheService()",
                "service.write_cache_entry('a', {'id': 1, 'status': 'ok', 'amount': 5})",
                "assert service.read_cache_entry('a') == {'id': 1, 'status': 'ok', 'amount': 5}",
            ],
        ),
        (
            "test_read_missing_key_returns_none",
            ["assert cache_service.CacheService().read_cache_entry('missing') is None"],
        ),
        (
            "test_evict_expired_removes_overdue_entries",
            [
                "service = cache_service.CacheService()",
                "service.write_cache_entry('a', {'id': 1, 'status': 'ok', 'amount': 0, 'expires_at': 1})",
                "assert service.evict_expired(10 ** 12) == 1",
                "assert service.entry_count() == 0",
            ],
        ),
        (
            "test_evict_expired_keeps_live_entries",
            [
                "service = cache_service.CacheService()",
                "service.write_cache_entry('a', {'id': 1, 'status': 'ok', 'amount': 0, 'expires_at': 10 ** 13})",
                "assert service.evict_expired(10 ** 12) == 0",
                "assert service.entry_count() == 1",
            ],
        ),
        (
            "test_storage_path_is_configurable",
            ["assert cache_service.CacheService().storage_path().endswith('entries.dat')"],
        ),
    ],
    "app.validators": [
        (
            "test_require_and_identifier",
            [
                "validators.require(True, 'ok')",
                "assert validators.is_identifier('cache_key-1') is True",
                "with pytest.raises(validators.ValidationError):",
                "    validators.require(False, 'boom')",
            ],
        )
    ],
    "app.services.billing_service": [
        (
            "test_settle_returns_receipt_fields",
            ["receipt = billing_service.settle(10)", "assert receipt == {'amount': 10, 'currency': 'EUR', 'settled': True}"],
        ),
        ("test_settle_defaults_to_eur", ["assert billing_service.settle(1)['currency'] == 'EUR'"]),
        ("test_settle_accepts_usd", ["assert billing_service.settle(1, 'USD')['currency'] == 'USD'"]),
        ("test_settle_accepts_inr", ["assert billing_service.settle(1, 'INR')['currency'] == 'INR'"]),
        (
            "test_settle_rejects_negative_amount",
            ["with pytest.raises(ValidationError):", "    billing_service.settle(-1)"],
        ),
        (
            "test_settle_rejects_unknown_currency",
            ["with pytest.raises(ValidationError):", "    billing_service.settle(1, 'XXX')"],
        ),
        ("test_settle_allows_zero", ["assert billing_service.settle(0)['settled'] is True"]),
        ("test_settle_is_deterministic", ["assert billing_service.settle(7) == billing_service.settle(7)"]),
        (
            "test_settle_records_a_counter",
            ["telemetry.reset()", "billing_service.settle(1)", "assert telemetry.snapshot()['billing.settle'] == 1"],
        ),
        ("test_currencies_are_declared", ["assert billing_service.CURRENCIES == ('EUR', 'USD', 'INR')"]),
        (
            "test_refund_returns_flag",
            [
                "receipt = billing_service.settle(10)",
                "assert billing_service.refund(receipt) == {'amount': 10, 'currency': 'EUR', 'refunded': True}",
            ],
        ),
        (
            "test_refund_keeps_amount_and_currency",
            [
                "refund = billing_service.refund({'amount': 5, 'currency': 'USD', 'settled': True})",
                "assert (refund['amount'], refund['currency']) == (5, 'USD')",
            ],
        ),
        (
            "test_refund_rejects_unsettled_receipt",
            ["with pytest.raises(ValidationError):", "    billing_service.refund({'amount': 1, 'settled': False})"],
        ),
        (
            "test_refund_rejects_non_mapping",
            ["with pytest.raises(ValidationError):", "    billing_service.refund('receipt')"],
        ),
        (
            "test_refund_does_not_mutate_receipt",
            [
                "receipt = {'amount': 3, 'currency': 'EUR', 'settled': True}",
                "billing_service.refund(receipt)",
                "assert receipt == {'amount': 3, 'currency': 'EUR', 'settled': True}",
            ],
        ),
        (
            "test_refund_records_a_counter",
            [
                "telemetry.reset()",
                "billing_service.refund({'amount': 1, 'currency': 'EUR', 'settled': True})",
                "assert telemetry.snapshot()['billing.refund'] == 1",
            ],
        ),
        ("test_net_amount_subtracts_fee", ["assert billing_service.net_amount({'amount': 10}, 3) == 7"]),
        ("test_net_amount_default_fee_is_zero", ["assert billing_service.net_amount({'amount': 10}) == 10"]),
        (
            "test_net_amount_can_go_negative",
            ["assert billing_service.net_amount({'amount': 5}, 8) == -3"],
        ),
        (
            "test_net_amount_requires_mapping",
            ["with pytest.raises(ValidationError):", "    billing_service.net_amount(5)"],
        ),
    ],
    "app.workers.report_worker": [
        (
            "test_cache_roundtrip_contract",
            [
                "@pytest.mark.contract",
                "def test_cache_roundtrip_contract():",
                "    service = cache_service.CacheService()",
                "    raw = service.write_cache_entry('k1', {'id': 1, 'status': 'ok', 'amount': 5})",
                "    assert report_worker.parse_recent_cache_entries(raw) == {'id': 1, 'status': 'ok', 'amount': 5}",
            ],
        ),
        (
            "test_summary_counts_contract",
            [
                "@pytest.mark.contract",
                "def test_summary_counts_contract():",
                "    service = cache_service.CacheService()",
                "    lines = [service.write_cache_entry(f'k{i}', {'id': i, 'status': 'ok', 'amount': i}) for i in (1, 2)]",
                "    report = report_worker.build_report(lines)",
                "    assert report.entries == 2 and report.total_amount == 3",
            ],
        ),
        (
            "test_amount_totals_contract",
            [
                "@pytest.mark.contract",
                "def test_amount_totals_contract():",
                "    service = cache_service.CacheService()",
                "    lines = [",
                "        service.write_cache_entry('k1', {'id': 1, 'status': 'new', 'amount': 10}),",
                "        service.write_cache_entry('k2', {'id': 2, 'status': 'new', 'amount': 32}),",
                "    ]",
                "    assert report_worker.build_report(lines).total_amount == 42",
            ],
        ),
        (
            "test_parses_legacy_pipe_payload",
            ["assert report_worker.parse_recent_cache_entries('1|ok|5') == {'id': 1, 'status': 'ok', 'amount': 5}"],
        ),
        ("test_skips_blank_lines", ["assert report_worker.parse_recent_cache_entries('   ') is None"]),
        (
            "test_legacy_field_order",
            [
                "parsed = report_worker.parse_recent_cache_entries('7|done|42')",
                "assert parsed['amount'] == 42 and parsed['status'] == 'done'",
            ],
        ),
    ],
}

# Imports each real test module needs.
REAL_IMPORTS: dict[str, str] = {
    "app.config": "import pytest\n\nfrom app import config",
    "app.logging_setup": "import pytest\n\nfrom app import logging_setup",
    "app.models": "import pytest\n\nfrom app import models",
    "app.storage.backends": "import pytest\n\nfrom app.storage import backends",
    "app.telemetry": "import pytest\n\nfrom app import telemetry",
    "app.utils.hashing": "import pytest\n\nfrom app.utils import hashing",
    "app.utils.encoding": "import pytest\n\nfrom app.utils import encoding, hashing",
    "app.utils.text": "import pytest\n\nfrom app.utils import text",
    "app.utils.timeutil": "import pytest\n\nfrom app.utils import timeutil",
    "app.services.cache_service": "import pytest\n\nfrom app.services import cache_service",
    "app.validators": "import pytest\n\nfrom app import validators",
    "app.services.billing_service": (
        "import pytest\n\nfrom app import telemetry\nfrom app.services import billing_service\n"
        "from app.validators import ValidationError"
    ),
    "app.workers.report_worker": (
        "import pytest\n\nfrom app.services import cache_service\nfrom app.workers import report_worker"
    ),
}

EXTRA_TEST_FILES = {
    "tests/test_ops_smoke.py": """\"\"\"Ops smoke check: parses a raw cache dump line.\"\"\"

from app.workers import report_worker


def test_ops_smoke_parses_cache_dump():
    raw = "3|ok|17"
    assert report_worker.parse_recent_cache_entries(raw) == {"id": 3, "status": "ok", "amount": 17}
""",
    "tests/test_metrics_dashboard.py": """\"\"\"Pre-existing failures kept out of the default run.\"\"\"
import pytest

from app.utils import metrics


@pytest.mark.known_broken
def test_histogram_buckets_match_expected():
    assert metrics.histogram([1, 2, 3, 4]) == {"low": 2, "high": 3}
""",
}

TEMPLATES = [
    ("describes_item", 'assert m.describe({i}) == "{slug}:{i}"'),
    ("describe_is_text", "assert isinstance(m.describe({i}), str)"),
    ("describe_is_prefixed", 'assert m.describe({i}).startswith("{slug}:")'),
    ("describe_is_distinct", "assert m.describe({i}) != m.describe({i} + 1)"),
    ("describe_has_length", 'assert len(m.describe({i})) > len("{slug}")'),
    ("counts_items", "assert m.count() == {count}"),
    ("count_is_integer", "assert isinstance(m.count(), int)"),
    ("revision_is_marked", 'assert m.revision() == "{slug}-v1"'),
]

TEMPLATED_MODULE_SOURCE = '''"""{dotted} fixture module for the demo inventory."""
SLUG = "{slug}"
REVISION = "{slug}-v1"
ITEMS = {count}


def describe(index: int) -> str:
    """Return the dashboard label of one {slug} item."""
    return f"{{SLUG}}:{{index}}"


def count() -> int:
    """Return the number of items this module knows about."""
    return ITEMS


def revision() -> str:
    """Return the module revision marker."""
    return REVISION
'''

METRICS_HISTOGRAM = '''

def histogram(values):
    """Return the low/high split of a list of numbers."""
    low = len([value for value in values if value < 3])
    return {"low": low, "high": len(values) - low}
'''


def write_templated_module(dotted: str, count: int) -> None:
    path = module_path(dotted)
    path.parent.mkdir(parents=True, exist_ok=True)
    source = TEMPLATED_MODULE_SOURCE.format(dotted=dotted, slug=slug_of(dotted), count=count)
    if slug_of(dotted) == "metrics":
        source += METRICS_HISTOGRAM
    path.write_text(source)


def write_templated_tests(dotted: str, count: int) -> list[str]:
    slug = slug_of(dotted)
    lines = [PREAMBLE, f"import {dotted} as m\n\n"]
    names: list[str] = []
    for index in range(count):
        suffix, body = TEMPLATES[index % len(TEMPLATES)]
        name = f"test_{slug}_case_{index:02d}_{suffix}"
        names.append(name)
        lines.append(f"\n\ndef {name}():\n")
        if index == 0:
            lines.append('    """Smallest template: the row is inventory filler."""\n')
        lines.append("    " + body.format(i=index, slug=slug, count=count) + "\n")
    path = test_path(dotted)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines))
    return names


def write_real_tests(dotted: str) -> list[str]:
    path = test_path(dotted)
    lines = [PREAMBLE, REAL_IMPORTS[dotted] + "\n\n"]
    names = []
    for name, body in REAL_TESTS[dotted]:
        names.append(name)
        lines.append("\n\n")
        if body and body[0].startswith("@"):
            # Body already carries its own decorator, def line and indentation.
            lines.append("\n".join(body) + "\n")
            continue
        lines.append(f"def {name}():\n")
        for row in body:
            lines.append("    " + row + "\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines))
    return names


def build_inventory_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for dotted, count, kind in MODULES:
        if kind == "real":
            names = [(name, dotted) for name, _ in REAL_TESTS[dotted]]
        else:
            names = [(name, dotted) for name in templated_names(dotted, count)]
        node_file = test_path(dotted).relative_to(DEMO).as_posix()
        for name, module in names:
            node_id = f"{node_file}::{name}"
            declared = DECLARATION_OVERRIDES.get(node_id, module)
            rows.append(
                {
                    "test_name": name,
                    "module": declared,
                    "node_id": node_id,
                    "description": f"covers {declared.rsplit('.', 1)[-1]} behaviour ({name.split('_')[1]})",
                }
            )
        for extra in EXTRA_ROWS_AFTER.get(dotted, []):
            rows.append(dict(extra))
    if len(rows) != 500:
        raise SystemExit(f"expected 500 inventory rows, built {len(rows)}")
    if len([row for row in rows if row["module"] == "app.workers.report_worker"]) != 5:
        raise SystemExit("report_worker must carry 5 declared rows (the hero is declared elsewhere)")
    # Plant the missing row: the last receipt_service row names a renamed node,
    # which leaves the real node it used to name unmapped.
    global swap
    swap = max(index for index, row in enumerate(rows) if row["module"] == MISSING_ROW["module"])
    rows[swap] = {
        "test_name": MISSING_ROW["test_name"],
        "module": MISSING_ROW["module"],
        "node_id": MISSING_ROW["node_id"],
        "description": "covers receipt_service uniqueness (renamed away)",
    }
    header = ["test_id", "test_name", "module", "node_id", "description", "avg_runtime_ms"]
    lines = [",".join(header)]
    for index, row in enumerate(rows, start=1):
        test_id = f"T-{index:04d}"
        lines.append(
            ",".join(
                [test_id, row["test_name"], row["module"], row["node_id"], row["description"], str(avg_runtime(test_id))]
            )
        )
    (DEMO / "inventory.csv").write_text("\n".join(lines) + "\n")
    return rows


def templated_names(dotted: str, count: int) -> list[str]:
    slug = slug_of(dotted)
    return [f"test_{slug}_case_{index:02d}_{TEMPLATES[index % len(TEMPLATES)][0]}" for index in range(count)]


def main() -> None:
    for package in ("app/api", "app/clients"):
        (DEMO / package / "__init__.py").parent.mkdir(parents=True, exist_ok=True)
        (DEMO / package / "__init__.py").write_text('"""Package."""\n')
    for dotted, count, kind in MODULES:
        if kind == "templated":
            write_templated_module(dotted, count)
    for dotted, count, kind in MODULES:
        if kind == "real":
            write_real_tests(dotted)
        else:
            write_templated_tests(dotted, count)
    for rel, source in EXTRA_TEST_FILES.items():
        (DEMO / rel).write_text(source)
    rows = build_inventory_rows()
    hero = rows[341]
    assert hero["test_name"] == "test_cache_roundtrip_contract", hero
    assert hero["module"] == "app.workers.legacy_adapter", hero
    assert rows[346]["test_name"] == "test_legacy_field_order", rows[346]
    assert rows[344]["test_name"] == "test_parses_legacy_pipe_payload", rows[344]
    print(f"wrote {len(rows)} inventory rows; report_worker block = T-0342..T-0347")
    print(f"hero row: T-0342 -> {hero['node_id']} declared {hero['module']}")
    print(f"missing row: T-{swap + 1:04d} -> {rows[swap]['node_id']}")
    print(f"unmapped node: tests/test_receipt_service.py::test_receipt_service_case_09_describe_is_text")


if __name__ == "__main__":
    main()
