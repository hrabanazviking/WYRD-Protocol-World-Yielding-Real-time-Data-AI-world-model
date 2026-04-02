"""Passive Oracle Model — read-only ground-truth world query API.

The oracle bridges the ECS World (entity/spatial/component state) with the
PersistentMemoryStore (canonical facts, policies, observations).  It is
intentionally *read-only*: it never mutates world state, never writes
memory records, and carries no personality — pure structured data.

Nine query methods:
    1. where_is          — spatial location of an entity
    2. who_is_here       — entities at a location
    3. what_is           — full entity snapshot
    4. get_fact          — single canonical fact (highest confidence)
    5. get_facts         — all canonical facts for a subject
    6. get_relations     — faction + co-presence
    7. get_nearby        — entities sharing the same location
    8. search_facts      — FTS search across memory
    9. build_context_packet — LLM-ready WorldContextPacket
"""
from __future__ import annotations

from datetime import datetime, timezone

from wyrdforge.ecs.components.character import FactionComponent
from wyrdforge.ecs.components.identity import (
    DescriptionComponent,
    NameComponent,
    StatusComponent,
)
from wyrdforge.ecs.components.spatial import (
    HierarchyLevel,
    ParentComponent,
    SpatialComponent,
)
from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree
from wyrdforge.models.common import ApprovalState, StoreName
from wyrdforge.models.memory import (
    CanonicalFactRecord,
    ContradictionRecord,
    ObservationRecord,
    PolicyRecord,
)
from wyrdforge.oracle.models import (
    EntitySummary,
    FactSummary,
    LocationResult,
    ObservationSummary,
    PolicySummary,
    RelationResult,
    WorldContextPacket,
)
from wyrdforge.persistence.memory_store import PersistentMemoryStore


