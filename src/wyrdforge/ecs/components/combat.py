"""Combat awareness components — Phase D1 (roadmap §6 / §9-D1).

WYRD owns the *remembered fight*; the host owns resolution. Dice,
physics, and hit resolution stay OUT of this module entirely: nothing
here rolls, hits, or misses. What lives here is the durable,
queryable state of a fight — who is fighting, in what stance, under
what effects, and who each participant *believes* threatens them.

Design, following the house patterns of the phases before it:

- :class:`CombatantComponent` composes with the existing
  ``HealthComponent`` / ``FactionComponent`` (character.py) rather
  than replacing them: health stays the vitality truth, faction
  stays the allegiance truth, and this component carries only the
  fight-specific state (stance, readiness, tempo timestamps) plus a
  *reference* to the faction (mirroring how ``PersonaRefComponent``
  references the memory layer instead of duplicating it).
- **Engagement is an entity**, not an edge: a fight is many-to-many,
  which edges model badly. The engagement entity carries an
  :class:`EngagementComponent` (participants, lifecycle) and — for
  its spatial anchor — an ordinary B3 ``PositionComponent``, so the
  anchor is queryable through the existing spatial core and there is
  no second positional truth.
- **Threat is perceived state.** A :class:`ThreatComponent` lives on
  the *observer*, holding that observer's own
  :class:`ThreatAssessment` per target, on the belief/MTOM machinery
  (``BeliefSource`` warrants from theory_of_mind, and each assessment
  projects to a :class:`~wyrdforge.ecs.components.theory_of_mind.Belief`).
  Two observers can therefore hold opposite assessments of the same
  target — a character can fear the wrong enemy, and the divergence
  is representable and measurable (:meth:`ThreatComponent.divergence_from`).
  There is deliberately NO global threat table: a world-level
  "true threat" would contradict the belief doctrine.
- **Effects are entities too.** One effect *instance* is one entity
  carrying an :class:`EffectComponent`; the entity ALSO carries a
  ``TemporalAnchorComponent`` whose validity window
  (``valid_from``/``valid_until``) is the effect's span — effects
  expire by the same tense machinery the engine already trusts.
  ``EffectComponent.expires_at`` mirrors the anchor's
  ``valid_until`` for direct reads, and the anchor wins when the two
  disagree (see :meth:`EffectComponent.is_expired`). The expiry
  *event* (``combat.effect_expired``) is emitted by
  ``services/combat_engine.CombatEngine.tick_effects`` — components
  themselves never publish, exactly as ``HealthComponent`` never does.
- **Tempo — one model, two clocks (B5).** In deterministic mode the
  initiative order (``initiative`` field, descending) owns tempo; in
  wall-clock mode tempo is the ``cooldown_until`` / ``last_acted_at``
  timestamps compared against ``WorldClock.current_time()``. Both
  live on the same component and the same helper
  (:meth:`CombatantComponent.is_ready_at`) works for either mode,
  because both modes ultimately hand the caller a ``now``.
- **Range bands are derived, never stored.** :func:`range_band`
  computes engaged/near/far from a B3 distance at query time; no
  component stores a band, so a band can never disagree with the
  positions it was derived from.

Persistence: all three components persist generically through
``WorldStore`` like B3's ``PositionComponent`` — no schema change,
no migration.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import ClassVar, Literal

from pydantic import Field

from wyrdforge.ecs.component import Component, register_component
from wyrdforge.ecs.components.theory_of_mind import Belief, BeliefSource
from wyrdforge.models.common import StrictModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Range bands — derived from B3 distances, never stored
# ---------------------------------------------------------------------------

#: Melee reach, in metres: at or below this distance two combatants
#: are *engaged* with each other.
ENGAGED_RANGE_M = 2.0

#: Near reach, in metres: at or below this (and beyond engaged) a
#: combatant is *near* — a move away from engagement.
NEAR_RANGE_M = 20.0

RangeBand = Literal["engaged", "near", "far"]


def range_band(distance: float | None) -> RangeBand | None:
    """The range band for a B3 distance, or None when undefined.

    ``None`` in (cross-frame / unpositioned — the B3 ``None``
    semantics) means ``None`` out: an undefined distance has no
    band, never an invented one.
    """
    if distance is None:
        return None
    if distance <= ENGAGED_RANGE_M:
        return "engaged"
    if distance <= NEAR_RANGE_M:
        return "near"
    return "far"


# ---------------------------------------------------------------------------
# Combatant
# ---------------------------------------------------------------------------

# §6 names engaged / withdrawing / down as the fight stances. An
# ``idle`` stance is added as the pre-engagement default: a combatant
# must be able to exist (persisted, queryable) before it joins any
# engagement, and defaulting a not-yet-fighting entity to "engaged"
# would be a false claim. Recorded as a design finding in the
# campaign state file.
CombatantStance = Literal["idle", "engaged", "withdrawing", "down"]


@register_component
class CombatantComponent(Component):
    """Fight state of one combatant entity.

    Composes with ``HealthComponent`` (vitality) and
    ``FactionComponent`` (allegiance): ``faction_id`` here is a
    *reference* snapshot for combat queries, not a replacement —
    ``FactionComponent`` remains the allegiance truth and callers
    keep the two in step when faction changes mid-fight matter.

    Attributes:
        stance:         idle / engaged / withdrawing / down.
        readiness:      0.0 (spent) .. 1.0 (fully ready) — the host's
                        readiness bookkeeping, carried not judged.
        faction_id:     Faction reference (mirrors FactionComponent).
        engagement_id:  The engagement entity this combatant is
                        currently part of, or None.
        initiative:     Deterministic-mode tempo: higher acts first
                        (ties break by entity_id — see CombatEngine).
        last_acted_at:  World-time of the combatant's last action
                        (wall-mode tempo).
        cooldown_until: World-time until which the combatant is on
                        cooldown (wall-mode tempo); None = no cooldown.
    """

    _type_key: ClassVar[str] = "combatant"
    component_type: Literal["combatant"] = "combatant"

    stance: CombatantStance = "idle"
    readiness: float = Field(default=1.0, ge=0.0, le=1.0)
    faction_id: str = ""
    engagement_id: str | None = None
    initiative: int = 0
    last_acted_at: datetime | None = None
    cooldown_until: datetime | None = None

    # -- stance -------------------------------------------------------

    def engage(self, engagement_id: str | None = None) -> None:
        self.stance = "engaged"
        if engagement_id is not None:
            self.engagement_id = engagement_id
        self.touch()

    def withdraw(self) -> None:
        self.stance = "withdrawing"
        self.touch()

    def mark_down(self) -> None:
        """The combatant is down (host decided; WYRD remembers)."""
        self.stance = "down"
        self.touch()

    def leave_engagement(self) -> None:
        self.engagement_id = None
        if self.stance in ("engaged", "withdrawing"):
            self.stance = "idle"
        self.touch()

    @property
    def is_down(self) -> bool:
        return self.stance == "down"

    # -- tempo (two clocks, one model) ---------------------------------

    def is_ready_at(self, now: datetime) -> bool:
        """True when the combatant can act at world-time ``now``.

        Works for both WorldClock modes: the caller passes
        ``clock.now`` (deterministic) or ``clock.current_time()``
        (wall-sync). A down combatant is never ready; a combatant
        whose cooldown has not yet elapsed is not ready.
        """
        if self.stance == "down":
            return False
        if self.cooldown_until is not None and self.cooldown_until > now:
            return False
        return True

    def begin_cooldown(self, seconds: float, *, now: datetime) -> datetime:
        """Put the combatant on cooldown for ``seconds`` from ``now``.

        Records ``last_acted_at = now`` and returns the new
        ``cooldown_until``. Negative spans are rejected — a cooldown
        that ends before it starts is a caller bug, not a state.
        """
        if seconds < 0:
            raise ValueError(f"cooldown seconds must be non-negative, got {seconds}")
        self.last_acted_at = now
        self.cooldown_until = now + timedelta(seconds=seconds)
        self.touch()
        return self.cooldown_until

    def clear_cooldown(self) -> None:
        self.cooldown_until = None
        self.touch()


# ---------------------------------------------------------------------------
# Engagement — a component on the engagement ENTITY
# ---------------------------------------------------------------------------

EngagementState = Literal["skirmish", "engaged", "broken", "ended"]

#: The lifecycle (§6: skirmish → engaged → broken → ended). ``broken``
#: may also be reached straight from skirmish, and any live state may
#: end directly; ``ended`` is terminal. Anything else (e.g. broken →
#: engaged, ended → anything) raises — a fight that resumes is a NEW
#: engagement, not a resurrection of the ended one.
_ENGAGEMENT_TRANSITIONS: dict[str, frozenset[str]] = {
    "skirmish": frozenset({"engaged", "broken", "ended"}),
    "engaged": frozenset({"broken", "ended"}),
    "broken": frozenset({"ended"}),
    "ended": frozenset(),
}


@register_component
class EngagementComponent(Component):
    """One fight, as an entity's component.

    The component lives on the engagement entity itself (whose
    entity_id IS the engagement id). The engagement entity should
    also carry a B3 ``PositionComponent`` as its spatial anchor and
    may carry a ``TemporalAnchorComponent`` for its span.

    Attributes:
        participant_ids: Combatant entity ids in the fight.
        state:           Lifecycle state (see _ENGAGEMENT_TRANSITIONS).
        anchor_entity_id: Optional entity the fight is anchored to
                         (a place, a vehicle, a defended person).
        label:           Short human tag, e.g. "ambush at the ford".
        started_at:      World-time the engagement began (caller-set
                         from its WorldClock; defaults to real now).
        ended_at:        World-time it ended, or None while live.
    """

    _type_key: ClassVar[str] = "engagement"
    component_type: Literal["engagement"] = "engagement"

    participant_ids: list[str] = Field(default_factory=list)
    state: EngagementState = "skirmish"
    anchor_entity_id: str | None = None
    label: str = ""
    started_at: datetime = Field(default_factory=_now)
    ended_at: datetime | None = None

    @property
    def is_live(self) -> bool:
        return self.state != "ended"

    def has_participant(self, entity_id: str) -> bool:
        return entity_id in self.participant_ids

    def add_participant(self, entity_id: str) -> bool:
        """Add a participant; False when already present or ended."""
        if self.state == "ended":
            raise ValueError("cannot add a participant to an ended engagement")
        if entity_id in self.participant_ids:
            return False
        self.participant_ids.append(entity_id)
        self.touch()
        return True

    def remove_participant(self, entity_id: str) -> bool:
        """Remove a participant; True when one was present."""
        if entity_id in self.participant_ids:
            self.participant_ids.remove(entity_id)
            self.touch()
            return True
        return False

    def can_transition_to(self, new_state: str) -> bool:
        return new_state in _ENGAGEMENT_TRANSITIONS[self.state]

    def transition_to(self, new_state: EngagementState, *, at: datetime | None = None) -> None:
        """Move along the lifecycle; invalid moves raise ValueError."""
        if new_state == self.state:
            return
        if not self.can_transition_to(new_state):
            raise ValueError(
                f"engagement cannot move {self.state} -> {new_state}; "
                f"allowed: {sorted(_ENGAGEMENT_TRANSITIONS[self.state]) or 'none (terminal)'}"
            )
        self.state = new_state
        if new_state == "ended":
            self.ended_at = at if at is not None else _now()
        self.touch()


# ---------------------------------------------------------------------------
# Threat — per-observer perceived state, on the belief machinery
# ---------------------------------------------------------------------------

class ThreatAssessment(StrictModel):
    """One observer's assessment of one target's threat.

    This is a BELIEF, not a fact: it carries its epistemic source
    (the MTOM ``BeliefSource`` vocabulary) and the events it rests
    on, so a downstream reader can weigh it exactly as it weighs any
    other belief — and an ``assumed`` assessment can never pose as an
    ``observed`` one.

    Attributes:
        target_id:       The entity assessed as threatening.
        level:           Perceived threat, 0.0 (none) .. 1.0 (extreme).
        basis_event_ids: Event/record ids the assessment rests on
                         (the §6 "basis events").
        source:          How the assessment was formed.
        confidence:      0.0..1.0, the observer's confidence in it.
        assessed_at:     World-time of the assessment.
    """

    target_id: str
    level: float = Field(default=0.0, ge=0.0, le=1.0)
    basis_event_ids: list[str] = Field(default_factory=list)
    source: BeliefSource = "assumed"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    assessed_at: datetime = Field(default_factory=_now)

    def to_belief(self) -> Belief:
        """Project this assessment onto the shared Belief shape."""
        return Belief(
            subject=self.target_id,
            claim=f"threat level {self.level:.2f}",
            confidence=self.confidence,
            source=self.source,
            formed_at=self.assessed_at,
        )


@register_component
class ThreatComponent(Component):
    """What THIS entity believes threatens it (and how much).

    One component per observer; assessments are keyed by target.
    Because the state is per-observer, divergence is intrinsic: two
    observers' components over the same target are two independent
    objects and can disagree arbitrarily — see
    :meth:`divergence_from`.
    """

    _type_key: ClassVar[str] = "threats"
    component_type: Literal["threats"] = "threats"

    assessments: dict[str, ThreatAssessment] = Field(default_factory=dict)

    def assess(
        self,
        target_id: str,
        level: float,
        *,
        basis_event_ids: list[str] | None = None,
        source: BeliefSource = "assumed",
        confidence: float = 0.5,
        at: datetime | None = None,
    ) -> ThreatAssessment:
        """Record (or revise) this observer's assessment of a target."""
        assessment = ThreatAssessment(
            target_id=target_id,
            level=max(0.0, min(1.0, level)),
            basis_event_ids=list(basis_event_ids or []),
            source=source,
            confidence=max(0.0, min(1.0, confidence)),
            assessed_at=at if at is not None else _now(),
        )
        self.assessments[target_id] = assessment
        self.touch()
        return assessment

    def get_assessment(self, target_id: str) -> ThreatAssessment | None:
        return self.assessments.get(target_id)

    def level_for(self, target_id: str) -> float | None:
        """Perceived level for a target, or None if never assessed.

        None — not 0.0 — for an unassessed target: "never considered
        them" and "considered them harmless" are different beliefs.
        """
        assessment = self.assessments.get(target_id)
        return assessment.level if assessment is not None else None

    def retract(self, target_id: str) -> bool:
        if target_id in self.assessments:
            del self.assessments[target_id]
            self.touch()
            return True
        return False

    def targets_above(self, threshold: float) -> list[ThreatAssessment]:
        """Assessments at or above ``threshold``, most threatening first.

        Order is total and deterministic: ``(-level, target_id)``.
        """
        found = [a for a in self.assessments.values() if a.level >= threshold]
        found.sort(key=lambda a: (-a.level, a.target_id))
        return found

    def divergence_from(self, other: "ThreatComponent") -> dict[str, tuple[float | None, float | None]]:
        """Where this observer's threat picture differs from another's.

        Returns ``{target_id: (my_level, their_level)}`` for every
        target either observer assessed where the two disagree
        (including targets only one of them has assessed at all —
        a level of None on the side that never assessed it). Equal
        assessments are agreement and are not reported.
        """
        out: dict[str, tuple[float | None, float | None]] = {}
        for target_id in sorted(set(self.assessments) | set(other.assessments)):
            mine = self.level_for(target_id)
            theirs = other.level_for(target_id)
            if mine != theirs:
                out[target_id] = (mine, theirs)
        return out


