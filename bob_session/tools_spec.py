"""The MCP tool surface: exactly four tools, defined once.

Why four and not twenty (C23, the context tax): tool definitions are re-sent on
every interaction and consume context, and Bob's own documentation says disabling
unused tools reduces that consumption. The tool *surface* is therefore a
recurring tax on a non-replenishable coin budget. The rule that follows is to
prefer few, wide tools over many narrow ones, and to return digests rather than
raw data. One tool that returns the whole ledger beats six that return slices,
because a narrow tool forces multi-turn iteration — which costs more than one
wide tool that answers fully.

This module is the single source of truth for the surface: ``mcp_server.py``
serves it and ``report.py`` validates the routing ring (invariant I17) against
it, so the producer and the tool surface cannot drift apart silently.
"""

SCHEMA_VERSION = "2.0"
PROMPT_VERSION = "v2.0.0"
TOOL_VERSION = "2.0.0"
SERVER_NAME = "testscope"
PROTOCOL_VERSION = "2024-11-05"

DETERMINISM_NOTE = " This tool is deterministic: it decides exactly and costs no model tokens."

TOOLS = [
    {
        "name": "testscope_ledger",
        "description": (
            "Compute the change-impact ledger for a code change, deterministically. "
            "Purpose: answer, for every test in the inventory, whether it must run, is now stale, "
            "became newly relevant through hidden behavioural coupling, or is untouched; and list the "
            "changed behaviours that have no test at all. "
            "Prerequisites: a repository path, a unified-diff path, and an inventory path (.csv or .xlsx). "
            "Expected outcome: the complete ledger artefact (JSON) including classification, dispositions, "
            "uncovered work items, measurement, triage and priority order. "
            "Use this INSTEAD of reasoning about selection: it is exact." + DETERMINISM_NOTE
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "path to the repository root"},
                "diff": {"type": "string", "description": "path to a unified diff (A -> B)"},
                "inventory": {"type": "string", "description": "path to the test inventory (.csv or .xlsx)"},
                "generated_at": {
                    "type": "string",
                    "description": "ISO-8601 timestamp used for run_metadata.generated_at; part of the input, so it is pinned by the caller",
                },
                "oracle": {
                    "type": "string",
                    "description": "optional path to an oracle result JSON; without it, recall is reported as undefined",
                },
                "claims": {
                    "type": "string",
                    "description": "optional path to a claim-envelope JSON array from the model roles",
                },
                "model_layer": {"type": "string", "enum": ["enabled", "disabled"], "default": "disabled"},
            },
            "required": ["repo", "diff", "inventory", "generated_at"],
            "additionalProperties": False,
        },
        "alwaysAllow": True,
    },
    {
        "name": "testscope_verify",
        "description": (
            "Re-derive model claims against the repository. This is the kernel and the trust boundary: "
            "no claim becomes a verdict until this tool accepts it. "
            "Purpose: turn a citation into an obligation. Each claim names files and symbols; this tool "
            "re-opens them and re-derives the claim mechanically. A claim whose citation does not resolve "
            "is rejected, with the failing gate named. "
            "Prerequisites: a claim envelope array (claim_type, role, targets, citations, confidence, "
            "rationale) and the repository path. "
            "Expected outcome: accepted / rejected / unconfirmed verdicts. Confidence affects ordering only, "
            "never acceptance." + DETERMINISM_NOTE
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "claims": {"type": "array", "description": "claim envelopes to verify", "items": {"type": "object"}},
                "repo": {"type": "string", "description": "path to the repository root"},
                "inventory": {"type": "string", "description": "optional inventory path for test-id lookups"},
            },
            "required": ["claims", "repo"],
            "additionalProperties": False,
        },
        "alwaysAllow": True,
    },
    {
        "name": "testscope_oracle",
        "description": (
            "Measure ground truth by executing the suite at both revisions. "
            "Purpose: compute the outcome discriminant Delta(t) = [outcome_A(t) != outcome_B(t)] for every "
            "test, which is a LOWER BOUND on the affected set: it can measure recall and can never measure "
            "precision. It also refuses to report a measurement it cannot trust: the run uses all markers "
            "(-m \"\") and asserts that it collected the full inventory, so a partial instrument reports "
            "complete:false instead of false confidence (invariant O1). "
            "Prerequisites: the repository, two revisions (git SHAs, or a diff to reverse-apply), and the "
            "pytest command to run. "
            "Expected outcome: per-node outcomes at A and B, the discriminating nodes, flaky exclusions, and "
            "completeness. Side effects: writes only inside a temp working copy; the input repository is never "
            "mutated." + DETERMINISM_NOTE
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "path to the repository"},
                "rev_a": {"type": "string", "description": "git SHA of the pre-change revision"},
                "rev_b": {"type": "string", "description": "git SHA of the post-change revision"},
                "patch": {
                    "type": "string",
                    "description": "alternative to SHAs: a unified diff (A -> B) reverse-applied in a temp copy to reconstruct A",
                },
                "inventory_total": {"type": "integer", "description": "expected population size, from the inventory"},
                "run_cmd": {"type": "string", "description": "pytest command; defaults to the full-marker run"},
                "timeout": {"type": "integer", "description": "seconds per revision run", "default": 900},
            },
            "required": ["repo"],
            "additionalProperties": False,
        },
        "alwaysAllow": True,
    },
    {
        "name": "testscope_gate",
        "description": (
            "Decide whether a model-authored test is admissible, by execution. "
            "Purpose: five behavioural gates — G1 buildable, G2 passes five times (anti-flake), "
            "G3 patch test (an ASSERTION must fire at the previous revision; a collection or import error "
            "does not qualify, because that proves the symbol is absent rather than that behaviour changed), "
            "G4 mutation strength restricted to the changed lines, G5 specification anchoring when (and only "
            "when) an intent artefact exists. "
            "Prerequisites: repository path, a test patch (unified diff or file path), and the symbol under "
            "test; the previous revision is either given or reconstructed by reverse-applying the change diff. "
            "Expected outcome: the individual gate results and an overall accepted flag. "
            "Side effects: writes only inside a sandbox temp directory, runs with a timeout, and inherits no "
            "environment secrets. This is the only tool that touches test files, so it is the only tool whose "
            "alwaysAllow is FALSE: it requires an explicit human click, and that click is the trust boundary "
            "expressed in the permission model."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "path to the repository"},
                "test_patch": {"type": "string", "description": "unified diff text or a path to a patch file"},
                "symbol": {"type": "string", "description": "dotted symbol the test is meant to pin"},
                "patch": {
                    "type": "string",
                    "description": "the change diff (A -> B) used to reconstruct the previous revision for G3",
                },
                "test_path": {"type": "string", "description": "optional target file inside the repository"},
                "intent": {
                    "type": "object",
                    "description": "optional intent artefact {path, line, quote}: when absent, G5 reports null",
                },
                "timeout": {"type": "integer", "default": 120},
            },
            "required": ["repo", "test_patch", "symbol"],
            "additionalProperties": False,
        },
        "alwaysAllow": False,
    },
]

TOOL_NAMES = tuple(tool["name"] for tool in TOOLS)
AUTO_APPROVED = tuple(tool["name"] for tool in TOOLS if tool["alwaysAllow"])
APPROVAL_REQUIRED = tuple(tool["name"] for tool in TOOLS if not tool["alwaysAllow"])


def tool_by_name(name):
    for tool in TOOLS:
        if tool["name"] == name:
            return tool
    return None
