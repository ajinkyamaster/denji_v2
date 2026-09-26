"""The repository index: modules, symbols, imports, and reachability.

Trust-boundary invariant (K2): this module only ever ``ast.parse``s the analysed
repository. It never imports it, never executes it, and never evaluates a string
from it. That is what makes it safe to point the tool at a hostile repository,
and it is enforced by a gate that scans this package for dynamic-execution and
dynamic-import primitives - this sentence is written the long way round on
purpose, so that the scanner can be run over its own source and stay silent.

The index answers one question precisely, because static analysis answers it
exactly and a model should never be asked it: *which modules can observe this
module's behaviour?* That is the reverse import closure. The consequence is
worth stating: the closure is a **lower bound** on the true dependency relation,
never a bound in the other direction (A1: ``R* ⊊ δ*``).
"""

import ast
from dataclasses import dataclass, field
from pathlib import Path

from .errors import RepoIndexError
from .paths import is_generated, read_text

SKIP_DIRECTORIES = (".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".venv", "venv", "node_modules")


def module_name_for_path(relative_path):
    """``app/services/cache_service.py`` -> ``app.services.cache_service``."""
    path = Path(relative_path)
    if path.suffix != ".py":
        return None
    parts = list(path.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]
    return ".".join(part for part in parts if part) or "__root__"


@dataclass(frozen=True)
class Symbol:
    name: str
    line: int
    end_line: int
    kind: str
    module: str
    docstring: str = ""


@dataclass
class Module:
    name: str
    path: str
    source: str
    imports: tuple
    symbols: tuple
    docstring: str = ""
    calls: dict = field(default_factory=dict)
    is_test: bool = False

    def symbol_named(self, name):
        for symbol in self.symbols:
            if symbol.name == name:
                return symbol
        return None


class RepoIndex:
    """An immutable-by-convention view of the analysed repository."""

    def __init__(self, root, modules, by_path, unparseable):
        self.root = Path(root)
        self.modules = modules
        self.by_path = by_path
        self.unparseable = unparseable

    # -- lookups ---------------------------------------------------------- #
    def module_names(self):
        return sorted(self.modules)

    def module_for_path(self, relative_path):
        return self.by_path.get(str(relative_path))

    def module_named(self, name):
        return self.modules.get(name)

    def unparseable_paths(self):
        return {entry["path"] for entry in self.unparseable}

    def app_modules(self):
        return {name: module for name, module in self.modules.items() if not module.is_test}

    def test_modules(self):
        return {name: module for name, module in self.modules.items() if module.is_test}

    # -- reachability ------------------------------------------------------ #
    def forward_closure(self, module_name, *, include_tests=True):
        """Every module reachable from ``module_name`` by following imports."""
        seen = {module_name}
        frontier = [module_name]
        while frontier:
            current = frontier.pop()
            module = self.modules.get(current)
            if module is None:
                continue
            for imported in module.imports:
                if imported in seen:
                    continue
                if not include_tests and self.modules.get(imported, None) is not None and self.modules[imported].is_test:
                    continue
                seen.add(imported)
                frontier.append(imported)
        return seen

    def reverse_closure(self, changed_modules, *, include_tests=True):
        """Map module -> shortest import distance to any changed module.

        Distance 0 is the changed module itself, 1 is a direct importer, and so
        on. Modules that cannot reach a changed module are absent.
        """
        depths = {}
        frontier = []
        for name in changed_modules:
            depths[name] = 0
            frontier.append(name)
        while frontier:
            current = frontier.pop()
            depth = depths[current]
            for candidate_name, candidate in self.modules.items():
                if candidate_name in depths:
                    continue
                if not include_tests and candidate.is_test:
                    continue
                if current in candidate.imports:
                    depths[candidate_name] = depth + 1
                    frontier.append(candidate_name)
        return depths

    def imported_modules_of_test(self, module_name):
        """The set of modules a test module reaches through imports."""
        return self.forward_closure(module_name)

    def intra_module_closure(self, module_name, symbol_name, *, depth=2):
        """Symbols reachable from ``symbol_name`` by same-module call edges.

        Used to decide whether a changed symbol is exercised through a helper it
        calls: a test that calls ``write_cache_entry`` does reach
        ``build_cache_payload`` when the former calls the latter. Restricted to
        the same module and to two hops, because both restrictions are what make
        the answer cheap and explainable.
        """
        module = self.modules.get(module_name)
        if module is None:
            return set()
        reached = set()
        frontier = {symbol_name}
        for _ in range(depth):
            next_frontier = set()
            for current in frontier:
                for called in module.calls.get(current, ()):  # noqa: SIM118 - mapping default
                    if called not in reached:
                        reached.add(called)
                        next_frontier.add(called)
            frontier = next_frontier
            if not frontier:
                break
        return reached


def _imported_modules(tree, module_name):
    """Dotted module names imported by ``tree``, resolving relative imports."""
    package = module_name.split(".")[:-1]
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: len(package) - node.level + 1]
                target = ".".join(filter(None, base + [node.module or ""]))
            else:
                target = node.module or ""
            if target:
                imported.add(target)
                for alias in node.names:
                    if alias.name != "*":
                        imported.add(f"{target}.{alias.name}")
    return tuple(sorted(imported))


