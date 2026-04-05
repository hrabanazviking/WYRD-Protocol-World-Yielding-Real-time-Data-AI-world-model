"""CharacterContext — assembles the full layered context for one character.

Combines:
    - WorldContextPacket    (PassiveOracle — ECS world + memory facts)
    - PersonaPacket         (PersonaCompiler — identity, traits, tone)
    - MicroContextPacket    (MicroRAGPipeline — semantically scored retrieval)

into a single CharacterContextResult with a ``formatted_for_llm`` block
ready for direct prompt injection.
"""
from __future__ import annotations

from wyrdforge.models.common import StrictModel
from wyrdforge.models.micro_rag import MicroContextPacket, QueryMode, TruthPacket
from wyrdforge.models.persona import PersonaMode, PersonaPacket
from wyrdforge.oracle.models import WorldContextPacket
from wyrdforge.oracle.passive_oracle import PassiveOracle
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.services.bond_graph_service import BondGraphService
from wyrdforge.services.memory_to_rag import MemoryToRAGAdapter
from wyrdforge.services.micro_rag_pipeline import MicroRAGPipeline
from wyrdforge.services.persona_compiler import PersonaCompiler


class CharacterContextResult(StrictModel):
    """Full layered context result for a character query."""

    world_packet: WorldContextPacket
    persona_packet: PersonaPacket
    micro_packet: MicroContextPacket
    formatted_for_llm: str


class CharacterContext:
    """Assembles the full WYRD context stack for one character.

    All service arguments are optional — the class degrades gracefully
    when services are not provided (empty packets are returned).

    Args:
        oracle:           PassiveOracle for world state.
        memory_store:     PersistentMemoryStore for facts/observations.
        bond_service:     BondGraphService for relationship state.
        persona_compiler: PersonaCompiler for identity compilation.
        rag_pipeline:     MicroRAGPipeline for scored retrieval.
        max_rag_candidates: Cap per retrieval family passed to MicroRAG.
        rag_packet_budget:  Token budget for MicroRAG assembly.
    """

    def __init__(
        self,
        oracle: PassiveOracle,
        memory_store: PersistentMemoryStore,
        *,
        bond_service: BondGraphService | None = None,
        persona_compiler: PersonaCompiler | None = None,
        rag_pipeline: MicroRAGPipeline | None = None,
        max_rag_candidates: int = 20,
        rag_packet_budget: int = 900,
    ) -> None:
        self._oracle = oracle
        self._store = memory_store
        self._bond_service = bond_service
        self._compiler = persona_compiler or PersonaCompiler()
        self._rag = rag_pipeline or MicroRAGPipeline()
        self._rag_adapter = MemoryToRAGAdapter(memory_store)
        self._max_rag_candidates = max_rag_candidates
        self._rag_packet_budget = rag_packet_budget

    # ------------------------------------------------------------------
    # Main API
    # ------------------------------------------------------------------

    def build(
        self,
        *,
        persona_id: str,
        user_id: str,
        query: str,
        mode: QueryMode = QueryMode.COMPANION_CONTINUITY,
        persona_mode: PersonaMode = PersonaMode.COMPANION,
        focus_entity_ids: list[str],
        location_id: str | None = None,
        bond_id: str | None = None,
        token_budget: int = 900,
        truth_packet: TruthPacket | None = None,
    ) -> CharacterContextResult:
        """Assemble the full context stack.

        Args:
            persona_id:        ID for the compiled PersonaPacket.
            user_id:           ID of the user/player entity.
            query:             The user's current query/input (for RAG scoring).
            mode:              MicroRAG query mode.
            persona_mode:      PersonaCompiler mode.
            focus_entity_ids:  Entity IDs to focus context around.
            location_id:       Override location for world context.
            bond_id:           Bond edge ID for relationship context.
            token_budget:      MicroRAG packet token budget.
            truth_packet:      Optional truth constraints for MicroRAG.
        """
        # 1. World context
        world_packet = self._oracle.build_context_packet(
            focus_entity_ids=focus_entity_ids,
            location_id=location_id,
        )

        # 2. Bond state
        bond_edge = None
        bond_excerpt_lines: list[str] = []
        if self._bond_service and bond_id and bond_id in self._bond_service.edges:
            bond_edge = self._bond_service.edges[bond_id]
            bond_excerpt_lines = self._bond_service.excerpt(bond_id)

        # 3. Memory records for PersonaCompiler
        all_facts = []
        for eid in focus_entity_ids:
            all_facts.extend(self._oracle.get_facts(eid))
        obs_records = self._store.list_by_record_type("observation", store="hugin_observation_store")
        records_for_persona = all_facts + obs_records[-10:]  # facts + recent obs

        # 4. Compile PersonaPacket
        persona_packet = self._compiler.compile(
            persona_id=persona_id,
            user_id=user_id,
            mode=persona_mode,
            records=records_for_persona,
            bond_edge=bond_edge,
            token_budget_hint=token_budget,
        )

        # 5. Build RAG candidates
        candidates = self._rag_adapter.get_candidates_by_family(
            subject_ids=focus_entity_ids if focus_entity_ids else None,
            max_per_family=self._max_rag_candidates,
            bond_excerpt_lines=bond_excerpt_lines,
        )

        # 6. Assemble MicroContextPacket
        micro_packet = self._rag.assemble(
            query=query,
            mode=mode,
            candidates_by_family=candidates,
            truth_packet=truth_packet or TruthPacket(),
            packet_budget=self._rag_packet_budget,
        )

        # 7. Render combined formatted text
        formatted = _render_combined(world_packet, persona_packet, micro_packet)

        return CharacterContextResult(
            world_packet=world_packet,
            persona_packet=persona_packet,
            micro_packet=micro_packet,
            formatted_for_llm=formatted,
        )


