"""Representation coupling: the class of dependency the import graph cannot see.

A *representation coupling* is two modules bound by a shared wire format with no
import edge between them. It is the counterexample the whole product rests on:
``cache_service`` writes ``key|status|count``, ``report_worker`` parses
``entry.split("|")``, and neither imports the other. A coverage-based or
import-based selector cannot see the link, so it deselects the consumer's tests
— and the change breaks them.

The detector is deliberately narrow, because a detector that fires on everything
is the same as no detector:

  * the separator literal must appear on the *changed* side of the diff (added or
    removed), so only formats this change touches are considered;
  * the consumer must actually parse with that literal (``split``/``partition``/
    ``replace``);
  * there must be **no import path in either direction** — when an import edge
    exists the link is already visible to static analysis, and reporting it as
    "hidden" would be a lie.
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Coupling:
    """A producer/consumer pair bound by a shared representation."""

    producer_module: str
    producer_symbol: str
    producer_path: str
    producer_line: int
    consumer_module: str
    consumer_symbol: str
    consumer_path: str
    consumer_line: int
    separator: str
    serializer: str = None
    evidence: list = field(default_factory=list)

    @property
    def digest(self):
        return (
            f"{self.producer_module}.{self.producer_symbol} <-> "
            f"{self.consumer_module}.{self.consumer_symbol} via {self.separator!r}"
        )


def _symbol_at(symbols, line):
    """The innermost symbol whose body contains ``line``, else the nearest above.

    ``symbols`` must be the table for the same line space as ``line``: the
    post-change table for added lines and the reconstructed pre-change table for
    removed lines. Mixing the two spaces is how evidence ends up attributed to
    the wrong function.
    """
    if not symbols or line is None:
        return None
    containing = None
    for symbol in symbols:
        if symbol.line <= line <= symbol.end_line:
            containing = symbol
            break
    if containing is not None:
        return containing
    nearest = None
    for symbol in symbols:
        if symbol.line <= line:
            nearest = symbol
    return nearest


def _consumer_parse_sites(module):
    """``(separator, line)`` pairs for parse calls in one module."""
    import ast

    sites = []
    try:
        tree = ast.parse(module.source)
    except SyntaxError:  # pragma: no cover - the index already refused these
        return sites
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        method = function.attr if isinstance(function, ast.Attribute) else None
        if method not in ("split", "rsplit", "partition", "rpartition", "replace"):
            continue
        for argument in node.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str) and argument.value:
                sites.append((argument.value, node.lineno))
                break
    return sites


def _has_import_edge(index, left, right):
    if left == right:
        return True
    return right in index.forward_closure(left) or left in index.forward_closure(right)


def detect_couplings(index, diff):
    """Find representation couplings introduced or touched by the change.

    Returns couplings sorted by ``(consumer_module, consumer_line, separator)``
    so the artefact is a pure function of the inputs.
    """
    from .diff_parser import previous_source, representations
    from .repo_index import symbols_from_source

    producers = {}
    for parsed in diff.active_files:
        module_name = _module_name(parsed.path)
        module = index.module_named(module_name)
        post_symbols = list(module.symbols) if module is not None else []
        pre_symbols = []
        if module is not None:
            rebuilt = previous_source(parsed, module.source)
            if rebuilt:
                pre_symbols = symbols_from_source(rebuilt, module_name)
        changes = [(number, text, "added", post_symbols) for number, text in parsed.added]
        changes += [(number, text, "removed", pre_symbols) for number, text in parsed.removed]
        for line_number, text, side, symbols in changes:
            separators, serializers = representations(text)
            for separator in separators:
                if not separator.strip():
                    continue
                symbol = _symbol_at(symbols, line_number)
                producers.setdefault(
                    separator,
                    {
                        "module": module_name,
                        "path": parsed.path,
                        "line": line_number,
                        "side": side,
                        "symbol": symbol.name if symbol else "",
                        "text": text.strip(),
                        "serializer": sorted(serializers)[0] if serializers else None,
                    },
                )

    couplings = []
    for separator, producer in sorted(producers.items()):
        for module in index.modules.values():
            if module.is_test or module.name == producer["module"]:
                continue
            if _has_import_edge(index, producer["module"], module.name):
                continue
            for consumed, line in _consumer_parse_sites(module):
                if consumed != separator:
                    continue
                symbol = _symbol_at(list(module.symbols), line)
                couplings.append(
                    Coupling(
                        producer_module=producer["module"],
                        producer_symbol=producer["symbol"],
                        producer_path=producer["path"],
                        producer_line=producer["line"],
                        consumer_module=module.name,
                        consumer_symbol=symbol.name if symbol else "",
                        consumer_path=module.path,
                        consumer_line=line,
                        separator=separator,
                        serializer=producer["serializer"],
                        evidence=[
                            f"{producer['path']}: {producer['side']} line {producer['line']} produces "
                            f"{separator!r} (in {producer['symbol'] or 'module scope'})",
                            f"{module.path}:{line} consumes {separator!r}",
                            f"no import edge between {producer['module']} and {module.name}",
                        ],
                    )
                )
    couplings.sort(key=lambda item: (item.consumer_module, item.consumer_line, item.separator))
    return couplings


def _module_name(path):
    text = Path(path).as_posix()
    return text[:-3].replace("/", ".") if text.endswith(".py") else text
