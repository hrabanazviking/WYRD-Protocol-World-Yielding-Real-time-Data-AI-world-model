from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from wyrdforge.models.common import ApprovalState, WritePolicy
from wyrdforge.models.memory import (
    CanonicalFactRecord,
    ContradictionRecord,
    EpisodeSummaryRecord,
    MemoryRecord,
    ObservationRecord,
    PolicyRecord,
    SymbolicTraceRecord,
)

# ---------------------------------------------------------------------------
# Record type registry — maps record_type string → MemoryRecord subclass
# ---------------------------------------------------------------------------

_RECORD_REGISTRY: dict[str, type[MemoryRecord]] = {
    "observation": ObservationRecord,
    "canonical_fact": CanonicalFactRecord,
    "episode_summary": EpisodeSummaryRecord,
    "symbolic_trace": SymbolicTraceRecord,
    "contradiction": ContradictionRecord,
    "policy": PolicyRecord,
}


def _deserialize_record(data: dict) -> MemoryRecord:
    record_type = data.get("record_type", "")
    cls = _RECORD_REGISTRY.get(record_type, MemoryRecord)
    return cls.model_validate(data)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_records (
    record_id       TEXT PRIMARY KEY,
    store           TEXT NOT NULL,
    record_type     TEXT NOT NULL,
    tenant_id       TEXT NOT NULL,
    system_id       TEXT NOT NULL,
    approval_state  TEXT NOT NULL DEFAULT 'pending',
    write_policy    TEXT NOT NULL DEFAULT 'ephemeral',
    confidence      REAL NOT NULL DEFAULT 0.5,
    access_count    INTEGER NOT NULL DEFAULT 0,
    expires_at      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    data_json       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mr_store          ON memory_records(store);
CREATE INDEX IF NOT EXISTS idx_mr_approval       ON memory_records(approval_state);
CREATE INDEX IF NOT EXISTS idx_mr_write_policy   ON memory_records(write_policy);
CREATE INDEX IF NOT EXISTS idx_mr_tenant         ON memory_records(tenant_id);
CREATE INDEX IF NOT EXISTS idx_mr_record_type    ON memory_records(record_type);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    record_id UNINDEXED,
    title,
    summary,
    lexical_terms,
    tokenize='unicode61'
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PersistentMemoryStore:
    """SQLite-backed memory store for all wyrdforge MemoryRecord types.

    Replaces InMemoryRecordStore with durable storage. Supports:
    - Full round-trip save/load of all MemoryRecord subtypes
    - FTS5 lexical search with priority scoring
    - Approval state promotion / quarantine
    - Expiry filtering
    - Store-level partitioning
    - Integrity check
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema init
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def add(self, record: MemoryRecord) -> None:
        """Insert or replace a memory record."""
        payload = json.loads(record.model_dump_json())
        expires_at = record.lifecycle.expires_at.isoformat() if record.lifecycle.expires_at else None

        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO memory_records "
                "(record_id, store, record_type, tenant_id, system_id, "
                " approval_state, write_policy, confidence, access_count, "
                " expires_at, created_at, updated_at, data_json) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record.record_id,
                    record.store.value,
                    record.record_type,
                    record.tenant_id,
                    record.system_id,
                    record.truth.approval_state.value,
                    record.lifecycle.write_policy.value,
                    record.truth.confidence,
                    record.lifecycle.access_count,
                    expires_at,
                    record.audit.created_at.isoformat(),
                    record.audit.updated_at.isoformat(),
                    json.dumps(payload),
                ),
            )
            # Sync FTS
            conn.execute("DELETE FROM memory_fts WHERE record_id=?", (record.record_id,))
            conn.execute(
                "INSERT INTO memory_fts (record_id, title, summary, lexical_terms) VALUES (?,?,?,?)",
                (
                    record.record_id,
                    record.content.title,
                    record.content.summary,
                    " ".join(record.retrieval.lexical_terms),
                ),
            )

    def delete(self, record_id: str) -> bool:
        """Remove a record. Returns True if it existed."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM memory_records WHERE record_id=?", (record_id,)
            )
            conn.execute("DELETE FROM memory_fts WHERE record_id=?", (record_id,))
            return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get(self, record_id: str) -> MemoryRecord | None:
        """Fetch a single record by ID, updating access metadata."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data_json, access_count FROM memory_records WHERE record_id=?",
                (record_id,),
            ).fetchone()
            if row is None:
                return None
            record = _deserialize_record(json.loads(row["data_json"]))
            # Update access tracking
            new_count = row["access_count"] + 1
            conn.execute(
                "UPDATE memory_records SET access_count=?, updated_at=? WHERE record_id=?",
                (new_count, _now_iso(), record_id),
            )
            record.lifecycle.access_count = new_count
            record.lifecycle.last_accessed_at = datetime.now(timezone.utc)
            return record

    def all(self, *, store: str | None = None, exclude_expired: bool = True) -> list[MemoryRecord]:
        """Return all records, optionally filtered by store and expiry."""
        now = _now_iso()
        clauses = []
        params: list = []
        if store:
            clauses.append("store=?")
            params.append(store)
        if exclude_expired:
            clauses.append("(expires_at IS NULL OR expires_at > ?)")
            params.append(now)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT data_json FROM memory_records {where} ORDER BY created_at",
                params,
            ).fetchall()
        return [_deserialize_record(json.loads(r["data_json"])) for r in rows]

    def search(
        self,
        query: str,
        *,
        store: str | None = None,
        approval_state: str | None = None,
        limit: int = 10,
        exclude_expired: bool = True,
    ) -> list[MemoryRecord]:
        """Lexical + scored search across memory records.

        Uses FTS5 for candidate retrieval, then applies the same
        multi-factor scoring as InMemoryRecordStore.
        """
        terms = [t.lower() for t in query.split() if t.strip()]
        if not terms:
            return []

        with self._connect() as conn:
            # FTS5 candidate retrieval
            fts_query = " OR ".join(f'"{t}"' for t in terms)
            fts_rows = conn.execute(
                "SELECT record_id FROM memory_fts WHERE memory_fts MATCH ?",
                (fts_query,),
            ).fetchall()
            candidate_ids = [r["record_id"] for r in fts_rows]

            if not candidate_ids:
                # Fallback: LIKE scan on title+summary if FTS finds nothing
                like_clauses = " OR ".join(
                    ["(LOWER(data_json) LIKE ?)"] * len(terms)
                )
                like_params = [f"%{t}%" for t in terms]
                store_clause = "AND store=?" if store else ""
                store_params = [store] if store else []
                rows = conn.execute(
                    f"SELECT data_json FROM memory_records WHERE ({like_clauses}) {store_clause} LIMIT 50",
                    like_params + store_params,
                ).fetchall()
                candidates = [_deserialize_record(json.loads(r["data_json"])) for r in rows]
            else:
                # Load candidates
                placeholders = ",".join("?" * len(candidate_ids))
                extra_clauses = []
                extra_params: list = list(candidate_ids)
                if store:
                    extra_clauses.append("store=?")
                    extra_params.append(store)
                if approval_state:
                    extra_clauses.append("approval_state=?")
                    extra_params.append(approval_state)
                if exclude_expired:
                    extra_clauses.append(f"(expires_at IS NULL OR expires_at > ?)")
                    extra_params.append(_now_iso())
                extra_where = (" AND " + " AND ".join(extra_clauses)) if extra_clauses else ""
                rows = conn.execute(
                    f"SELECT data_json FROM memory_records "
                    f"WHERE record_id IN ({placeholders}){extra_where}",
                    extra_params,
                ).fetchall()
                candidates = [_deserialize_record(json.loads(r["data_json"])) for r in rows]

        # Score candidates
        scored: list[tuple[float, MemoryRecord]] = []
        for record in candidates:
            haystack = " ".join([
                record.content.title,
                record.content.summary,
                " ".join(record.retrieval.lexical_terms),
            ]).lower()
            overlap = sum(1 for t in terms if t in haystack)
            score = overlap * 1.5 + record.retrieval.default_priority + record.truth.confidence
            if score > 0:
                scored.append((score, record))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:limit]]

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def promote(self, record_id: str) -> MemoryRecord:
        """Mark a record as APPROVED + CANONICAL write policy."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data_json FROM memory_records WHERE record_id=?", (record_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Record '{record_id}' not found")
            record = _deserialize_record(json.loads(row["data_json"]))
            record.truth.approval_state = ApprovalState.APPROVED
            record.lifecycle.write_policy = WritePolicy.CANONICAL
            payload = json.loads(record.model_dump_json())
            conn.execute(
                "UPDATE memory_records "
                "SET approval_state=?, write_policy=?, updated_at=?, data_json=? "
                "WHERE record_id=?",
                (
                    ApprovalState.APPROVED.value,
                    WritePolicy.CANONICAL.value,
                    _now_iso(),
                    json.dumps(payload),
                    record_id,
                ),
            )
        return record

    def quarantine(self, record_id: str) -> MemoryRecord:
        """Mark a record as QUARANTINED and block runtime use."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data_json FROM memory_records WHERE record_id=?", (record_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Record '{record_id}' not found")
            record = _deserialize_record(json.loads(row["data_json"]))
            record.truth.approval_state = ApprovalState.QUARANTINED
            record.governance.allowed_for_runtime = False
            payload = json.loads(record.model_dump_json())
            conn.execute(
                "UPDATE memory_records "
                "SET approval_state=?, updated_at=?, data_json=? "
                "WHERE record_id=?",
                (
                    ApprovalState.QUARANTINED.value,
                    _now_iso(),
                    json.dumps(payload),
                    record_id,
                ),
            )
        return record

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def list_by_store(self, store: str) -> list[MemoryRecord]:
        return self.all(store=store)

    def list_pending_promotion(self) -> list[MemoryRecord]:
        """Records with PROMOTABLE write policy that haven't been quarantined."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT data_json FROM memory_records "
                "WHERE write_policy=? AND approval_state != ? "
                "ORDER BY confidence DESC",
                (WritePolicy.PROMOTABLE.value, ApprovalState.QUARANTINED.value),
            ).fetchall()
        return [_deserialize_record(json.loads(r["data_json"])) for r in rows]

    def list_by_record_type(self, record_type: str, *, store: str | None = None) -> list[MemoryRecord]:
        clauses = ["record_type=?"]
        params: list = [record_type]
        if store:
            clauses.append("store=?")
            params.append(store)
        where = "WHERE " + " AND ".join(clauses)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT data_json FROM memory_records {where} ORDER BY created_at",
                params,
            ).fetchall()
        return [_deserialize_record(json.loads(r["data_json"])) for r in rows]

    def count(self, *, store: str | None = None) -> int:
        where = "WHERE store=?" if store else ""
        params = [store] if store else []
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) FROM memory_records {where}", params
            ).fetchone()
            return row[0] if row else 0

    def integrity_check(self) -> bool:
        with self._connect() as conn:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            return result is not None and result[0] == "ok"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_and_patch(self, record_id: str, conn: sqlite3.Connection | None) -> MemoryRecord | None:
        ctx = conn or self._connect()
        row = ctx.execute(
            "SELECT data_json FROM memory_records WHERE record_id=?", (record_id,)
        ).fetchone()
        if row is None:
            return None
        return _deserialize_record(json.loads(row["data_json"]))
