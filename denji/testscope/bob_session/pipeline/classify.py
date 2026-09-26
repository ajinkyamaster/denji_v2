"""Classification: which tests the change touches, and by what evidence.

v1's three buckets are semantic and **unchanged in shape**: every inventory row
lands in exactly one of ``definitely_affected`` / ``semantically_affected`` /
``not_affected``, with a ``reason`` that agrees with its bucket.

The rule that makes the selection defensible, and that a reviewer should attack
first, is the *link direction*: a test is selected when the module it exercises
can reach a changed module through imports — never the other way round. A test of
a module that a changed module happens to import does not observe the change
unless the changed module's behaviour reaches it, which the reverse closure
captures exactly.

Semantic selection exists because the reverse closure is a lower bound (A1).
A representation coupling names a consumer whose tests must run even though no
import path exists. Model-proposed links enter here too, but **only** after the
kernel has re-derived them.
"""

from dataclasses import dataclass, field

BUCKETS = ("definitely_affected", "semantically_affected", "not_affected")

REASONS = {
    "definitely_affected": {"structural_import_closure"},
    "semantically_affected": {"representation_coupling", "verified_model_claim"},
    "not_affected": {
        "no_import_path_to_changed_module",
        "normalised_inert_change",
        "docs_only_change",
        "no_changed_behaviour",
        "unsupported_file_type",
        "orphan_module_missing",
        "test_not_found_in_repository",
        "unparseable_module",
    },
}


@dataclass
class RowVerdict:
    test_id: str
    test_name: str
    module: str
    bucket: str
    reason: str
    explanation: str
    test_module: str = None
    derived_module: str = None
    declared_module: str = None
    depth: int = None

    def as_classification_entry(self):
        return {
            "test_id": self.test_id,
            "test_name": self.test_name,
            "module": self.module,
            "reason": self.reason,
            "explanation": self.explanation,
        }


@dataclass
class Classification:
    verdicts: dict = field(default_factory=dict)
    link_corrections: list = field(default_factory=list)
    unlocated: list = field(default_factory=list)

    def bucket(self, name):
        return [verdict for verdict in self.verdicts.values() if verdict.bucket == name]

    def test_ids(self, name):
        return sorted(verdict.test_id for verdict in self.verdicts.values() if verdict.bucket == name)

    def selected_ids(self):
        return sorted(self.test_ids("definitely_affected") + self.test_ids("semantically_affected"))

    def as_artifact(self):
        return {
            bucket: [verdict.as_classification_entry() for verdict in self.bucket(bucket)] for bucket in BUCKETS
        }


def _index_tests_by_name(index):
    """Map a test function name to its test module (first match, deterministic)."""
    mapping = {}
    for module in sorted(index.test_modules().values(), key=lambda item: item.name):
        for symbol in module.symbols:
            mapping.setdefault(symbol.name, module)
    return mapping


def _module_under_test(index, test_module):
    """Which application module a test file exercises.

    The declared module in the inventory is a *claim*; the test file's imports
    are facts. The derived answer wins, and any disagreement is recorded as a
    link correction rather than hidden.
    """
    candidates = []
    for imported in test_module.imports:
        candidate = index.module_named(imported)
        if candidate is None or candidate.is_test:
            continue
        if candidate.path == test_module.path:
            continue
        candidates.append(candidate)
    if not candidates:
        return None, False
    # A test file may import several modules; the one it names in its body wins.
    from .repo_index import references

    import ast

    try:
        tree = ast.parse(test_module.source)
    except SyntaxError:  # pragma: no cover
        return sorted(candidates, key=lambda item: item.name)[0], len(candidates) > 1
    referenced = references(tree)
    named = [candidate for candidate in candidates if any(
        symbol.name.split(".")[-1] in referenced for symbol in candidate.symbols
    )]
    chosen = sorted(named or candidates, key=lambda item: item.name)[0]
    return chosen, len(candidates) > 1


