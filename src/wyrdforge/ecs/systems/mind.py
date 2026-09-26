"""CognitionSystem — the tick-level weaving of the four mind modules.

On every tick this system:
1. **Advances world-time** (temporal.py): the deterministic WorldClock
   moves forward by ``delta_t``. Wyrd never rewinds.
2. **Watches the threads of wyrd**: temporal anchors whose validity ends
   are reported as newly-urðr (become past). Nothing is deleted — the
   past stays queryable.
3. **Maintains the zero-bleed partition** (mtom.py): entities tagged
   POTENTIAL are tracked separately from MANIFEST ones, so oracle-facing
   code can never silently merge them.
4. **Flags speculation** (mtom.py Rule 4): beliefs whose confidence
   exceeds their source's warrant are reported, not silently trusted.

This system is opt-in (add it to a WorldRunner). It never creates or
destroys entities and never rewrites minds — it watches, advances time,
and reports. Deterministic; no LLM involvement.
"""
from __future__ import annotations

from wyrdforge.ecs.components.micro_reality import MicroRealityComponent
from wyrdforge.ecs.components.mtom import (
    RealityState,
    RealityStateComponent,
    explicit_subjectivity_check,
)
from wyrdforge.ecs.components.temporal import (
    TemporalAnchorComponent,
    WorldClock,
)
from wyrdforge.ecs.components.theory_of_mind import BeliefComponent
from wyrdforge.ecs.system import System
from wyrdforge.ecs.world import World
from wyrdforge.models.common import StrictModel


class TickReport(StrictModel):
    """What the CognitionSystem observed on one tick."""

    world_now: str
    newly_urdhr: list[str] = []          # anchor labels that just became past
    speculation_warnings: list[str] = []  # Rule 4 flags
    manifest_entities: int = 0
    potential_entities: int = 0


class CognitionSystem(System):
    """Weaves time, theory of mind, micro-realities, and the MTOM firewall."""

    component_interests = ["temporal_anchor", "beliefs", "mind_models",
                           "micro_reality", "reality_state"]

    def __init__(self, clock: WorldClock | None = None) -> None:
        self.clock = clock or WorldClock()
        self.last_report: TickReport | None = None
        # entity_ids currently holding POTENTIAL-tagged claims
        self.potential_entities: set[str] = set()

    def tick(self, world: World, delta_t: float = 1.0) -> None:
        now = self.clock.advance(delta_t)
        newly_urdhr: list[str] = []
        speculation_warnings: list[str] = []
        manifest = 0
        self.potential_entities.clear()

        for _entity, comp in world.iter_components("temporal_anchor"):
            if isinstance(comp, TemporalAnchorComponent) and comp.has_expired(now):
                newly_urdhr.append(comp.label or comp.entity_id)

        for entity, comp in world.iter_components("beliefs"):
            if isinstance(comp, BeliefComponent):
                for b in comp.beliefs:
                    warning = explicit_subjectivity_check(b.source, b.confidence)
                    if warning:
                        speculation_warnings.append(
                            f"{entity.entity_id} believes '{b.claim}': {warning}")

        for entity, comp in world.iter_components("reality_state"):
            if isinstance(comp, RealityStateComponent):
                if comp.state is RealityState.POTENTIAL:
                    self.potential_entities.add(entity.entity_id)
                else:
                    manifest += 1

        self.last_report = TickReport(
            world_now=now.isoformat(),
            newly_urdhr=newly_urdhr,
            speculation_warnings=speculation_warnings,
            manifest_entities=manifest,
            potential_entities=len(self.potential_entities),
        )

    def micro_realities(self, world: World) -> dict[str, MicroRealityComponent]:
        """All entities' sovereign micro-realities, keyed by entity_id."""
        return {e.entity_id: c for e, c in world.iter_components("micro_reality")
                if isinstance(c, MicroRealityComponent)}
