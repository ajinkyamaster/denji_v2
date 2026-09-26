"""Security controls, each with the reason it exists.

The analysed repository is untrusted input: a diff is a text file written by
somebody else, and the tool is pointed at repositories it has never seen. These
tests pin the controls that make that safe.

T10 is the trust-boundary invariant: the pipeline never imports or executes the
analysed code. ``ast.parse`` only. Without it, "point the tool at this repository"
would be an instruction to run that repository's code - which is a backdoor, not
a feature.
"""

import hashlib
import json
import pathlib
import re

import pytest

from bob_session.pipeline import cache as cache_module
from bob_session.pipeline.errors import SafetyError
from bob_session.pipeline.paths import resolve_in_repo
from bob_session.tools_spec import AUTO_APPROVED, APPROVAL_REQUIRED, TOOLS

PROJECT = pathlib.Path(__file__).resolve().parents[2]
PIPELINE = PROJECT / "bob_session" / "pipeline"

FORBIDDEN = re.compile(r"\b(exec|eval)\s*\(|__import__|importlib")


def test_T10_pipeline_never_executes_or_imports_the_analysed_code():
    offenders = []
    for path in sorted(PIPELINE.rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            if FORBIDDEN.search(line):
                offenders.append(f"{path.relative_to(PROJECT)}:{number}")
    assert offenders == [], f"trust boundary violated: {offenders}"


def test_T10_holds_for_the_whole_server_side_surface():
    """The MCP server, the kernel and the gates must not exec analysed code either."""
    offenders = []
    for name in ("mcp_server.py", "verify.py", "oracle.py", "gates.py"):
        for number, line in enumerate((PROJECT / "bob_session" / name).read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#") or "sys.executable" in line or "subprocess" in line:
                continue
            if re.search(r"\beval\s*\(|__import__|importlib", line):
                offenders.append(f"{name}:{number}")
    assert offenders == []


@pytest.mark.parametrize(
    "bad_path",
    [
        "../../etc/passwd",
        "/etc/passwd",
        "app/../../outside.py",
        "app\\..\\..\\outside.py",
        "app/services/\x00cache.py",
        "",
    ],
)
def test_path_traversal_is_refused(bad_path):
    with pytest.raises(SafetyError):
        resolve_in_repo("/tmp", bad_path)


def test_symlink_escape_is_refused(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "inside.py").write_text("VALUE = 1\n", encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("SECRET = 1\n", encoding="utf-8")
    (root / "link.py").symlink_to(outside)
    assert resolve_in_repo(root, "inside.py")
    with pytest.raises(SafetyError, match="escapes the repository"):
        resolve_in_repo(root, "link.py")


def test_kernel_rejects_a_citation_that_escapes_the_repository():
    from bob_session.verify import verify_claims

    result = verify_claims(
        [
            {
                "claim_type": "link_exists",
                "role": "scout",
                "targets": {"test_id": "T-0342", "consumer_symbol": "parse_recent_cache_entries"},
                "citations": [{"path": "../../etc/passwd", "symbol": "root", "line": 1}],
                "confidence": "high",
                "rationale": "attempts to read outside the repository",
            }
        ],
        repo="demo_repo",
        inventory=[],
    )
    assert result["rejected"][0]["gate"] == "citation_invalid"
    assert "refused" in result["rejected"][0]["detail"]


def test_cache_refuses_to_write_inside_the_analysed_repository(tmp_path):
    store = cache_module.ArtifactCache(tmp_path / "demo_copy" / ".cache")
    (tmp_path / "demo_copy").mkdir()
    with pytest.raises(SafetyError, match="inside the analysed repository"):
        store.ensure_outside(tmp_path / "demo_copy")


def test_sandbox_environment_carries_no_secrets():
    from bob_session.gates import _sandbox_environment

    environment = _sandbox_environment()
    assert set(environment) == {"PATH", "HOME", "LANG", "PYTHONDONTWRITEBYTECODE", "PYTHONHASHSEED", "PYTHONPATH"}
    assert not any(key.lower().endswith(("_key", "_token", "_secret")) for key in environment)
    assert environment["PYTHONHASHSEED"] == "0"


def test_oversized_patch_is_refused_before_it_is_applied(tmp_path):
    from bob_session import gates

    huge = tmp_path / "huge.patch"
    huge.write_text("+" + "x" * (1024 * 1024 + 1), encoding="utf-8")
    with pytest.raises(RuntimeError, match="larger than"):
        gates._apply_patch(str(huge), tmp_path)


def test_always_allow_covers_exactly_the_three_pure_tools():
    assert AUTO_APPROVED == ("testscope_ledger", "testscope_verify", "testscope_oracle")
    assert APPROVAL_REQUIRED == ("testscope_gate",)
    assert [tool["alwaysAllow"] for tool in TOOLS] == [True, True, True, False]


def test_the_analysed_repository_is_never_written_by_the_pipeline():
    root = pathlib.Path("demo_repo")
    before = _tree_digest(root)
    from bob_session.run_analysis import run_pipeline

    run_pipeline(
        repo="demo_repo",
        diff_path="demo_repo/revisions/post_change.diff",
        inventory_path="inventory.csv",
        generated_at="2026-09-27T04:12:00Z",
    )
    assert _tree_digest(root) == before


def test_a_diff_naming_a_path_outside_the_repository_is_handled_without_reading_it():
    """Declared, not ignored: an escaping path is inert and never opened."""
    from bob_session.pipeline.diff_parser import parse_diff
    from bob_session.run_analysis import run_pipeline

    text = (
        "diff --git a/../../evil.py b/../../evil.py\n"
        "--- a/../../evil.py\n"
        "+++ b/../../evil.py\n"
        "@@ -0,0 +1,1 @@\n"
        "+SECRET = 1\n"
    )
    diff = parse_diff(text)
    assert diff.files[0].path == "../../evil.py"
    assert diff.changed_modules == [], "a path outside the repository must not become a changed module"


def _tree_digest(root):
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and ".pytest_cache" not in path.parts:
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()