def classify(index, inventory, diff, couplings, *, verified_links=()):
    """Classify every inventory row. Pure function of its inputs.

    ``verified_links`` are kernel-accepted ``link_exists`` claims: each names a
    test id and is used as evidence, never as a verdict in itself.
    """
    tests_by_name = _index_tests_by_name(index)
    active_modules = set(diff.changed_modules)
    inert_modules = set(diff.inert_modules)
    closure = index.reverse_closure(active_modules, include_tests=True) if active_modules else {}
    couplings_by_consumer = {}
    for coupling in couplings:
        couplings_by_consumer.setdefault(coupling.consumer_module, []).append(coupling)

    claimed = {}
    for claim in verified_links:
        test_id = (claim.get("targets") or {}).get("test_id")
        if test_id:
            claimed.setdefault(test_id, []).append(claim)

    result = Classification()
    for row in inventory:
        test_module = tests_by_name.get(row.test_name)
        derived, ambiguous = (None, False)
        if test_module is not None:
            derived, ambiguous = _module_under_test(index, test_module)
        derived_name = derived.name if derived is not None else None
        if derived_name and row.module and derived_name != row.module:
            result.link_corrections.append(
                {
                    "test_id": row.test_id,
                    "declared_module": row.module,
                    "derived_module": derived_name,
                    "test_module": test_module.name if test_module else None,
                    "note": "the inventory is a claim, the import is a fact; the derived link is used",
                }
            )
        effective_module = derived_name or row.module

        verdict = RowVerdict(
            test_id=row.test_id,
            test_name=row.test_name,
            module=effective_module,
            bucket="not_affected",
            reason="no_changed_behaviour",
            explanation="the change touches no Python module",
            test_module=test_module.name if test_module else None,
            derived_module=derived_name,
            declared_module=row.module,
        )

        if test_module is None:
            verdict.reason = "test_not_found_in_repository"
            verdict.explanation = f"no test named {row.test_name!r} was found in the repository"
            result.unlocated.append(row.test_id)
        elif test_module.name in index.unparseable_paths():
            verdict.reason = "unparseable_module"
            verdict.explanation = f"{test_module.path} could not be parsed; selected conservatively"
        elif effective_module is None:
            verdict.reason = "orphan_module_missing"
            verdict.explanation = "the module this test exercises is not in the repository index"
        elif not active_modules:
            verdict.reason = "docs_only_change" if diff.files else "no_changed_behaviour"
            verdict.explanation = "no semantics-modifying Python change: nothing is selected"
        else:
            test_closure = index.forward_closure(test_module.name)
            reached = sorted(active_modules & test_closure)
            if reached:
                target = reached[0]
                verdict.bucket = "definitely_affected"
                verdict.reason = "structural_import_closure"
                verdict.depth = closure.get(target)
                verdict.explanation = (
                    f"{test_module.path} imports {effective_module}, which transitively imports the "
                    f"changed module {target} (depth {verdict.depth})"
                )
            elif row.test_id in claimed:
                targets = claimed[row.test_id]
                verdict.bucket = "semantically_affected"
                verdict.reason = "verified_model_claim"
                verdict.explanation = "; ".join(
                    claim.get("rationale", "kernel-verified link") for claim in targets
                )[:400]
            else:
                consumer = couplings_by_consumer.get(effective_module, [])
                if consumer and test_module is not None and _references_any(test_module, consumer):
                    names = ", ".join(sorted({coupling.consumer_symbol for coupling in consumer if coupling.consumer_symbol}))
                    verdict.bucket = "semantically_affected"
                    verdict.reason = "representation_coupling"
                    verdict.depth = 1
                    verdict.explanation = (
                        f"{test_module.path} exercises {effective_module}, which parses a wire format "
                        f"produced by the changed module {consumer[0].producer_module} "
                        f"(coupling through {consumer[0].separator!r}, no import edge). Symbols: {names}"
                    )
                elif test_module.name in closure:
                    verdict.reason = "no_changed_behaviour"
                    verdict.explanation = "the test module reaches a changed module but exercises none of it"
                elif any(module in inert_modules for module in index.forward_closure(test_module.name)):
                    verdict.reason = "normalised_inert_change"
                    verdict.explanation = (
                        "the only reachable change is non-semantics-modifying (a log reword or "
                        "documentation): re-running these tests cannot reveal anything"
                    )
                else:
                    verdict.reason = "no_import_path_to_changed_module"
                    verdict.explanation = (
                        "no import path reaches a changed module and no representation coupling applies"
                    )
        if ambiguous:
            verdict.explanation += " [multiple candidate modules under test]"
        result.verdicts[row.test_id] = verdict
    return result


def _references_any(test_module, couplings):
    """True when the test file names the consumer symbol or module of a coupling."""
    from .repo_index import references

    import ast

    try:
        tree = ast.parse(test_module.source)
    except SyntaxError:  # pragma: no cover
        return False
    names = references(tree)
    for coupling in couplings:
        if coupling.consumer_symbol and coupling.consumer_symbol in names:
            return True
        if coupling.consumer_symbol and any(name.endswith(f".{coupling.consumer_symbol}") for name in names):
            return True
    return False
