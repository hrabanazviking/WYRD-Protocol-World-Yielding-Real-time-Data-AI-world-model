"""Dusk forge 2026-10-11 (Gullinbursti) — worker C slices 7, 8, 17.

Slice 7:  search() scores from FTS5 columns, deserializing only the
         final top-`limit` records.
Slice 8:  thread-local SQLite connection reuse in PersistentMemoryStore.
Slice 17: deterministic search ranking (score ties break by record_id).
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from wyrdforge.hardening.input_validation import fts5_phrase, validate_search_query
from wyrdforge.models.common import (
    ApprovalState,
    Audit,
    EntityScope,
    Governance,
    Lifecycle,
    Provenance,
    RetrievalMeta,
    StoreName,
    TruthMeta,
)
from wyrdforge.models.memory import (
    ObservationContent,
    ObservationKind,
    ObservationPayload,
    ObservationRecord,
)
from wyrdforge.persistence import memory_store as ms_module
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.runtime.demo_seed import build_seed_fact


def _store() -> PersistentMemoryStore:
    return PersistentMemoryStore(tempfile.mktemp(suffix=".db"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mk_fact(
    record_id: str,
    title: str,
    summary: str,
    lexical_terms: list[str],
    confidence: float,
    default_priority: float = 0.0,
    approval_state: ApprovalState = ApprovalState.APPROVED,
    expires_at: datetime | None = None,
) -> "object":
    r = build_seed_fact(record_id=record_id)
    r.content.title = title
    r.content.summary = summary
    r.retrieval.lexical_terms = list(lexical_terms)
    r.retrieval.default_priority = default_priority
    r.truth.confidence = confidence
    r.truth.approval_state = approval_state
    r.lifecycle.expires_at = expires_at
    return r


def _mk_observation(
    record_id: str, title: str, summary: str, lexical_terms: list[str]
) -> ObservationRecord:
    now = _now()
    return ObservationRecord(
        record_id=record_id,
        tenant_id="test",
        system_id="wyrd",
        entity_scope=EntityScope(primary_subjects=["user:volmarr"]),
        content=ObservationContent(
            title=title,
            summary=summary,
            structured_payload=ObservationPayload(
                observation_kind=ObservationKind.UTTERANCE,
                raw_excerpt=summary,
                observed_at=now,
            ),
        ),
        truth=TruthMeta(confidence=0.6, approval_state="approved"),
        provenance=Provenance(
            source_type="test",
            source_ref="test://dusk-c",
            extracted_at=now,
            extracted_by="test",
        ),
        lifecycle=Lifecycle(),
        retrieval=RetrievalMeta(lexical_terms=list(lexical_terms)),
        governance=Governance(),
        audit=Audit(
            created_at=now,
            updated_at=now,
            created_by_agent="test",
            updated_by_agent="test",
        ),
    )


# ---------------------------------------------------------------------------
# Slice 7 — reference: verbatim transcription of search() before the change
# ---------------------------------------------------------------------------

def _reference_search_pre_slice7(
    mst: PersistentMemoryStore,
    query: str,
    /,
    *,
    store: str | None = None,
    approval_state: str | None = None,
    limit: int = 10,
    exclude_expired: bool = True,
):
    """The pre-slice-7 search: deserializes EVERY candidate to score it.

    Transcribed from PersistentMemoryStore.search as of commit 4c822ce
    (dusk-forge base). Ties resolve by candidate load order (stable sort,
    no tie-break) — the nondeterminism slice 17 removes.
    """
    terms = validate_search_query(query)
    if not terms:
        return []

    with mst._connect() as conn:
        fts_query = " OR ".join(fts5_phrase(t) for t in terms)
        fts_rows = conn.execute(
            "SELECT record_id FROM memory_fts WHERE memory_fts MATCH ?",
            (fts_query,),
        ).fetchall()
        candidate_ids = [r["record_id"] for r in fts_rows]

        if not candidate_ids:
            like_clauses = " OR ".join(["(LOWER(data_json) LIKE ?)"] * len(terms))
            like_params = [f"%{t}%" for t in terms]
            store_clause = "AND store=?" if store else ""
            store_params = [store] if store else []
            rows = conn.execute(
                f"SELECT data_json FROM memory_records WHERE ({like_clauses}) {store_clause} LIMIT 50",
                like_params + store_params,
            ).fetchall()
            candidates = [ms_module._deserialize_record(json.loads(r["data_json"])) for r in rows]
        else:
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
                extra_clauses.append("(expires_at IS NULL OR expires_at > ?)")
                extra_params.append(ms_module._now_iso())
            extra_where = (" AND " + " AND ".join(extra_clauses)) if extra_clauses else ""
            rows = conn.execute(
                f"SELECT data_json FROM memory_records "
                f"WHERE record_id IN ({placeholders}){extra_where}",
                extra_params,
            ).fetchall()
            candidates = [ms_module._deserialize_record(json.loads(r["data_json"])) for r in rows]

    scored: list[tuple[float, object]] = []
    for record in candidates:
        haystack = " ".join(
            [
                record.content.title,
                record.content.summary,
                " ".join(record.retrieval.lexical_terms),
            ]
        ).lower()
        overlap = sum(1 for t in terms if t in haystack)
        score = overlap * 1.5 + record.retrieval.default_priority + record.truth.confidence
        if score > 0:
            scored.append((score, record))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:limit]]


def _seed_ranking_corpus(store: PersistentMemoryStore) -> None:
    """30 facts + 4 observations; per-term scores unique by construction.

    confidence = 0.05 + 0.01*i (unique per record), default_priority = 0,
    so within one overlap-group every score is distinct and groups never
    interleave (overlap 2 scores >= 3.05 > overlap 1 scores <= 1.84).
    """
    topics = ["rune lore", "seidr craft", "galdr song", "wyrd threads"]
    for i in range(30):
        topic = topics[i % 4]
        extra = "rune" if i % 5 == 0 else "seidr" if i % 5 == 1 else "wyrd"
        rec = _mk_fact(
            record_id=f"rank-{i:02d}",
            title=f"note {i} on {topic}",
            summary=f"a {topic} summary with {extra} mention",
            lexical_terms=[topic.split()[0], extra],
            confidence=0.05 + 0.01 * i,
        )
        # A few records exercise the filters: one expired, one quarantined.
        if i == 7:
            rec.lifecycle.expires_at = _now() - timedelta(days=1)
        if i == 13:
            rec.truth.approval_state = ApprovalState.QUARANTINED
        store.add(rec)
    for j in range(4):
        store.add(
            _mk_observation(
                record_id=f"obs-{j}",
                title=f"hugin observation {j} about runes",
                summary="rune sighting in the woods",
                lexical_terms=["rune", "woods"],
            )
        )


_QUERIES = [
    # (query, kwargs)
    ("rune", {}),
    ("seidr", {}),
    ("wyrd", {}),
    ("rune seidr", {}),
    ("rune seidr wyrd galdr", {}),
    ("rune", {"limit": 3}),
    ("rune", {"limit": 1}),
    ("rune", {"store": StoreName.MIMIR.value}),
    ("rune", {"store": StoreName.HUGIN.value}),
    ("rune", {"approval_state": ApprovalState.QUARANTINED.value}),
    ("rune", {"exclude_expired": False}),
    ("RUNE", {}),  # case-insensitivity
]


def test_search_differential_ranking_matches_old_path() -> None:
    """Slice 7: new FTS-column scoring ranks identically to the old path.

    Seeded corpus has unique per-term scores, so the old load-order tie
    behavior cannot mask a divergence: ordered record_id lists must match
    exactly across queries, limits, and filters.
    """
    store = _store()
    _seed_ranking_corpus(store)
    for query, kwargs in _QUERIES:
        expected = [r.record_id for r in _reference_search_pre_slice7(store, query, **kwargs)]
        actual = [r.record_id for r in store.search(query, **kwargs)]
        assert actual == expected, f"ranking diverged for query={query!r} kwargs={kwargs}"


def test_search_fallback_path_differential() -> None:
    """Slice 7: the LIKE fallback (no FTS hits) also ranks identically.

    The payload-only term never reaches the FTS index, forcing the
    LIKE-scan fallback on both paths.
    """
    store = _store()
    for i in range(6):
        rec = _mk_fact(
            record_id=f"fb-{i}",
            title=f"plain title {i}",
            summary=f"plain summary {i}",
            lexical_terms=["plain"],
            confidence=0.1 + 0.05 * i,
        )
        # smuggle the term into data_json outside FTS-indexed columns
        rec.content.structured_payload.fact_value = f"zzq_payload_term_{i}"
        store.add(rec)
    expected = [r.record_id for r in _reference_search_pre_slice7(store, "zzq_payload_term")]
    actual = [r.record_id for r in store.search("zzq_payload_term")]
    assert actual == expected
    assert len(actual) == 6  # fallback really ran (FTS found nothing)


def test_search_deserializes_only_top_limit() -> None:
    """Slice 7 (white-box): scoring deserializes nothing; only top-limit records do."""
    store = _store()
    _seed_ranking_corpus(store)

    calls = {"n": 0}
    orig = ms_module._deserialize_record

    def counting(data):
        calls["n"] += 1
        return orig(data)

    ms_module._deserialize_record = counting
    try:
        results = store.search("rune", limit=5)
    finally:
        ms_module._deserialize_record = orig

    assert len(results) == 5
    assert calls["n"] == 5, (
        f"expected exactly 5 deserializations (top-limit), got {calls['n']}"
    )

    # And the old path, for contrast, deserializes every candidate.
    ms_module._deserialize_record = counting
    try:
        calls["n"] = 0
        _reference_search_pre_slice7(store, "rune", limit=5)
        old_count = calls["n"]
    finally:
        ms_module._deserialize_record = orig
    assert old_count > 5, f"old path should deserialize all candidates, got {old_count}"


def test_search_still_returns_full_records() -> None:
    """Slice 7: top-limit results are fully deserialized, correct subtypes."""
    store = _store()
    _seed_ranking_corpus(store)
    results = store.search("rune", limit=4)
    assert len(results) == 4
    for r in results:
        assert r.content.title  # real deserialized record, not a stub
        assert r.record_id.startswith(("rank-", "obs-"))


# ---------------------------------------------------------------------------
# Slice 17 — deterministic ranking
# ---------------------------------------------------------------------------

def _seed_tied_corpus(store: PersistentMemoryStore, record_ids: list[str]) -> None:
    """Records with byte-identical scoring inputs -> exact score ties."""
    for rid in record_ids:
        store.add(
            _mk_fact(
                record_id=rid,
                title="rune lore compendium",
                summary="rune tales gathered at dusk",
                lexical_terms=["rune", "lore"],
                confidence=0.5,
                default_priority=0.0,
            )
        )


def test_search_tie_break_by_record_id_is_stable() -> None:
    """Slice 17: tied scores order by record_id, identically every run."""
    store = _store()
    ids = ["tie-05", "tie-01", "tie-04", "tie-02", "tie-06", "tie-03"]
    _seed_tied_corpus(store, ids)

    first = [r.record_id for r in store.search("rune", limit=10)]
    assert first == sorted(ids), f"ties must break by record_id, got {first}"
    for _ in range(10):
        again = [r.record_id for r in store.search("rune", limit=10)]
        assert again == first, "ranking changed between runs"


def test_search_tie_break_independent_of_insertion_order() -> None:
    """Slice 17: insertion order cannot leak into ranking via load order."""
    ids = ["k-03", "k-01", "k-02"]
    store_a, store_b = _store(), _store()
    _seed_tied_corpus(store_a, ids)
    _seed_tied_corpus(store_b, list(reversed(ids)))

    order_a = [r.record_id for r in store_a.search("rune")]
    order_b = [r.record_id for r in store_b.search("rune")]
    assert order_a == order_b == sorted(ids)


# ---------------------------------------------------------------------------
# Slice 8 — thread-local connection reuse
# ---------------------------------------------------------------------------

def _bench_ops(store: PersistentMemoryStore, n: int = 200) -> None:
    """200-op mixed READ workload for the slice-8 benchmark.

    Read-only on purpose: write ops pay a ~10 ms fsync per commit on this
    machine (pre-existing; ``with``-exit commit), which would bury the
    connection-setup signal the benchmark measures. Writes are covered
    by the soak test instead.
    """
    queries = ["rune", "seidr", "wyrd galdr", "lore"]
    for i in range(n):
        op = i % 3
        if op == 0:
            store.count()
        elif op == 1:
            store.search(queries[i % len(queries)], limit=1)
        else:
            store.search(queries[(i + 1) % len(queries)], limit=3)


def test_connect_reuses_one_connection_per_thread() -> None:
    """Slice 8 (white-box): 200 mixed ops open exactly one SQLite connection."""
    store = _store()
    _seed_ranking_corpus(store)
    store.close()  # drop the seeding connection: the cache must start cold

    opened = {"n": 0}
    orig_new = PersistentMemoryStore._new_connection

    def counting_new(self):
        opened["n"] += 1
        return orig_new(self)

    PersistentMemoryStore._new_connection = counting_new
    try:
        _bench_ops(store, 200)
    finally:
        PersistentMemoryStore._new_connection = orig_new

    assert opened["n"] == 1, f"200 ops opened {opened['n']} connections, want 1"
    # WAL mode still in force on the cached connection.
    assert store._connect().execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_connect_cache_speedup_on_200op_mixed_workload() -> None:
    """Slice 8: per-op connection setup cost is gone — 200 mixed ops run faster.

    Measured on this machine (2026-10-11, hatch VM): cached ~30 ms vs
    fresh-connection ~55 ms for 200 read ops (connection setup alone is
    ~133 us/op fresh vs ~3 us/op cached — 41x; the workload's own SQL
    dilutes it to ~1.8x). Generous bound: cached must beat fresh; the
    assertion message prints the real numbers either way.
    """
    store = _store()
    _seed_ranking_corpus(store)

    def run_cached() -> float:
        t0 = time.perf_counter()
        _bench_ops(store, 200)
        return time.perf_counter() - t0

    def run_fresh() -> float:
        # Bypass the thread-local cache: every op opens a new connection,
        # exactly the pre-slice-8 behavior.
        original = store._connect
        store._connect = store._new_connection  # type: ignore[method-assign]
        try:
            t0 = time.perf_counter()
            _bench_ops(store, 200)
            return time.perf_counter() - t0
        finally:
            store._connect = original  # type: ignore[method-assign]

    run_cached()  # warmup
    cached = min(run_cached() for _ in range(3))
    fresh = min(run_fresh() for _ in range(3))
    assert cached < fresh, (
        f"SLICE 8: no speedup — cached 200 ops took {cached*1000:.1f} ms, "
        f"fresh-connection took {fresh*1000:.1f} ms "
        f"({fresh/cached:.1f}x slower without the cache)"
    )


def test_concurrent_thread_read_write_soak() -> None:
    """Slice 8: threads reading/writing concurrently stay correct.

    2 writers + 6 readers work the store simultaneously (writes interleave
    with pure-read traffic). Each thread must reuse exactly one
    connection, and no connection may ever cross threads (sqlite3 would
    raise ProgrammingError if it did).

    NOTE (pre-existing store characteristic, not slice-8): every write
    txn pays ~11 ms for the WAL commit fsync on this machine, and writers
    serialize on SQLite's write lock under the 5 s busy timeout — so ~450+
    back-to-back write txns from many threads can starve a waiter past the
    timeout (``database is locked``). Verified on the pre-slice-8 path too
    (fresh connection per op flaked the same way at 8 writers; per-op
    close/checkpoint accidentally paced the old writers). The soak below
    stays in realistic territory: ~100 write txns total, waits in ms.
    """
    store = _store()
    _seed_ranking_corpus(store)
    errors: list[BaseException] = []
    thread_conns: dict[int, int] = {}

    def writer(tid: int) -> None:
        try:
            for i in range(25):
                rec = _mk_fact(
                    record_id=f"soak-t{tid}-{i}",
                    title=f"soak rune note {i}",
                    summary="rune seidr wyrd",
                    lexical_terms=["rune"],
                    confidence=0.3,
                )
                store.add(rec)
                store.get(rec.record_id)
                store.search("rune", limit=3)
                store.count()
            thread_conns[tid] = id(store._connect())
        except BaseException as exc:  # noqa: BLE001 — soak must surface everything
            errors.append(exc)
        finally:
            store.close()

    def reader(tid: int) -> None:
        try:
            for _ in range(40):
                # Pure reads: get() bumps access_count (a write), so readers
                # use search/count/list to stay read-only.
                store.search("seidr", limit=3)
                store.count()
                store.list_by_record_type("observation")
                store.search("rune", limit=1)
            thread_conns[tid] = id(store._connect())
        except BaseException as exc:  # noqa: BLE001 — soak must surface everything
            errors.append(exc)
        finally:
            store.close()

    threads = [threading.Thread(target=writer, args=(t,)) for t in range(2)]
    threads += [threading.Thread(target=reader, args=(100 + t,)) for t in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=180)
        assert not t.is_alive(), "worker thread hung"

    assert not errors, f"soak raised: {errors!r}"
    # 8 threads -> 8 distinct connections, one per thread.
    assert len(thread_conns) == 8
    assert len(set(thread_conns.values())) == 8, "a connection was shared across threads"
    # Main thread's connection is its own.
    assert id(store._connect()) not in set(thread_conns.values())
    # WAL mode intact and all writes landed.
    assert store._connect().execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert store.count() == 34 + 2 * 25


def test_close_releases_thread_connection() -> None:
    """Slice 8: close() drops the cached connection; next op reopens."""
    store = _store()
    store.add(_mk_fact("c1", "rune title", "rune summary", ["rune"], 0.5))
    first = store._connect()
    store.close()
    store.close()  # double close is safe
    second = store._connect()
    assert second is not first
    assert store.get("c1") is not None  # store still fully usable


def test_close_is_thread_scoped() -> None:
    """Slice 8: one thread's close() does not disturb another thread's work."""
    store = _store()
    store.add(_mk_fact("c2", "rune title", "rune summary", ["rune"], 0.5))
    seen: dict[str, object] = {}

    def worker() -> None:
        seen["conn"] = store._connect()
        seen["count"] = store.count()
        store.close()

    t = threading.Thread(target=worker)
    t.start()
    t.join(timeout=60)
    assert seen["count"] == 1
    # Main thread unaffected: its cached connection still works.
    assert store.count() == 1
