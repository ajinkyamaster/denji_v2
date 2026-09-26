"""Thin STDIO client for the four MCP tools (Person B consuming Person A's kernel).

The frozen contract: all four tools speak JSON on stdout for a single JSON request
on stdin. This client is TRANSPORT ONLY. It never reimplements a tool, never
interprets a verdict, and never writes to the repository.

The request frame used here is `{"tool": <name>, "input": <payload>}`. If Person A's
server frames requests differently, change `_frame` and nothing else -- the cascade
takes a `verify` callable, so tests and the live run share one seam.

Tests use `bob_session.roles.testing.StubVerifier` instead of this client, so the
layer's tests never depend on the server being present.

Tool payloads (frozen interfaces):

  testscope_ledger  {"repo", "diff", "inventory", "generated_at"}
  testscope_verify  {"claims": [...claim envelopes...], "repo"}
  testscope_oracle  {"repo", "rev_a", "rev_b", "run_cmd"}    testscope_gate    {"repo", "test_patch", "symbol"}      <- needs a human click
`call` returns the tool's output and raises on refusal; `call_raw` returns the whole
response document, refusals included.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .errors import KernelUnavailable

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SERVER = REPO_ROOT / "bob_session" / "mcp_server.py"


class McpToolClient:
    """One subprocess per call: the documented single-JSON-request contract."""

    def __init__(
        self,
        server: str | Path = DEFAULT_SERVER,
        *,
        python: str = sys.executable,
        timeout: float = 120.0,
        cwd: str | Path = REPO_ROOT,
    ):
        self.server = Path(server)
        self.python = python
        self.timeout = timeout
        self.cwd = str(cwd)

    # ---- the four tools, exactly as frozen ---------------------------------- #

    def ledger(self, *, repo: str, diff: str, inventory: str, generated_at: str) -> dict:
        return self.call(
            "testscope_ledger",
            {"repo": repo, "diff": diff, "inventory": inventory, "generated_at": generated_at},
        )

    def verify(self, claims: list[dict], repo: str) -> dict:
        return self.call("testscope_verify", {"claims": claims, "repo": repo})

    def oracle(self, *, repo: str, rev_a: str, rev_b: str, run_cmd: str) -> dict:
        return self.call(
            "testscope_oracle", {"repo": repo, "rev_a": rev_a, "rev_b": rev_b, "run_cmd": run_cmd}
        )

    def gate(self, payload: dict[str, Any]) -> dict:
        """testscope_gate requires an explicit human click in Bob. This method only
        transports the request; the permission belongs to the UI."""
        return self.call("testscope_gate", dict(payload))

    # ---- transport ---------------------------------------------------------- #

    def call(self, tool: str, payload: dict[str, Any]) -> dict:
        """The tool's output. Raised as KernelUnavailable on any refusal or failure."""
        response = self.call_raw(tool, payload)
        if response.get("ok") is False:
            raise KernelUnavailable(f"{tool} reported failure: {response.get('error') or response}")
        if "output" in response:
            return response["output"]
        return response

    def call_raw(self, tool: str, payload: dict[str, Any]) -> dict:
        """The response document exactly as the server wrote it, refusals included.

        `ok: false` is a STRUCTURED REFUSAL -- the request was adjudicated and
        refused -- whereas an exception means the call never completed at all (no
        server, a crash, a timeout, unparseable stdout). The cascade does not need
        that distinction and uses `call`; the conformance suite does need it, because
        "the gate refused an empty patch" and "the gate never ran" must not be
        reported as the same thing.
        """
        if not self.server.is_file():
            raise KernelUnavailable(f"kernel server not found: {self.server}")
        request = _frame(tool, payload)
        try:
            completed = subprocess.run(
                [self.python, str(self.server)],
                input=request,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=self.cwd,
            )
        except subprocess.TimeoutExpired:
            raise KernelUnavailable(f"{tool} timed out after {self.timeout}s") from None
        except OSError as exc:
            raise KernelUnavailable(f"{tool} could not start the server: {exc}") from None

        if completed.returncode != 0:
            raise KernelUnavailable(
                f"{tool} exited {completed.returncode}: {completed.stderr.strip()[:400]}"
            )
        return _parse(completed.stdout, tool)


def _frame(tool: str, payload: dict[str, Any]) -> str:
    return json.dumps({"tool": tool, "input": payload}, ensure_ascii=False) + "\n"


def _parse(stdout: str, tool: str) -> dict:
    text = stdout.strip()
    if not text:
        raise KernelUnavailable(f"{tool} produced no output")
    try:
        response = json.loads(text)
    except json.JSONDecodeError as exc:
        raise KernelUnavailable(f"{tool} produced non-JSON output ({exc.msg}): {text[:200]!r}") from None
    if not isinstance(response, dict):
        raise KernelUnavailable(f"{tool} responded with {type(response).__name__}; expected an object")
    return response
