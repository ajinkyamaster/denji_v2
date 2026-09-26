"""Unified-diff parsing, and the removed-behaviour set rho(D).

The parser is deliberately strict: a malformed hunk header names the line and
raises, because deciding on a partially parsed diff means deciding on partial
data.

Two normalisations do the analytical work:

``skeleton(line)``
    A structural fingerprint of one source line with **string and comment
    content blanked**. ``logger.info("settled account %s", a)`` and
    ``logger.info("settlement complete for %s", a)`` have the same skeleton: the
    change is a reword.

``representations(lines)``
    The *wire format* a line produces or consumes: separator literals inside
    ``join``/``split``/``partition``/``replace`` and f-strings, plus the
    serializer calls it makes. ``f"{key}|{status}"`` contributes the separator
    ``|``; ``json.dumps(...)`` contributes a serializer.

Inertness (the second soundness lever, A3) is then a conjunction, and each part
catches a different way a change can matter:

    sorted(removed_skeletons) == sorted(added_skeletons)   structure preserved
    removed_representations == added_representations       wire format preserved
    removed_symbols == added_symbols                       API preserved
    every changed line is a log call, comment or blank     content in an
                                                           unobservable positionWithout the last clause a change from ``status = "ok"`` to ``status = "done"``
would be declared inert, which it is not. Without the second, ``"|"`` -> ``":"``
would be declared inert, which it is not either. Both defects are pinned by tests.

A path the diff names may be hostile (``../../etc/passwd``, an absolute path, a
backslash separator, NUL). Such an entry is **declared and excluded**, never read:
it keeps its place in the parsed diff and in the reason map, and is dropped from
every computation that could attribute behaviour to it.
"""

import ast
import re
from dataclasses import dataclass, field

from .errors import DiffError
from .paths import is_confined_relative

HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
LOG_CALL = re.compile(r"^(?:logger|logging)\.[a-z_]+\(|^print\(", re.IGNORECASE)
DEFINITION = re.compile(r"^\s*(?:async\s+)?(def|class)\s+([A-Za-z_]\w*)")
SERIALIZER_NAMES = {
    "json.dumps",
    "json.loads",
    "json.dump",
    "json.load",
    "ast.literal_eval",
    "pickle.dumps",
    "pickle.loads",
    "yaml.dump",
    "yaml.load",
    "csv.reader",
    "csv.writer",
}
SEPARATOR_METHODS = {"split", "rsplit", "partition", "rpartition", "join", "replace"}
QUOTED = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")
DOTTED_CALL = re.compile(r"\b([a-z_][\w]*(?:\.[a-z_][\w]*)+)\(")


def routine_name(node):
    """Dotted name of the callable in a Call node, or '' when it has none.

    Terminates by construction: the only recursive step moves strictly inward
    (``f(...)`` -> the ``f`` node), so a chain such as ``foo()()`` cannot loop.
    """
    if isinstance(node, ast.Call):
        return routine_name(node.func)
    parts = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    if isinstance(current, ast.Subscript):  # ``'|'.join`` reached through an index
        return routine_name(current.value)
    return ""


class _BlankStrings(ast.NodeTransformer):
    """Replace every string literal with the empty string."""

    def visit_Constant(self, node):  # noqa: N802 - ast API
        if isinstance(node.value, str):
            node.value = ""
        return node


def _blank_strings(tree):
    return _BlankStrings().visit(tree)


def _raw_skeleton(line):
    """Fallback fingerprint for fragments that are not standalone statements."""
    without_strings = QUOTED.sub('""', line.strip())
    return re.sub(r"\s+", " ", without_strings)


def skeleton(line):
    """Structural fingerprint of one source line with string content blanked."""
    source = line.strip()
    if not source:
        return ""
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError:
        return _raw_skeleton(line)
    tree = _blank_strings(tree)
    return ast.dump(tree, annotate_fields=False, include_attributes=False)


