"""Subagent dispatch rules (Person B, deliverable B6 / person_b.txt section 7).

  1. scout         PARALLEL, one subagent per candidate pair. Disjoint inputs by
                   construction; independent claims, independently verified.
  2. cartographer  PARALLEL, one per file. Independent.
  3. author        PARALLEL, one subagent per uncovered symbol, ONE FILE EACH. If
                   two symbols live in the same test file they are NOT parallel --
                   they are serialised, or you get a conflicting edit. NEVER two
                   writers on one file. This is the rule teams break first.
  4. falsifier     SEQUENTIAL, after the ledger is final, ALONE.
  5. Every subagent starts with a CLEAN context window containing ONLY its bundle
                   and returns ONLY a claim envelope. Its intermediate reasoning
                   must not enter the main thread.
  6. Never more than two model tiers per unit (enforced in cascade.run_cascade).
  7. EVERY claim goes to testscope_verify, including the ones you are confident in.
                   There is no fast path around the kernel.

Rules 3 and 5 are enforced by CODE here -- a registry that refuses a second writer,
and a subagent boundary that can only return validated claims.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from . import context, envelope
from .errors import SequentialRoleInParallel, TwoWritersOneFile

PARALLEL_ROLES = ("scout", "cartographer", "author")
SEQUENTIAL_ROLES = ("falsifier",)


@dataclass
class WriterRegistry:
    """One writer per file AT A TIME, asserted in code rather than by eye.

    A claim is held while a wave runs and released when it finishes; two waves of
    the same file are serial by construction, which is exactly the fix for "two
    symbols in one test file".
    """

    owners: dict[str, tuple[str, str]] = field(default_factory=dict)

    def claim_file(self, path: str, *, role: str, unit_id: str) -> None:
        current = self.owners.get(path)
        if current is None:
            self.owners[path] = (role, unit_id)
            return
        if current == (role, unit_id):
            return
        raise TwoWritersOneFile(
            f"{path!r} is already claimed by {current[0]}/{current[1]}; "
            f"{role}/{unit_id} may not write it (serialise instead)"
        )

    def release(self, path: str) -> None:
        self.owners.pop(path, None)

    def owner_of(self, path: str) -> tuple[str, str] | None:
        return self.owners.get(path)


def assert_parallelisable(role: str) -> None:
    """The falsifier is the only non-parallel role: parallelising it would give it
    conflicting assumptions about the ledger."""
    if role in SEQUENTIAL_ROLES:
        raise SequentialRoleInParallel(
            f"{role} runs sequentially and alone (section 7); it may not join a parallel wave"
        )


def default_file_of(unit: dict[str, Any]) -> str:
    return str(unit.get("target_file") or unit.get("test_class_file") or unit.get("unit_id") or "?")


def assert_no_parallel_writers(wave: Sequence[dict], *, file_of: Callable[[dict], str] = default_file_of) -> None:
    seen: dict[str, str] = {}
    for unit in wave:
        path = file_of(unit)
        if path in seen:
            raise TwoWritersOneFile(
                f"two units in one parallel wave write {path!r}: "
                f"{seen[path]} and {_unit_name(unit)}"
            )
        seen[path] = _unit_name(unit)


def plan_waves(
    units: Sequence[dict],
    *,
    file_of: Callable[[dict], str] = default_file_of,
    writers: WriterRegistry | None = None,
    role: str = "author",
) -> list[list[dict]]:
    """Schedule units so that no parallel wave contains two writers of one file.

    Groups are placed in deterministic order (by file path), so the same inputs
    always produce the same schedule. Each file claim goes through the registry.
    """
    if role in SEQUENTIAL_ROLES:
        raise SequentialRoleInParallel(f"{role} may not be scheduled as a parallel wave")

    groups: dict[str, list[dict]] = {}
    for unit in units:
        groups.setdefault(file_of(unit), []).append(unit)

    waves: list[list[dict]] = []
    for path in sorted(groups):
        for index, unit in enumerate(groups[path]):
            while len(waves) <= index:
                waves.append([])
            waves[index].append(unit)

    registry = writers if writers is not None else WriterRegistry()
    for wave in waves:
        assert_no_parallel_writers(wave, file_of=file_of)
        claimed: list[str] = []
        for unit in wave:
            path = file_of(unit)
            registry.claim_file(path, role=role, unit_id=_unit_name(unit))
            claimed.append(path)
        for path in claimed:
            registry.release(path)
    return waves


def invoke_subagent(role: str, bundle: dict[str, Any], model: Callable[[str], Any]) -> list[dict]:
    """One subagent, one clean context: rendered bundle in, claim envelope out.

    The subagent receives ONLY its bundle and returns ONLY validated claims. Its
    intermediate reasoning is not a return value and never reaches the main thread;
    prose instead of an envelope is a schema violation and is rejected, not parsed.
    """
    prompt = context.render_prompt(role, bundle)
    raw = model(prompt)
    return envelope.parse_claims(role, raw)


def _unit_name(unit: dict[str, Any]) -> str:
    return str(unit.get("unit_id") or unit.get("test_id") or unit.get("symbol") or "?")
