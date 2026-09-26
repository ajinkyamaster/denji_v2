"""Unified-diff parsing, symbol attribution and inertness classification.

The inertness rule (Lever 2 of the architecture) is implemented here: a
change whose added and removed lines carry the *same token skeleton* after
literals are normalised cannot alter observable behaviour, so it licenses
not re-running the tests that only touched that symbol.

Skeletons are computed with the tokenizer, not with a regex, so a reworded
log message or a renamed local collapses to the same skeleton while a
changed expression does not.
"""
from __future__ import annotations

import ast
import collections
import dataclasses
import io
import re
import tokenize
from typing import Dict, List, Optional, Sequence, Tuple

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
DOC_SUFFIXES = (".md", ".rst", ".txt")
SKELETON_NAME = "N"
SKELETON_NUMBER = "0"
SKELETON_STRING = "S"


@dataclasses.dataclass(frozen=True)
class HunkLine:
    """One line of a hunk, with its line numbers on either side."""

    kind: str  # " " context, "-" removed, "+" added
    text: str
    a_line: Optional[int] = None
    b_line: Optional[int] = None


@dataclasses.dataclass
class FileChange:
    """Every hunk touching one file."""

    path: str
    hunks: List[List[HunkLine]]
    is_python: bool
    is_docs: bool

    def added(self) -> List[Tuple[str, int]]:
        return [(line.text, line.b_line) for hunk in self.hunks for line in hunk if line.kind == "+"]

    def removed(self) -> List[Tuple[str, int]]:
        return [(line.text, line.a_line) for hunk in self.hunks for line in hunk if line.kind == "-"]


@dataclasses.dataclass
class SymbolChange:
    """One changed symbol, with its inertness verdict."""

    module: str
    symbol: str
    path: str
    kind: str  # modified | added | removed
    semantic: bool
    added: List[Tuple[str, int]]
    removed: List[Tuple[str, int]]
    evidence: str

    @property
    def changed_lines(self) -> List[int]:
        return sorted({number for _, number in self.added} | {number for _, number in self.removed})

    @property
    def line(self) -> int:
        lines = self.changed_lines
        return lines[0] if lines else 0


def parse_diff(diff_text: str) -> List[FileChange]:
    """Parse a unified diff into per-file changes."""
    files: List[FileChange] = []
    current: Optional[FileChange] = None
    hunk: Optional[List[HunkLine]] = None
    a_no = b_no = 0
    for raw in diff_text.splitlines():
        if raw.startswith("diff --git "):
            if current is not None:
                files.append(current)
            path = raw.split(" b/", 1)[1] if " b/" in raw else raw.split(" ", 3)[-1]
            current = FileChange(
                path=path,
                hunks=[],
                is_python=path.endswith(".py"),
                is_docs=path.endswith(DOC_SUFFIXES),
            )
            hunk = None
            continue
        if current is None:
            continue
        if raw.startswith(("--- ", "+++ ", "index ", "new file", "deleted file", "similarity ", "rename ")):
            continue
        if raw.startswith("@@"):
            match = HUNK_RE.match(raw)
            if not match:
                raise ValueError(f"malformed hunk header: {raw}")
            a_no = int(match.group(1))
            b_no = int(match.group(3))
            hunk = []
            current.hunks.append(hunk)
            continue
        if hunk is None or not raw:
            continue
        marker, text = raw[0], raw[1:]
        if marker == "-":
            hunk.append(HunkLine("-", text, a_line=a_no))
            a_no += 1
        elif marker == "+":
            hunk.append(HunkLine("+", text, b_line=b_no))
            b_no += 1
        elif marker == " ":
            hunk.append(HunkLine(" ", text, a_line=a_no, b_line=b_no))
            a_no += 1
            b_no += 1
        elif marker == "\\":
            continue
    if current is not None:
        files.append(current)
    return files


def reconstruct_pre(post_text: str, change: FileChange) -> str:
    """Reconstruct the pre-change text of a file by reverse-applying its hunks."""
    lines = post_text.splitlines()
    for hunk in change.hunks:
        # The pre image of a hunk is its context + removed lines; the post image
        # is its context + added lines.  Both spans start at the hunk's first
        # post-side line number.
        pre_block = [line.text for line in hunk if line.kind in " -"]
        post_count = len([line for line in hunk if line.kind in " +"])
        starts = [line.b_line for line in hunk if line.b_line is not None]
        if not starts:
            continue
        start = min(starts)
        lines[start - 1 : start - 1 + post_count] = pre_block
    joined = "\n".join(lines)
    if post_text.endswith("\n"):
        joined += "\n"
    return joined