def representations(line):
    """Return ``(separators, serializers)`` for one source line.

    ``separators`` are the literal separators the line produces or consumes;
    ``serializers`` are the serializer calls it makes.
    """
    source = line.strip()
    separators = set()
    serializers = set()
    if not source:
        return separators, serializers
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError:
        for name in DOTTED_CALL.findall(source):
            if name in SERIALIZER_NAMES:
                serializers.add(name)
        for match in re.finditer(r"\.(?:split|rsplit|partition|rpartition|replace)\(\s*(['\"])(.*?)\1", source):
            separators.add(match.group(2))
        for match in re.finditer(r"(['\"])\s*\.join\(", source):
            pass
        return separators, serializers
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            for part in node.values:
                if isinstance(part, ast.Constant) and isinstance(part.value, str) and part.value:
                    separators.add(part.value)
        elif isinstance(node, ast.Call):
            name = routine_name(node)
            if name in SERIALIZER_NAMES:
                serializers.add(name)
            method = name.rsplit(".", 1)[-1]
            if method in SEPARATOR_METHODS:
                for argument in node.args:
                    if isinstance(argument, ast.Constant) and isinstance(argument.value, str) and argument.value:
                        separators.add(argument.value)
                    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                        break
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            pass
    return separators, serializers


def representation_descriptors(lines):
    """Human-readable descriptors of what a set of lines produces or consumes."""
    separators = set()
    serializers = set()
    for line in lines:
        line_separators, line_serializers = representations(line)
        separators |= line_separators
        serializers |= line_serializers
    descriptors = [f'separator "{separator}"' for separator in sorted(separators)]
    descriptors += [f"serializer {name}(...)" for name in sorted(serializers)]
    return descriptors


def is_log_or_doc_line(line):
    """True when a line carries string content in a position nobody can observe."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return True
    return bool(LOG_CALL.match(stripped))


@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    header: str
    body: list = field(default_factory=list)  # (marker, old_line, new_line, text)


@dataclass
class ParsedFile:
    """One file's change: lines on both sides, symbols, representations, inertness."""

    path: str
    old_path: str = None
    status: str = "modified"
    is_python: bool = False
    is_binary: bool = False
    confined: bool = True
    unsupported: str = None
    hunks: list = field(default_factory=list)
    added: list = field(default_factory=list)       # (new_line_number, text)
    removed: list = field(default_factory=list)     # (old_line_number, text)
    added_skeletons: list = field(default_factory=list)
    removed_skeletons: list = field(default_factory=list)
    removed_separators: list = field(default_factory=list)
    added_separators: list = field(default_factory=list)
    removed_serializers: list = field(default_factory=list)
    added_serializers: list = field(default_factory=list)
    added_symbols: list = field(default_factory=list)
    removed_symbols: list = field(default_factory=list)
    inert: bool = False
    inert_reason: str = ""

    @property
    def added_lines(self):
        return [text for _, text in self.added]

    @property
    def removed_lines(self):
        return [text for _, text in self.removed]

    @property
    def changed_new_lines(self):
        return [number for number, _ in self.added]

    @property
    def changed_old_lines(self):
        return [number for number, _ in self.removed]

    @property
    def removed_representations(self):
        return representation_descriptors(self.removed_lines)

    @property
    def added_representations(self):
        return representation_descriptors(self.added_lines)

    def decide_inertness(self):
        """Apply the inertness rule and record the reason."""
        if not self.confined:
            # Declared, never ignored: the entry stays in the artefact with this
            # reason, and is excluded from every computation that could attribute
            # behaviour to it. Reading it is what the confinement rule forbids.
            self.inert = True
            self.inert_reason = "path_escapes_repository"
            return
        if self.status in ("renamed",):
            self.inert = False
            self.inert_reason = "renamed_path"
            return
        if self.is_binary:
            self.inert = True
            self.inert_reason = "binary_or_undecodable_payload"
            return
        if not self.is_python:
            self.inert = True
            self.inert_reason = "non_python_documentation"
            return
        if not self.added and not self.removed:
            self.inert = True
            self.inert_reason = "no_content_change"
            return
        if sorted(self.removed_skeletons) != sorted(self.added_skeletons):
            self.inert = False
            self.inert_reason = "structure_changed"
            return
        if self.removed_representations != self.added_representations:
            self.inert = False
            self.inert_reason = "representation_changed"
            return
        if self.removed_symbols != self.added_symbols:
            self.inert = False
            self.inert_reason = "symbol_changed"
            return
        changed = [(text, "removed") for _, text in self.removed]
        for _, text in self.added:
            others = [candidate for candidate, _ in self.removed]
            if text not in others:
                changed.append((text, "added"))
        if all(is_log_or_doc_line(text) for text, _ in changed):
            self.inert = True
            self.inert_reason = "string_content_in_unobservable_position"
            return
        self.inert = False
        self.inert_reason = "string_content_in_observable_position"


