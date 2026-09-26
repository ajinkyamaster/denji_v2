#!/usr/bin/env python3
"""Capture the §11 wire evidence: tools/list, and one kernel rejection.

Runs the MCP server exactly as Bob would: newline-delimited JSON-RPC on stdin,
stdout is protocol only. Nothing here imports the analysed repository.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "bob_session" / "mcp_server.py"

REQUESTS = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    {
        "jsonrpc": "2.0",
        "id": 3,
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
                        "citations": [{"path": "app/services/does_not_exist.py", "symbol": "ghost", "line": 1}],
                        "confidence": "high",
                        "rationale": "fabricated citation on purpose",
                    }
                ],
            },
        },
    },
]


def main():
    payload = "".join(json.dumps(request) + "\n" for request in REQUESTS)
    completed = subprocess.run(
        [sys.executable, str(SERVER)],
        input=payload,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=120,
    )
    messages = [json.loads(line) for line in completed.stdout.splitlines()]
    tools = messages[1]["result"]["tools"]
    print("=== tools/list (name -> alwaysAllow) ===")
    print(json.dumps([{"name": t["name"], "alwaysAllow": t.get("alwaysAllow")} for t in tools], indent=2))
    print("=== ONE kernel rejection, gate named, over the wire ===")
    print(json.dumps(messages[2]["result"], indent=2))
    print("=== stdout is protocol only; stderr carries diagnostics ===")
    print("returncode:", completed.returncode)
    print("stderr:", repr(completed.stderr[:300]))


if __name__ == "__main__":
    main()
