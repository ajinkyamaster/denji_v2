#!/usr/bin/env python3
"""The kernel: the only door a model claim can come through.

A model never "decides". It proposes a **claim**, and the claim's citations are
its **obligations**: the kernel re-opens those files and re-derives the claim from
the repository. A claim whose citation does not resolve is rejected
automatically, with the failing gate named.

Three rules that are architecture rather than style:

``confidence`` affects ORDERING ONLY, never acceptance. That is deliberate: it
removes any incentive to talk the model into a verdict, and it means a
manipulated model cannot promote its own output.

Coverage is admissible **only as a positive witness**. If a test covered a line,
it executed it, so coverage can prove a link exists. Absence of coverage proves
nothing (A1: ``L* ⊄ L_cov``), so it may never be used to reject a link. The
asymmetry is enforced here, in the one place where coverage is read.

Untrusted text cannot cause an unsound accept. Repository prose is data, and the
worst a hostile comment can do is produce a false claim - which this file
rejects. The verifier is the trust boundary; the model is not.

Claim types and their obligations:

  link_exists  the cited consumer symbol is referenced in the test's file, or the
               test covers the cited line (coverage as positive witness)
  intent       the quoted text is byte-present at the cited location AND the code
               it describes was removed or redefined by the change
  missed       the claimed dependency path re-derives: every hop resolves, and the
               last hop is a changed symbol, and the test is not already selected
  test         delegated to testscope_gate (G1..G5); this tool harvests nothing
"""

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bob_session.pipeline.errors import DiffError, SafetyError
from bob_session.pipeline.paths import read_text, resolve_in_repo
from bob_session.pipeline.repo_index import build_index, references, symbols_from_source

CLAIM_TYPES = ("link_exists", "intent", "test", "missed")
ROLES = ("scout", "cartographer", "author", "falsifier")
REJECTION_GATES = (
    "schema_violation",
    "citation_invalid",
    "symbol_mismatch",
    "contradicts_symbolic",
    "quote_not_present",
    "rationale_too_long",
)
MAX_RATIONALE = 200
INTERNAL_PATH_LIMIT = 512


def _reject(claim, gate, detail):
    return {"claim": claim, "gate": gate, "detail": detail}


def _validate_envelope(claim):
    """Structural validation. A malformed envelope is a schema violation, not a rejection."""
    if not isinstance(claim, dict):
        return "claim is not an object"
    if claim.get("claim_type") not in CLAIM_TYPES:
        return f"claim_type must be one of {CLAIM_TYPES}"
    if claim.get("role") not in ROLES:
        return f"role must be one of {ROLES}"
    rationale = claim.get("rationale") or ""
    if not isinstance(rationale, str) or len(rationale) > MAX_RATIONALE:
        return f"rationale must be a string of at most {MAX_RATIONALE} characters"
    citations = claim.get("citations")
    if not isinstance(citations, list):
        return "citations must be a list"
    if claim.get("claim_type") != "test" and not citations:
        return "a non-test claim must carry at least one citation: the citation is the obligation"
    if len(citations) > 8:
        return "at most 8 citations per claim"
    for citation in citations:
        if not isinstance(citation, dict) or not isinstance(citation.get("path"), str):
            return "each citation needs a path"
    return None


def _resolve_citation(citation, repo, index):
    """Resolve one citation into a verdict about its own admissibility.

    Returns ``(ok, gate, detail, resolved)``. Line drift is *defined* behaviour:
    the symbol resolving in the correct file accepts with a note, because moving
    code is not lying.
    """
    path = citation.get("path") or ""
    symbol = citation.get("symbol") or ""
    line = citation.get("line")
    if len(path) > INTERNAL_PATH_LIMIT:
        return False, "citation_invalid", "citation path is implausibly long", None
    try:
        resolved_path = resolve_in_repo(repo, path)
    except SafetyError as error:
        return False, "citation_invalid", f"citation refused: {error}", None
    text, reason = read_text(resolved_path)
    if text is None:
        return False, "citation_invalid", f"{path} is not readable ({reason})", None
    if symbol:
        module = index.module_named(_module_name(path))
        symbols = list(module.symbols) if module is not None else symbols_from_source(text, _module_name(path))
        match = next((candidate for candidate in symbols if candidate.name == symbol), None)
        if match is None and symbol not in references_from_text(text) and symbol not in text:
            return False, "symbol_mismatch", f"symbol {symbol!r} does not appear in {path}", None
        drift = bool(match is not None and line is not None and match.line != line)
        return (
            True,
            None,
            f"line_drift: {symbol} is defined at line {match.line}, citation said {line}" if drift else None,
            {"path": path, "symbol": symbol, "line": line, "defined_at": match.line if match else None, "text": text},
        )
    return True, None, None, {"path": path, "symbol": symbol, "line": line, "text": text}


