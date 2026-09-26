"""The MCP surface: protocol correctness, stdout discipline, and the approval policy.

Two things are being protected here. First, stdout carries the protocol and
nothing else - a stray print breaks the client and the failure looks like a broken
server rather than a stray log line. Second, ``alwaysAllow`` covers exactly the
three pure tools: the gate is the only tool that touches test files, so it is the
only one that requires a human click, and that click is the trust boundary
expressed in the permission model.
"""

import json
import pathlib
import subprocess
import sys

import pytest

from bob_session.tools_spec import APPROVAL_REQUIRED, AUTO_APPROVED, TOOLS

PROJECT = pathlib.Path(__file__).resolve().parents[2]
SERVER = PROJECT / "bob_session" / "mcp_server.py"
MCP_JSON = PROJECT / ".bob" / "mcp.json"


def _serve(requests):
    payload = "".join(json.dumps(request) + "\n" for request in requests)
    completed = subprocess.run(
        [sys.executable, str(SERVER)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    messages = []
    for line in completed.stdout.splitlines():
        messages.append(json.loads(line))  # every stdout line must be protocol JSON
    return messages


def test_handshake_and_tool_listing():
    messages = _serve(
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ]
    )
    assert len(messages) == 2, "a notification must not produce a response"
    assert messages[0]["result"]["serverInfo"]["name"] == "testscope"
    assert messages[0]["result"]["protocolVersion"] == "2024-11-05"
    names = [tool["name"] for tool in messages[1]["result"]["tools"]]
    assert names == ["testscope_ledger", "testscope_verify", "testscope_oracle", "testscope_gate"]


def test_stdout_is_protocol_only_and_diagnostics_go_to_stderr():
    completed = subprocess.run(
        [sys.executable, str(SERVER)],
        input=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\n",
        capture_output=True,
        text=True,
        timeout=60,
    )
    for line in completed.stdout.splitlines():
        json.loads(line)
    assert "testscope" in completed.stderr, "the server must say where its diagnostics went"


def test_tool_descriptions_meet_the_documented_standard():
    for tool in TOOLS:
        description = tool["description"]
        assert len(description) > 200, f"{tool['name']} needs a description a client can choose from"
        assert "Prerequisites" in description or "Purpose" in description
        if tool["name"] != "testscope_gate":
            assert "deterministic" in description.lower()


def test_unknown_and_missing_arguments_are_refused():
    messages = _serve(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "testscope_ledger", "arguments": {"repo": "demo_repo"}},
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "testscope_ledger",
                    "arguments": {
                        "repo": "demo_repo",
                        "diff": "x",
                        "inventory": "y",
                        "generated_at": "2026-01-01T00:00:00Z",
                        "misspelled": 1,
                    },
                },
            },
        ]
    )
    assert "missing required argument" in messages[0]["error"]["message"]
    assert "unknown argument" in messages[1]["error"]["message"]


def test_unknown_method_and_malformed_json():
    completed = subprocess.run(
        [sys.executable, str(SERVER)],
        input='{"jsonrpc":"2.0","id":1,"method":"no/such"}\nnot json\n',
        capture_output=True,
        text=True,
        timeout=60,
    )
    messages = [json.loads(line) for line in completed.stdout.splitlines()]
    assert messages[0]["error"]["code"] == -32601
    assert messages[1]["error"]["code"] == -32700


def test_verify_tool_rejects_a_fabricated_citation_over_the_wire():
    messages = _serve(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "testscope_verify",
                    "arguments": {
                        "repo": "demo_repo",
                        "claims": [
                            {
                                "claim_type": "link_exists",
                                "role": "scout",
                                "targets": {"test_id": "T-0342", "consumer_symbol": "parse_recent_cache_entries"},
                                "citations": [{"path": "ghost/file.py", "symbol": "nothing", "line": 1}],
                                "confidence": "high",
                                "rationale": "a citation that does not resolve",
                            }
                        ],
                    },
                },
            }
        ]
    )
    payload = json.loads(messages[0]["result"]["content"][0]["text"])
    assert payload["rejected"][0]["gate"] == "citation_invalid"
    assert messages[0]["result"]["isError"] is False, "a rejection is a verdict, not a server error"


def test_registration_file_matches_the_policy_and_points_at_real_paths():
    document = json.loads(MCP_JSON.read_text(encoding="utf-8"))
    server = document["mcpServers"]["testscope"]
    assert server["alwaysAllow"] == list(AUTO_APPROVED)
    assert list(APPROVAL_REQUIRED) == ["testscope_gate"]
    assert server["alwaysAllow"] != [tool["name"] for tool in TOOLS], "the gate must not be auto-approved"
    assert pathlib.Path(server["command"]).exists(), "the interpreter must exist"
    for argument in server["args"]:
        assert pathlib.Path(argument).exists(), f"registered path does not exist: {argument}"
    assert pathlib.Path(server["cwd"]).is_dir()


def test_the_server_imports_nothing_from_the_analysed_repository():
    source = SERVER.read_text(encoding="utf-8")
    assert "import app" not in source
    assert "from app" not in source