# ------------------------------------------------------------------
# Rendering
# ------------------------------------------------------------------

def _render_combined(
    world_packet: WorldContextPacket,
    persona_packet: PersonaPacket,
    micro_packet: MicroContextPacket,
) -> str:
    lines: list[str] = []

    # Persona identity
    if persona_packet.identity_core:
        lines.append("[IDENTITY]")
        lines.extend(f"  {line}" for line in persona_packet.identity_core[:6])

    if persona_packet.tone_contract:
        lines.append("\n[TONE]")
        lines.extend(f"  • {t}" for t in persona_packet.tone_contract[:4])

    if persona_packet.active_traits:
        trait_str = ", ".join(
            f"{t.trait_name}({t.weight:.2f})"
            for t in persona_packet.active_traits[:5]
        )
        lines.append(f"\n[TRAITS] {trait_str}")

    # World state
    lines.append("\n" + world_packet.formatted_for_llm)

    # Retrieved facts
    if micro_packet.canonical_facts:
        lines.append("\n[RETRIEVED FACTS]")
        for item in micro_packet.canonical_facts[:6]:
            lines.append(f"  • {item.text}  (score:{item.final_score:.2f})")

    # Bond state
    if micro_packet.bond_excerpt:
        lines.append("\n[BOND STATE]")
        for item in micro_packet.bond_excerpt[:4]:
            lines.append(f"  • {item.text}")

    # Symbolic context
    if micro_packet.symbolic_context:
        lines.append("\n[SYMBOLIC]")
        for item in micro_packet.symbolic_context[:3]:
            lines.append(f"  • {item.text}")

    # Response guidance
    if persona_packet.response_guidance:
        lines.append("\n[GUIDANCE]")
        lines.extend(f"  • {g}" for g in persona_packet.response_guidance[:4])

    # Uncertainty
    if persona_packet.uncertainty_points:
        lines.append("\n[UNCERTAINTY]")
        lines.extend(f"  ? {u}" for u in persona_packet.uncertainty_points[:3])

    return "\n".join(lines)
