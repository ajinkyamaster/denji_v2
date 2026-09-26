"""The verification-gated cascade (Person B, deliverable B6).

The shape (person_b.txt section 4):

    candidate unit
        |
        v  (free) SUFFICIENCY GATE -- can this bundle even decide?  no -> UNKNOWN + safe direction
        v
    [ SCOUT -- cheap, wide ]  propose claims WITH CITATIONS
        |
        v  (free) testscope_verify
        |---- VERIFIED -> ACCEPT, STOP. Most units end here.
        |---- REJECTED -> escalate
        v
    [ CARTOGRAPHER -- reads the repository's prose ]  propose intent anchors
        |
        v  (free) testscope_verify
        |---- VERIFIED -> ACCEPT     |---- REJECTED -> UNCONFIRMED + safe direction
        v
    [ AUTHOR -- one test for ONE uncovered symbol ] -> testscope_gate G1..G5
    [ FALSIFIER -- runs LAST and ALONE over the UNSELECTED rows ] -> testscope_verify

WHY THIS IS A CASCADE AND NOT AN ENSEMBLE:

  * the escalation trigger is a MECHANICAL VERIFICATION FAILURE, not a learned,
    calibrated confidence score -- no calibration set, no drift, no distribution
    shift. A cascade normally needs a scorer; the kernel replaces it, and it is
    exact.
  * disagreement is never resolved by a vote: each claim is verified independently
    and the survivors are unioned. Majority voting is inadmissible for correctness.
  * a model is never the verifier (documented systematic bias).
  * at most TWO model tiers per unit. If tier 2 is also rejected: UNCONFIRMED,
    safe direction, log. Unbounded escalation burns budget for no correctness gain.

WHERE THE SAFE DIRECTION (C18) IS APPLIED -- and nowhere else:

  1. sufficiency gate failed              -> UNKNOWN: include the candidate test, mark it
  2. tier cap reached, still unresolved   -> UNCONFIRMED: include, mark, log
  3. the kernel said "unconfirmed"        -> include, mark
  4. kernel unavailable                   -> accept NOTHING; selection = baseline

Everywhere else nothing is added. The final selection is `baseline UNION verified
additions`, so a model layer that is unavailable, wrong, slow or hostile can only
cause OVER-selection, never under-selection (Lemma 2, monotonicity). Missing a
regression costs more than running one extra test, and a test asserts the
disabled-model case equals the baseline byte for byte.

NO CLAIM REACHES AN ARTEFACT WITHOUT A VERIFY CALL. `_apply_verdict` accepts a claim
only if it is in the batch that was just submitted, and compares the kernel's echo to
the submitted claim; anything else raises UnverifiedClaimError and voids the run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from . import context, envelope
from .errors import (
    EnvelopeError,
    FalsifierInputError,
    FalsifierOrderError,
    KernelUnavailable,
    ModelUnavailable,
    UnverifiedClaimError,
)

PROPOSE = Callable[[str, dict[str, Any]], Any]
VERIFY = Callable[[list[dict], str], dict]
GATE = Callable[[dict[str, Any]], dict]

TIER_ROLES: tuple[str, str] = ("scout", "cartographer")
MAX_TIERS = 2

@dataclass(frozen=True)
class Rejection:
    """One entry of the rejection ledger: every rejected proposal, with its gate."""

    role: str
    gate: str
    detail: str
    claim_ref: str

    def as_ledger_entry(self) -> dict[str, str]:
        return {
            "role": self.role,
            "gate": self.gate,
            "detail": self.detail,
            "claim_ref": self.claim_ref,
        }


@dataclass
class Outcome:
    """The result of one cascade run over one unit."""

    unit_id: str
    status: str
    tiers_used: int = 0
    model_calls: int = 0
    accepted: list[dict] = field(default_factory=list)
    unconfirmed: list[dict] = field(default_factory=list)
    unmapped_findings: list[dict] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)
    safe_direction_ids: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def selection_additions(self) -> list[dict]:
        """Verified additions only: `selection = baseline UNION this`."""
        return list(self.accepted)

    def rejection_ledger(self) -> list[dict[str, str]]:
        return [rejection.as_ledger_entry() for rejection in self.rejections]


def run_cascade(
    unit: dict[str, Any],
    *,
    propose: PROPOSE,
    verify: VERIFY,
    repo: str,
    inventory_ids: Sequence[str] | None = None,
    unit_id: str | None = None,
    tier_roles: Sequence[str] = TIER_ROLES,
) -> Outcome:
    """Run the scout -> verify -> (cartographer -> verify) cascade over one unit."""
    roles = tuple(tier_roles)
    if len(roles) > MAX_TIERS:
        raise ValueError(
            f"at most {MAX_TIERS} model tiers per unit are allowed; got {len(roles)}: {roles}"
        )

    outcome = Outcome(unit_id=unit_id or _unit_id(unit), status="no_claims")
    inventory = set(map(str, inventory_ids)) if inventory_ids is not None else None
    candidate_ids: list[str] = []

    for tier_index, role in enumerate(roles, start=1):
        assembled = context.assemble(role, unit)
        if not assembled.sufficient:
            outcome.tiers_used = tier_index - 1
            outcome.missing = list(assembled.missing)
            outcome.status = "skipped_insufficient"
            outcome.safe_direction_ids = _ids_from_unit(unit)
            outcome.notes.append(
                f"sufficiency gate: {role} bundle insufficient "
                f"(missing: {', '.join(assembled.missing)}); zero model calls, safe direction"
            )
            return outcome

        outcome.tiers_used = tier_index
        claims = _propose_once(propose, role, assembled.bundle, outcome)
        if claims is None:
            outcome.notes.append(f"{role}: MODEL_UNAVAILABLE after one retry; item degrades to baseline")
            continue
        if not claims:
            outcome.notes.append(f"{role}: empty proposal (honest silence is a valid answer)")
            continue
        candidate_ids = _merge(candidate_ids, _ids_from_claims(claims))

        verdict = _verify(verify, claims, repo, outcome)
        if verdict is None:
            outcome.status = "kernel_unavailable"
            outcome.notes.append(
                "kernel unavailable: nothing accepted; the selection equals the deterministic baseline"
            )
            return outcome

        accepted, _ = _apply_verdict(verdict, claims, role, outcome, inventory)
        if accepted:
            outcome.accepted = accepted
            outcome.status = "accepted" if tier_index == 1 else "escalated_accepted"
            outcome.notes.append(f"{role}: {len(accepted)} claim(s) accepted; escalation stops")
            return outcome

    if outcome.unconfirmed or outcome.rejections or candidate_ids:
        outcome.status = "unconfirmed"
        outcome.safe_direction_ids = _merge(
            outcome.safe_direction_ids,
            _ids_from_claims([entry["claim"] for entry in outcome.unconfirmed]),
            candidate_ids,
            _ids_from_unit(unit),
        )
        outcome.notes.append(
            "tier cap reached with no verified claim; safe direction: include and mark UNCONFIRMED"
        )
    else:
        outcome.status = "no_claims"
    return outcome


def run_author(
    unit: dict[str, Any],
    *,
    propose: PROPOSE,
    gate: GATE,
    repo: str,
    unit_id: str | None = None,
) -> Outcome:
    """Author one test for ONE uncovered symbol; adjudication is `testscope_gate`.

    The author is not an escalation tier: it is a separate phase, entered only for
    uncovered symbols that passed the sufficiency gate. Its output is a patch to an
    EXISTING test file, and nothing enters the suite unless G1..G5 accept it.
    """
    outcome = Outcome(unit_id=unit_id or _unit_id(unit), status="no_claims")
    assembled = context.assemble_author(unit)
    if not assembled.sufficient:
        outcome.status = "skipped_insufficient"
        outcome.missing = list(assembled.missing)
        outcome.safe_direction_ids = _ids_from_unit(unit)
        outcome.notes.append(
            f"sufficiency gate: author bundle insufficient (missing: {', '.join(assembled.missing)}); "
            "zero model calls"
        )
        return outcome

    claims = _propose_once(propose, "author", assembled.bundle, outcome)
    if claims is None:
        outcome.notes.append("author: MODEL_UNAVAILABLE after one retry; item degrades to baseline")
        return outcome
    if not claims:
        outcome.notes.append("author: empty proposal; nothing authored for this symbol")
        return outcome

    outcome.tiers_used = 1
    if len(claims) > 1:
        outcome.status = "discarded"
        outcome.rejections.append(
            Rejection("author", "too_many_claims", f"{len(claims)} claims for one symbol; at most 1", envelope.claim_ref(claims[0]))
        )
        outcome.notes.append("author proposed more than one test for one symbol; discarded")
        return outcome

    claim = claims[0]
    target_file = claim["targets"]["file"]
    if target_file != assembled.bundle["test_class_file"]:
        outcome.status = "discarded"
        outcome.rejections.append(
            Rejection(
                "author",
                "target_file_mismatch",
                f"proposed {target_file!r}; the role extends {assembled.bundle['test_class_file']!r} and creates no new file",
                envelope.claim_ref(claim),
            )
        )
        outcome.notes.append("author targeted a different file; discarded before the gate")
        return outcome

    gate_payload = {
        "repo": repo,
        "test_patch": claim["targets"]["patch"],
        "symbol": claim["targets"]["symbol"],
    }
    try:
        gate_result = gate(gate_payload)
    except KernelUnavailable as exc:
        outcome.status = "kernel_unavailable"
        outcome.notes.append(f"testscope_gate unavailable ({exc}); nothing authored is accepted")
        return outcome

    outcome.notes.append(f"testscope_gate: {json.dumps(gate_result, sort_keys=True)}")
    if gate_result.get("accepted"):
        outcome.accepted = [claim]
        outcome.status = "authored_accepted"
        outcome.notes.append("author output cleared G1..G5; admitted to the suite")
    else:
        outcome.rejections.append(
            Rejection("author", "gate_failed", _gate_failure_detail(gate_result), envelope.claim_ref(claim))
        )
        outcome.status = "authored_discarded"
        outcome.notes.append("author output failed the filtration; discarded and logged")
    return outcome


def run_falsifier(
    *,
    ledger: dict[str, Any],
    diff_hunks: str,
    unselected_rows: Sequence[dict],
    selected_ids: Sequence[str],
    propose: PROPOSE,
    verify: VERIFY,
    repo: str,
    ledger_is_final: bool,
    inventory_ids: Sequence[str] | None = None,
) -> Outcome:
    """Run the falsifier LAST and ALONE, over the UNSELECTED rows only.

    It needs the whole picture, which is why it is never parallelised: parallelising
    it would give it conflicting assumptions. Two hard guards are enforced here and
    tested: the ledger must be final, and no already-selected row may be supplied.
    """
    if not ledger_is_final:
        raise FalsifierOrderError(
            "the falsifier runs LAST, after the ledger is final; ledger_is_final=False"
        )
    selected = {str(x) for x in (selected_ids or [])}
    offenders = sorted(
        {str(row.get("test_id")) for row in unselected_rows if str(row.get("test_id") or "") in selected}
    )
    if offenders:
        raise FalsifierInputError(
            f"the falsifier may only see UNSELECTED rows; selected rows supplied: {offenders}"
        )

    unit = {
        "unit_id": "falsifier",
        "final_ledger": ledger,
        "diff_hunks": diff_hunks,
        "unselected_rows": list(unselected_rows),
        "selected_ids": sorted(selected),
    }
    return run_cascade(
        unit,
        propose=propose,
        verify=verify,
        repo=repo,
        inventory_ids=inventory_ids,
        unit_id="falsifier",
        tier_roles=("falsifier",),
    )


# --------------------------------------------------------------------------- #
# internals
# --------------------------------------------------------------------------- #


def _propose_once(
    propose: PROPOSE,
    role: str,
    bundle: dict[str, Any],
    outcome: Outcome,
) -> list[dict] | None:
    """Call the proposer with ONE retry. Returns None if it stays unavailable.

    A schema violation is recorded as a rejection and treated as an empty batch:
    the proposal is rejected, never salvaged, and the cascade may escalate.
    """
    for attempt in (1, 2):
        try:
            raw = propose(role, bundle)
            outcome.model_calls += 1
        except ModelUnavailable as exc:
            outcome.model_calls += 1
            outcome.notes.append(f"{role}: proposal attempt {attempt} failed ({exc})")
            continue
        try:
            return envelope.parse_claims(role, raw)
        except EnvelopeError as exc:
            outcome.rejections.append(
                Rejection(role, "schema_violation", str(exc), "unparsed")
            )
            outcome.notes.append(f"{role}: schema violation rejected, never salvaged: {exc}")
            return []
    return None


def _verify(
    verify: VERIFY,
    claims: list[dict],
    repo: str,
    outcome: Outcome,
) -> dict | None:
    try:
        verdict = verify(claims, repo)
    except KernelUnavailable as exc:
        outcome.notes.append(f"kernel unavailable: {exc}")
        return None
    if not isinstance(verdict, dict):
        raise UnverifiedClaimError(
            f"the kernel returned {type(verdict).__name__}; a verdict must be an object"
        )
    return verdict


def _apply_verdict(
    verdict: dict,
    submitted: list[dict],
    role: str,
    outcome: Outcome,
    inventory: set[str] | None,
) -> tuple[list[dict], list[dict]]:
    """Extract accepted/unconfirmed claims. THE trust-boundary check lives here."""
    submitted_forms = {_canonical(claim) for claim in submitted}

    accepted: list[dict] = []
    for entry in verdict.get("accepted") or []:
        claim = _claim_of(entry)
        if _canonical(claim) not in submitted_forms:
            raise UnverifiedClaimError(
                "the kernel accepted a claim that was never submitted; refusing the run"
            )
        accepted.append(claim)
        if inventory is not None:
            test_id = str((claim.get("targets") or {}).get("test_id") or "")
            if test_id and test_id not in inventory:
                outcome.unmapped_findings.append(
                    {"claim": claim, "reason": f"no inventory row for {test_id}; kept, never dropped"}
                )

    for entry in verdict.get("rejected") or []:
        claim = _claim_of(entry)
        outcome.rejections.append(
            Rejection(
                role,
                str(entry.get("gate") or "unspecified"),
                str(entry.get("detail") or ""),
                envelope.claim_ref(claim),
            )
        )

    unconfirmed: list[dict] = []
    for entry in verdict.get("unconfirmed") or []:
        claim = _claim_of(entry)
        unconfirmed.append(claim)
        outcome.unconfirmed.append(
            {"claim": claim, "reason": str(entry.get("reason") or "verifiable by neither mechanism")}
        )

    return accepted, unconfirmed


def _gate_failure_detail(gate_result: dict) -> str:
    """Name the gates that produced a refusal, so the rejection ledger is auditable.

    The four booleans are read by their documented names. G4 is a strength, not a
    boolean, so it is reported by value: when no named boolean failed, the refusal is
    g4's, and recording it as a bare `accepted=false` would hide which gate fired.
    """
    failing = sorted(
        key
        for key in ("g1_buildable", "g2_passes_5x", "g3_assertion_fires_at_a", "g5_spec_anchored")
        if gate_result.get(key) is False
    )
    if failing:
        return f"failing gates: {', '.join(failing)}"
    strength = gate_result.get("g4_mutation_strength")
    if isinstance(strength, (int, float)) and not isinstance(strength, bool) and strength < 1.0:
        return f"accepted=false with g4_mutation_strength={strength}; no named boolean failed"
    return "failing gates: accepted=false (the kernel named no rule)"


def _claim_of(entry: Any) -> dict:
    if isinstance(entry, dict) and "claim" in entry and isinstance(entry["claim"], dict):
        return entry["claim"]
    if isinstance(entry, dict):
        return entry
    raise UnverifiedClaimError(f"kernel verdict entry is not an object: {entry!r}")


def _canonical(claim: Any) -> str:
    return json.dumps(claim, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _unit_id(unit: dict[str, Any]) -> str:
    if unit.get("unit_id"):
        return str(unit["unit_id"])
    test_row = unit.get("test_row") or {}
    return str(test_row.get("test_id") or unit.get("changed_symbol") or unit.get("symbol") or "unit")


def _ids_from_unit(unit: dict[str, Any]) -> list[str]:
    ids = []
    test_row = unit.get("test_row") or {}
    if test_row.get("test_id"):
        ids.append(str(test_row["test_id"]))
    if unit.get("test_id"):
        ids.append(str(unit["test_id"]))
    return _merge(ids)


def _ids_from_claims(claims: Sequence[dict]) -> list[str]:
    ids = []
    for claim in claims:
        target = str((claim.get("targets") or {}).get("test_id") or "")
        if target:
            ids.append(target)
    return _merge(ids)


def _merge(*lists: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for items in lists:
        for item in items:
            if item and item not in seen:
                seen.add(item)
                merged.append(item)
    return sorted(merged)