class PassiveOracle:
    """Read-only ground-truth reporter over ECS World + PersistentMemoryStore.

    Args:
        world:        The ECS World to query for entity/component state.
        memory_store: The PersistentMemoryStore to query for facts/policies/
                      observations.
        yggdrasil:    Optional YggdrasilTree for richer spatial navigation.
                      When omitted, spatial queries fall back to component scans.
    """

    def __init__(
        self,
        world: World,
        memory_store: PersistentMemoryStore,
        *,
        yggdrasil: YggdrasilTree | None = None,
    ) -> None:
        self._world = world
        self._store = memory_store
        self._yggdrasil = yggdrasil

    # ------------------------------------------------------------------
    # Query 1: where_is
    # ------------------------------------------------------------------

    def where_is(self, entity_id: str) -> LocationResult | None:
        """Return the spatial position of an entity, or None if not in world."""
        if self._world.get_entity(entity_id) is None:
            return None
        spatial = self._world.get_component(entity_id, "spatial")
        if not isinstance(spatial, SpatialComponent):
            return LocationResult(
                entity_id=entity_id,
                location_id=None,
                location_name=None,
                zone_id=None,
                region_id=None,
                path=[],
            )
        loc_id = spatial.most_specific_id()
        loc_name = self._node_name(loc_id) if loc_id else None
        return LocationResult(
            entity_id=entity_id,
            location_id=loc_id,
            location_name=loc_name,
            zone_id=spatial.zone_id,
            region_id=spatial.region_id,
            path=spatial.path(),
        )

    # ------------------------------------------------------------------
    # Query 2: who_is_here
    # ------------------------------------------------------------------

    def who_is_here(self, location_id: str) -> list[EntitySummary]:
        """Return summaries of non-spatial entities present at a location."""
        if self._yggdrasil:
            entities = self._yggdrasil.entities_at(location_id)
        else:
            entities = []
            for entity, spatial in self._world.iter_components("spatial"):
                if (
                    isinstance(spatial, SpatialComponent)
                    and spatial.most_specific_id() == location_id
                    and not entity.has_tag("spatial_node")
                ):
                    entities.append(entity)
        return [s for eid in [e.entity_id for e in entities] if (s := self._entity_summary(eid))]

    # ------------------------------------------------------------------
    # Query 3: what_is
    # ------------------------------------------------------------------

    def what_is(self, entity_id: str) -> EntitySummary | None:
        """Return a compact snapshot of an entity, or None if not found."""
        return self._entity_summary(entity_id)

    # ------------------------------------------------------------------
    # Query 4: get_fact  (highest-confidence, non-quarantined)
    # ------------------------------------------------------------------

    def get_fact(self, subject_id: str, fact_key: str) -> CanonicalFactRecord | None:
        """Return the best canonical fact for subject+key, or None."""
        matching = [
            f for f in self.get_facts(subject_id)
            if f.content.structured_payload.fact_key == fact_key
        ]
        if not matching:
            return None
        return max(matching, key=lambda r: r.truth.confidence)

    # ------------------------------------------------------------------
    # Query 5: get_facts  (all non-quarantined for a subject)
    # ------------------------------------------------------------------

    def get_facts(self, subject_id: str) -> list[CanonicalFactRecord]:
        """Return all non-quarantined canonical facts for a subject."""
        all_facts = self._store.list_by_record_type(
            "canonical_fact", store=StoreName.MIMIR.value
        )
        return [
            r for r in all_facts
            if isinstance(r, CanonicalFactRecord)
            and r.truth.approval_state != ApprovalState.QUARANTINED
            and r.content.structured_payload.fact_subject_id == subject_id
        ]

    # ------------------------------------------------------------------
    # Query 6: get_relations
    # ------------------------------------------------------------------

    def get_relations(self, entity_id: str) -> RelationResult:
        """Return faction membership and co-located entity IDs."""
        faction_comp = self._world.get_component(entity_id, "faction")
        faction_id: str | None = None
        faction_name: str | None = None
        reputations: dict[str, float] = {}
        if isinstance(faction_comp, FactionComponent):
            faction_id = faction_comp.faction_id or None
            faction_name = faction_comp.faction_name or None
            reputations = dict(faction_comp.reputation)

        co_located: list[str] = []
        if self._yggdrasil:
            co_located = [e.entity_id for e in self._yggdrasil.get_co_located(entity_id)]
        else:
            spatial = self._world.get_component(entity_id, "spatial")
            if isinstance(spatial, SpatialComponent):
                loc_id = spatial.most_specific_id()
                if loc_id:
                    for ent, s in self._world.iter_components("spatial"):
                        if (
                            ent.entity_id != entity_id
                            and isinstance(s, SpatialComponent)
                            and s.most_specific_id() == loc_id
                            and not ent.has_tag("spatial_node")
                        ):
                            co_located.append(ent.entity_id)

        return RelationResult(
            entity_id=entity_id,
            faction_id=faction_id,
            faction_name=faction_name,
            faction_reputations=reputations,
            co_located_entity_ids=co_located,
        )

    # ------------------------------------------------------------------
    # Query 7: get_nearby
    # ------------------------------------------------------------------

    def get_nearby(self, entity_id: str) -> list[EntitySummary]:
        """Return summaries of entities sharing the same location."""
        if self._yggdrasil:
            entities = self._yggdrasil.get_co_located(entity_id)
        else:
            spatial = self._world.get_component(entity_id, "spatial")
            if not isinstance(spatial, SpatialComponent):
                return []
            loc_id = spatial.most_specific_id()
            if not loc_id:
                return []
            entities = [
                ent for ent, s in self._world.iter_components("spatial")
                if ent.entity_id != entity_id
                and isinstance(s, SpatialComponent)
                and s.most_specific_id() == loc_id
                and not ent.has_tag("spatial_node")
            ]
        return [s for eid in [e.entity_id for e in entities] if (s := self._entity_summary(eid))]

    # ------------------------------------------------------------------
    # Query 8: search_facts
    # ------------------------------------------------------------------

    def search_facts(self, query: str, *, limit: int = 5) -> list[CanonicalFactRecord]:
        """FTS search across MIMIR store, excluding quarantined records."""
        results = self._store.search(query, store=StoreName.MIMIR.value, limit=limit)
        return [
            r for r in results
            if isinstance(r, CanonicalFactRecord)
            and r.truth.approval_state != ApprovalState.QUARANTINED
        ]

    # ------------------------------------------------------------------
    # Query 9: build_context_packet
    # ------------------------------------------------------------------

    def build_context_packet(
        self,
        *,
        focus_entity_ids: list[str],
        location_id: str | None = None,
        include_policies: bool = True,
        include_observations: bool = True,
        max_observations: int = 5,
    ) -> WorldContextPacket:
        """Assemble an LLM-ready context bundle.

        Args:
            focus_entity_ids:   Entity IDs to centre the packet around.
            location_id:        Override the location context.  Defaults to
                                the first focus entity's current location.
            include_policies:   Include ORLOG policy records.
            include_observations: Include recent HUGIN observations.
            max_observations:   How many recent observations to include.
        """
        # Focus entities
        focus_entities = [
            s for eid in focus_entity_ids if (s := self._entity_summary(eid))
        ]

        # Effective location
        effective_loc_id = location_id
        if not effective_loc_id and focus_entities:
            effective_loc_id = focus_entities[0].location_id

        # Location context
        loc_ctx: LocationResult | None = None
        if effective_loc_id:
            loc_ctx = self._build_location_result_for_node(effective_loc_id)

        # Entities present at location
        present_entities = self.who_is_here(effective_loc_id) if effective_loc_id else []

        # Canonical facts for all focus entities
        canonical_facts: dict[str, list[FactSummary]] = {}
        for eid in focus_entity_ids:
            facts = self.get_facts(eid)
            if facts:
                canonical_facts[eid] = [
                    FactSummary(
                        record_id=f.record_id,
                        subject_id=f.content.structured_payload.fact_subject_id,
                        fact_key=f.content.structured_payload.fact_key,
                        fact_value=f.content.structured_payload.fact_value,
                        confidence=f.truth.confidence,
                        domain=f.content.structured_payload.domain,
                    )
                    for f in facts
                ]

        # Policies
        policies: list[PolicySummary] = []
        if include_policies:
            policy_records = self._store.list_by_record_type(
                "policy", store=StoreName.ORLOG.value
            )
            for r in policy_records:
                if isinstance(r, PolicyRecord) and r.governance.allowed_for_runtime:
                    p = r.content.structured_payload
                    policies.append(PolicySummary(
                        record_id=r.record_id,
                        title=r.content.title,
                        rule_text=p.rule_text,
                        policy_kind=p.policy_kind,
                        priority=p.priority,
                    ))
            policies.sort(key=lambda p: p.priority)

        # Recent observations
        observations: list[ObservationSummary] = []
        if include_observations:
            obs_all = self._store.all(store=StoreName.HUGIN.value)
            obs_typed = [r for r in obs_all if isinstance(r, ObservationRecord)]
            obs_typed.sort(
                key=lambda r: r.content.structured_payload.observed_at,
                reverse=True,
            )
            for r in obs_typed[:max_observations]:
                observations.append(ObservationSummary(
                    record_id=r.record_id,
                    title=r.content.title,
                    summary=r.content.summary,
                    observed_at=r.content.structured_payload.observed_at,
                ))

        # Open contradictions (count only — no detector dependency)
        contra_records = self._store.list_by_record_type(
            "contradiction", store=StoreName.WYRD.value
        )
        open_contradiction_count = sum(
            1 for r in contra_records
            if isinstance(r, ContradictionRecord)
            and r.content.structured_payload.resolution_state == "open"
        )

        formatted = self._render_for_llm(
            focus_entities=focus_entities,
            loc_ctx=loc_ctx,
            present_entities=present_entities,
            canonical_facts=canonical_facts,
            policies=policies,
            observations=observations,
            open_contradiction_count=open_contradiction_count,
        )

        return WorldContextPacket(
            query_timestamp=datetime.now(timezone.utc),
            world_id=self._world.world_id,
            focus_entities=focus_entities,
            location_context=loc_ctx,
            present_entities=present_entities,
            canonical_facts=canonical_facts,
            active_policies=policies,
            recent_observations=observations,
            open_contradiction_count=open_contradiction_count,
            formatted_for_llm=formatted,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _entity_summary(self, entity_id: str) -> EntitySummary | None:
        entity = self._world.get_entity(entity_id)
        if entity is None:
            return None

        name_comp = self._world.get_component(entity_id, "name")
        name = name_comp.name if isinstance(name_comp, NameComponent) else None

        desc_comp = self._world.get_component(entity_id, "description")
        description = desc_comp.short_desc if isinstance(desc_comp, DescriptionComponent) else None

        status_comp = self._world.get_component(entity_id, "status")
        status = status_comp.state if isinstance(status_comp, StatusComponent) else None

        spatial_comp = self._world.get_component(entity_id, "spatial")
        location_id = (
            spatial_comp.most_specific_id()
            if isinstance(spatial_comp, SpatialComponent)
            else None
        )

        return EntitySummary(
            entity_id=entity_id,
            name=name,
            description=description,
            status=status,
            tags=sorted(entity.tags),
            location_id=location_id,
        )

    def _node_name(self, entity_id: str) -> str | None:
        name_comp = self._world.get_component(entity_id, "name")
        return name_comp.name if isinstance(name_comp, NameComponent) else None

    def _build_location_result_for_node(self, node_id: str) -> LocationResult:
        """Build a LocationResult for a spatial node (location or sublocation)."""
        loc_name = self._node_name(node_id)
        zone_id: str | None = None
        region_id: str | None = None
        path_ids: list[str] = []

        if self._yggdrasil:
            ancestors = self._yggdrasil.get_ancestors(node_id)
            # ancestors: [immediate_parent, ..., zone] — reverse for path order
            for anc in reversed(ancestors):
                anc_parent = self._world.get_component(anc.entity_id, "parent")
                if isinstance(anc_parent, ParentComponent):
                    if anc_parent.hierarchy_level == HierarchyLevel.ZONE:
                        zone_id = anc.entity_id
                    elif anc_parent.hierarchy_level == HierarchyLevel.REGION:
                        region_id = anc.entity_id
                path_ids.append(anc.entity_id)
        else:
            # Walk parents manually
            current = node_id
            chain: list[str] = []
            while True:
                parent_comp = self._world.get_component(current, "parent")
                if not isinstance(parent_comp, ParentComponent) or not parent_comp.parent_entity_id:
                    break
                parent_id = parent_comp.parent_entity_id
                # Determine level of current node
                if parent_comp.hierarchy_level == HierarchyLevel.REGION:
                    region_id = current
                elif parent_comp.hierarchy_level == HierarchyLevel.ZONE:
                    zone_id = current
                chain.append(parent_id)
                current = parent_id
            path_ids = list(reversed(chain))

        path_ids.append(node_id)

        return LocationResult(
            entity_id=node_id,
            location_id=node_id,
            location_name=loc_name,
            zone_id=zone_id,
            region_id=region_id,
            path=path_ids,
        )

    def _render_for_llm(
        self,
        *,
        focus_entities: list[EntitySummary],
        loc_ctx: LocationResult | None,
        present_entities: list[EntitySummary],
        canonical_facts: dict[str, list[FactSummary]],
        policies: list[PolicySummary],
        observations: list[ObservationSummary],
        open_contradiction_count: int,
    ) -> str:
        lines: list[str] = []
        lines.append("=== WORLD STATE ===")
        lines.append(f"World: {self._world.world_id}")

        # Focus
        if focus_entities:
            lines.append("\n[FOCUS]")
            for e in focus_entities:
                name_part = e.name or e.entity_id
                loc_part = f" — at {e.location_id}" if e.location_id else ""
                status_part = f" ({e.status})" if e.status else ""
                lines.append(f"  {name_part} ({e.entity_id}){status_part}{loc_part}")

        # Location
        if loc_ctx:
            lines.append(f"\n[LOCATION: {loc_ctx.location_id}]")
            if loc_ctx.location_name:
                lines.append(f"  Name: {loc_ctx.location_name}")
            if loc_ctx.path:
                lines.append(f"  Path: {' → '.join(loc_ctx.path)}")
            if present_entities:
                names = ", ".join(e.name or e.entity_id for e in present_entities)
                lines.append(f"  Present: {names}")
            else:
                lines.append("  Present: (empty)")

        # Facts
        if canonical_facts:
            lines.append("\n[CANONICAL FACTS]")
            for subject_id, facts in canonical_facts.items():
                lines.append(f"  {subject_id}:")
                for f in sorted(facts, key=lambda x: x.fact_key):
                    lines.append(
                        f"    • {f.fact_key} = {f.fact_value} (conf: {f.confidence:.2f})"
                    )

        # Policies
        if policies:
            lines.append("\n[POLICIES]")
            for p in policies:
                lines.append(f"  [{p.policy_kind}/{p.priority}] {p.rule_text[:120]}")

        # Observations
        if observations:
            lines.append("\n[RECENT EVENTS]")
            for o in observations:
                ts = o.observed_at.strftime("%Y-%m-%dT%H:%M:%SZ")
                lines.append(f"  • {o.title} ({ts})")

        # Contradictions
        lines.append(f"\n[CONTRADICTIONS] {open_contradiction_count} open")

        return "\n".join(lines)
