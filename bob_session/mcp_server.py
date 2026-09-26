#!/usr/bin/env python3
"""The MCP kernel: four tools, no more.

A deliberately small, coarse surface, because tool definitions are re-sent
every interaction and therefore cost coins on every turn:

    testscope_ledger   the deterministic engine            alwaysAllow
    testscope_verify   the kernel                          alwaysAllow
    testscope_oracle   executed ground truth               alwaysAllow
    testscope_gate     G1..G5 on an authored test          requires a click

Transport: one JSON request per line on stdin, one JSON response per line on
stdout. None of the four tools imports the target repository or executes its
code; they only ``ast.parse`` it, and the gate executes tests only inside a
sandbox copy.
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Callable, Dict, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from bob_session import gate as gate_mod
from bob_session import oracle as oracle_mod
from bob_session import verify
from bob_session.pipeline import inventory as inventory_mod
from bob_session.pipeline.index import RepoIndex
from bob_session.pipeline.run_analysis import run as run_ledger

TOOLS: Dict[str, Callable[[dict], dict]] = {}


def tool(name: str) -> Callable[[Callable[[dict], dict]], Callable[[dict], dict]]:
    def register(function: Callable[[dict], dict]) -> Callable[[dict], dict]:
        TOOLS[name] = function
        return function

    return register


@tool("testscope_ledger")
def _ledger(request: dict) -> dict:
    return run_ledger(
        repo=request.get("repo", "demo"),
        diff_path=request.get("diff", "diffs/change_b.patch"),
        inventory_path=request.get("inventory", "demo/inventory.csv"),
        generated_at=request.get("generated_at", "2026-09-26T00:00:00Z"),
        model_layer=request.get("model_layer", "enabled"),
        proposal_cache=request.get("proposal_cache", "bob_session/proposal_cache"),
        evidence_dir=request.get("evidence_dir", "bob_session/evidence"),
        ablation_baseline=request.get("ablation_baseline"),
    )


@tool("testscope_verify")
def _verify(request: dict) -> dict:
    repo = pathlib.Path(request.get("repo", "demo"))
    index = RepoIndex(repo)
    return verify.verify_claims(
        request.get("claims", []),
        repo_root=repo,
        index=index,
        symbolic_selection=set(request.get("symbolic_selection", [])),
        coverage=verify.coverage_from_evidence(request.get("coverage", "bob_session/evidence/coverage_b.json")),
        intent_lines=request.get("intent_lines"),
        gate_evidence=request.get("gate_evidence"),
    )


@tool("testscope_oracle")
def _oracle(request: dict) -> dict:
    rows = inventory_mod.load(request.get("inventory", "demo/inventory.csv"))
    import tempfile

    with tempfile.TemporaryDirectory(prefix="testscope-mcp-oracle-") as tmp:
        workdir = pathlib.Path(tmp)
        runs_a, deselected_a = oracle_mod.run_revision(
            request.get("repo", "demo"),
            request["rev_a"],
            python=request.get("python", sys.executable),
            markers=request.get("markers", "-m ''"),
            repeats=int(request.get("repeats", 2)),
            workdir=workdir / "a",
        )
        runs_b, deselected_b = oracle_mod.run_revision(
            request.get("repo", "demo"),
            request["rev_b"],
            python=request.get("python", sys.executable),
            markers=request.get("markers", "-m ''"),
            repeats=int(request.get("repeats", 2)),
            workdir=workdir / "b",
        )
    evidence = oracle_mod.analyse(
        rows=rows,
        runs_a=runs_a,
        runs_b=runs_b,
        strategy=request.get("label", "mcp"),
        deselected=max(deselected_a, deselected_b),
    )
    return evidence


@tool("testscope_gate")
def _gate(request: dict) -> dict:
    return gate_mod.run_for_patch(
        repo=request.get("repo", "demo"),
        patch_path=request["test_patch"],
        test_node=request["test_node"],
        symbol=request["symbol"],
        rev_a=request["rev_a"],
        rev_b=request["rev_b"],
    )


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            print(json.dumps({"error": f"malformed request: {exc}"}), flush=True)
            continue
        name = request.get("tool")
        if name == "list":
            print(json.dumps({"tools": sorted(TOOLS)}), flush=True)
            continue
        function = TOOLS.get(name or "")
        if function is None:
            print(json.dumps({"error": f"unknown tool {name!r}", "tools": sorted(TOOLS)}), flush=True)
            continue
        try:
            result = function(request.get("params") or {})
            print(json.dumps({"tool": name, "ok": True, "result": result}), flush=True)
        except Exception as exc:  # fail loud, never silently coerce
            print(json.dumps({"tool": name, "ok": False, "error": f"{exc.__class__.__name__}: {exc}"}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
