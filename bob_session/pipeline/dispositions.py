"""Dispositions: what the change did to the suite, and what has no test.

The ledger partitions **every** inventory row into exactly one of
``valid`` / ``stale`` / ``newly_relevant`` / ``unknown``. The partition is the
point: a test is never both "stale, delete it" and "newly relevant, run it".

STALE is deliberately hard to earn, and the hard part is where the evidence has
to be:

  S1 ORPHAN          the module the test exercises is not in the repository.
                     Definitionally obsolete, and free.
  S2 ASSERTED REMOVED BEHAVIOUR
                     the *test file itself* contains an expression whose skeleton
                     the change removed, or parses a representation the change
                     stopped producing.

The second clause is the one to argue about, so state the refusal plainly: the
*consumer's* parse site is NOT evidence for STALE, because a test that observes a
broken consumer is catching a **regression**, and calling it stale would tell the
developer to delete the test that caught the bug. In the demo repository the
consumer ``report_worker`` still splits on ``|`` while the producer now writes
JSON; the three tests that observe it are NEWLY_RELEVANT (run it, the red is
real), not STALE (repair the test). Mislabeling them would be the single most
damaging thing this artefact could do.

UNCOVERED is about symbols, not tests, and the two kinds imply different work:
``UNCOVERED_NEW`` is "write a test from nothing", ``UNCOVERED_BY_STALENESS`` is
"the tests that used to assert this are now stale: repair one". They are never
merged.
"""

from dataclasses import dataclass, field

from .diff_parser import representations, skeleton


@dataclass
class Ledger:
    valid: list = field(default_factory=list)
    stale: list = field(default_factory=list)
    newly_relevant: list = field(default_factory=list)
    unknown: list = field(default_factory=list)

    def as_artifact(self):
        return {
            "valid": self.valid,
            "stale": self.stale,
            "newly_relevant": self.newly_relevant,
            "unknown": self.unknown,
        }

    def counts(self):
        return {
            "valid_count": len(self.valid),
            "stale_count": len(self.stale),
            "newly_relevant_count": len(self.newly_relevant),
            "unknown_count": len(self.unknown),
        }

    def total(self):
        return len(self.valid) + len(self.stale) + len(self.newly_relevant) + len(self.unknown)


def _test_file_lines(index, test_module):
    if test_module is None:
        return []
    return [(number, line) for number, line in enumerate(test_module.source.splitlines(), start=1)]


def _stale_by_assertion(index, test_module, rho):
    """Evidence that the test file itself asserts removed behaviour."""
    evidence = []
    removed_skeletons = set(rho.get("removed_skeletons", ()))
    removed_separators = set()
    removed_serializers = set()
    for descriptor in rho.get("removed_representations", ()):
        if descriptor.startswith("separator "):
            removed_separators.add(descriptor[len("separator ") :].strip('"'))
        elif descriptor.startswith("serializer "):
            removed_serializers.add(descriptor[len("serializer ") :].split("(")[0])
    for number, line in _test_file_lines(index, test_module):
        if line.strip() in ("", "import pytest"):
            continue
        if skeleton(line) in removed_skeletons and line.strip():
            evidence.append((number, line.strip(), "removed_expression"))
            continue
        separators, serializers = representations(line)
        if separators & removed_separators:
            evidence.append((number, line.strip(), "removed_representation"))
        elif serializers & removed_serializers:
            evidence.append((number, line.strip(), "removed_serializer"))
    return evidence


