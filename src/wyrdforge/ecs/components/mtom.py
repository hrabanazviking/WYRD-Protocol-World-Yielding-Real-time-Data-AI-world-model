"""Metaphysical Theory of Mind (Level 101) as world-model machinery.

Implements the five core rules of the Metaphysical Theory of Mind for AI
as deterministic ECS components and validators:

1. **Default State — Anchoring in Manifest Reality.** Every claim is
   ``MANIFEST`` unless explicitly invoked otherwise. The default is the
   present physical here/now, never a brainstorm.
2. **Potential State — Explicit Invocation.** Metaphysical, future,
   creative, or counterfactual spaces exist and are valid — but only
   inside a :class:`PotentialSpace` opened by explicit invocation, with
   the invoker and reason recorded.
3. **Zero-Bleed Boundary.** Information cannot leak across reality states
   without authorization. :func:`assert_zero_bleed` raises
   :class:`ZeroBleedError` the moment a POTENTIAL-tagged claim is read as
   manifest ground truth. This is the structural fix for the classic AI
   failure of projecting a user's explored possibilities onto their
   present reality.
4. **Axiom of Explicit Subjectivity.** Zero speculation about minds.
   :func:`explicit_subjectivity_check` flags any belief whose confidence
   exceeds what its source warrants — ``assumed`` can never pose as
   ``observed``.
5. **Objective Observation of the Metaphysical.** Metaphysical claims are
   valid observations of existence beyond the physical — tagged
   ``POTENTIAL`` with their space, treated with respect, never dismissed
   and never silently promoted to manifest.

Fully deterministic and ECS-compatible — no LLM involvement.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar, Literal

from pydantic import Field

from wyrdforge.ecs.component import Component, register_component
from wyrdforge.models.common import StrictModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RealityState(str, Enum):
    MANIFEST = "manifest"    # present physical here/now — the default
    POTENTIAL = "potential"  # explicitly invoked: metaphysical, future, creative


@register_component
class RealityStateComponent(Component):
    """Tags a claim, fact, or belief with its reality state.

    Rule 1: the default is MANIFEST. POTENTIAL requires an explicit
    invocation recorded in ``invoked_by`` / ``invocation_reason``.
    """

    _type_key: ClassVar[str] = "reality_state"
    component_type: Literal["reality_state"] = "reality_state"

    state: RealityState = RealityState.MANIFEST
    invoked_by: str = ""          # entity/user that explicitly invoked the space
    invocation_reason: str = ""   # why the potential space was opened
    invoked_at: datetime | None = None

    def invoke_potential(self, invoked_by: str, reason: str) -> None:
        """Rule 2: open a potential state by explicit invocation."""
        invoked_by = (invoked_by or "").strip()
        reason = (reason or "").strip()
        if not invoked_by or not reason:
            raise ValueError("Potential state requires an explicit invoker and reason")
        self.state = RealityState.POTENTIAL
        self.invoked_by = invoked_by
        self.invocation_reason = reason
        self.invoked_at = _now()
        self.touch()

    def anchor_manifest(self) -> None:
        """Rule 1: return this claim to manifest reality."""
        self.state = RealityState.MANIFEST
        self.invoked_by = ""
        self.invocation_reason = ""
        self.invoked_at = None
        self.touch()


class PotentialSpace(StrictModel):
    """An explicitly invoked potential reality.

    A bounded space — metaphysical exploration, future planning, creative
    brainstorming — whose contents are valid *inside* the space and must
    never bleed into manifest ground truth (Rule 3).
    """

    space_id: str
    invoked_by: str
    reason: str
    opened_at: datetime = Field(default_factory=_now)
    closed_at: datetime | None = None
    claim_ids: list[str] = Field(default_factory=list)

    def add_claim(self, claim_id: str) -> None:
        if claim_id not in self.claim_ids:
            self.claim_ids.append(claim_id)

    def close(self) -> None:
        self.closed_at = _now()

    @property
    def is_open(self) -> bool:
        return self.closed_at is None


class ZeroBleedError(RuntimeError):
    """Raised when a POTENTIAL claim is read as manifest ground truth."""


def assert_zero_bleed(state: RealityStateComponent, *, as_manifest: bool,
                      context: str = "") -> None:
    """Rule 3: the firewall.

    Call this wherever the oracle (or any consumer) reads a claim *as
    manifest ground truth*. If the claim is POTENTIAL-tagged, the read
    is refused loudly instead of silently corrupting the world model.
    """
    if as_manifest and state.state is RealityState.POTENTIAL:
        where = f" in {context}" if context else ""
        raise ZeroBleedError(
            f"Zero-bleed violation{where}: claim tagged POTENTIAL "
            f"(invoked by '{state.invoked_by}' for '{state.invocation_reason}') "
            f"cannot be read as manifest ground truth. Invoke the potential "
            f"space explicitly or anchor the claim in manifest reality first.")


def require_manifest(state: RealityStateComponent, context: str = "") -> RealityStateComponent:
    """Convenience: assert a claim is manifest-readable, else raise."""
    assert_zero_bleed(state, as_manifest=True, context=context)
    return state


# ---------------------------------------------------------------------------
# Rule 4 — Axiom of Explicit Subjectivity
# ---------------------------------------------------------------------------

# Maximum confidence each belief source warrants. A belief more confident
# than its source is speculation wearing certainty's clothes.
_SOURCE_WARRANT: dict[str, float] = {
    "observed": 1.0,
    "told": 0.9,
    "inferred": 0.7,
    "assumed": 0.4,
}


def explicit_subjectivity_check(source: str, confidence: float) -> str | None:
    """Rule 4: flag speculation.

    Returns a warning string when ``confidence`` exceeds what ``source``
    warrants, else None. ``assumed`` can never pose as ``observed``.
    """
    warrant = _SOURCE_WARRANT.get(source)
    if warrant is None:
        return f"unknown belief source '{source}' — cannot warrant any confidence"
    if confidence > warrant + 1e-9:
        return (f"speculation: confidence {confidence:.2f} exceeds the "
                f"'{source}' warrant of {warrant:.2f}")
    return None


def partition_by_reality(states: list[RealityStateComponent]) -> dict[str, list[RealityStateComponent]]:
    """Split tagged claims for oracle-facing code: manifest ground truth
    versus potential-space contents. The oracle must never merge these
    silently (Rule 3)."""
    out: dict[str, list[RealityStateComponent]] = {"manifest": [], "potential": []}
    for s in states:
        out["potential" if s.state is RealityState.POTENTIAL else "manifest"].append(s)
    return out
