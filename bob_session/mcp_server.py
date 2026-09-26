#!/usr/bin/env python3
"""MCP over STDIO: the four tools that expose TestScope to Bob.

Protocol: JSON-RPC 2.0, one JSON object per line on stdin, one per line on
stdout, and **nothing else on stdout ever**. A stray ``print`` corrupts the
stream and the client sees a broken server, so every diagnostic goes to stderr
and stdout is flushed after each protocol message.

Methods served: ``initialize``, ``notifications/initialized``, ``tools/list``,
``tools/call``, ``ping``.

Hard rules, each with a reason:

  * Tools 1-3 are pure with respect to the user's inputs: no writes into the
    analysed repository, no network. Tool 4 is the only one that touches test
    files, and it writes only inside a temp sandbox - which is why its
    ``alwaysAllow`` is false in ``.bob/mcp.json``: the human click is the trust
    boundary expressed in the permission model.
  * No tool imports or executes the analysed repository's code. ``ast.parse``
    only. That is what makes it safe to point the server at a hostile repository.
  * Input lines are capped (8 MiB) and every request is validated before it is
    dispatched; malformed input produces a JSON-RPC error, never a traceback on
    stdout.
  * Unknown arguments are refused rather than ignored: silently dropping a
    misspelled parameter is how a caller ends up believing it asked for something
    it did not.
"""

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bob_session import gates as gates_module
from bob_session import oracle as oracle_module
from bob_session.pipeline.report import validate
from bob_session.run_analysis import run_pipeline
from bob_session.tools_spec import (
    PROTOCOL_VERSION,
    SERVER_NAME,
    TOOLS,
    TOOL_NAMES,
    TOOL_VERSION,
    tool_by_name,
)
from bob_session.verify import summary_of, verify_claims

MAX_LINE_BYTES = 8 * 1024 * 1024
JSONRPC_ERRORS = {
    "parse": -32700,
    "invalid_request": -32600,
    "method_not_found": -32601,
    "invalid_params": -32602,
    "internal": -32603,
}


def log(message):
    """Diagnostics go to stderr only: stdout carries the protocol and nothing else."""
    print(f"[testscope] {message}", file=sys.stderr, flush=True)


def _check_arguments(name, arguments):
    """Minimal JSON-Schema enforcement: required keys present, unknown keys refused."""
    spec = tool_by_name(name)
    if spec is None:
        raise ValueError(f"unknown tool: {name}")
    schema = spec["inputSchema"]
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")
    required = schema.get("required", [])
    missing = [key for key in required if key not in arguments]
    if missing:
        raise ValueError(f"missing required argument(s): {', '.join(missing)}")
    known = set(schema.get("properties", {}))
    unknown = sorted(set(arguments) - known)
    if unknown:
        raise ValueError(f"unknown argument(s): {', '.join(unknown)}")
    return spec


def call_tool(name, arguments):
    """Dispatch one tool call. Returns ``(payload, is_error)``."""
    spec = _check_arguments(name, arguments)

    if name == "testscope_ledger":
        artifact, inventory_ids = run_pipeline(
            repo=arguments["repo"],
            diff_path=arguments["diff"],
            inventory_path=arguments["inventory"],
            generated_at=arguments["generated_at"],
            oracle_path=arguments.get("oracle"),
            claims_path=arguments.get("claims"),
            model_layer=arguments.get("model_layer", "disabled"),
        )
        problems = validate(artifact, inventory_ids=inventory_ids)
        if problems:
            return {"validation_problems": problems, "artifact": artifact}, True
        return artifact, False

    if name == "testscope_verify":
        inventory = None
        if arguments.get("inventory"):
            from bob_session.pipeline.inventory import load_inventory

            inventory = load_inventory(Path(arguments["inventory"]))
        result = verify_claims(arguments["claims"], repo=Path(arguments["repo"]), inventory=inventory)
        return result, False

    if name == "testscope_oracle":
        result = oracle_module.run_oracle(
            repo=arguments["repo"],
            patch=arguments.get("patch"),
            rev_a=arguments.get("rev_a"),
            rev_b=arguments.get("rev_b"),
            inventory_total=arguments.get("inventory_total"),
            run_cmd=arguments.get("run_cmd").split() if arguments.get("run_cmd") else None,
            timeout=int(arguments.get("timeout", 900)),
        )
        return result, False

    if name == "testscope_gate":
        result = gates_module.run_gates(
            repo=arguments["repo"],
            test_patch=arguments["test_patch"],
            symbol=arguments["symbol"],
            change_patch=arguments.get("patch"),
            test_path=arguments.get("test_path"),
            intent=arguments.get("intent"),
            timeout=int(arguments.get("timeout", 120)),
        )
        return result, not result["accepted"]

    raise ValueError(f"unhandled tool: {spec['name']}")


def handle(request):
    """Handle one JSON-RPC request; return a response dict, or None for a notification."""
    if not isinstance(request, dict):
        return _error(None, JSONRPC_ERRORS["invalid_request"], "request must be an object")
    method = request.get("method")
    identifier = request.get("id")
    is_notification = identifier is None
    if not isinstance(method, str):
        return _error(identifier, JSONRPC_ERRORS["invalid_request"], "method must be a string")

    if method == "initialize":
        return _result(
            identifier,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": TOOL_VERSION},
            },
        )
    if method in ("notifications/initialized", "initialized", "notifications/cancelled"):
        return None
    if method == "ping":
        return None if is_notification else _result(identifier, {})
    if method == "tools/list":
        return _result(identifier, {"tools": TOOLS})
    if method == "tools/call":
        params = request.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            payload, is_error = call_tool(name, arguments)
        except Exception as error:  # noqa: BLE001 - every failure becomes a protocol error
            log(f"tool {name!r} failed: {type(error).__name__}: {error}")
            return _error(identifier, JSONRPC_ERRORS["internal"], f"{type(error).__name__}: {error}")
        if is_error:
            log(f"tool {name!r} reported a problem")
        return _result(
            identifier,
            {
                "content": [{"type": "text", "text": json.dumps(payload, sort_keys=True)}],
                "isError": bool(is_error),
            },
        )
    if is_notification:
        return None
    return _error(identifier, JSONRPC_ERRORS["method_not_found"], f"unknown method: {method}")


def _result(identifier, result):
    return {"jsonrpc": "2.0", "id": identifier, "result": result}


def _error(identifier, code, message):
    return {"jsonrpc": "2.0", "id": identifier, "error": {"code": code, "message": message}}


def serve(instream=None, outstream=None):
    """Read newline-delimited JSON-RPC from ``instream`` and answer on ``outstream``."""
    instream = instream or sys.stdin
    outstream = outstream or sys.stdout
    for raw in instream:
        if len(raw.encode("utf-8", errors="ignore")) > MAX_LINE_BYTES:
            response = _error(None, JSONRPC_ERRORS["invalid_request"], "request line too large")
        else:
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                request = json.loads(stripped)
            except json.JSONDecodeError as error:
                response = _error(None, JSONRPC_ERRORS["parse"], f"invalid JSON: {error.msg}")
            else:
                try:
                    response = handle(request)
                except Exception as error:  # noqa: BLE001
                    log(f"dispatch failed: {type(error).__name__}: {error}")
                    response = _error(None, JSONRPC_ERRORS["internal"], f"{type(error).__name__}: {error}")
        if response is None:
            continue
        outstream.write(json.dumps(response, sort_keys=True) + "\n")
        outstream.flush()
    return 0


def main():
    log(f"serving {len(TOOL_NAMES)} tools over stdio: {', '.join(TOOL_NAMES)}")
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
