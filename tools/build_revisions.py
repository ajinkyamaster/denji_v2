#!/usr/bin/env python3
"""Build the demo repository's revision diffs.

Why generated rather than hand-written: a hand-written unified diff drifts from
the files it claims to describe, and a diff that does not apply is the one input
the oracle cannot recover from. This tool builds revision A in a temp tree from
the checked-in A-side files, builds revision B from the repository on disk, asks
``git diff --no-index`` for the hunks, and rewrites the headers to the
``a/<path>`` / ``b/<path>`` form so the result reverse-applies to the repository.

Outputs (all under demo_repo/revisions/):

  post_change.diff                    the change under analysis (A -> B)
  post_change_behavioural_billing.diff  causal control: a semantics-modifying
                                        edit in the same module as the inert one
  docs_only.diff                      reachability control: a docs-only change

Run:  python3 tools/build_revisions.py
"""

import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo_repo"
REVISIONS = DEMO / "revisions"
REV_A = ROOT / "fixtures" / "rev_a"
BEHAVIOURAL_CONTROL = ROOT / "fixtures" / "behavioural_control"
SKIP = ("revisions", "__pycache__", ".pytest_cache", ".git")


def copy_tree(source, destination):
    """Copy a tree, skipping generated and fixture-only directories."""
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns(*SKIP))


def overlaid_tree(overrides):
    """Build revision A in a temp directory; return (tempdir, path)."""
    handle = tempfile.mkdtemp(prefix="testscope-revisions-")
    root = pathlib.Path(handle)
    target = root / "a"
    copy_tree(DEMO, target)
    if overrides is not None:
        for path in sorted(overrides.rglob("*")):
            if path.is_file():
                destination = target / path.relative_to(overrides)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
    return root


def build_additive_diff(overrides, output_name):
    """Diff ``repo`` -> ``repo + overrides`` (used for authored test patches)."""
    root = pathlib.Path(tempfile.mkdtemp(prefix="testscope-revisions-"))
    try:
        source = root / "a"
        target = root / "b"
        copy_tree(DEMO, source)
        copy_tree(DEMO, target)
        for path in sorted(overrides.rglob("*")):
            if path.is_file():
                destination = target / path.relative_to(overrides)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
        _write_git_diff(root, output_name)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _write_git_diff(root, output_name):
    completed = subprocess.run(
        ["git", "diff", "--no-index", "--no-color", "a", "b"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if completed.returncode not in (0, 1):
        print(completed.stderr, file=sys.stderr)
        raise SystemExit(f"git diff failed for {output_name}")
    text = completed.stdout
    if not text.strip():
        raise SystemExit(f"empty diff for {output_name}: overrides did not change anything")
    text = text.replace(" a/a/", " a/").replace(" b/b/", " b/")
    text = text.replace("--- a/a/", "--- a/").replace("+++ b/b/", "+++ b/")
    REVISIONS.mkdir(parents=True, exist_ok=True)
    (REVISIONS / output_name).write_text(text, encoding="utf-8")
    print(f"wrote revisions/{output_name} ({len(text.splitlines())} lines)")


def build_diff(overrides, output_name):
    """Generate one diff and write it to demo_repo/revisions/<output_name>."""
    root = overlaid_tree(overrides)
    try:
        source = root / "a"
        target = root / "b"
        copy_tree(DEMO, target)
        completed = subprocess.run(
            ["git", "diff", "--no-index", "--no-color", "a", "b"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        if completed.returncode not in (0, 1):
            print(completed.stderr, file=sys.stderr)
            raise SystemExit(f"git diff failed for {output_name}")
        text = completed.stdout
        if not text.strip():
            raise SystemExit(f"empty diff for {output_name}: overrides did not change anything")
        # git prefixes both the temp directory and its own a/ b/ labels; keep one.
        text = text.replace(" a/a/", " a/").replace(" b/b/", " b/")
        text = text.replace("--- a/a/", "--- a/").replace("+++ b/b/", "+++ b/")
        REVISIONS.mkdir(parents=True, exist_ok=True)
        (REVISIONS / output_name).write_text(text, encoding="utf-8")
        print(f"wrote revisions/{output_name} ({len(text.splitlines())} lines)")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main():
    build_diff(REV_A, "post_change.diff")
    build_diff(BEHAVIOURAL_CONTROL, "post_change_behavioural_billing.diff")
    build_diff(ROOT / "fixtures" / "docs_only", "docs_only.diff")
    build_additive_diff(ROOT / "fixtures" / "authored", "authored_cache_test.diff")


if __name__ == "__main__":
    main()
