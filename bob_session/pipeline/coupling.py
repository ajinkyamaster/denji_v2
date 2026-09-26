"""Representation coupling: modules bound by a shared wire format.

This is the detector that finds the counterexample the architecture is built
around: ``cache_service.write_cache_entry`` (producer) and
``report_worker.parse_recent_cache_entries`` (consumer) share the "|" format
and have no import edge in either direction.

The rule is deliberately narrow and checkable:

  a coupling is CONSEQUENTIAL iff the producer's change removed a format tag
  the consumer consumes, and the producer's new form does not already carry
  the tag the consumer consumes.  So "producer writes JSON, consumer parses
  JSON" is not a coupling at all, while "producer stopped writing pipes,
  consumer parses pipes" is.

Coverage is never used here: this is a text/AST-level argument, and it is
sound because it is a proof of *non-modification of the consumer*, not an
inference from non-coverage.
"""
from __future__ import annotations

import dataclasses
import io
import re
import tokenize
from typing import Dict, Iterable, List, Sequence, Set, Tuple

from bob_session.pipeline.index import ModuleIndex, RepoIndex
from bob_session.pipeline.diffparse import SymbolChange

SEPARATOR_RE = re.compile(r"^(?:[|,;:\t]|->|=>|::|/)$")
JSON_DUMP_RE = re.compile(r"\bjson\.dumps\b")
JSON_LOAD_RE = re.compile(r"\bjson\.loads\b")
STRING_LITERAL_RE = re.compile(r"'([^'\n]*)'|\"([^\"\n]*)\"")
CONSUMER_CALLS = ("split", "rsplit", "partition", "rpartition", "join")
JSON_TAG = "fmt:json"


_FSTRING_MIDDLE = {
    getattr(tokenize, name) for name in ("FSTRING_MIDDLE",) if hasattr(tokenize, name)
}


def literal_pieces(line: str) -> List[str]:
    """Every literal piece of a source line, f-string middle parts included.

    Tokenising rather than regexing is what makes the "|" of
    ``f"{a}|{b}"`` visible: in a 3.12 token stream it arrives as an
    FSTRING_MIDDLE token, not as part of a quoted string.
    """
    pieces: List[str] = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(line).readline):
            if token.type == tokenize.STRING:
                text = token.string
                for prefix in ('r"', "r'", '"', "'"):
                    if text.startswith(prefix):
                        text = text[len(prefix) :]
                        break
                if text.endswith(("\"", "'")):
                    text = text[:-1]
                pieces.append(text)
            elif token.type in _FSTRING_MIDDLE:
                pieces.append(token.string)
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        pieces.extend(literal for single, double in STRING_LITERAL_RE.findall(line) for literal in (single or double,))
    return pieces


def text_tags(lines: Iterable[str]) -> Set[str]:
    """Format tags a block of source text produces or consumes."""
    tags: Set[str] = set()
    for line in lines:
        if JSON_DUMP_RE.search(line) or JSON_LOAD_RE.search(line):
            tags.add(JSON_TAG)
        for literal in literal_pieces(line):
            if SEPARATOR_RE.match(literal):
                tags.add(f"sep:{literal}")
    return tags


def module_tags(index: ModuleIndex) -> Dict[str, List[int]]:
    """Format tag -> lines where this module consumes that format."""
    found: Dict[str, List[int]] = {}
    for call in index.calls:
        if call.name in CONSUMER_CALLS:
            for arg in call.args:
                if SEPARATOR_RE.match(arg):
                    found.setdefault(f"sep:{arg}", []).append(call.line)
        if call.name == "loads" and call.receiver.endswith("json"):
            found.setdefault(JSON_TAG, []).append(call.line)
    return found


@dataclasses.dataclass(frozen=True)
class CouplingLink:
    """A verified-by-construction shared format between two modules."""

    producer_module: str
    producer_symbol: str
    producer_path: str
    producer_line: int
    removed_tags: List[str]
    added_tags: List[str]
    consumer_module: str
    consumer_path: str
    consumer_line: int
    shared_tag: str

    def evidence(self) -> str:
        return (
            f"{self.producer_module}.{self.producer_symbol} stopped producing {self.shared_tag} text "
            f"({self.producer_path}:{self.producer_line}); "
            f"{self.consumer_module} consumes it at {self.consumer_path}:{self.consumer_line}"
        )


def detect(
    changes: Sequence[SymbolChange],
    index: RepoIndex,
    closure: Dict[str, int],
) -> List[CouplingLink]:
    """Find consequential representation couplings for the changed symbols."""
    links: List[CouplingLink] = []
    for change in changes:
        if not change.semantic:
            continue
        removed_tags = text_tags(text for text, _ in change.removed)
        if not removed_tags:
            continue
        added_tags = text_tags(text for text, _ in change.added)
        for module in index.modules.values():
            if module.dotted == change.module or module.dotted in closure:
                continue
            consumed = module_tags(module)
            shared = sorted(set(consumed) & removed_tags)
            if not shared:
                continue
            if set(consumed) & added_tags:
                # The consumer already accepts the new form: no consequential change.
                continue
            tag = shared[0]
            line = min(consumed[tag])
            links.append(
                CouplingLink(
                    producer_module=change.module,
                    producer_symbol=change.symbol,
                    producer_path=change.path,
                    producer_line=change.line,
                    removed_tags=sorted(removed_tags),
                    added_tags=sorted(added_tags),
                    consumer_module=module.dotted,
                    consumer_path=module.path,
                    consumer_line=line,
                    shared_tag=tag,
                )
            )
    return sorted(links, key=lambda link: (link.consumer_module, link.producer_symbol, link.consumer_line))