@dataclass
class Diff:
    """A parsed change: its files plus the removed-behaviour set rho(D)."""

    files: list = field(default_factory=list)
    source: str = ""

    @property
    def paths(self):
        return [parsed.path for parsed in self.files]

    @property
    def python_files(self):
        return [parsed for parsed in self.files if parsed.is_python]

    @property
    def active_files(self):
        """Python files whose change is semantics-modifying (not inert)."""
        return [parsed for parsed in self.python_files if parsed.confined and not parsed.inert]

    @property
    def changed_modules(self):
        """Dotted module names of the actively changed Python files."""
        return sorted({_module_name(parsed.path) for parsed in self.active_files})

    @property
    def inert_modules(self):
        return sorted(
            {
                _module_name(parsed.path)
                for parsed in self.python_files
                if parsed.inert and parsed.confined and parsed.status != "deleted"
            }
        )

    @property
    def is_empty(self):
        return not self.files

    def rho(self):
        """rho(D): the behaviour the change removed.

        ``removed_skeletons``        multiset of skeleton-normalised removed expressions
        ``removed_representations``  serialisation calls the change stopped making
        ``removed_symbols``          functions or classes deleted (not renamed)
        ``removed_modules``          changed modules whose test target no longer exists
        """
        removed_skeletons = []
        added_skeletons = []
        representations_removed = []
        representations_added = []
        symbols_removed = []
        symbols_added = []
        for parsed in self.files:
            if not parsed.confined:
                continue
            removed_skeletons.extend(parsed.removed_skeletons)
            added_skeletons.extend(parsed.added_skeletons)
            representations_removed.extend(parsed.removed_representations)
            representations_added.extend(parsed.added_representations)
            symbols_removed.extend(parsed.removed_symbols)
            symbols_added.extend(parsed.added_symbols)
        renamed = set(symbols_removed) & set(symbols_added)
        return {
            "removed_skeletons": sorted(removed_skeletons),
            "added_skeletons": sorted(added_skeletons),
            "removed_representations": sorted(set(representations_removed)),
            "added_representations": sorted(set(representations_added)),
            "removed_symbols": sorted(set(symbols_removed) - renamed),
            "removed_modules": sorted(
                {_module_name(parsed.path) for parsed in self.files if parsed.status == "deleted" and parsed.confined}
            ),
            "semantics_modifying": sorted({_module_name(parsed.path) for parsed in self.active_files}),
            "inert_modules": sorted(self.inert_modules),
        }


def _module_name(path):
    if path.endswith(".py"):
        return path[:-3].replace("/", ".")
    return path


def _unescape_git_path(value):
    """Decode git's C-style quoting of a path in a diff header.

    Git emits a bare path when it is plain and a double-quoted, C-escaped one
    otherwise (whitespace, control characters, and - under the default
    ``core.quotePath`` - non-ASCII bytes, which arrive as octal escapes). The
    decode is byte-exact per git's own escaping rules; an escape that does not
    decode is returned unmodified rather than guessed at, and the confinement
    check downstream then refuses the entry instead of inventing a filename.
    """
    escapes = {"a": 7, "b": 8, "f": 12, "n": 10, "r": 13, "t": 9, "v": 11, "\\": 92, '"': 34}
    out = bytearray()
    index = 0
    while index < len(value):
        char = value[index]
        if char != "\\" or index + 1 >= len(value):
            out.extend(char.encode("utf-8"))
            index += 1
            continue
        nxt = value[index + 1]
        if nxt in escapes:
            out.append(escapes[nxt])
            index += 2
        elif nxt.isdigit():
            out.append(int(value[index + 1 : index + 4], 8) & 0xFF)
            index += 4
        else:
            out.extend(nxt.encode("utf-8"))
            index += 2
    try:
        return out.decode("utf-8")
    except UnicodeDecodeError:
        return value


