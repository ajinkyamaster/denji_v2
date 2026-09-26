"""Repository index: modules, imports, symbols, call sites and closures.

Everything here is a pure function of the repository text. No module of the
target repository is imported and no code of it is executed: only
``ast.parse`` is used, which is the v1 invariant kept by v2.
"""
from __future__ import annotations

import ast
import dataclasses
import pathlib
import re
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "var",
}


@dataclasses.dataclass(frozen=True)
class CallSite:
    """One call expression, with the literal string arguments it passes."""

    name: str
    receiver: str
    args: Tuple[str, ...]
    line: int


@dataclasses.dataclass
class ModuleIndex:
    dotted: str
    path: str
    source: str
    symbols: Dict[str, Tuple[int, int]]
    imports: List[str]
    calls: List[CallSite]
    parse_error: Optional[str]


def _dotted(node: ast.AST) -> str:
    parts: List[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _literal_args(call: ast.Call) -> Tuple[str, ...]:
    values: List[str] = []
    for arg in list(call.args) + [kw.value for kw in call.keywords]:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            values.append(arg.value)
        elif isinstance(arg, ast.JoinedStr):
            piece = "".join(
                part.value for part in arg.values if isinstance(part, ast.Constant) and isinstance(part.value, str)
            )
            values.append(piece)
        elif isinstance(arg, ast.Constant) and isinstance(arg.value, int):
            values.append(str(arg.value))
    return tuple(values)


class RepoIndex:
    """An index over the Python files of a repository."""

    def __init__(self, root: os.PathLike | str) -> None:
        self.root = pathlib.Path(root)
        self.modules: Dict[str, ModuleIndex] = {}
        self.by_path: Dict[str, str] = {}
        self.text_by_path: Dict[str, str] = {}
        self._reference_cache: Dict[str, Set[str]] = {}
        self._build()

    # -- construction ------------------------------------------------------
    def _build(self) -> None:
        for path in sorted(self.root.rglob("*.py")):
            rel_parts = path.relative_to(self.root).parts
            if any(part in SKIP_DIRS for part in rel_parts):
                continue
            rel = path.relative_to(self.root).as_posix()
            parts = rel[:-3].split("/")
            if parts[-1] == "__init__":
                parts = parts[:-1]
            dotted = ".".join(parts)
            source = path.read_text(encoding="utf-8", errors="replace")
            self.text_by_path[rel] = source
            index = self._index_module(dotted, rel, source)
            self.modules[dotted] = index
            self.by_path[rel] = dotted

    def _index_module(self, dotted: str, rel: str, source: str) -> ModuleIndex:
        symbols: Dict[str, Tuple[int, int]] = {}
        imports: List[str] = []
        calls: List[CallSite] = []
        parse_error = None
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:  # guarded parse: never raise on a bad module
            return ModuleIndex(dotted, rel, source, {}, [], [], f"{exc.__class__.__name__}: {exc.msg}")
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                end = getattr(node, "end_lineno", None) or node.lineno
                symbols[node.name] = (node.lineno, end)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if base:
                    imports.append(base)
                    imports.extend(f"{base}.{alias.name}" for alias in node.names)
            elif isinstance(node, ast.Call):
                calls.append(
                    CallSite(
                        name=_dotted(node.func).rsplit(".", 1)[-1],
                        receiver=_dotted(node.func).rsplit(".", 1)[0] if "." in _dotted(node.func) else "",
                        args=_literal_args(node),
                        line=getattr(node, "lineno", 0),
                    )
                )
        return ModuleIndex(dotted, rel, source, symbols, sorted(set(imports)), calls, parse_error)

    # -- queries -----------------------------------------------------------
    def path_of(self, dotted: str) -> Optional[str]:
        module = self.modules.get(dotted)
        return module.path if module else None

    def module_of_path(self, rel_path: str) -> Optional[str]:
        return self.by_path.get(rel_path)

    def closure(self, roots: Iterable[str]) -> Dict[str, int]:
        """Breadth-first forward import closure with shortest depths."""
        depths: Dict[str, int] = {}
        queue: List[Tuple[str, int]] = []
        for root in sorted(set(roots)):
            if root in self.modules and root not in depths:
                depths[root] = 0
                queue.append((root, 0))
        while queue:
            node, depth = queue.pop(0)
            for imported in self.modules[node].imports:
                if imported in self.modules and imported not in depths:
                    depths[imported] = depth + 1
                    queue.append((imported, depth + 1))
        return depths

    def names_referenced(self, rel_path: str) -> Set[str]:
        """Every identifier and attribute name the file mentions."""
        cached = self._reference_cache.get(rel_path)
        if cached is not None:
            return cached
        text = self.text_by_path.get(rel_path)
        names: Set[str] = set()
        if text is None:
            path = self.root / rel_path
            if path.exists():
                text = path.read_text(encoding="utf-8", errors="replace")
        if text is not None:
            try:
                for node in ast.walk(ast.parse(text)):
                    if isinstance(node, ast.Name):
                        names.add(node.id)
                    elif isinstance(node, ast.Attribute):
                        names.add(node.attr)
                    elif isinstance(node, ast.keyword) and node.arg:
                        names.add(node.arg)
                    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        # A definition binds its name, so a citation to a test
                        # function or to a method must resolve.
                        names.add(node.name)
            except SyntaxError:
                names = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text))
        self._reference_cache[rel_path] = names
        return names

    def references(self, rel_path: str, name: str) -> bool:
        return name in self.names_referenced(rel_path)

    def symbol_location(self, rel_path: str, symbol: str) -> Optional[Tuple[int, int]]:
        dotted = self.module_of_path(rel_path)
        if dotted is None:
            text = self.text_by_path.get(rel_path)
            if text is None:
                path = self.root / rel_path
                if not path.exists():
                    return None
                text = path.read_text(encoding="utf-8", errors="replace")
            index = self._index_module(dotted or rel_path, rel_path, text)
            return index.symbols.get(symbol)
        return self.modules[dotted].symbols.get(symbol)

    def docs_files(self) -> List[str]:
        return [rel for rel in self.text_by_path if rel.endswith((".md", ".rst", ".txt"))]
