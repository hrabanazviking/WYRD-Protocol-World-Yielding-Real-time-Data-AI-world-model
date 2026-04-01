from __future__ import annotations

from collections import defaultdict

from wyrdforge.models.bond import BondEdge
from wyrdforge.models.memory import CanonicalFactRecord, MemoryRecord, SymbolicTraceRecord
from wyrdforge.models.persona import PersonaMode, PersonaPacket, PersonaSourceItem, TraitSignal


class PersonaCompiler:
    def compile(
        self,
        *,
        persona_id: str,
        user_id: str,
        mode: PersonaMode,
        records: list[MemoryRecord],
        bond_edge: BondEdge | None = None,
        token_budget_hint: int = 800,
    ) -> PersonaPacket:
        identity_core: list[str] = []
        truth_anchor_points: list[str] = []
        uncertainty_points: list[str] = []
        symbolic_context: list[str] = []
        tone_contract: list[str] = [
            "preserve continuity without inventing unsupported memory",
            "prefer grounded specifics over vague mythic filler",
            "mark uncertainty cleanly when canon or memory is missing",
        ]
        response_guidance: list[str] = []
        source_items: list[PersonaSourceItem] = []
        trait_buckets: dict[str, float] = defaultdict(float)
        trait_support: dict[str, list[str]] = defaultdict(list)

        for record in records:
            source_items.append(
                PersonaSourceItem(
                    record_id=record.record_id,
                    item_type=record.record_type,
                    text=record.content.summary,
                    confidence=record.truth.confidence,
                )
            )
            if isinstance(record, CanonicalFactRecord):
                payload = record.content.structured_payload
                line = f"{payload.fact_subject_id}.{payload.fact_key}={payload.fact_value}"
                if payload.domain in {"identity", "style", "mission"}:
                    identity_core.append(line)
                else:
                    truth_anchor_points.append(line)
                if payload.fact_key in {"temperament", "tone", "value", "mood"}:
                    trait_buckets[payload.fact_value] += record.truth.confidence
                    trait_support[payload.fact_value].append(record.record_id)
            elif isinstance(record, SymbolicTraceRecord):
                sp = record.content.structured_payload
                symbolic_context.append(
                    f"symbol={sp.symbol_type};runes={','.join(sp.rune_signature)};charge={sp.ritual_charge:.2f}"
                )
            elif record.truth.approval_state.value != "approved":
                uncertainty_points.append(record.content.summary)

        if bond_edge is not None:
            response_guidance.extend(
                [
                    f"relationship_mode={bond_edge.active_modes.relational_mode}",
                    f"relationship_weather={bond_edge.active_modes.emotional_weather}",
                    f"closeness_index={bond_edge.closeness_index():.2f}",
                ]
            )

        active_traits = [
            TraitSignal(trait_name=name, weight=min(1.0, weight), supporting_record_ids=trait_support[name])
            for name, weight in sorted(trait_buckets.items(), key=lambda item: item[1], reverse=True)[:8]
        ]

        if mode is PersonaMode.CODING_GUIDE:
            tone_contract.append("opt for terse correctness and verifiable claims")
            response_guidance.append("surface missing evidence before offering code-level certainty")
        elif mode is PersonaMode.WORLD_SEER:
            tone_contract.append("preserve mythic atmosphere while separating omen from fact")
            response_guidance.append("do not present symbolic traces as hard world canon without support")
        elif mode is PersonaMode.COMPANION:
            tone_contract.append("maintain warmth without synthetic intimacy inflation")
            response_guidance.append("never claim vows or memories that are not supported")

        return PersonaPacket(
            persona_id=persona_id,
            user_id=user_id,
            mode=mode,
            tone_contract=tone_contract,
            identity_core=identity_core[:10],
            active_traits=active_traits,
            relationship_excerpt=response_guidance[:6],
            truth_anchor_points=truth_anchor_points[:16],
            uncertainty_points=uncertainty_points[:8],
            symbolic_context=symbolic_context[:8],
            response_guidance=response_guidance[:10],
            source_items=source_items[:20],
            token_budget_hint=token_budget_hint,
        )
