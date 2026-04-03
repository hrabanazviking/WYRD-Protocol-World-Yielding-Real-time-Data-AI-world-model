"""RunicEngine — deterministic update service for runic metaphysics components.

Operates on ECS entities that carry HamingjaComponent, RunicChargeComponent,
or AncestralResonanceComponent.  All operations are pure in-memory mutations
of component state; no LLM calls, no I/O.

Typical usage::

    engine = RunicEngine(world)
    engine.invoke_rune("sigrid", "fehu", strength=0.6)
    engine.tick()            # apply decay + hamingja drift for all entities
    report = engine.report("sigrid")
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from wyrdforge.ecs.components.runic import (
    AncestralResonanceComponent,
    HamingjaComponent,
    RunicChargeComponent,
)
from wyrdforge.ecs.world import World


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Report dataclass
# ---------------------------------------------------------------------------

@dataclass
class RunicReport:
    """Snapshot of the runic state for one entity.

    Attributes:
        entity_id:      Entity whose state is reported.
        hamingja_score: Current hamingja in [-1.0, 1.0], or None if no component.
        dominant_rune:  Name of the rune with highest charge, or None.
        total_charge:   Sum of all rune charges, or 0.0 if no component.
        resonance_score: Ancestral resonance in [0.0, 1.0], or 0.0 if no component.
        rune_charges:   Copy of the charges dict.
    """

    entity_id: str
    hamingja_score: float | None
    dominant_rune: str | None
    total_charge: float
    resonance_score: float
    rune_charges: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class RunicEngine:
    """Deterministic update service for WYRD runic metaphysics.

    Args:
        world: The ECS World to operate on.
    """

    def __init__(self, world: World) -> None:
        self._world = world

    # ------------------------------------------------------------------
    # Rune invocation
    # ------------------------------------------------------------------

    def invoke_rune(
        self,
        entity_id: str,
        rune_name: str,
        *,
        strength: float = 0.5,
    ) -> None:
        """Add runic charge to an entity, creating the component if absent.

        Charge for the named rune is increased by ``strength`` (clamped to
        [0.0, 1.0]).  The dominant_rune is updated automatically.

        Also applies a hamingja boost of ``strength * 0.1`` — invoking a rune
        is considered a mild positive omen.

        Args:
            entity_id: Target entity.
            rune_name: Lower-case Elder Futhark rune name (e.g. ``"fehu"``).
            strength:  Invocation intensity in [0.0, 1.0].
        """
        strength = max(0.0, min(1.0, strength))

        comp = self._world.get_component(entity_id, "runic_charge")
        if comp is None:
            comp = RunicChargeComponent(entity_id=entity_id)
            self._world.add_component(entity_id, comp)

        current = comp.charges.get(rune_name, 0.0)
        comp.charges[rune_name] = min(1.0, current + strength)
        comp.dominant_rune = max(comp.charges, key=lambda k: comp.charges[k])

        # Hamingja boost
        self._adjust_hamingja(entity_id, delta=strength * 0.1)

    # ------------------------------------------------------------------
    # Hamingja
    # ------------------------------------------------------------------

    def apply_hamingja_event(
        self,
        entity_id: str,
        *,
        delta: float,
        event_id: str | None = None,
    ) -> None:
        """Apply a hamingja delta to an entity.

        Creates a HamingjaComponent if the entity doesn't have one.

        Args:
            entity_id: Target entity.
            delta:     Change to apply (positive = fortunate, negative = cursed).
            event_id:  Optional record ID of the triggering event.
        """
        self._adjust_hamingja(entity_id, delta=delta, event_id=event_id)

    # ------------------------------------------------------------------
    # Ancestral resonance
    # ------------------------------------------------------------------

    def reinforce_resonance(
        self,
        entity_id: str,
        *,
        boost: float = 0.1,
        fragment: str | None = None,
    ) -> None:
        """Reinforce ancestral resonance for an entity.

        Creates an AncestralResonanceComponent if absent.

        Args:
            entity_id: Target entity.
            boost:     Score increase in [0.0, 1.0].
            fragment:  Optional ancestral memory text to append.
        """
        boost = max(0.0, min(1.0, boost))
        comp = self._world.get_component(entity_id, "ancestral_resonance")
        if comp is None:
            comp = AncestralResonanceComponent(entity_id=entity_id)
            self._world.add_component(entity_id, comp)

        comp.score = min(1.0, comp.score + boost)
        comp.last_communion = _now_iso()
        if fragment and fragment not in comp.memory_fragments:
            comp.memory_fragments.append(fragment)

    def add_lineage(self, entity_id: str, ancestor_id: str) -> None:
        """Register an ancestor in an entity's lineage.

        Args:
            entity_id:   Descendant entity.
            ancestor_id: Ancestor entity ID to add.
        """
        comp = self._world.get_component(entity_id, "ancestral_resonance")
        if comp is None:
            comp = AncestralResonanceComponent(entity_id=entity_id)
            self._world.add_component(entity_id, comp)
        if ancestor_id not in comp.lineage_ids:
            comp.lineage_ids.append(ancestor_id)

    # ------------------------------------------------------------------
    # Tick (decay + drift)
    # ------------------------------------------------------------------

    def tick(self, entity_ids: list[str] | None = None) -> None:
        """Advance one engine tick: apply rune decay and hamingja drift.

        If ``entity_ids`` is None, all entities with runic components are
        updated.  Pass a list to restrict the update to specific entities.

        Args:
            entity_ids: Entities to tick, or None for all.
        """
        targets = (
            entity_ids if entity_ids is not None
            else [e.entity_id for e in self._world.all_entities()]
        )

        for eid in targets:
            self._tick_runic_charge(eid)
            self._tick_hamingja(eid)

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def report(self, entity_id: str) -> RunicReport:
        """Build a snapshot report for one entity.

        Args:
            entity_id: Entity to report on.

        Returns:
            RunicReport with current state (all fields None/0.0 if components absent).
        """
        h_comp: HamingjaComponent | None = self._world.get_component(entity_id, "hamingja")
        r_comp: RunicChargeComponent | None = self._world.get_component(entity_id, "runic_charge")
        a_comp: AncestralResonanceComponent | None = self._world.get_component(
            entity_id, "ancestral_resonance"
        )

        return RunicReport(
            entity_id=entity_id,
            hamingja_score=h_comp.score if h_comp else None,
            dominant_rune=r_comp.dominant_rune if r_comp else None,
            total_charge=r_comp.total_charge() if r_comp else 0.0,
            resonance_score=a_comp.score if a_comp else 0.0,
            rune_charges=dict(r_comp.charges) if r_comp else {},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _adjust_hamingja(
        self,
        entity_id: str,
        *,
        delta: float,
        event_id: str | None = None,
    ) -> None:
        comp = self._world.get_component(entity_id, "hamingja")
        if comp is None:
            comp = HamingjaComponent(entity_id=entity_id)
            self._world.add_component(entity_id, comp)

        new_score = max(-1.0, min(1.0, comp.score + delta))
        comp.score = new_score
        if new_score > comp.peak:
            comp.peak = new_score
        if event_id:
            comp.last_event_id = event_id

    def _tick_runic_charge(self, entity_id: str) -> None:
        comp: RunicChargeComponent | None = self._world.get_component(entity_id, "runic_charge")
        if comp is None:
            return
        if not comp.charges:
            return

        decay = comp.decay_rate
        updated: dict[str, float] = {}
        for rune, charge in comp.charges.items():
            new_charge = charge * (1.0 - decay)
            if new_charge > 0.001:  # prune near-zero charges
                updated[rune] = new_charge

        comp.charges = updated
        if updated:
            comp.dominant_rune = max(updated, key=lambda k: updated[k])
        else:
            comp.dominant_rune = None

    def _tick_hamingja(self, entity_id: str) -> None:
        comp: HamingjaComponent | None = self._world.get_component(entity_id, "hamingja")
        if comp is None:
            return
        # Drift toward 0 (neutral)
        if comp.score > 0:
            comp.score = max(0.0, comp.score - comp.drift_rate)
        elif comp.score < 0:
            comp.score = min(0.0, comp.score + comp.drift_rate)