# ---------------------------------------------------------------------------
# Effects over time — one effect instance per entity
# ---------------------------------------------------------------------------

@register_component
class EffectComponent(Component):
    """One running effect (poison, buff, wound, blessing, …).

    The component lives on its own effect entity; that entity should
    ALSO carry a ``TemporalAnchorComponent`` whose
    ``valid_from``/``valid_until`` window is the effect's span
    (``CombatEngine.apply_effect`` attaches both). Expiry is judged
    against the anchor when one is supplied to the check, else
    against ``expires_at`` — and when both exist the ANCHOR wins,
    because the anchor is the engine's tense truth and ``expires_at``
    is a convenience mirror of it.

    Attributes:
        name:              Human/mechanical name, e.g. "nightshade".
        kind:              Free-form kind tag: poison/buff/wound/…
        source_entity_id:  Who/what applied the effect ("" if none).
        target_entity_id:  The entity the effect rides on.
        magnitude:         Strength in the host's units — WYRD
                           carries it, never interprets it.
        applied_at:        World-time the effect began.
        expires_at:        World-time it ends, or None (until removed).
        expired:           Set by CombatEngine.tick_effects when the
                           expiry event has been emitted, so an effect
                           expires (and announces) exactly once.
    """

    _type_key: ClassVar[str] = "effect"
    component_type: Literal["effect"] = "effect"

    name: str = ""
    kind: str = ""
    source_entity_id: str = ""
    target_entity_id: str = ""
    magnitude: float = 0.0
    applied_at: datetime = Field(default_factory=_now)
    expires_at: datetime | None = None
    expired: bool = False

    def is_expired(self, now: datetime, anchor=None) -> bool:
        """True when the effect's span has fully passed at ``now``.

        ``anchor`` (a TemporalAnchorComponent on the same entity)
        wins when given: its ``has_expired`` is the tense truth.
        """
        if anchor is not None:
            return anchor.has_expired(now)
        return self.expires_at is not None and self.expires_at <= now

    def is_active(self, now: datetime, anchor=None) -> bool:
        if self.expired:
            return False
        if self.applied_at > now:
            return False
        return not self.is_expired(now, anchor)

    def remaining(self, now: datetime, anchor=None) -> timedelta | None:
        """Time left at ``now``; None when open-ended, 0 when expired."""
        if self.is_expired(now, anchor):
            return timedelta(0)
        until = None
        if anchor is not None and anchor.valid_until is not None:
            until = anchor.valid_until
        elif self.expires_at is not None:
            until = self.expires_at
        if until is None:
            return None
        return until - now
