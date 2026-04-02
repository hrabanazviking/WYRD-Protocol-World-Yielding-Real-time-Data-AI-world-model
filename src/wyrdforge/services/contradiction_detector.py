from __future__ import annotations

import uuid
from datetime import datetime, timezone

from wyrdforge.models.common import ApprovalState, StoreName, WritePolicy
from wyrdforge.models.memory import (
    CanonicalFactRecord,
    ContradictionContent,
    ContradictionPayload,
    ContradictionRecord,
    MemoryContent,
    MemoryRecord,
)
from wyrdforge.models.common import (
    Audit,
    EntityScope,
    Governance,
    Lifecycle,
    Provenance,
    RetrievalMeta,
    TruthMeta,
)
from wyrdforge.persistence.memory_store import PersistentMemoryStore


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ContradictionDetector:
    """Detects conflicting canonical facts and manages contradictions.

    On every new CanonicalFactRecord write, this detector checks whether
    another APPROVED canonical fact already exists for the same subject+key.
    If a conflict is found:
      - A ContradictionRecord is written to the WYRD store
      - The lower-confidence record is quarantined
      - The caller is notified via the return value

    This keeps the MIMIR (canonical) store clean and the world model
    internally consistent.
    """

    def __init__(self, store: PersistentMemoryStore) -> None:
        self._store = store

    def check_and_record(self, new_record: CanonicalFactRecord) -> list[ContradictionRecord]:
        """Check for conflicts when adding a new CanonicalFactRecord.

        Call this BEFORE or AFTER calling store.add(new_record).
        Returns a list of ContradictionRecords created (empty if no conflicts).
        """
        subject = new_record.content.structured_payload.fact_subject_id
        key = new_record.content.structured_payload.fact_key
        new_value = new_record.content.structured_payload.fact_value

        # Find all existing canonical facts for this subject+key
        existing = self._find_existing_canonical_facts(subject, key)
        conflicts: list[ContradictionRecord] = []

        for existing_record in existing:
            if existing_record.record_id == new_record.record_id:
                continue  # same record
            if existing_record.content.structured_payload.fact_value == new_value:
                continue  # same value — no conflict

            # Conflict found — create a ContradictionRecord
            contradiction = self._create_contradiction(new_record, existing_record)
            self._store.add(contradiction)

            # Quarantine the weaker record
            weaker = self._weaker_of(new_record, existing_record)
            self._store.quarantine(weaker.record_id)

            conflicts.append(contradiction)

        return conflicts

    def find_open_contradictions(self) -> list[ContradictionRecord]:
        """Return all unresolved ContradictionRecords."""
        records = self._store.list_by_record_type("contradiction", store=StoreName.WYRD.value)
        open_ones = []
        for r in records:
            if isinstance(r, ContradictionRecord):
                if r.content.structured_payload.resolution_state == "open":
                    open_ones.append(r)
        return open_ones

    def resolve(self, contradiction_record_id: str, *, preferred_record_id: str) -> bool:
        """Mark a contradiction as resolved, preferring a specific record.

        Quarantines the non-preferred record. Returns True on success.
        """
        record = self._store.get(contradiction_record_id)
        if not isinstance(record, ContradictionRecord):
            return False

        payload = record.content.structured_payload
        other_id = (
            payload.claim_b_record_id
            if preferred_record_id == payload.claim_a_record_id
            else payload.claim_a_record_id
        )

        # Update contradiction state
        payload.resolution_state = "resolved"
        payload.preferred_record_id = preferred_record_id
        self._store.add(record)

        # Quarantine the non-preferred record
        self._store.quarantine(other_id)

        # Promote the preferred record
        self._store.promote(preferred_record_id)
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_existing_canonical_facts(
        self, subject_id: str, fact_key: str
    ) -> list[CanonicalFactRecord]:
        all_canonical = self._store.list_by_record_type(
            "canonical_fact", store=StoreName.MIMIR.value
        )
        results = []
        for r in all_canonical:
            if not isinstance(r, CanonicalFactRecord):
                continue
            if r.truth.approval_state == ApprovalState.QUARANTINED:
                continue
            payload = r.content.structured_payload
            if payload.fact_subject_id == subject_id and payload.fact_key == fact_key:
                results.append(r)
        return results

    def _weaker_of(self, a: MemoryRecord, b: MemoryRecord) -> MemoryRecord:
        return a if a.truth.confidence <= b.truth.confidence else b

    def _create_contradiction(
        self,
        record_a: CanonicalFactRecord,
        record_b: CanonicalFactRecord,
    ) -> ContradictionRecord:
        now = _now()
        payload_a = record_a.content.structured_payload
        payload_b = record_b.content.structured_payload

        reason = (
            f"Conflicting values for {payload_a.fact_subject_id}.{payload_a.fact_key}: "
            f"'{payload_a.fact_value}' vs '{payload_b.fact_value}'"
        )

        return ContradictionRecord(
            record_id=f"contradiction_{uuid.uuid4().hex[:12]}",
            tenant_id=record_a.tenant_id,
            system_id=record_a.system_id,
            entity_scope=EntityScope(),
            content=ContradictionContent(
                title=f"Contradiction: {payload_a.fact_subject_id}.{payload_a.fact_key}",
                summary=reason,
                structured_payload=ContradictionPayload(
                    claim_a_record_id=record_a.record_id,
                    claim_b_record_id=record_b.record_id,
                    contradiction_reason=reason,
                    resolution_state="open",
                ),
            ),
            truth=TruthMeta(confidence=1.0),
            provenance=Provenance(
                source_type="system",
                source_ref="contradiction_detector",
                extracted_at=now,
                extracted_by="contradiction_detector",
            ),
            lifecycle=Lifecycle(write_policy=WritePolicy.CANONICAL),
            retrieval=RetrievalMeta(
                lexical_terms=[
                    payload_a.fact_subject_id,
                    payload_a.fact_key,
                    "contradiction",
                ]
            ),
            governance=Governance(),
            audit=Audit(
                created_at=now,
                updated_at=now,
                created_by_agent="contradiction_detector",
                updated_by_agent="contradiction_detector",
            ),
        )
