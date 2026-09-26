#!/usr/bin/env python3
"""Person B's acceptance check (deliverables B1..B6 and the section 12 criteria).

Run from the repository root:

    python3 bob_session/roles/acceptance_check.py

One `[PASS]`/`[FAIL]` line per mechanically checkable criterion, then `[PENDING]`
lines for the criteria that require the live Bob session or another owner's files.
"Done" means this prints a PASS verdict; a PENDING item is a known, named gap, not a
claim of completion.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bob_session.roles import cascade, context, dispatch, testing  # noqa: E402
from bob_session.roles.errors import (  # noqa: E402
    FalsifierInputError,
    FalsifierOrderError,
    TwoWritersOneFile,
    UnverifiedClaimError,
)

ROLES_DIR = Path(__file__).resolve().parent
SCREENSHOTS_DIR = ROOT / "bob_session" / "session_screenshots"
SENTINEL = "ACCEPTANCE_POST_CHANGE_SENTINEL_4471"

ROLE_FILES = ("scout.md", "cartographer.md", "author.md", "falsifier.md")
RULE_FILES = ("no-unverified-claim.md", "one-writer-one-file.md", "prefer-deterministic.md")
ARTEFACTS = (
    ROOT / ".bob" / "custom_modes.yaml",
    ROOT / ".bob" / "skills" / "testscope-ledger" / "SKILL.md",
    ROOT / ".bobignore",
    ROOT / "AGENTS.md",
    ROOT / "bob_session" / "coins.md",
    SCREENSHOTS_DIR / "README.md",
    ROLES_DIR / "video_storyboard_notes.md",
    ROLES_DIR / "WORKFLOW.md",
) + tuple(ROOT / ".bobrules" / name for name in RULE_FILES) + tuple(
    ROLES_DIR / name for name in ROLE_FILES
)

SCREENSHOT_FILES = (
    "workflow-deterministic-steps-completing.png",
    "subagent-own-context-window.png",
    "kernel-rejects-fabricated-citation.png",
    "select-action-developer-gate.png",
    "g3-assertion-fires-before-change.png",
    "final-artefact-dashboard.png",
    "bob-task-session-summary.png",
)

OWNED_PREFIXES = (".bob/", ".bobrules/", "AGENTS.md", ".bobignore", "bob_session/roles/",
                  "bob_session/coins.md", "bob_session/session_screenshots/")

INTENT_REF = "cartographer:intent:app.services.cache_service.write_cache_entry"
SCOUT_REF = "scout:link_exists:T-0342"


@dataclass
class Result:
    status: str  # PASS | FAIL | PENDING
    label: str
    detail: str = ""


def _fail_detail(problems: list[str]) -> str:
    return "; ".join(problems) if problems else ""


# --------------------------------------------------------------------------- #
# code-layer checks
# --------------------------------------------------------------------------- #


def check_layer_tests() -> Result:
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "bob_session/roles/tests", "-t", "."],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = (completed.stdout + completed.stderr).strip()
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    summary = " ".join(lines[-2:]) if len(lines) >= 2 else (lines[-1] if lines else "no output")
    ok = completed.returncode == 0 and "OK" in output
    return Result(
        "PASS" if ok else "FAIL",
        "layer tests green (B2 role prompts, B3 context assembly, B6 cascade + dispatch)",
        summary,
    )


def check_role_prompts() -> Result:
    problems: list[str] = []
    for name in ROLE_FILES:
        path = ROLES_DIR / name
        if not path.is_file():
            problems.append(f"missing {name}")
            continue
        text = path.read_text(encoding="utf-8")
        if context.PROMPT_BEGIN not in text or context.PROMPT_END not in text:
            problems.append(f"{name}: missing prompt markers")
        for block in ("## INPUTS THIS ROLE MUST RECEIVE", "## WHAT HAPPENS TO YOUR OUTPUT"):
            if block not in text:
                problems.append(f"{name}: missing '{block}'")

    # "actually used": every role assembles a real bundle, and the cascade drives them
    fixtures = {
        "scout": testing.scout_unit(),
        "cartographer": testing.cartographer_unit(),
        "author": testing.author_unit(),
        "falsifier": testing.falsifier_unit(),
    }
    if tuple(context.ROLES) != tuple(fixtures):
        problems.append(f"context.ROLES={context.ROLES} does not match the four role files")
    for role, unit in fixtures.items():
        assembled = context.assemble(role, unit)
        if not assembled.sufficient:
            problems.append(f"{role}: its own fixture bundle is insufficient: {assembled.missing}")
        if not assembled.bundle.get("prompt_version"):
            problems.append(f"{role}: bundle carries no prompt_version")
    if tuple(cascade.TIER_ROLES) != ("scout", "cartographer"):
        problems.append(f"cascade tier order is {cascade.TIER_ROLES}")
    if not callable(getattr(cascade, "run_author", None)) or not callable(
        getattr(cascade, "run_falsifier", None)
    ):
        problems.append("author/falsifier cascade entry points are missing")
    if tuple(dispatch.SEQUENTIAL_ROLES) != ("falsifier",):
        problems.append(f"sequential roles are {dispatch.SEQUENTIAL_ROLES}")

    return Result(
        "PASS" if not problems else "FAIL",
        "B2 four role prompts present, both required blocks, wired into assembly + cascade",
        _fail_detail(problems) or "all four assemble; tier order scout -> cartographer; author and falsifier wired",
    )


def check_author_withholding() -> Result:
    assembled = context.assemble_author(testing.author_unit(post_change_body=SENTINEL))
    if not assembled.sufficient:
        return Result("FAIL", "B4 author bundle withholds the post-change body", "bundle insufficient")
    in_bundle = SENTINEL in json.dumps(assembled.bundle)
    in_prompt = SENTINEL in context.render_prompt("author", assembled.bundle)
    withheld = "post_change_body" in assembled.bundle.get("withheld_fields", [])
    ok = not in_bundle and not in_prompt and withheld
    detail = "sentinel absent from bundle and prompt; withheld recorded" if ok else (
        f"leaked: in_bundle={in_bundle} in_prompt={in_prompt} withheld={withheld}"
    )
    return Result("PASS" if ok else "FAIL", "B3 author bundle provably excludes the post-change body", detail)


def check_verify_boundary() -> Result:
    # (a) a rejected claim reaches no outcome, and is logged with its gate
    proposer = testing.ScriptedProposer(
        [testing.as_envelope(testing.scout_claim()), testing.as_envelope(testing.intent_claim())]
    )
    verifier = testing.StubVerifier(default_gate="symbol_mismatch")
    outcome = cascade.run_cascade(
        testing.candidate_unit(), propose=proposer, verify=verifier, repo=str(ROOT)
    )
    if outcome.accepted:
        return Result("FAIL", "cascade: no claim reaches an outcome without a verify call", "rejected claim accepted")
    ledger = outcome.rejection_ledger()
    if not ledger or not ledger[0]["gate"]:
        return Result("FAIL", "cascade: every rejection is recorded with its gate", "no ledger entry")

    # (b) a forged accept (a claim the kernel never saw) raises and voids the run
    class HostileVerifier:
        def __call__(self, claims, repo):
            return {
                "accepted": [{"claim": testing.scout_claim(test_id="T-9999"), "obligation": "forged"}],
                "rejected": [],
                "unconfirmed": [],
            }

    try:
        cascade.run_cascade(
            testing.candidate_unit(),
            propose=testing.ScriptedProposer([testing.as_envelope(testing.scout_claim())]),
            verify=HostileVerifier(),
            repo=str(ROOT),
        )
    except UnverifiedClaimError:
        return Result(
            "PASS",
            "cascade: no claim reaches an outcome without a verify call",
            f"rejected claim logged (gate={ledger[0]['gate']}); forged accept raises UnverifiedClaimError",
        )
    return Result("FAIL", "cascade: no claim reaches an outcome without a verify call", "forged accept did not raise")


def check_escalation() -> Result:
    proposer = testing.ScriptedProposer(
        [testing.as_envelope(testing.scout_claim()), testing.as_envelope(testing.intent_claim())]
    )
    verifier = testing.StubVerifier(accept=[INTENT_REF], default_gate="symbol_mismatch")
    outcome = cascade.run_cascade(
        testing.candidate_unit(), propose=proposer, verify=verifier, repo=str(ROOT)
    )
    ok = (
        outcome.status == "escalated_accepted"
        and outcome.tiers_used == 2
        and proposer.call_count == 2
        and outcome.rejections[0].gate == "symbol_mismatch"
    )
    return Result(
        "PASS" if ok else "FAIL",
        "cascade: escalation path tier 1 rejected -> tier 2 verified (2-tier cap)",
        f"status={outcome.status} tiers={outcome.tiers_used} model_calls={proposer.call_count}",
    )


def check_one_writer() -> Result:
    registry = dispatch.WriterRegistry()
    registry.claim_file("tests/test_a.py", role="author", unit_id="u1")
    refused = False
    try:
        registry.claim_file("tests/test_a.py", role="author", unit_id="u2")
    except TwoWritersOneFile:
        refused = True
    waves = dispatch.plan_waves(
        [
            {"unit_id": "u1", "target_file": "tests/test_a.py"},
            {"unit_id": "u2", "target_file": "tests/test_a.py"},
            {"unit_id": "u3", "target_file": "tests/test_b.py"},
        ]
    )
    serialised = len(waves) == 2 and all(
        len({u["target_file"] for u in wave}) == len(wave) for wave in waves
    )
    ok = refused and serialised
    return Result(
        "PASS" if ok else "FAIL",
        "dispatch: one writer per file, enforced in code",
        f"second writer refused={refused}; same-file units serialised into {len(waves)} waves",
    )


def check_falsifier() -> Result:
    early = False
    try:
        cascade.run_falsifier(
            ledger={"selected": ["T-0342"]},
            diff_hunks=testing.DIFF,
            unselected_rows=[{"test_id": "T-0404"}],
            selected_ids=["T-0342"],
            propose=testing.ScriptedProposer([]),
            verify=testing.StubVerifier(),
            repo=str(ROOT),
            ledger_is_final=False,
        )
    except FalsifierOrderError:
        early = True

    selected = False
    try:
        cascade.run_falsifier(
            ledger={"selected": ["T-0342"]},
            diff_hunks=testing.DIFF,
            unselected_rows=[{"test_id": "T-0342"}],
            selected_ids=["T-0342"],
            propose=testing.ScriptedProposer([]),
            verify=testing.StubVerifier(),
            repo=str(ROOT),
            ledger_is_final=True,
        )
    except FalsifierInputError:
        selected = True

    outcome = cascade.run_falsifier(
        ledger={"selected": ["T-0342"]},
        diff_hunks=testing.DIFF,
        unselected_rows=[{"test_id": "T-0404"}, {"test_id": "T-0405"}],
        selected_ids=["T-0342"],
        propose=testing.ScriptedProposer([testing.as_envelope(testing.missed_claim())]),
        verify=testing.StubVerifier(default_gate="citation_invalid"),
        repo=str(ROOT),
        ledger_is_final=True,
    )
    recorded = (
        len(outcome.rejection_ledger()) == 1
        and outcome.rejection_ledger()[0]["role"] == "falsifier"
        and outcome.safe_direction_ids == ["T-0404"]
    )
    ok = early and selected and recorded
    return Result(
        "PASS" if ok else "FAIL",
        "cascade: falsifier runs last, alone, over the unselected rows only",
        f"refused-early={early} refused-selected={selected} rejection-ledger={recorded}",
    )


def check_bob_artefacts() -> Result:
    missing = [str(p.relative_to(ROOT)) for p in ARTEFACTS if not p.is_file()]
    return Result(
        "PASS" if not missing else "FAIL",
        "deliverable files present (B1 artefacts, B2 workflow + role files, B4 coins, B5 plan, B6 storyboard)",
        f"{len(ARTEFACTS) - len(missing)}/{len(ARTEFACTS)} present"
        + (f"; missing: {', '.join(missing)}" if missing else ""),
    )


def check_storyboard() -> Result:
    path = ROLES_DIR / "video_storyboard_notes.md"
    if not path.is_file():
        return Result("FAIL", "B6 video storyboard notes for Person D", "missing")
    text = path.read_text(encoding="utf-8").lower()
    problems = [
        f"missing segment marker {marker!r}"
        for marker in ("0:00", "0:20", "live demo", "90s", "never say", "kernel")
        if marker not in text
    ]
    return Result(
        "PASS" if not problems else "FAIL",
        "B6 video storyboard notes for Person D",
        _fail_detail(problems) or "segments, demo order, say/never-say and the capture checklist present",
    )


def check_custom_mode() -> Result:
    path = ROOT / ".bob" / "custom_modes.yaml"
    try:
        import yaml  # type: ignore
    except ImportError:
        return Result("PENDING", "B1 custom_modes.yaml parses and lists exactly four tools", "pyyaml not installed")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - report any parse failure
        return Result("FAIL", "B1 custom_modes.yaml parses and lists exactly four tools", f"YAML error: {exc}")
    modes = (data or {}).get("customModes") or []
    mode = next((m for m in modes if m.get("slug") == "testscope"), None)
    if mode is None:
        return Result("FAIL", "B1 custom_modes.yaml parses and lists exactly four tools", "no `testscope` mode")
    tools = set(mode.get("tools") or [])
    expected = {"testscope_ledger", "testscope_oracle", "testscope_verify", "testscope_gate"}
    groups = set(mode.get("groups") or [])
    ok = tools == expected and {"read", "mcp"} <= groups and bool(mode.get("roleDefinition"))
    return Result(
        "PASS" if ok else "FAIL",
        "B1 custom_modes.yaml parses and lists exactly four tools",
        f"tools={sorted(tools)} groups={sorted(groups)}",
    )


def check_workflow_manifest() -> Result:
    text = (ROLES_DIR / "WORKFLOW.md").read_text(encoding="utf-8")
    manifest = None
    for block in re.findall(r"```json\s*(.*?)```", text, re.S):
        try:
            candidate = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and "steps" in candidate:
            manifest = candidate
            break
    if manifest is None:
        return Result("FAIL", "B2 workflow manifest: 9 steps, 3 kinds, deterministic steps name their tool", "no JSON manifest found")

    steps = manifest["steps"]
    problems: list[str] = []
    if len(steps) != 9:
        problems.append(f"{len(steps)} steps, expected 9")
    kinds = {s.get("kind") for s in steps}
    if not kinds <= {"DETERMINISTIC", "AI", "INTERACTIVE"}:
        problems.append(f"unknown kinds: {kinds}")
    if sum(1 for s in steps if s.get("kind") == "INTERACTIVE") != 1:
        problems.append("expected exactly one INTERACTIVE gate")
    for step in steps:
        if step.get("kind") == "DETERMINISTIC" and not step.get("tool"):
            problems.append(f"step {step.get('step')} names no tool")
    for step in list(steps) + list(manifest.get("post_steps") or []):
        value = step.get("role_prompt")
        for path in value if isinstance(value, list) else ([value] if value else []):
            if not (ROOT / path).is_file():
                problems.append(f"missing role prompt {path}")
    return Result(
        "PASS" if not problems else "FAIL",
        "B2 workflow manifest: 9 steps, 3 kinds, deterministic steps name their tool",
        _fail_detail(problems) or f"steps={len(steps)} post_steps={len(manifest.get('post_steps') or [])}",
    )


def check_coins() -> Result:
    path = ROOT / "bob_session" / "coins.md"
    if not path.is_file():
        return Result("FAIL", "B4 coins.md with the real spend and the determinism audit column", "missing")
    text = path.read_text(encoding="utf-8")
    has_audit = "answerable deterministically" in text.lower()
    has_budget = "160" in text and "40" in text
    pending = len(re.findall(r"\bPENDING\b", text))
    ok = has_audit and has_budget
    return Result(
        "PASS" if ok else "FAIL",
        "B4 coins.md with the real spend and the determinism audit column",
        f"audit column={has_audit}; {pending} session rows marked PENDING until the recorded run",
    )


def check_select_action() -> Result:
    workflow = (ROLES_DIR / "WORKFLOW.md").read_text(encoding="utf-8")
    skill = (ROOT / ".bob" / "skills" / "testscope-ledger" / "SKILL.md").read_text(encoding="utf-8")
    problems = []
    if "Select Action" not in workflow or "INTERACTIVE" not in workflow:
        problems.append("WORKFLOW.md does not define the interactive gate")
    if not any(
        phrase in workflow.lower()
        for phrase in ("stale tests should i repair", "which stale tests")
    ):
        problems.append("WORKFLOW.md does not state the developer question")
    if "developer" not in skill and "Wait for the answer" not in skill:
        problems.append("SKILL.md skips the developer gate")
    return Result(
        "PASS" if not problems else "FAIL",
        "B2/B1 Select Action gate present in the workflow and the skill",
        _fail_detail(problems),
    )


def check_screenshots_plan() -> Result:
    path = SCREENSHOTS_DIR / "README.md"
    if not path.is_file():
        return Result("FAIL", "B5 screenshot capture plan lists the seven evidence files", "missing README")
    text = path.read_text(encoding="utf-8")
    missing = [name for name in SCREENSHOT_FILES if name not in text]
    return Result(
        "PASS" if not missing else "FAIL",
        "B5 screenshot capture plan lists the seven evidence files",
        _fail_detail(missing),
    )


def check_screenshots_captured() -> Result:
    captured = [name for name in SCREENSHOT_FILES if (SCREENSHOTS_DIR / name).is_file()]
    if len(captured) == len(SCREENSHOT_FILES):
        return Result("PASS", "B5 screenshots 1-7 captured", "all seven present")
    return Result(
        "PENDING",
        "B5 screenshots 1-7 captured",
        f"{len(captured)}/7 present; the rest are captured during the recorded session "
        f"(see bob_session/session_screenshots/README.md)",
    )


def check_mcp_json() -> Result:
    path = ROOT / ".bob" / "mcp.json"
    if path.is_file():
        return Result("PASS", "A .bob/mcp.json configured for the four tools", "present (Person A owns it)")
    return Result(
        "PENDING",
        "A .bob/mcp.json configured for the four tools",
        "owned by Person A; descriptions and the alwaysAllow policy are in bob_session/roles/mcp_tool_descriptions.md",
    )


def check_kernel_server() -> Result:
    path = ROOT / "bob_session" / "mcp_server.py"
    if path.is_file():
        return Result("PASS", "A kernel server bob_session/mcp_server.py present", "present (Person A owns it)")
    return Result(
        "PENDING",
        "A kernel server bob_session/mcp_server.py present",
        "owned by Person A; the layer talks to it through bob_session/roles/kernel_client.py",
    )


def check_kernel_conformance() -> Result:
    """The seam: does the server actually speak the frozen four-tool contract?

    "The file exists" and "the file is compatible" are different claims, and only the
    second one unblocks the integration. The suite is B's, and Person A can run it
    against their own server before telling anyone it is ready.
    """
    label = "Person A's kernel conforms to the frozen four-tool contract"
    if not (ROOT / "bob_session" / "mcp_server.py").is_file():
        return Result(
            "PENDING",
            label,
            "no server to test; the suite runs today against the bundled stub "
            "(python3 bob_session/roles/kernel_conformance.py --reference)",
        )
    try:
        completed = subprocess.run(
            [sys.executable, "bob_session/roles/kernel_conformance.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return Result("FAIL", label, "the conformance suite timed out after 600s")
    output = (completed.stdout + completed.stderr).strip().splitlines()
    verdict = next((line for line in reversed(output) if line.startswith("VERDICT")), "no verdict line")
    failures = [line.split("] ", 1)[-1] for line in output if line.startswith("[FAIL]")]
    if completed.returncode == 0:
        return Result("PASS", label, verdict)
    return Result("FAIL", label, f"{verdict}; failing: {_fail_detail(failures)}")


def check_live_evidence() -> Result:
    missing = [name for name in SCREENSHOT_FILES if not (SCREENSHOTS_DIR / name).is_file()]
    if not missing:
        return Result("PASS", "Live session evidence: rejection, escalation, falsifier observed", "screenshots present")
    return Result(
        "PENDING",
        "Live session evidence: rejection, escalation, falsifier observed",
        "the kernel rejection (shot 3), the escalation event, the Select Action gate and the falsifier "
        "run must be observed in the recorded Bob session",
    )


def check_commit_state() -> Result:
    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
    except OSError:
        return Result("PENDING", "Person B's files committed", "git unavailable")
    if inside.returncode != 0:
        return Result("PENDING", "Person B's files committed", "not a git work tree")

    status = subprocess.run(
        ["git", "status", "--porcelain", "-uall"], cwd=ROOT, capture_output=True, text=True, timeout=60
    )
    dirty = [
        line
        for line in status.stdout.splitlines()
        if any(line.endswith(prefix.rstrip("/")) or prefix in line for prefix in OWNED_PREFIXES)
    ]
    if not dirty:
        return Result("PASS", "Person B's files committed", "working tree clean for Person B's paths")
    return Result(
        "PENDING",
        "Person B's files committed",
        f"{len(dirty)} owned path(s) not committed yet — a human action (this agent does not commit unless asked)",
    )


CHECKS = (
    check_layer_tests,
    check_role_prompts,
    check_author_withholding,
    check_verify_boundary,
    check_escalation,
    check_one_writer,
    check_falsifier,
    check_bob_artefacts,
    check_custom_mode,
    check_storyboard,
    check_workflow_manifest,
    check_coins,
    check_select_action,
    check_screenshots_plan,
    check_screenshots_captured,
    check_mcp_json,
    check_kernel_server,
    check_kernel_conformance,
    check_live_evidence,
    check_commit_state,
)


def main() -> int:
    print("TestScope — Person B acceptance check (deliverables B1..B6, section 12)")
    print("=" * 78)
    results: list[Result] = []
    for check in CHECKS:
        try:
            results.append(check())
        except Exception as exc:  # noqa: BLE001 - a crashing check is a failure, not a traceback
            results.append(Result("FAIL", check.__name__, f"check crashed: {exc!r}"))

    for result in results:
        if result.status == "PENDING":
            continue
        line = f"[{result.status}] {result.label}"
        print(f"{line}\n         {result.detail}" if result.detail else line)

    pending = [r for r in results if r.status == "PENDING"]
    failed = [r for r in results if r.status == "FAIL"]
    if pending:
        print("-" * 78)
        print(f"Pending ({len(pending)}) — live Bob session or another owner's files:")
        for result in pending:
            print(f"  [PENDING] {result.label}\n            {result.detail}")

    print("-" * 78)
    if failed:
        print(f"VERDICT: FAIL — {len(failed)} criterion/criteria failed; {len(pending)} pending")
        return 1
    print(
        f"VERDICT: PASS — code layer green; {len(pending)} item(s) pending the live Bob "
        f"session / other owners"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