def skeleton_tokens(line: str) -> Tuple[str, ...]:
    """Token skeleton of one line: names, numbers and literals collapse."""
    tokens: List[str] = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(line).readline):
            if token.type == tokenize.NAME:
                tokens.append(SKELETON_NAME)
            elif token.type == tokenize.NUMBER:
                tokens.append(SKELETON_NUMBER)
            elif token.type == tokenize.STRING:
                tokens.append(SKELETON_STRING)
            elif token.type in _FSTRING_TYPES:
                tokens.append(SKELETON_STRING)
            elif token.type == tokenize.OP:
                tokens.append(token.string)
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        return (re.sub(r"\s+", " ", line).strip(),)
    return tuple(tokens)


_FSTRING_TYPES = {
    getattr(tokenize, name)
    for name in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END")
    if hasattr(tokenize, name)
}


def skeleton_multiset(lines: Sequence[str]) -> collections.Counter:
    """Multiset of line skeletons, so pure reordering is inert."""
    return collections.Counter(skeleton_tokens(line) for line in lines)


def _symbol_ranges(text: str) -> List[Tuple[str, int, int]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    ranges = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            end = getattr(node, "end_lineno", None) or node.lineno
            ranges.append((node.name, node.lineno, end))
    return ranges


def _covering(ranges: Sequence[Tuple[str, int, int]], line: int) -> str:
    best: Optional[Tuple[str, int]] = None
    for name, start, end in ranges:
        if start <= line <= end:
            if best is None or start >= best[1]:
                best = (name, start)
    return best[0] if best else "<module>"


def attribute(
    change: FileChange,
    post_text: str,
    module: str,
) -> List[SymbolChange]:
    """Attribute a file's changed lines to the symbols that own them."""
    if not change.is_python:
        return []
    pre_text = reconstruct_pre(post_text, change)
    post_ranges = _symbol_ranges(post_text)
    pre_ranges = _symbol_ranges(pre_text)
    post_names = {name for name, _, _ in post_ranges}
    pre_names = {name for name, _, _ in pre_ranges}
    added: Dict[str, List[Tuple[str, int]]] = collections.defaultdict(list)
    removed: Dict[str, List[Tuple[str, int]]] = collections.defaultdict(list)
    for text, line in change.added():
        if line is not None:
            added[_covering(post_ranges, line)].append((text, line))
    for text, line in change.removed():
        if line is not None:
            removed[_covering(pre_ranges, line)].append((text, line))
    out: List[SymbolChange] = []
    for symbol in sorted(set(added) | set(removed)):
        if symbol in added and symbol not in removed:
            kind = "added" if symbol not in pre_names else "modified"
        elif symbol in removed and symbol not in added:
            kind = "removed" if symbol not in post_names else "modified"
        else:
            kind = "modified"
        semantic, evidence = _classify(kind, added.get(symbol, []), removed.get(symbol, []))
        out.append(
            SymbolChange(
                module=module,
                symbol=symbol,
                path=change.path,
                kind=kind,
                semantic=semantic,
                added=sorted(added.get(symbol, []), key=lambda item: item[1]),
                removed=sorted(removed.get(symbol, []), key=lambda item: item[1]),
                evidence=evidence,
            )
        )
    return out


def _trivial(lines: Sequence[Tuple[str, int]]) -> bool:
    """Blank and comment-only lines cannot change behaviour."""
    return all(not text.strip() or text.strip().startswith("#") for text, _ in lines)


def _classify(
    kind: str,
    added: Sequence[Tuple[str, int]],
    removed: Sequence[Tuple[str, int]],
) -> Tuple[bool, str]:
    if kind == "added":
        if _trivial(added) and not removed:
            return False, "only blank or comment lines were added: inert"
        return True, "symbol exists only in the new revision"
    if kind == "removed":
        if _trivial(removed) and not added:
            return False, "only blank or comment lines were removed: inert"
        return True, "symbol exists only in the base revision"
    if skeleton_multiset([text for text, _ in removed]) == skeleton_multiset([text for text, _ in added]):
        return False, "identical line skeletons after literal normalisation: inert reword or reorder"
    return True, "line skeletons differ: semantics-modifying"
