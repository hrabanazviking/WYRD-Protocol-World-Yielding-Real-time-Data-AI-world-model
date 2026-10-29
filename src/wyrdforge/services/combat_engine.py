"""CombatEngine — the remembered fight's mutation service (Phase D1).

The companion to ``ecs/components/combat.py``: components carry the
state, this engine performs the fight's named acts — starting and
ending engagements, applying damage through the existing
``HealthComponent``, applying effects on temporal anchors, and
expiring them — and announces each act on the EventBus.

Truth-ownership (roadmap §6): the host owns resolution. This engine
never decides whether an attack hits, how much damage a weapon
"should" do, or who wins. The host calls :meth:`apply_damage` with
the amount IT resolved; the engine records it through
``HealthComponent.take_damage`` (the one existing vitality path —
no second hp bookkeeping is invented) and emits
``combat.damage_applied``.

Event topics (house dotted convention, §6 names under ``combat.``)::

    combat.engagement_started   {engagement_id, participant_ids, anchor_entity_id}
    combat.damage_applied       {target_id, source_id, amount, hp_after, max_hp, alive, wounded}
    combat.effect_applied       {effect_id, target_id, source_id, name, kind, magnitude, expires_at}
    combat.effect_expired       {effect_id, target_id, source_id, name, kind, magnitude}
    combat.engagement_ended     {engagement_id, participant_ids, state}

Bus posture follows the house: the engine is bus-optional
(``bus=None`` preserves call-only behaviour, exactly as ``World``),
registers its topics idempotently, and publishes AFTER the state
mutation — a failing bus never breaks combat semantics (publishes
are wrapped like ``World._emit``).

Tempo (one model, two clocks — B5): :meth:`initiative_order` reads
a :class:`WorldClock`. In deterministic mode the order is the
combatants' ``initiative`` (descending, entity_id tie-break). In
wall-sync mode the order is readiness: combatants ready at
``clock.current_time()`` first (by earliest cooldown expiry, then
initiative), the rest after — cooldown timestamps, not initiative,
own live tempo.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import wyrdforge.ecs.components.combat  # noqa: F401  (registration)
import wyrdforge.ecs.components.temporal  # noqa: F401  (registration)
from wyrdforge.ecs.components.character import HealthComponent
from wyrdforge.ecs.components.combat import (
    CombatantComponent,
    EffectComponent,
    EngagementComponent,
)
from wyrdforge.ecs.components.temporal import TemporalAnchorComponent, WorldClock
from wyrdforge.ecs.entity import _new_id
from wyrdforge.ecs.world import World

if TYPE_CHECKING:
    from wyrdforge.runtime.events import EventBus


def _now() -> datetime:
    return datetime.now(timezone.utc)


#: Topics emitted by CombatEngine when wired to an EventBus.
COMBAT_TOPICS = (
    "combat.engagement_started",
    "combat.damage_applied",
    "combat.effect_applied",
    "combat.effect_expired",
    "combat.engagement_ended",
)


def _register_combat_topics(bus: "EventBus") -> None:
    """Register the combat.* topics once; tolerate double registration."""
    for topic in COMBAT_TOPICS:
        try:
            bus.register_topic(topic)
        except (ValueError, KeyError):
            pass  # already registered — another producer got here first


class CombatEngine:
    """Deterministic mutation service for combat state.

    Args:
        world: The ECS World to operate on.
        bus:   Optional EventBus for combat.* announcements. When
               omitted, the World's own bus (if it was constructed
               with one) is NOT silently reused — pass a bus
               explicitly so announcement wiring is a stated choice.
    """

    def __init__(self, world: World, *, bus: "EventBus | None" = None) -> None:
        self._world = world
        self._bus = bus
        if self._bus is not None:
            _register_combat_topics(self._bus)

    @property
    def world(self) -> World:
        return self._world

    # ------------------------------------------------------------------
    # Engagements
    # ------------------------------------------------------------------

    def start_engagement(
        self,
        participant_ids: list[str],
        *,
        engagement_id: str | None = None,
        anchor_entity_id: str | None = None,
        label: str = "",
        at: datetime | None = None,
        anchor_position: tuple[float, float, float] | None = None,
        frame_id: str | None = None,
    ) -> str:
        """Create an engagement entity and return its id.

        The engagement entity carries the EngagementComponent and —
        when a position is known — a B3 PositionComponent anchor:
        ``anchor_position`` wins when given, else the anchor
        entity's current position is copied when it has one.
        Participants who carry a CombatantComponent are marked
        engaged with this engagement; participants without one are
        still recorded (a bystander-turned-participant may gain the
        component later — the engagement is the fight's truth, the
        component is per-combatant state).
        """
        eid = engagement_id or _new_id()
        started = at if at is not None else _now()
        self._world.create_entity(entity_id=eid, tags={"engagement"})
        comp = EngagementComponent(
            entity_id=eid,
            participant_ids=list(dict.fromkeys(participant_ids)),
            state="skirmish",
            anchor_entity_id=anchor_entity_id,
            label=label,
            started_at=started,
        )
        self._world.add_component(eid, comp)

        # Spatial anchor on the B3 core: an explicit position, else
        # a copy of the anchor entity's position when it has one.
        pos = anchor_position
        if pos is None and anchor_entity_id is not None:
            anchor_pos = self._world.get_position(anchor_entity_id)
            if anchor_pos is not None:
                pos = anchor_pos.position
                if frame_id is None:
                    frame_id = anchor_pos.frame_id
        if pos is not None:
            self._world.set_position(eid, pos[0], pos[1], pos[2], frame_id=frame_id)

        for pid in comp.participant_ids:
            combatant = self._world.get_component(pid, "combatant")
            if isinstance(combatant, CombatantComponent):
                combatant.engage(eid)
        self._emit("combat.engagement_started", {
            "engagement_id": eid,
            "participant_ids": list(comp.participant_ids),
            "anchor_entity_id": anchor_entity_id,
        })
        return eid

    def join_engagement(self, engagement_id: str, entity_id: str) -> None:
        comp = self._require_engagement(engagement_id)
        comp.add_participant(entity_id)
        combatant = self._world.get_component(entity_id, "combatant")
        if isinstance(combatant, CombatantComponent):
            combatant.engage(engagement_id)

    def leave_engagement(self, engagement_id: str, entity_id: str) -> bool:
        comp = self._require_engagement(engagement_id)
        removed = comp.remove_participant(entity_id)
        combatant = self._world.get_component(entity_id, "combatant")
        if isinstance(combatant, CombatantComponent) and combatant.engagement_id == engagement_id:
            combatant.leave_engagement()
        return removed

    def transition_engagement(
        self, engagement_id: str, new_state: str, *, at: datetime | None = None
    ) -> EngagementComponent:
        """Advance the lifecycle (skirmish → engaged → broken → ended).

        Reaching ``ended`` clears participants' engagement refs and
        emits ``combat.engagement_ended``.
        """
        comp = self._require_engagement(engagement_id)
        comp.transition_to(new_state, at=at)  # type: ignore[arg-type]
        if new_state == "ended":
            for pid in list(comp.participant_ids):
                combatant = self._world.get_component(pid, "combatant")
                if isinstance(combatant, CombatantComponent) and combatant.engagement_id == engagement_id:
                    combatant.leave_engagement()
            self._emit("combat.engagement_ended", {
                "engagement_id": engagement_id,
                "participant_ids": list(comp.participant_ids),
                "state": comp.state,
            })
        return comp

    def end_engagement(self, engagement_id: str, *, at: datetime | None = None) -> EngagementComponent:
        return self.transition_engagement(engagement_id, "ended", at=at)

    # ------------------------------------------------------------------
    # Damage — through HealthComponent, never around it
    # ------------------------------------------------------------------

    def apply_damage(
        self,
        target_id: str,
        amount: float,
        *,
        source_id: str = "",
    ) -> HealthComponent:
        """Apply host-resolved damage via ``HealthComponent.take_damage``.

        Emits ``combat.damage_applied`` with the post-damage vitality
        state. A target brought to 0 hp is marked ``down`` on its
        CombatantComponent when it has one (health's ``alive`` flag
        remains the vitality truth — ``down`` is the fight stance
        that follows from it). Raises KeyError when the target has
        no HealthComponent: damage with nowhere to land is a caller
        bug, not a state to invent.
        """
        health = self._world.get_component(target_id, "health")
        if not isinstance(health, HealthComponent):
            raise KeyError(f"entity '{target_id}' has no HealthComponent to damage")
        health.take_damage(amount)
        if not health.alive:
            combatant = self._world.get_component(target_id, "combatant")
            if isinstance(combatant, CombatantComponent):
                combatant.mark_down()
        self._emit("combat.damage_applied", {
            "target_id": target_id,
            "source_id": source_id,
            "amount": float(amount),
            "hp_after": health.hp,
            "max_hp": health.max_hp,
            "alive": health.alive,
            "wounded": health.wounded,
        })
        return health

    # ------------------------------------------------------------------
    # Effects — on TemporalAnchor validity windows
    # ------------------------------------------------------------------

    def apply_effect(
        self,
        target_id: str,
        *,
        name: str = "",
        kind: str = "",
        source_id: str = "",
        magnitude: float = 0.0,
        duration_seconds: float | None = None,
        at: datetime | None = None,
        expires_at: datetime | None = None,
        effect_id: str | None = None,
    ) -> str:
        """Create an effect entity riding a TemporalAnchor window.

        The effect entity carries BOTH the EffectComponent and a
        TemporalAnchorComponent with ``valid_from = at`` and
        ``valid_until = expires_at`` (explicit, else
        ``at + duration_seconds``, else None = open-ended). Returns
        the effect entity's id. Emits ``combat.effect_applied``.
        """
        applied = at if at is not None else _now()
        until = expires_at
        if until is None and duration_seconds is not None:
            if duration_seconds < 0:
                raise ValueError("duration_seconds must be non-negative")
            until = applied + timedelta(seconds=duration_seconds)
        eid = effect_id or _new_id()
        self._world.create_entity(entity_id=eid, tags={"effect"})
        self._world.add_component(eid, EffectComponent(
            entity_id=eid,
            name=name,
            kind=kind,
            source_entity_id=source_id,
            target_entity_id=target_id,
            magnitude=float(magnitude),
            applied_at=applied,
            expires_at=until,
        ))
        self._world.add_component(eid, TemporalAnchorComponent(
            entity_id=eid,
            valid_from=applied,
            valid_until=until,
            observed_at=applied,
            label=name or kind,
        ))
        self._emit("combat.effect_applied", {
            "effect_id": eid,
            "target_id": target_id,
            "source_id": source_id,
            "name": name,
            "kind": kind,
            "magnitude": float(magnitude),
            "expires_at": until.isoformat() if until is not None else None,
        })
        return eid

    def tick_effects(self, now: datetime) -> list[str]:
        """Expire every effect whose window has passed at ``now``.

        Each newly expired effect is marked (``expired=True``) and
        announced exactly once via ``combat.effect_expired``; a
        second tick over the same effect emits nothing. Returns the
        effect ids expired by THIS tick, in entity_id order for
        determinism. Expiry is judged by the effect entity's
        TemporalAnchor when present (the tense truth), else by the
        component's own ``expires_at``.
        """
        expired_now: list[str] = []
        pairs = [
            (entity, comp)
            for entity, comp in self._world.iter_components("effect")
            if isinstance(comp, EffectComponent)
        ]
        for entity, comp in sorted(pairs, key=lambda pair: pair[0].entity_id):
            if comp.expired:
                continue
            anchor = self._world.get_component(entity.entity_id, "temporal_anchor")
            anchor = anchor if isinstance(anchor, TemporalAnchorComponent) else None
            if comp.is_expired(now, anchor):
                comp.expired = True
                comp.touch()
                expired_now.append(entity.entity_id)
                self._emit("combat.effect_expired", {
                    "effect_id": entity.entity_id,
                    "target_id": comp.target_entity_id,
                    "source_id": comp.source_entity_id,
                    "name": comp.name,
                    "kind": comp.kind,
                    "magnitude": comp.magnitude,
                })
        return expired_now

    def active_effects_on(self, target_id: str, now: datetime) -> list[EffectComponent]:
        """Live (unexpired at ``now``) effects riding on a target."""
        out: list[EffectComponent] = []
        for _entity, comp in self._world.iter_components("effect"):
            if not isinstance(comp, EffectComponent):
                continue
            if comp.target_entity_id != target_id:
                continue
            anchor = self._world.get_component(comp.entity_id, "temporal_anchor")
            anchor = anchor if isinstance(anchor, TemporalAnchorComponent) else None
            if comp.is_active(now, anchor):
                out.append(comp)
        out.sort(key=lambda c: c.entity_id)
        return out

    # ------------------------------------------------------------------
    # Tempo & initiative — one model, two clocks
    # ------------------------------------------------------------------

    def initiative_order(
        self,
        clock: WorldClock,
        *,
        engagement_id: str | None = None,
    ) -> list[str]:
        """Acting order for combatants, per the clock's mode.

        Deterministic mode: ``initiative`` descending, entity_id
        tie-break — the order is a pure function of the components.
        Wall-sync mode: combatants READY at ``clock.current_time()``
        first (initiative descending among themselves), then the
        not-ready by earliest cooldown expiry (when each becomes
        ready, then initiative); down combatants sort last in both
        modes (they do not act).
        ``engagement_id`` restricts the order to that engagement's
        participants.
        """
        allowed: set[str] | None = None
        if engagement_id is not None:
            allowed = set(self._require_engagement(engagement_id).participant_ids)
        combatants: list[tuple[str, CombatantComponent]] = []
        for entity, comp in self._world.iter_components("combatant"):
            if not isinstance(comp, CombatantComponent):
                continue
            if allowed is not None and entity.entity_id not in allowed:
                continue
            combatants.append((entity.entity_id, comp))

        if clock.mode == "wall":
            now = clock.current_time()

            def wall_key(pair: tuple[str, CombatantComponent]):
                eid, comp = pair
                down = 1 if comp.stance == "down" else 0
                ready = 0 if comp.is_ready_at(now) else 1
                # Among the READY, initiative orders (cooldown is
                # history, not a queue position); among the NOT-ready,
                # earliest cooldown expiry — when each becomes ready —
                # orders, then initiative.
                cooldown = (
                    comp.cooldown_until or datetime.max.replace(tzinfo=timezone.utc)
                ) if ready else datetime.min.replace(tzinfo=timezone.utc)
                return (down, ready, cooldown, -comp.initiative, eid)

            combatants.sort(key=wall_key)
        else:

            def det_key(pair: tuple[str, CombatantComponent]):
                eid, comp = pair
                down = 1 if comp.stance == "down" else 0
                return (down, -comp.initiative, eid)

            combatants.sort(key=det_key)
        return [eid for eid, _ in combatants]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_engagement(self, engagement_id: str) -> EngagementComponent:
        comp = self._world.get_component(engagement_id, "engagement")
        if not isinstance(comp, EngagementComponent):
            raise KeyError(f"entity '{engagement_id}' is not an engagement")
        return comp

    def _emit(self, topic: str, payload: dict) -> None:
        """Publish after mutation; a failing bus never breaks combat."""
        if self._bus is None:
            return
        try:
            self._bus.publish(topic, payload, source="combat.engine")
        except Exception:
            pass