def references_from_text(text):
    """Names referenced in a source string, or an empty set when it will not parse."""
    import ast

    try:
        return references(ast.parse(text))
    except SyntaxError:
        return set()


def _module_name(path):
    text = str(path).replace("\\", "/")
    return text[:-3].replace("/", ".") if text.endswith(".py") else text


def _test_file_for(test_id, index, inventory):
    """Locate the test file that implements an inventory row."""
    if test_id is None:
        return None, None
    row = next((candidate for candidate in inventory if candidate.test_id == test_id), None) if inventory else None
    if row is None:
        return None, None
    for module in index.test_modules().values():
        for symbol in module.symbols:
            if symbol.name == row.test_name:
                return module, row
    return None, row


def _consumer_site(claim, consumer_symbol):
    """Return ``(path, line, problem)`` for the site a coverage witness must attest.

    The witness is anchored to the **citation** that carries the consumer symbol -
    the obligation the kernel has already resolved - and never to a separately
    named target. A model able to point the witness somewhere other than its own
    citation would be attesting a site the claim never named, which is exactly the
    unsound-accept path the kernel exists to close.

    So when ``targets`` names a site too and it disagrees, the claim is internally
    contradictory: rejected, not repaired. The kernel does not guess which of the
    two the proposer meant.
    """
    cited = cited_line = None
    for citation in reversed(claim.get("citations") or []):
        symbol = citation.get("symbol")
        if citation.get("path") and citation.get("line") is not None and (not symbol or symbol == consumer_symbol):
            cited, cited_line = citation["path"], int(citation["line"])
            break
    targets = claim.get("targets") or {}
    declared_path = targets.get("consumer_path")
    declared_line = targets.get("consumer_line")
    if declared_path is not None and declared_line is not None:
        if cited is not None and (str(declared_path) != str(cited) or int(declared_line) != cited_line):
            return cited, cited_line, (
                f"targets name {declared_path}:{declared_line} but the citation carrying {consumer_symbol!r} "
                f"is {cited}:{cited_line}; a coverage witness must attest the cited site"
            )
        if cited is None:
            cited, cited_line = str(declared_path), int(declared_line)
    return cited, cited_line, None


def _verify_link_exists(claim, *, repo, index, inventory, coverage, notes):
    targets = claim.get("targets") or {}
    test_id = targets.get("test_id")
    test_module, row = _test_file_for(test_id, index, inventory)
    if test_module is None:
        return _reject(claim, "citation_invalid", f"test {test_id!r} is not in the inventory or has no test file")
    consumer_symbol = targets.get("consumer_symbol")
    if not consumer_symbol and claim.get("citations"):
        consumer_symbol = claim["citations"][-1].get("symbol")
    referenced = references_from_text(test_module.source)
    if consumer_symbol and (consumer_symbol in referenced or any(
        name.endswith(f".{consumer_symbol}") for name in referenced
    )):
        notes.append(f"{test_module.path} references {consumer_symbol}")
        return {"claim": claim, "obligation": "re-derived fact: the cited consumer symbol is referenced by the test"}
    # Coverage is admissible ONLY in this direction: as a positive witness.
    # Absence of coverage is never a rejection here (A1: coverage is one-sided).
    if coverage and consumer_symbol:
        cited, cited_line, problem = _consumer_site(claim, consumer_symbol)
        if problem:
            return _reject(claim, "contradicts_symbolic", problem)
        if cited and cited_line is not None:
            covered = coverage.get(str(cited)) or {}
            if covered.get(str(int(cited_line))):
                notes.append(f"coverage attests {test_id} executed {cited}:{cited_line}")
                return {
                    "claim": claim,
                    "obligation": "re-derived fact: the test executes the cited consumer line (coverage as positive witness)",
                }
    return {
        "claim": claim,
        "reason": (
            "the test's file does not reference the cited symbol and no coverage witness was supplied; "
            "verifiable by neither mechanism"
        ),
    }