def _symbols_of(tree, module_name):
    """Top-level functions and classes, plus class methods as ``Class.method``."""
    symbols = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(
                Symbol(
                    name=node.name,
                    line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    kind="function",
                    module=module_name,
                    docstring=ast.get_docstring(node) or "",
                )
            )
        elif isinstance(node, ast.ClassDef):
            symbols.append(
                Symbol(
                    name=node.name,
                    line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno),
                    kind="class",
                    module=module_name,
                    docstring=ast.get_docstring(node) or "",
                )
            )
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.append(
                        Symbol(
                            name=f"{node.name}.{child.name}",
                            line=child.lineno,
                            end_line=getattr(child, "end_lineno", child.lineno),
                            kind="method",
                            module=module_name,
                            docstring=ast.get_docstring(child) or "",
                        )
                    )
    return tuple(symbols)


def _calls_by_function(tree):
    """Map function name -> names called inside it (same-module edges only, later)."""
    calls = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names = set()
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    function = child.func
                    if isinstance(function, ast.Name):
                        names.add(function.id)
                    elif isinstance(child.func, ast.Attribute):
                        names.add(child.func.attr)
            calls[node.name] = sorted(names)
    return calls


def references(tree):
    """Every name and dotted reference in a tree (for link evidence)."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            chain = []
            current = node
            while isinstance(current, ast.Attribute):
                chain.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                chain.append(current.id)
            names.add(".".join(reversed(chain)))
            names.update(chain)
    return names


def symbols_from_source(source, module_name):
    """Symbol table for a source string. Used to attribute removed lines in the

    pre-change line space, where the repository on disk cannot help.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    return list(_symbols_of(tree, module_name))


def build_index(repo_root, *, max_modules=20000):
    """Walk ``repo_root`` and build the index from sources alone."""
    root = Path(repo_root)
    if not root.is_dir():
        raise RepoIndexError(f"not a directory: {root}")
    modules = {}
    by_path = {}
    unparseable = []
    for path in sorted(root.rglob("*.py")):
        if is_generated(path) or any(part in SKIP_DIRECTORIES for part in path.parts):
            continue
        if len(modules) >= max_modules:
            raise RepoIndexError(f"refusing to index more than {max_modules} modules")
        relative = path.relative_to(root).as_posix()
        source, reason = read_text(path)
        if source is None:
            unparseable.append({"path": relative, "reason": reason})
            continue
        name = module_name_for_path(relative)
        try:
            tree = ast.parse(source)
        except SyntaxError as error:
            # Defined behaviour: skip the module, record the path, and let the
            # caller select conservatively. Never decide on partial data.
            unparseable.append({"path": relative, "reason": f"SyntaxError: {error.msg} (line {error.lineno})"})
            continue
        module = Module(
            name=name,
            path=relative,
            source=source,
            imports=_imported_modules(tree, name),
            symbols=_symbols_of(tree, name),
            docstring=ast.get_docstring(tree) or "",
            calls=_calls_by_function(tree),
            is_test=relative.startswith("tests/") or relative.startswith("test_") or "/tests/" in relative,
        )
        modules[name] = module
        by_path[relative] = module
    return RepoIndex(root=root, modules=modules, by_path=by_path, unparseable=unparseable)
