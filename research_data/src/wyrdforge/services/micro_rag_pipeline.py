from __future__ import annotations

from collections import Counter

from wyrdforge.models.micro_rag import MicroContextPacket, QueryMode, RankedCandidate, RetrievalItem, TruthPacket


class MicroRAGPipeline:
    MODE_TARGETS = {
        QueryMode.FACTUAL_LOOKUP: ("canonical", "recent", "contradiction"),
        QueryMode.COMPANION_CONTINUITY: ("bond", "canonical", "recent", "symbolic"),
        QueryMode.WORLD_STATE: ("canonical", "recent", "symbolic", "contradiction"),
        QueryMode.SYMBOLIC_INTERPRETATION: ("symbolic", "canonical", "recent"),
        QueryMode.CODING_TASK: ("code", "canonical", "recent", "contradiction"),
        QueryMode.REPAIR_OR_BOUNDARY: ("bond", "canonical", "contradiction"),
        QueryMode.CREATIVE_GENERATION: ("canonical", "symbolic", "bond", "recent"),
    }

    def score(self, query: str, item: RetrievalItem, mode: QueryMode) -> RankedCandidate:
        q_terms = [term.lower() for term in query.split() if term.strip()]
        text = (item.text + " " + " ".join(item.lexical_terms)).lower()
        similarity = min(1.0, sum(1 for t in q_terms if t in text) / max(1, len(q_terms)))
        facet_values = {v.lower() for values in item.facets.values() for v in values}
        task_relevance = 1.0 if mode.value in facet_values or item.item_type.startswith(mode.value.split("_")[0]) else 0.5
        support_quality = item.confidence
        scope_match = 1.0 if "global" in facet_values or not facet_values else 0.7
        recency = 0.5
        contradiction_penalty = 0.6 if item.item_type == "contradiction" else 0.0
        token_cost_penalty = min(1.0, item.token_cost / 400.0)
        lexical_counter = Counter(item.lexical_terms)
        novelty_bonus = 0.2 if lexical_counter and lexical_counter.most_common(1)[0][1] == 1 else 0.0
        bond_fit = 0.8 if mode is QueryMode.COMPANION_CONTINUITY and item.item_type in {"bond", "vow", "hurt"} else 0.0
        final_score = (
            similarity * 0.24
            + task_relevance * 0.24
            + support_quality * 0.14
            + scope_match * 0.12
            + recency * 0.08
            + contradiction_penalty * -0.10
            + token_cost_penalty * -0.04
            + novelty_bonus * 0.04
            + bond_fit * 0.08
        )
        return RankedCandidate(**item.model_dump(), final_score=round(final_score, 4), similarity=similarity, task_relevance=task_relevance, support_quality=support_quality, scope_match=scope_match, recency=recency, contradiction_penalty=contradiction_penalty, token_cost_penalty=token_cost_penalty, novelty_bonus=novelty_bonus, bond_fit=bond_fit)

    def assemble(
        self,
        *,
        query: str,
        mode: QueryMode,
        candidates_by_family: dict[str, list[RetrievalItem]],
        truth_packet: TruthPacket | None = None,
        packet_budget: int = 900,
    ) -> MicroContextPacket:
        ranked_by_family: dict[str, list[RankedCandidate]] = {}
        for family, items in candidates_by_family.items():
            ranked = [self.score(query, item, mode) for item in items]
            ranked.sort(key=lambda item: item.final_score, reverse=True)
            ranked_by_family[family] = ranked

        packet = MicroContextPacket(mode=mode, goal=query, truth_packet=truth_packet or TruthPacket())
        budget = 0
        for family in self.MODE_TARGETS[mode]:
            for item in ranked_by_family.get(family, [])[:5]:
                if budget + item.token_cost > packet_budget:
                    continue
                budget += item.token_cost
                if family == "canonical":
                    packet.canonical_facts.append(item)
                elif family == "recent":
                    packet.recent_events.append(item)
                elif family == "bond":
                    packet.bond_excerpt.append(item)
                elif family == "symbolic":
                    packet.symbolic_context.append(item)
                elif family == "code":
                    packet.code_context.append(item)
                elif family == "contradiction":
                    packet.contradiction_items.append(item)
        packet.packet_budget_used = budget
        return packet