def _verify_intent(claim, *, repo, index, diff, notes):
    targets = claim.get("targets") or {}
    quote = targets.get("quote") or ""
    if not quote.strip():
        return _reject(claim, "schema_violation", "an intent claim must carry targets.quote")
    removed_text = ""
    if diff is not None:
        for parsed in diff.files:
            for _, line in parsed.removed:
                removed_text += line + "\n"
    for citation in claim.get("citations", []):
        resolution = _resolve_citation(citation, repo, index)
        ok, gate, detail, resolved = resolution
        if not ok:
            return _reject(claim, gate, detail)
        text = resolved["text"]
        present_now = quote in text
        present_before = quote in removed_text
        if not present_now and not present_before:
            return _reject(
                claim,
                "quote_not_present",
                f"the quoted text is byte-absent from {resolved['path']} in both the current revision and the removed lines",
            )
        if present_now and not present_before:
            # The quoted specification is still live and the change did not remove
            # it. That is not automatically a contradiction - the violation may be
            # in another module that the quote describes. It is only acceptable if
            # the quote names a representation the change stopped producing.
            representation = _representation_match(quote, diff)
            if not representation:
                return _reject(
                    claim,
                    "contradicts_symbolic",
                    "the quoted text is still satisfied and names no representation the change removed",
                )
            notes.append(f"quote describes {representation}, which the change removed")
            return {"claim": claim, "obligation": f"re-derived: the quote describes {representation}, removed by the change"}
        notes.append(f"the quoted specification was removed from {resolved['path']}")
        return {"claim": claim, "obligation": "re-derived fact: the quoted specification was removed by the change"}
    return _reject(claim, "schema_violation", "an intent claim must carry at least one citation")


def _representation_match(quote, diff):
    """Does the quote name a representation the change actually removed?"""
    if diff is None:
        return None
    rho = diff.rho()
    lowered = quote.lower()
    for descriptor in rho["removed_representations"]:
        if descriptor.startswith("separator "):
            separator = descriptor[len("separator ") :].strip('"')
            if separator and separator in quote:
                return repr(separator)
            for word in ("pipe", "delimiter", "comma", "tab"):
                if word in lowered and (
                    (word == "pipe" and separator == "|")
                    or (word == "comma" and separator == ",")
                    or (word == "tab" and separator == "\t")
                ):
                    return repr(separator)
        elif descriptor.startswith("serializer "):
            name = descriptor[len("serializer ") :].split("(")[0]
            if name.split(".")[-1] in lowered:
                return name
    for symbol in rho["removed_symbols"]:
        if symbol in quote:
            return symbol
    return None


def _verify_missed(claim, *, repo, index, inventory, diff, selected_ids, notes):
    targets = claim.get("targets") or {}
    test_id = targets.get("test_id")
    if test_id in selected_ids:
        return _reject(claim, "contradicts_symbolic", f"{test_id} is already selected: nothing is missed")
    test_module, _ = _test_file_for(test_id, index, inventory)
    if test_module is None:
        return _reject(claim, "citation_invalid", f"test {test_id!r} is not in the inventory or has no test file")
    changed_modules = set(diff.changed_modules) if diff is not None else set()
    resolved_hops = []
    for citation in claim.get("citations", []):
        ok, gate, detail, resolved = _resolve_citation(citation, repo, index)
        if not ok:
            return _reject(claim, gate, detail)
        resolved_hops.append(resolved["path"])
    if not resolved_hops:
        return _reject(claim, "schema_violation", "a missed claim must cite the dependency path")
    last_module = _module_name(resolved_hops[-1])
    if last_module not in changed_modules:
        return _reject(
            claim,
            "contradicts_symbolic",
            f"the claimed path ends at {resolved_hops[-1]}, which the change does not modify",
        )
    if not any(_module_name(path) == test_module.name.replace(".", "/") + ".py" for path in resolved_hops):
        reachable = test_module.name in {_module_name(path) for path in resolved_hops} or any(
            hop in test_module.imports for hop in (_module_name(path) for path in resolved_hops)
        )
        if not reachable:
            notes.append("path re-derives, but the test does not import its first hop")
    notes.append(f"dependency path re-derives: {' -> '.join(resolved_hops)}")
    return {"claim": claim, "obligation": "re-derived fact: the claimed dependency path resolves against the repository"}


