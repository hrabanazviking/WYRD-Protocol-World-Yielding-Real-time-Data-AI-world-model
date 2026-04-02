from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from wyrdforge.models.common import (
    Audit,
    EntityScope,
    Governance,
    Lifecycle,
    Provenance,
    RetrievalMeta,
    RetentionClass,
    StoreName,
    TruthMeta,
    WritePolicy,
)
from wyrdforge.models.memory import (
    CanonicalFactContent,
    CanonicalFactPayload,
    CanonicalFactRecord,
    EpisodeSummaryContent,
    EpisodeSummaryPayload,
    EpisodeSummaryRecord,
    MemoryContent,
    ObservationContent,
    ObservationKind,
    ObservationPayload,
    ObservationRecord,
    PolicyContent,
    PolicyPayload,
    PolicyRecord,
)
from wyrdforge.persistence.memory_store import PersistentMemoryStore


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _base_provenance(source_type: str, source_ref: str) -> Provenance:
    return Provenance(
        source_type=source_type,
        source_ref=source_ref,
        extracted_at=_now(),
        extracted_by="writeback_engine",
    )


def _base_audit(agent: str = "writeback_engine") -> Audit:
    now = _now()
    return Audit(
        created_at=now,
        updated_at=now,
        created_by_agent=agent,
        updated_by_agent=agent,
    )