def paths_from_git_header(line):
    """Best-effort ``(old_path, new_path)`` from a ``diff --git`` header.

    A *fallback only*: a ``---``/``+++`` pair overrides it. It exists for entries
    that carry no file header at all, which is exactly what a binary change looks
    like (``Binary files ... differ`` with no ``---``/``+++``), and it is what lets
    such an entry be *declared and confined* rather than raising. Git quotes any
    path it cannot emit bare, so the two forms are unambiguous in practice; a
    header that does not split cleanly yields nothing and the entry keeps
    requiring a file header, which is the previous behaviour.
    """
    rest = line[len("diff --git ") :].strip()
    if rest.startswith('"'):
        parts = [
            _strip_prefix(_unescape_git_path(part)) for part in re.findall(r'"((?:[^"\\]|\\.)*)"', rest)
        ]
    else:
        parts = [_strip_prefix(part) for part in rest.split()]
    if len(parts) == 2:
        return parts[0], parts[1]
    if len(parts) == 1:
        return parts[0], parts[0]
    return None, None


def _annotate(parsed):
    """Fill in skeletons, representations and symbol names for one parsed file."""
    parsed.added_skeletons = [skeleton(text) for _, text in parsed.added]
    parsed.removed_skeletons = [skeleton(text) for _, text in parsed.removed]
    for text in parsed.removed_lines:
        separators, serializers = representations(text)
        parsed.removed_separators.extend(sorted(separators))
        parsed.removed_serializers.extend(sorted(serializers))
    for text in parsed.added_lines:
        separators, serializers = representations(text)
        parsed.added_separators.extend(sorted(separators))
        parsed.added_serializers.extend(sorted(serializers))
    parsed.removed_separators = sorted(set(parsed.removed_separators))
    parsed.added_separators = sorted(set(parsed.added_separators))
    parsed.removed_serializers = sorted(set(parsed.removed_serializers))
    parsed.added_serializers = sorted(set(parsed.added_serializers))
    for _, text in parsed.removed:
        match = DEFINITION.match(text)
        if match:
            parsed.removed_symbols.append(match.group(2))
    for _, text in parsed.added:
        match = DEFINITION.match(text)
        if match:
            parsed.added_symbols.append(match.group(2))
    parsed.removed_symbols = sorted(set(parsed.removed_symbols))
    parsed.added_symbols = sorted(set(parsed.added_symbols))