def verify_claims(claims, *, repo, inventory=None, diff=None, index=None, coverage=None, gate=None, selected_ids=()):
    """Verify claims against the repository.

    Returns ``{"accepted": [...], "rejected": [...], "unconfirmed": [...]}`` with
    the rejecting gate named for every rejection. Deterministic ordering: the
    result is sorted, so it is a pure function of its inputs.
    """
    repo = Path(repo)
    index = index if index is not None else build_index(repo)
    inventory = list(inventory or [])
    selected = set(selected_ids)
    accepted, rejected, unconfirmed = [], [], []

    for claim in claims:
        problem = _validate_envelope(claim)
        if problem:
            rejected.append(_reject(claim, "schema_violation", problem))
            continue
        citation_notes = []
        for citation in claim.get("citations", []):
            ok, gate_name, detail, _resolved = _resolve_citation(citation, repo, index)
            if not ok:
                rejected.append(_reject(claim, gate_name, detail))
                break
            if detail:
                citation_notes.append(detail)
        else:
            notes = list(citation_notes)
            claim_type = claim["claim_type"]
            if claim_type == "link_exists":
                outcome = _verify_link_exists(
                    claim, repo=repo, index=index, inventory=inventory, coverage=coverage, notes=notes
                )
            elif claim_type == "intent":
                outcome = _verify_intent(claim, repo=repo, index=index, diff=diff, notes=notes)
            elif claim_type == "missed":
                outcome = _verify_missed(
                    claim,
                    repo=repo,
                    index=index,
                    inventory=inventory,
                    diff=diff,
                    selected_ids=selected,
                    notes=notes,
                )
            else:  # claim_type == "test"
                if gate is None:
                    outcome = {
                        "claim": claim,
                        "reason": "delegated to testscope_gate (tool 4): G1-G5 are decided by execution, not here",
                    }
                else:
                    outcome = gate(claim)
            if outcome.get("gate"):
                rejected.append(outcome)
            elif "obligation" in outcome:
                if notes:
                    outcome["obligation"] = outcome["obligation"] + " | " + "; ".join(notes)
                accepted.append(outcome)
            else:
                unconfirmed.append(outcome)

    def sort_key(entry):
        claim = entry["claim"]
        citations = claim.get("citations") or [{}]
        return (
            claim.get("claim_type", ""),
            claim.get("role", ""),
            str((claim.get("targets") or {}).get("test_id") or ""),
            str(citations[0].get("path") or ""),
        )

    for bucket in (accepted, rejected, unconfirmed):
        bucket.sort(key=sort_key)
    return {"accepted": accepted, "rejected": rejected, "unconfirmed": unconfirmed}


def summary_of(result):
    """A compact digest for the CLI and for the ledger tool."""
    return {
        "accepted": len(result["accepted"]),
        "rejected": len(result["rejected"]),
        "unconfirmed": len(result["unconfirmed"]),
        "gates": sorted({entry.get("gate") for entry in result["rejected"] if entry.get("gate")}),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="TestScope kernel: re-derive claims against the repository")
    parser.add_argument("--claims", required=True, help="claim envelope JSON array, or '-' for stdin")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--inventory", default=None)
    parser.add_argument("--diff", default=None)
    parser.add_argument("--coverage", default=None, help="optional coverage witness JSON: {path: {line: true}}")
    parser.add_argument("--full", action="store_true", help="print the full verdicts, not just the summary")
    args = parser.parse_args(argv)

    if args.claims == "-":
        claims = json.load(sys.stdin)
    else:
        claims = json.loads(Path(args.claims).read_text(encoding="utf-8"))

    inventory = None
    if args.inventory:
        from bob_session.pipeline.inventory import load_inventory

        inventory = load_inventory(Path(args.inventory))
    diff = None
    if args.diff:
        from bob_session.pipeline.diff_parser import parse_diff_file

        try:
            diff = parse_diff_file(args.diff)
        except DiffError as error:
            print(json.dumps({"error": str(error)}), file=sys.stderr)
            return 2
    coverage = json.loads(Path(args.coverage).read_text(encoding="utf-8")) if args.coverage else None

    result = verify_claims(claims, repo=Path(args.repo), inventory=inventory, diff=diff, coverage=coverage)
    payload = result if args.full else {"summary": summary_of(result), "rejected": [entry["detail"] for entry in result["rejected"]]}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
