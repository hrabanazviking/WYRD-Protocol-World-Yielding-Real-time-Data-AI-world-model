"""MemoryToRAGAdapter — converts PersistentMemoryStore records into
MicroRAGPipeline RetrievalItems organised by retrieval family.

Family mapping:
    "canonical"     ← CanonicalFactRecord   (MIMIR store)
    "recent"        ← ObservationRecord      (HUGIN store)
    "symbolic"      ← SymbolicTraceRecord    (SEIDR store)
    "contradiction" ← ContradictionRecord    (WYRD store)
    "bond"          ← bond excerpt lines     (supplied separately)
"""
from __future__ import annotations

from collections import defaultdict

from wyrdforge.models.common import ApprovalState, StoreName
from wyrdforge.models.memory import (
    CanonicalFactRecord,
    ContradictionRecord,
    MemoryRecord,
    ObservationRecord,
    SymbolicTraceRecord,
)
from wyrdforge.models.micro_rag import RetrievalItem
from wyrdforge.persistence.memory_store import PersistentMemoryStore


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return max(10, len(text) // 4)


class MemoryToRAGAdapter:
    """Bridges PersistentMemoryStore to MicroRAGPipeline.

    Args:
        store: The persistent memory store to read from.
    """

    def __init__(self, store: PersistentMemoryStore) -> None:
        self._store = store

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def get_candidates_by_family(
        self,
        *,
        subject_ids: list[str] | None = None,
        max_per_family: int = 20,
        bond_excerpt_lines: list[str] | None = None,
    ) -> dict[str, list[RetrievalItem]]:
        """Return a family-keyed dict of RetrievalItems for MicroRAGPipeline.

        Args:
            subject_ids:        If provided, filter canonical facts to these
                                subject IDs only.
            max_per_family:     Cap per retrieval family.
            bond_excerpt_lines: Pre-rendered lines from BondGraphService.excerpt().
                                Converted to "bond" family items.
        """
        candidates: dict[str, list[RetrievalItem]] = defaultdict(list)

        # Canonical facts → "canonical"
        for r in self._store.list_by_record_type(
            "canonical_fact", store=StoreName.MIMIR.value
        )[:max_per_family]:
            if not isinstance(r, CanonicalFactRecord):
                continue
            if r.truth.approval_state == ApprovalState.QUARANTINED:
                continue
            if subject_ids:
                sid = r.content.structured_payload.fact_subject_id
                if sid not in subject_ids:
                    continue
            candidates["canonical"].append(self._canonical_to_item(r))

        # Observations → "recent"  (take the most recent max_per_family)
        obs_all = self._store.list_by_record_type(
            "observation", store=StoreName.HUGIN.value
        )
        for r in obs_all[-max_per_family:]:
            if isinstance(r, ObservationRecord):
                candidates["recent"].append(self._obs_to_item(r))

        # Symbolic traces → "symbolic"
        for r in self._store.list_by_record_type(
            "symbolic_trace", store=StoreName.SEIDR.value
        )[:max_per_family]:
            if isinstance(r, SymbolicTraceRecord):
                candidates["symbolic"].append(self._symbolic_to_item(r))

        # Contradictions → "contradiction"
        for r in self._store.list_by_record_type(
            "contradiction", store=StoreName.WYRD.value
        )[:max_per_family]:
            if isinstance(r, ContradictionRecord):
                candidates["contradiction"].append(self._contra_to_item(r))

        # Bond excerpt lines → "bond"
        if bond_excerpt_lines:
            for idx, line in enumerate(bond_excerpt_lines[:max_per_family]):
                candidates["bond"].append(
                    RetrievalItem(
                        item_id=f"bond_excerpt_{idx}",
                        item_type="bond",
                        text=line,
                        support_class="supported",
                        confidence=0.9,
                        source_ref="bond_graph_service",
                        lexical_terms=line.lower().split("=")[:2],
                        facets={"domain": ["bond"]},
                        token_cost=_estimate_tokens(line),
                    )
                )

        return dict(candidates)

    # ------------------------------------------------------------------
    # Single-record conversion
    # ------------------------------------------------------------------

    def record_to_item(self, record: MemoryRecord) -> RetrievalItem:
        """Convert any MemoryRecord to a RetrievalItem.

        The family is determined by record type — use
        ``get_candidates_by_family`` for grouped retrieval.
        """
        if isinstance(record, CanonicalFactRecord):
            return self._canonical_to_item(record)
        if isinstance(record, ObservationRecord):
            return self._obs_to_item(record)
        if isinstance(record, SymbolicTraceRecord):
            return self._symbolic_to_item(record)
        if isinstance(record, ContradictionRecord):
            return self._contra_to_item(record)
        # Generic fallback
        text = record.content.summary
        return RetrievalItem(
            item_id=record.record_id,
            item_type=record.record_type,
            text=text,
            support_class=record.truth.support_class.value,
            confidence=record.truth.confidence,
            source_ref=record.provenance.source_ref,
            lexical_terms=record.retrieval.lexical_terms[:10],
            facets=record.retrieval.facets,
            token_cost=_estimate_tokens(text),
        )

    # ------------------------------------------------------------------
    # Private converters
    # ------------------------------------------------------------------

    def _canonical_to_item(self, r: CanonicalFactRecord) -> RetrievalItem:
        p = r.content.structured_payload
        text = f"{p.fact_subject_id}.{p.fact_key} = {p.fact_value}"
        return RetrievalItem(
            item_id=r.record_id,
            item_type="canonical_fact",
            text=text,
            support_class=r.truth.support_class.value,
            confidence=r.truth.confidence,
            source_ref=r.provenance.source_ref,
            lexical_terms=[p.fact_subject_id, p.fact_key, p.fact_value.lower(), p.domain],
            facets={"domain": [p.domain]},
            token_cost=_estimate_tokens(text),
        )

    def _obs_to_item(self, r: ObservationRecord) -> RetrievalItem:
        text = r.content.summary
        participants = r.content.structured_payload.participants
        return RetrievalItem(
            item_id=r.record_id,
            item_type="observation",
            text=text,
            support_class=r.truth.support_class.value,
            confidence=r.truth.confidence,
            source_ref=r.provenance.source_ref,
            lexical_terms=r.retrieval.lexical_terms[:10],
            facets={"participants": participants} if participants else {},
            token_cost=_estimate_tokens(text),
        )

    def _symbolic_to_item(self, r: SymbolicTraceRecord) -> RetrievalItem:
        p = r.content.structured_payload
        text = (
            f"symbol={p.symbol_type}; "
            f"runes={','.join(p.rune_signature)}; "
            f"charge={p.ritual_charge:.2f}"
        )
        return RetrievalItem(
            item_id=r.record_id,
            item_type="symbolic_trace",
            text=text,
            support_class=r.truth.support_class.value,
            confidence=r.truth.confidence,
            source_ref=r.provenance.source_ref,
            lexical_terms=[p.symbol_type] + p.rune_signature[:4] + p.mood_tags[:4],
            facets={"domain": ["symbolic"]},
            token_cost=_estimate_tokens(text),
        )

    def _contra_to_item(self, r: ContradictionRecord) -> RetrievalItem:
        p = r.content.structured_payload
        text = p.contradiction_reason
        return RetrievalItem(
            item_id=r.record_id,
            item_type="contradiction",
            text=text,
            support_class="supported",
            confidence=r.truth.confidence,
            source_ref=r.provenance.source_ref,
            lexical_terms=r.retrieval.lexical_terms[:8],
            facets={"resolution": [p.resolution_state]},
            token_cost=_estimate_tokens(text),
        )
