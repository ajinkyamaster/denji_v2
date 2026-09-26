"""The claim envelope: the only language the models may speak (Person B).

A model never "decides". It proposes a CLAIM; the citations it carries are the
OBLIGATION the kernel re-derives against the repository. This module is the strict
parser at the layer's inbound boundary:

  * STRICT JSON only. Prose around the JSON, markdown fences, or a partial object
    are SCHEMA VIOLATIONS and are rejected -- never salvaged. ("Never write a
    best-effort JSON salvage path -- that is how a verifier silently becomes a
    guesser.")
  * exact key set, exact enums, per-role claim_type, per-role target keys.
  * `confidence` is parsed and preserved for ORDERING ONLY. This module -- and the
    cascade -- never let it influence acceptance.

Role contracts enforced here (person_b.txt section 5.4 / 6):

  scout        claim_type link_exists, targets test_id + changed_symbol
  cartographer claim_type intent,      targets changed_symbol + quote + contradiction
  author       claim_type test,        targets symbol + file + test_name +
                                       behaviour_pinned + patch (a unified diff
                                       against an EXISTING test file)
  falsifier    claim_type missed,      targets test_id + missing_reason

The author's `patch` lives in `targets` because section 5.4 defines the author's
output as "one claim of type test, as a patch to an EXISTING test file", and the
envelope's targets are the role-specific payload.
"""

from __future__ import annotations

import json
from typing import Any

from .errors import EnvelopeError

CLAIM_TYPES = ("link_exists", "intent", "test", "missed")
ROLES = ("scout", "cartographer", "author", "falsifier")
ROLE_CLAIM_TYPE = {
    "scout": "link_exists",
    "cartographer": "intent",
    "author": "test",
    "falsifier": "missed",
}
CONFIDENCES = ("low", "med", "high")
ENVELOPE_KEYS = ("claim_type", "role", "targets", "citations", "confidence", "rationale")
CITATION_KEYS = ("path", "symbol", "line")
MAX_RATIONALE = 200

TARGET_KEYS = {
    "scout": ("test_id", "changed_symbol"),
    "cartographer": ("changed_symbol", "quote", "contradiction"),
    "author": ("symbol", "file", "test_name", "behaviour_pinned", "patch"),
    "falsifier": ("test_id", "missing_reason"),
}


def parse_claims(role: str, raw: Any) -> list[dict]:
    """Parse one model response into a list of validated claim envelopes.

    `raw` is the exact text the model returned, or an already-parsed mapping of the
    documented shape. Anything else raises EnvelopeError.
    """
    if role not in ROLES:
        raise EnvelopeError(f"unknown role {role!r}; roles: {', '.join(ROLES)}")

    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            raise EnvelopeError("empty response; expected the claim envelope")
        try:
            data = _strict_json(text)
        except ValueError as exc:
            raise EnvelopeError(f"not strict JSON ({exc}); the envelope is rejected, never salvaged") from None
    elif isinstance(raw, dict):
        data = raw
    else:
        raise EnvelopeError(
            f"expected strict JSON text or an envelope dict, got {type(raw).__name__}"
        )

    if not isinstance(data, dict) or set(data) != {"claims"}:
        raise EnvelopeError('top level must be exactly {"claims": [...]}')

    claims = data["claims"]
    if not isinstance(claims, list):
        raise EnvelopeError('"claims" must be a list')
    return [validate_claim(role, claim, index=i) for i, claim in enumerate(claims)]


def validate_claim(role: str, claim: Any, index: int = 0) -> dict:
    """Validate one claim against its role contract; return it in canonical order."""
    where = f"claim[{index}]"
    if not isinstance(claim, dict):
        raise EnvelopeError(f"{where}: must be an object, got {type(claim).__name__}")

    if set(claim) != set(ENVELOPE_KEYS):
        missing = sorted(set(ENVELOPE_KEYS) - set(claim))
        extra = sorted(set(claim) - set(ENVELOPE_KEYS))
        raise EnvelopeError(f"{where}: keys must be exactly {list(ENVELOPE_KEYS)}; missing={missing} extra={extra}")

    if claim["role"] != role:
        raise EnvelopeError(f"{where}: role is {claim['role']!r}, expected {role!r}")
    if claim["claim_type"] != ROLE_CLAIM_TYPE[role]:
        raise EnvelopeError(
            f"{where}: claim_type is {claim['claim_type']!r}, expected {ROLE_CLAIM_TYPE[role]!r} for {role}"
        )
    if claim["confidence"] not in CONFIDENCES:
        raise EnvelopeError(f"{where}: confidence must be one of {list(CONFIDENCES)}")

    targets = claim["targets"]
    if not isinstance(targets, dict):
        raise EnvelopeError(f"{where}: targets must be an object")
    for key in TARGET_KEYS[role]:
        value = targets.get(key)
        if not isinstance(value, str) or not value.strip():
            raise EnvelopeError(f"{where}: targets.{key} must be a non-empty string")

    citations = claim["citations"]
    if not isinstance(citations, list) or not citations:
        raise EnvelopeError(f"{where}: citations must be a non-empty list (cite or abstain)")
    for j, citation in enumerate(citations):
        _validate_citation(citation, where=f"{where}.citations[{j}]")

    rationale = claim["rationale"]
    if not isinstance(rationale, str) or not rationale.strip():
        raise EnvelopeError(f"{where}: rationale must be a non-empty string")
    if len(rationale) > MAX_RATIONALE:
        raise EnvelopeError(f"{where}: rationale is {len(rationale)} chars; maximum is {MAX_RATIONALE}")

    return {key: claim[key] for key in ENVELOPE_KEYS}


def _validate_citation(citation: Any, where: str) -> None:
    if not isinstance(citation, dict):
        raise EnvelopeError(f"{where}: citation must be an object")
    if set(citation) != set(CITATION_KEYS):
        raise EnvelopeError(f"{where}: citation keys must be exactly {list(CITATION_KEYS)}")
    for key in ("path", "symbol"):
        value = citation[key]
        if not isinstance(value, str) or not value.strip():
            raise EnvelopeError(f"{where}: citation.{key} must be a non-empty string")
    line = citation["line"]
    if not isinstance(line, int) or isinstance(line, bool) or line < 1:
        raise EnvelopeError(f"{where}: citation.line must be an integer >= 1")


def _strict_json(text: str) -> Any:
    """The text itself must be the JSON document: no fences, no prose, no trailing
    content. json.loads already rejects trailing content; the fence check is ours."""
    if text.startswith("```") or text.endswith("```"):
        raise ValueError("markdown fences are not the envelope")
    return json.loads(text)


def claim_ref(claim: dict) -> str:
    """A short, stable reference for the rejection ledger."""
    targets = claim.get("targets") or {}
    target = (
        targets.get("test_id")
        or targets.get("symbol")
        or targets.get("changed_symbol")
        or targets.get("file")
        or "?"
    )
    return f"{claim.get('role', '?')}:{claim.get('claim_type', '?')}:{target}"