def parse_diff(text, *, source="<text>"):
    """Parse a unified diff into a :class:`Diff`.

    Raises :class:`DiffError` naming the offending line for anything malformed,
    rather than returning a partially parsed change.
    """
    files = []
    current = None
    in_hunk = False
    old_line = new_line = 0
    for number, raw in enumerate(text.splitlines(), start=1):
        if raw.startswith("diff --git "):
            header_old, header_new = paths_from_git_header(raw)
            current = ParsedFile(path=header_new or "", old_path=header_old)
            files.append(current)
            in_hunk = False
            continue
        if raw.startswith("@@"):
            if current is None:
                raise DiffError(f"{source}: line {number}: hunk before any file header")
            match = HUNK_HEADER.match(raw)
            if not match:
                raise DiffError(f"{source}: line {number}: malformed hunk header: {raw!r}")
            old_line = int(match.group(1))
            new_line = int(match.group(3))
            current.hunks.append(
                Hunk(
                    old_start=old_line,
                    old_count=int(match.group(2) or 1),
                    new_start=new_line,
                    new_count=int(match.group(4) or 1),
                    header=raw,
                )
            )
            in_hunk = True
            continue
        if in_hunk and current is not None:
            marker, body = (raw[:1], raw[1:]) if raw[:1] in ("+", "-", " ", "\\") else (" ", raw)
            if marker == "+":
                current.added.append((new_line, body))
                if current.hunks:
                    current.hunks[-1].body.append(("+", None, new_line, body))
                new_line += 1
            elif marker == "-":
                current.removed.append((old_line, body))
                if current.hunks:
                    current.hunks[-1].body.append(("-", old_line, None, body))
                old_line += 1
            elif marker == " ":
                if current.hunks:
                    current.hunks[-1].body.append((" ", old_line, new_line, body))
                old_line += 1
                new_line += 1
            else:
                pass  # "\ No newline at end of file"
            continue
        if raw.startswith("--- "):
            if current is None:
                raise DiffError(f"{source}: line {number}: file header before 'diff --git'")
            current.old_path = _strip_prefix(raw[4:])
            continue
        if raw.startswith("+++ "):
            if current is None:
                raise DiffError(f"{source}: line {number}: file header before 'diff --git'")
            current.path = _strip_prefix(raw[4:])
            continue
        if raw.startswith("rename from "):
            if current is not None:
                current.status = "renamed"
                current.old_path = raw[len("rename from ") :].strip()
            continue
        if raw.startswith("rename to "):
            if current is not None:
                current.status = "renamed"
                current.path = raw[len("rename to ") :].strip()
            continue
        if raw.startswith("new file mode"):
            if current is not None:
                current.status = "added"
            continue
        if raw.startswith("deleted file mode"):
            if current is not None:
                current.status = "deleted"
            continue
        if raw.startswith("Binary files ") or raw.startswith("GIT binary patch"):
            if current is not None:
                current.is_binary = True
            continue
        if raw.startswith(("index ", "old mode ", "new mode ", "similarity index ", "dissimilarity index ")):
            continue
        if not raw.strip():
            continue
        raise DiffError(f"{source}: line {number}: unexpected diff line: {raw!r}")

    for parsed in files:
        if not parsed.path:
            if parsed.status == "deleted" and parsed.old_path:
                parsed.path = parsed.old_path
            elif parsed.old_path:
                parsed.path = parsed.old_path
            else:
                raise DiffError(f"{source}: file entry has no path")
        if parsed.path == "/dev/null":
            parsed.path = parsed.old_path or ""
            parsed.status = "deleted"
        parsed.is_python = parsed.path.endswith(".py")
        if not is_confined_relative(parsed.path):
            parsed.confined = False
            parsed.unsupported = "path_escapes_repository"
        elif not parsed.is_python:
            parsed.unsupported = "unsupported_file_type"
        _annotate(parsed)
        parsed.decide_inertness()
    return Diff(files=files, source=source)


def previous_source(parsed, new_source):
    """Rebuild the pre-change source of one file from the diff alone.

    Why this exists: a removed line's line number is in the *pre-change* line
    space, so attributing it to a symbol by looking up the post-change symbol
    table attributes evidence to the wrong function - and a citation that points
    at the wrong symbol is exactly what the kernel exists to refuse. Rebuilding
    revision A in memory (no filesystem, no git) is cheap and makes the pre-change
    attribution exact instead of approximate.

    Returns None when the file is newly added (there is no previous revision).
    """
    if parsed.status == "added":
        return None
    new_lines = new_source.splitlines()
    out = []
    cursor = 0  # zero-based index into new_lines
    for hunk in parsed.hunks:
        while cursor < hunk.new_start - 1 and cursor < len(new_lines):
            out.append(new_lines[cursor])
            cursor += 1
        for marker, _, _, text in hunk.body:
            if marker == " ":
                out.append(text)
                cursor += 1
            elif marker == "-":
                out.append(text)
            elif marker == "+":
                cursor += 1
    while cursor < len(new_lines):
        out.append(new_lines[cursor])
        cursor += 1
    return "\n".join(out) + "\n"


def parse_diff_file(path):
    """Parse a diff from disk."""
    with open(path, "r", encoding="utf-8") as handle:
        return parse_diff(handle.read(), source=str(path))


def _strip_prefix(value):
    value = value.strip()
    if value == "/dev/null":
        return "/dev/null"
    if value.startswith(("a/", "b/")):
        return value[2:]
    return value
