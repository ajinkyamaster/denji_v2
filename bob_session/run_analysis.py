#!/usr/bin/env python3
"""Run the deterministic engine and emit the ledger artefact.

This is TOOL 1 of the MCP surface as a command line: the whole symbolic stratum,
zero model calls, zero coins, no network. Its output is a pure function of its
inputs plus the cache, so ``generated_at`` is a *parameter* rather than a clock
read — the artefact cannot differ between two runs unless an input differed.

Usage:
    python3 bob_session/run_analysis.py \
        --repo demo_repo \
        --diff demo_repo/revisions/post_change.diff \
        --inventory inventory.csv \
        --generated-at 2026-09-27T04:12:00Z \
        --out bob_session/testscope_report.json
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

if __package__ in (None, ""):  # allow `python3 bob_session/run_analysis.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bob_session.pipeline import cache as cache_module
from bob_session.pipeline.classify import classify
from bob_session.pipeline.coupling import detect_couplings
from bob_session.pipeline.diff_parser import parse_diff
from bob_session.pipeline.dispositions import build_ledger, build_uncovered
from bob_session.pipeline.inventory import load_inventory
from bob_session.pipeline.measurement import build_measurement
from bob_session.pipeline.priority import priority_order
from bob_session.pipeline.report import build_artifact, digest, serialize, validate, write_artifact
from bob_session.pipeline.repo_index import build_index
from bob_session.pipeline.triage import build_triage
from bob_session.tools_spec import PROMPT_VERSION, SCHEMA_VERSION, TOOL_VERSION


def _sha256_of(path):
    digest_handle = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest_handle.update(chunk)
    return digest_handle.hexdigest()


def _read_json(path):
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def build_cache_key(*, repo, diff_path, inventory_path, generated_at, oracle_path, claims_path, model_layer):
    extra = [f"generated_at={generated_at}", f"model_layer={model_layer}"]
    if oracle_path:
        extra.append(f"oracle={_sha256_of(oracle_path)}")
    if claims_path:
        extra.append(f"claims={_sha256_of(claims_path)}")
    return cache_module.cache_key(
        repo_hash=cache_module.content_hash_of_tree(repo),
        diff_hash=_sha256_of(diff_path),
        inventory_hash=_sha256_of(inventory_path),
        prompt_version=PROMPT_VERSION,
        tool_version=TOOL_VERSION,
        env_fingerprint=cache_module.environment_fingerprint(),
        extra=extra,
    )


def run_pipeline(
    *,
    repo,
    diff_path,
    inventory_path,
    generated_at,
    oracle_path=None,
    claims_path=None,
    model_layer="disabled",
    run_oracle=None,
    coins_spent=0,
):
    """Compute the artefact (no cache, no IO beyond reading the inputs)."""
    repo = Path(repo).resolve()
    inventory = load_inventory(Path(inventory_path))
    with open(diff_path, "r", encoding="utf-8") as handle:
        diff = parse_diff(handle.read(), source=str(diff_path))
    index = build_index(repo)

    couplings = detect_couplings(index, diff)

    claims_supplied = _read_json(claims_path) or []
    claims_in = claims_supplied
    claims_ignored = False
    if claims_supplied and model_layer == "disabled":
        # Monotonicity is a testable claim, and this is the test: with the model
        # layer disabled the selection must equal the deterministic baseline, so
        # a supplied claim set is *not* ingested. It is recorded rather than
        # silently dropped.
        claims_in = []
        claims_ignored = True
    verification = {"accepted": [], "rejected": [], "unconfirmed": []}
    if claims_in:
        from bob_session.verify import verify_claims

        verification = verify_claims(claims_in, repo=repo, inventory=inventory, diff=diff, index=index)
    verified_links = [entry["claim"] for entry in verification["accepted"] if entry["claim"].get("claim_type") == "link_exists"]

    classification = classify(index, inventory, diff, couplings, verified_links=verified_links)
    ledger = build_ledger(index, inventory, diff, classification, couplings)
    uncovered, uncovered_counters = build_uncovered(index, inventory, diff, classification)

    oracle = _read_json(oracle_path) if oracle_path else None
    if oracle is None and run_oracle:
        oracle = run_oracle

    structural_ids = classification.test_ids("definitely_affected")
    selected_ids = classification.selected_ids()

    measurement = build_measurement(
        oracle=oracle,
        inventory=inventory,
        selected_ids=selected_ids,
        structural_ids=structural_ids,
        model_layer=model_layer,
    )
    triage = build_triage(
        index,
        inventory,
        classification,
        ledger,
        couplings,
        oracle,
        structural_modules=set(diff.changed_modules),
    )
    order = priority_order(inventory, classification, ledger, selection=selected_ids)

    by_role = {"scout": 0, "cartographer": 0, "author": 0, "falsifier": 0}
    for claim in claims_in:
        role = claim.get("role")
        if role in by_role:
            by_role[role] += 1
    claims_block = {
        "proposed": len(claims_in),
        "accepted": len(verification["accepted"]),
        "rejected": len(verification["rejected"]),
        "unconfirmed": len(verification["unconfirmed"]),
        "by_role": by_role,
    }
    rejection_ledger = [
        {
            "role": entry["claim"].get("role"),
            "gate": entry.get("gate"),
            "detail": entry.get("detail"),
            "claim_ref": _claim_ref(entry["claim"]),
        }
        for entry in verification["rejected"]
    ]

    unsupported = [
        {"path": parsed.path, "reason": parsed.unsupported}
        for parsed in diff.files
        if parsed.unsupported
    ]
    closure = index.reverse_closure(diff.changed_modules, include_tests=False) if diff.changed_modules else {}
    histogram = {}
    members = []
    rows_by_depth = {}
    outside_package = []
    for module_name, depth in sorted(closure.items(), key=lambda item: (item[1], item[0])):
        module = index.module_named(module_name)
        if module is None or module.is_test:
            continue
        entry = {"module": module_name, "path": module.path, "depth": depth}
        if module.path.startswith("app/"):
            histogram[depth] = histogram.get(depth, 0) + 1
            members.append(entry)
        else:
            outside_package.append(entry)
    for verdict in classification.verdicts.values():
        if verdict.module in closure:
            rows_by_depth[closure[verdict.module]] = rows_by_depth.get(closure[verdict.module], 0) + 1
    direct_rows = sum(count for depth, count in rows_by_depth.items() if depth <= 1)
    transitive_rows = sum(count for depth, count in rows_by_depth.items() if depth >= 2)
    import_closure = {
        "modules": len(members),
        "depth_histogram": {str(depth): histogram[depth] for depth in sorted(histogram)},
        "members": members,
        "inventory_rows": direct_rows + transitive_rows,
        "direct_rows": direct_rows,
        "transitive_rows": transitive_rows,
        "rows_by_depth": {str(depth): rows_by_depth[depth] for depth in sorted(rows_by_depth)},
        "outside_package_dependents": outside_package,
        "scope_note": (
            "the closure above is the application package (app/**); operator entry points under scripts/ "
            "also depend on the change and are listed separately rather than silently folded in"
        ),
        "note": (
            "reverse import closure of the actively changed modules: the modules that can observe the "
            "change. It is a lower bound on the true dependency relation, never an upper bound (A1)."
        ),
    }
    run_metadata = {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "prompt_version": PROMPT_VERSION,
        "diff_files": sorted(diff.paths),
        "total_tests_in_suite": len(inventory),
        "generated_at": generated_at,
        "model_layer": model_layer,
        "coins_spent": coins_spent,
        "environment_fingerprint": cache_module.environment_fingerprint(),
        "inputs": {
            "diff_sha256": _sha256_of(diff_path),
            "inventory_sha256": _sha256_of(inventory_path),
            "repo_sha256": cache_module.content_hash_of_tree(repo),
            "oracle_sha256": _sha256_of(oracle_path) if oracle_path else None,
            "claims_sha256": _sha256_of(claims_path) if claims_path else None,
        },
        "change_summary": {
            "semantics_modifying_modules": diff.changed_modules,
            "inert_modules": diff.inert_modules,
            "inert_reasons": {parsed.path: parsed.inert_reason for parsed in diff.files},
            "removed_representations": diff.rho()["removed_representations"],
            "added_representations": diff.rho()["added_representations"],
            "removed_symbols": diff.rho()["removed_symbols"],
            "added_symbols": sorted({name for parsed in diff.files for name in parsed.added_symbols}),
        },
        "link_corrections": classification.link_corrections,
        "unparseable_modules": index.unparseable,
        "unsupported_files": unsupported,
        "exclusions": uncovered_counters,
        "claims_ignored": claims_ignored,
        "import_closure": import_closure,
        "structurally_reachable_ids": structural_ids,
        "declared_assumptions": list(cache_module.DECLARED_ASSUMPTIONS),
    }

    artifact = build_artifact(
        run_metadata=run_metadata,
        classification=classification,
        ledger=ledger,
        uncovered=uncovered,
        couplings=couplings,
        claims=claims_block,
        rejection_ledger=rejection_ledger,
        measurement=measurement,
        triage=triage,
        priority_order=order,
        inventory=inventory,
        uncovered_counters=uncovered_counters,
    )
    artifact["accepted_claims"] = [entry["claim"] for entry in verification["accepted"]]
    artifact["unconfirmed_claims"] = [entry["claim"] for entry in verification["unconfirmed"]]
    return artifact, [row.test_id for row in inventory]


def _claim_ref(claim):
    targets = claim.get("targets") or {}
    candidate = targets.get("test_id") or targets.get("symbol") or targets.get("path") or "claim"
    return f"{claim.get('role')}:{claim.get('claim_type')}:{candidate}"


def main(argv=None):
    parser = argparse.ArgumentParser(description="TestScope deterministic engine")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--diff", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--generated-at", required=True, help="ISO-8601 timestamp; pinned, not read from the clock")
    parser.add_argument("--out", default=None, help="artefact path (default: bob_session/testscope_report.json)")
    parser.add_argument("--oracle", default=None, help="oracle result JSON to fold in")
    parser.add_argument("--claims", default=None, help="claim envelope JSON array from the model layer")
    parser.add_argument("--model-layer", default="disabled", choices=("enabled", "disabled"))
    parser.add_argument("--coins-spent", type=int, default=0)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--cache-dir", default=None)
    parser.add_argument("--print-artifact", action="store_true", help="print the whole artefact to stdout")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    out_path = Path(args.out) if args.out else root / "bob_session" / "testscope_report.json"
    cache_dir = Path(args.cache_dir) if args.cache_dir else root / ".cache" / "testscope"

    key = build_cache_key(
        repo=args.repo,
        diff_path=args.diff,
        inventory_path=args.inventory,
        generated_at=args.generated_at,
        oracle_path=args.oracle,
        claims_path=args.claims,
        model_layer=args.model_layer,
    )
    store = cache_module.ArtifactCache(cache_dir).ensure_outside(args.repo)

    text = None
    cache_state = "cold"
    if not args.no_cache:
        cached = store.load(key)
        if cached is not None:
            text = cached
            cache_state = "warm"
    if text is None:
        artifact, inventory_ids = run_pipeline(
            repo=args.repo,
            diff_path=args.diff,
            inventory_path=args.inventory,
            generated_at=args.generated_at,
            oracle_path=args.oracle,
            claims_path=args.claims,
            model_layer=args.model_layer,
            coins_spent=args.coins_spent,
        )
        problems = validate(artifact, inventory_ids=inventory_ids)
        if problems:
            print(json.dumps({"valid": False, "problems": problems}, indent=2), file=sys.stderr)
            return 2
        text = serialize(artifact)
        if not args.no_cache:
            store.store(key, text)
    write_artifact_path = write_artifact_text(text, out_path)

    digest_value = hashlib.sha256(text.encode("utf-8")).hexdigest()
    parsed = json.loads(text)
    if args.print_artifact:
        sys.stdout.write(text)
        return 0
    summary = {
        "out": str(write_artifact_path),
        "cache": cache_state,
        "cache_key": key,
        "digest": digest_value,
        "generated_at": parsed["run_metadata"]["generated_at"],
        "schema_version": parsed["run_metadata"]["schema_version"],
        "selected_for_run": parsed["summary"]["selected_for_run"],
        "definitely_affected": parsed["summary"]["definitely_affected_count"],
        "semantically_affected": parsed["summary"]["semantically_affected_count"],
        "reduction_pct": parsed["summary"]["reduction_pct"],
        "stale": parsed["summary"]["stale_count"],
        "uncovered": parsed["summary"]["uncovered_count"],
        "recall": parsed["measurement"]["recall"],
        "truth_size": parsed["measurement"]["truth_size"],
        "price_of_safety": parsed["measurement"]["price_of_safety"],
        "oracle_complete": parsed["measurement"]["oracle"]["complete"],
        "priority_head": parsed["priority_order"][:3],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def write_artifact_text(text, path):
    """Write already-serialised artefact text atomically (keeps cache replay byte-exact)."""
    target = str(path)
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    import tempfile

    handle, temporary = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(target)), prefix=".artifact-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


if __name__ == "__main__":
    raise SystemExit(main())