class WritebackEngine:
    """Converts structured turn output into MemoryRecord writes.

    Handles five record types:
        - ObservationRecord  → HUGIN store  (raw turn events)
        - EpisodeSummaryRecord → MUNIN store (distilled summaries)
        - CanonicalFactRecord → MIMIR store  (world/character facts)
        - PolicyRecord        → ORLOG store  (behavioral rules)

    All writes default to EPHEMERAL write_policy — the MemoryPromoter
    handles elevation to PROMOTABLE / CANONICAL over time.

    In Phase 2, input is structured dicts (not raw LLM text).
    Phase 4 will add an LLM-output parser that feeds this engine.
    """

    def __init__(
        self,
        store: PersistentMemoryStore,
        *,
        default_tenant_id: str = "default",
        default_system_id: str = "wyrd",
    ) -> None:
        self._store = store
        self._tenant_id = default_tenant_id
        self._system_id = default_system_id

    # ------------------------------------------------------------------
    # Observation (HUGIN)
    # ------------------------------------------------------------------

    def write_observation(
        self,
        *,
        title: str,
        summary: str,
        observation_kind: str = "utterance",
        participants: list[str] | None = None,
        salience: float = 0.5,
        place_id: str | None = None,
        confidence: float = 0.6,
        tags: list[str] | None = None,
        entity_scope: dict[str, Any] | None = None,
    ) -> ObservationRecord:
        """Write a raw observation to the HUGIN store."""
        now = _now()
        record = ObservationRecord(
            record_id=_new_id("obs"),
            tenant_id=self._tenant_id,
            system_id=self._system_id,
            entity_scope=EntityScope(**(entity_scope or {})),
            content=ObservationContent(
                title=title,
                summary=summary,
                structured_payload=ObservationPayload(
                    observation_kind=ObservationKind(observation_kind),
                    normalized_claims=[summary],
                    participants=participants or [],
                    observed_at=now,
                    place_id=place_id,
                    salience=salience,
                ),
            ),
            truth=TruthMeta(confidence=confidence),
            provenance=_base_provenance("turn", "writeback_engine"),
            lifecycle=Lifecycle(
                write_policy=WritePolicy.EPHEMERAL,
                retention_class=RetentionClass.SHORT,
            ),
            retrieval=RetrievalMeta(
                lexical_terms=list(set((tags or []) + title.lower().split())),
                default_priority=salience,
            ),
            governance=Governance(),
            audit=_base_audit(),
        )
        self._store.add(record)
        return record

    # ------------------------------------------------------------------
    # Episode Summary (MUNIN)
    # ------------------------------------------------------------------

    def write_episode_summary(
        self,
        *,
        title: str,
        summary: str,
        episode_id: str | None = None,
        start_turn: int = 0,
        end_turn: int = 0,
        major_events: list[str] | None = None,
        open_threads: list[str] | None = None,
        confidence: float = 0.7,
        tags: list[str] | None = None,
    ) -> EpisodeSummaryRecord:
        """Write a distilled episode summary to the MUNIN store."""
        eid = episode_id or _new_id("ep")
        record = EpisodeSummaryRecord(
            record_id=_new_id("epsum"),
            tenant_id=self._tenant_id,
            system_id=self._system_id,
            entity_scope=EntityScope(),
            content=EpisodeSummaryContent(
                title=title,
                summary=summary,
                structured_payload=EpisodeSummaryPayload(
                    episode_id=eid,
                    start_turn=start_turn,
                    end_turn=end_turn,
                    major_events=major_events or [],
                    open_threads=open_threads or [],
                    recommended_retrieval_tags=tags or [],
                ),
            ),
            truth=TruthMeta(confidence=confidence),
            provenance=_base_provenance("episode", "writeback_engine"),
            lifecycle=Lifecycle(
                write_policy=WritePolicy.REVIEWED,
                retention_class=RetentionClass.MEDIUM,
            ),
            retrieval=RetrievalMeta(
                lexical_terms=list(set((tags or []) + title.lower().split())),
                default_priority=0.5,
            ),
            governance=Governance(),
            audit=_base_audit(),
        )
        self._store.add(record)
        return record

    # ------------------------------------------------------------------
    # Canonical Fact (MIMIR)
    # ------------------------------------------------------------------

    def write_canonical_fact(
        self,
        *,
        fact_subject_id: str,
        fact_key: str,
        fact_value: str,
        domain: str = "general",
        confidence: float = 0.8,
        tags: list[str] | None = None,
        value_type: str = "string",
    ) -> CanonicalFactRecord:
        """Write a canonical world/character fact to the MIMIR store."""
        title = f"{fact_subject_id}.{fact_key} = {fact_value}"
        record = CanonicalFactRecord(
            record_id=_new_id("fact"),
            tenant_id=self._tenant_id,
            system_id=self._system_id,
            entity_scope=EntityScope(primary_subjects=[fact_subject_id]),
            content=CanonicalFactContent(
                title=title,
                summary=f"{fact_subject_id}: {fact_key} is {fact_value}",
                structured_payload=CanonicalFactPayload(
                    fact_subject_id=fact_subject_id,
                    fact_key=fact_key,
                    fact_value=fact_value,
                    value_type=value_type,
                    domain=domain,
                ),
            ),
            truth=TruthMeta(confidence=confidence),
            provenance=_base_provenance("inference", "writeback_engine"),
            lifecycle=Lifecycle(
                write_policy=WritePolicy.EPHEMERAL,
                retention_class=RetentionClass.LONG,
            ),
            retrieval=RetrievalMeta(
                lexical_terms=list(
                    set((tags or []) + [fact_subject_id, fact_key, fact_value.lower()])
                ),
                default_priority=0.6,
            ),
            governance=Governance(),
            audit=_base_audit(),
        )
        self._store.add(record)
        return record

    # ------------------------------------------------------------------
    # Policy (ORLOG)
    # ------------------------------------------------------------------

    def write_policy(
        self,
        *,
        title: str,
        rule_text: str,
        policy_kind: str = "behavioral",
        applies_to_domains: list[str] | None = None,
        priority: int = 100,
        confidence: float = 0.95,
    ) -> PolicyRecord:
        """Write a behavioral policy to the ORLOG store."""
        record = PolicyRecord(
            record_id=_new_id("pol"),
            tenant_id=self._tenant_id,
            system_id=self._system_id,
            entity_scope=EntityScope(),
            content=PolicyContent(
                title=title,
                summary=rule_text[:220],
                structured_payload=PolicyPayload(
                    policy_kind=policy_kind,
                    rule_text=rule_text,
                    applies_to_domains=applies_to_domains or [],
                    priority=priority,
                ),
            ),
            truth=TruthMeta(confidence=confidence),
            provenance=_base_provenance("config", "writeback_engine"),
            lifecycle=Lifecycle(
                write_policy=WritePolicy.IMMUTABLE,
                retention_class=RetentionClass.PERMANENT,
            ),
            retrieval=RetrievalMeta(
                lexical_terms=[policy_kind, "policy"] + (applies_to_domains or []),
                default_priority=0.9,
            ),
            governance=Governance(
                sensitivity="medium",
                requires_review_before_promotion=False,
            ),
            audit=_base_audit(),
        )
        self._store.add(record)
        return record

    # ------------------------------------------------------------------
    # Batch writeback
    # ------------------------------------------------------------------

    def process_turn(
        self,
        *,
        user_input: str,
        response_text: str,
        participants: list[str] | None = None,
        place_id: str | None = None,
        facts: list[dict] | None = None,
    ) -> dict[str, list]:
        """Write a full conversation turn to memory stores.

        Always writes an ObservationRecord for the turn.
        Optionally writes CanonicalFactRecords if `facts` are provided.

        Args:
            user_input:    The user's message text.
            response_text: The AI's response text.
            participants:  Entity IDs present in the turn.
            place_id:      Location entity ID where this turn occurred.
            facts:         Optional list of dicts, each with:
                           {fact_subject_id, fact_key, fact_value, confidence?, domain?}

        Returns:
            dict with 'observations' and 'facts' lists of written records.
        """
        obs = self.write_observation(
            title=f"Turn: {user_input[:80]}",
            summary=f"User: {user_input[:120]} | Response: {response_text[:120]}",
            observation_kind="utterance",
            participants=participants or [],
            place_id=place_id,
            salience=0.5,
        )

        written_facts: list[CanonicalFactRecord] = []
        for fact_def in (facts or []):
            fact_record = self.write_canonical_fact(
                fact_subject_id=fact_def["fact_subject_id"],
                fact_key=fact_def["fact_key"],
                fact_value=fact_def["fact_value"],
                confidence=fact_def.get("confidence", 0.75),
                domain=fact_def.get("domain", "general"),
            )
            written_facts.append(fact_record)

        return {"observations": [obs], "facts": written_facts}
