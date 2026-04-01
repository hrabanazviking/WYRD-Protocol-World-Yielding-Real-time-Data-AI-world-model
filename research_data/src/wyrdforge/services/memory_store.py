from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Iterable

from wyrdforge.models.memory import MemoryRecord
from wyrdforge.models.common import ApprovalState, WritePolicy


class InMemoryRecordStore:
    def __init__(self) -> None:
        self._records: dict[str, MemoryRecord] = {}
        self._by_store: dict[str, set[str]] = defaultdict(set)

    def add(self, record: MemoryRecord) -> None:
        self._records[record.record_id] = record
        self._by_store[record.store.value].add(record.record_id)

    def get(self, record_id: str) -> MemoryRecord | None:
        record = self._records.get(record_id)
        if record is not None:
            record.lifecycle.last_accessed_at = datetime.now(UTC)
            record.lifecycle.access_count += 1
        return record

    def all(self) -> list[MemoryRecord]:
        return list(self._records.values())

    def search(self, query: str, *, store: str | None = None, limit: int = 10) -> list[MemoryRecord]:
        terms = [term.lower() for term in query.split() if term.strip()]
        candidates: Iterable[MemoryRecord]
        if store:
            candidates = (self._records[rid] for rid in self._by_store.get(store, set()))
        else:
            candidates = self._records.values()
        scored: list[tuple[float, MemoryRecord]] = []
        for record in candidates:
            haystack = " ".join(
                [
                    record.content.title,
                    record.content.summary,
                    " ".join(record.retrieval.lexical_terms),
                    str(record.content.structured_payload),
                ]
            ).lower()
            overlap = sum(1 for term in terms if term in haystack)
            priority = record.retrieval.default_priority
            confidence = record.truth.confidence
            score = overlap * 1.5 + priority + confidence
            if score > 0:
                scored.append((score, record))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [record for _, record in scored[:limit]]

    def promote(self, record_id: str) -> MemoryRecord:
        record = self._records[record_id]
        record.truth.approval_state = ApprovalState.APPROVED
        record.lifecycle.write_policy = WritePolicy.CANONICAL
        record.audit.updated_at = datetime.now(UTC)
        return record

    def quarantine(self, record_id: str) -> MemoryRecord:
        record = self._records[record_id]
        record.truth.approval_state = ApprovalState.QUARANTINED
        record.governance.allowed_for_runtime = False
        record.audit.updated_at = datetime.now(UTC)
        return record