def build_ledger(index, inventory, diff, classification, couplings, *, oracle=None):
    """Compute the disposition ledger. Pure function of its inputs."""
    rho = diff.rho()
    ledger = Ledger()
    coupling_by_consumer = {}
    for coupling in couplings:
        coupling_by_consumer.setdefault(coupling.consumer_module, []).append(coupling)
    oracle_failures = set()
    if oracle and oracle.get("complete"):
        for node, outcome in sorted((oracle.get("outcome") or {}).items()):
            if outcome.get("b") not in (None, "passed"):
                oracle_failures.add(node)

    for row in inventory:
        verdict = classification.verdicts.get(row.test_id)
        if verdict is None:  # pragma: no cover - classification covers every row
            continue
        test_module = index.module_named(verdict.test_module) if verdict.test_module else None
        effective_module = verdict.module

        if effective_module and index.module_named(effective_module) is None and verdict.derived_module is None:
            ledger.stale.append(
                {
                    "test_id": row.test_id,
                    "why": (
                        f"orphan: the inventory points at module {effective_module!r}, which does not exist in "
                        "the repository. A test for a deleted module is definitionally obsolete."
                    ),
                    "removed_behaviour": f"module {effective_module} no longer exists",
                    "evidence": [f"inventory:{row.test_id} declares module {effective_module}",
                                 f"{effective_module.replace('.', '/')}.py is absent from the index"],
                }
            )
            continue

        if test_module is not None and verdict.bucket in ("definitely_affected", "semantically_affected"):
            evidence = _stale_by_assertion(index, test_module, rho)
            if evidence:
                ledger.stale.append(
                    {
                        "test_id": row.test_id,
                        "why": (
                            "this test file asserts behaviour the change removed; its assertion encodes a "
                            "contract that was deliberately redefined, so its red is noise: repair or delete "
                            "the test rather than reverting the code."
                        ),
                        "removed_behaviour": "; ".join(rho.get("removed_representations", ())[:4]) or "removed expression",
                        "evidence": [f"{test_module.path}:{number} {text[:90]}" for number, text, _ in evidence[:5]],
                    }
                )
                continue

        if verdict.bucket == "semantically_affected":
            consumer = coupling_by_consumer.get(effective_module, [])
            link_evidence = []
            for coupling in consumer:
                link_evidence.extend(coupling.evidence)
            if not link_evidence:
                link_evidence = [f"kernel-verified model claim for {row.test_id}"]
            ledger.newly_relevant.append(
                {
                    "test_id": row.test_id,
                    "why": (
                        "hidden behavioural coupling: this test observes a module that consumes a format the "
                        "changed module produces, and there is no import path between them. Nobody would have "
                        "run it; its green was false assurance."
                    ),
                    "link_evidence": sorted(dict.fromkeys(link_evidence))[:6],
                }
            )
            continue

        if verdict.reason == "unparseable_module" or verdict.reason == "test_not_found_in_repository":
            ledger.unknown.append(
                {
                    "test_id": row.test_id,
                    "why": (
                        f"cannot be decided from the available evidence ({verdict.reason}); when in doubt the "
                        "safe direction is to run the test, never to exclude it."
                    ),
                }
            )
            continue

        ledger.valid.append(
            {
                "test_id": row.test_id,
                "why": (
                    "the change preserves this test's contracts; run it, a green here means something"
                    if verdict.bucket != "not_affected"
                    else "no link to the change: the test's contracts are untouched"
                ),
            }
        )
    return ledger


def _private(name):
    tail = name.split(".")[-1]
    return tail.startswith("_")


def build_uncovered(index, inventory, diff, classification, *, max_changed_lines=200):
    """Find changed or added symbols with no linking test.

    Restriction (recorded, never silent): only symbols in a module that carries
    inventory rows, or that a test module reaches, are considered. Without it
    every private helper in the repository would be reported and the signal would
    drown. Excluded counts are returned so the restriction is visible.
    """
    in_scope = set()
    for row in inventory:
        verdict = classification.verdicts.get(row.test_id)
        if verdict and verdict.module:
            in_scope.add(verdict.module)
    for module in index.test_modules().values():
        for imported in index.forward_closure(module.name):
            candidate = index.module_named(imported)
            if candidate is not None and not candidate.is_test:
                in_scope.add(candidate.name)

    referenced_by_tests = {}
    for module in index.test_modules().values():
        from .repo_index import references

        import ast

        try:
            tree = ast.parse(module.source)
        except SyntaxError:  # pragma: no cover
            continue
        for name in references(tree):
            referenced_by_tests.setdefault(name, set()).add(module.name)

    items = []
    counters = {"uncovered_symbols_excluded": 0, "private_symbols_excluded": 0, "changed_symbols_considered": 0}
    for parsed in diff.active_files:
        module_name = _module_name(parsed.path)
        module = index.module_named(module_name)
        if module is None:
            counters["uncovered_symbols_excluded"] += 0
            continue
        changed_new = set(parsed.changed_new_lines)
        changed_old = set(parsed.changed_old_lines)
        added_names = set(parsed.added_symbols)
        for symbol in module.symbols:
            body_changed = [number for number in sorted(changed_new) if symbol.line <= number <= symbol.end_line]
            touched = bool(body_changed) or symbol.line in changed_old or symbol.name in added_names
            if not touched:
                continue
            if module_name not in in_scope:
                counters["uncovered_symbols_excluded"] += 1
                continue
            if _private(symbol.name):
                counters["private_symbols_excluded"] += 1
                continue
            counters["changed_symbols_considered"] += 1
            short = symbol.name.split(".")[-1]
            linked = short in referenced_by_tests
            if not linked:
                # A symbol a tested caller reaches is exercised by that test, even
                # though no test names it directly. Without this, every extracted
                # helper would be reported as uncovered the moment it is created.
                for referenced in referenced_by_tests:
                    if referenced not in module.calls:
                        continue
                    if short in index.intra_module_closure(module_name, referenced, depth=2):
                        linked = True
                        break
            if linked:
                continue
            kind = "UNCOVERED_NEW" if symbol.name in added_names else "UNCOVERED_BY_STALENESS"
            items.append(
                {
                    "symbol": f"{module_name}.{symbol.name}",
                    "path": module.path,
                    "line": symbol.line,
                    "changed_lines": sorted(set(body_changed) | ({symbol.line} if symbol.name in added_names else set()))[
                        :max_changed_lines
                    ],
                    "kind": kind,
                    "has_any_test": False,
                    "docstring": symbol.docstring,
                }
            )
    items.sort(key=lambda item: (item["path"], item["line"], item["symbol"]))
    return items, counters


def _module_name(path):
    text = str(path).replace("\\", "/")
    return text[:-3].replace("/", ".") if text.endswith(".py") else text
