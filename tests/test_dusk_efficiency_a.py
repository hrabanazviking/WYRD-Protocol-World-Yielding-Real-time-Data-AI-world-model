"""Dusk-forge 2026-10-11 — worker A ("Gullinbursti — the Swift and True").

Wedge SWIFT slices 1, 2, 9: SQL pushdown for the contradiction detector's
conflict scan and open-contradiction listing, plus batched contradiction
checking.  Every acceptance criterion below is a real test against real
SQLite — no fake benchmarks, no mocks of the store.
"""
from __future__ import annotations

import time

import pytest

from wyrdforge.models.common import ApprovalState, StoreName
from wyrdforge.models.memory import CanonicalFactRecord, ContradictionRecord
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.services.contradiction_detector import ContradictionDetector
from wyrdforge.services.writeback_engine import WritebackEngine


# ---------------------------------------------------------------------------
# Legacy reference implementations — exact copies of the pre-forge Python
# scan paths these slices replace.  Kept here as the differential baseline.
# ---------------------------------------------------------------------------

def _legacy_find_existing_canonical_facts(
    store: PersistentMemoryStore, subject_id: str, fact_key: str
) -> list[CanonicalFactRecord]:
    all_canonical = store.list_by_record_type(
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


def _legacy_find_open_contradictions(
    store: PersistentMemoryStore,
) -> list[ContradictionRecord]:
    records = store.list_by_record_type("contradiction", store=StoreName.WYRD.value)
    open_ones = []
    for r in records:
        if isinstance(r, ContradictionRecord):
            if r.content.structured_payload.resolution_state == "open":
                open_ones.append(r)
    return open_ones


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _fresh_store(tmp_path) -> PersistentMemoryStore:
    return PersistentMemoryStore(str(tmp_path / "dusk_a.db"))


def _seed_canonical_facts(store: PersistentMemoryStore, n: int = 500) -> list[CanonicalFactRecord]:
    """Seed *n* canonical facts across 50 subjects x 10 keys; quarantine ~10%."""
    engine = WritebackEngine(store)
    facts = []
    for i in range(n):
        fact = engine.write_canonical_fact(
            fact_subject_id=f"subject_{i % 50:02d}",
            fact_key=f"key_{i % 10}",
            fact_value=f"value_{(i // 50) % 4}",
            confidence=0.5 + (i % 10) / 20.0,
        )
        facts.append(fact)
    for i, fact in enumerate(facts):
        if i % 10 == 0:  # ~10% quarantined
            store.quarantine(fact.record_id)
    return facts


def _conflict_signature(store: PersistentMemoryStore, c: ContradictionRecord) -> tuple:
    """Semantic signature of a contradiction — independent of random record ids."""
    p = c.content.structured_payload

    def triple(rid: str) -> tuple[str, str, str]:
        r = store.get(rid)
        assert isinstance(r, CanonicalFactRecord), f"claim {rid} not a canonical fact"
        sp = r.content.structured_payload
        return (sp.fact_subject_id, sp.fact_key, sp.fact_value)

    return (triple(p.claim_a_record_id), triple(p.claim_b_record_id), p.contradiction_reason)


def _store_snapshot(store: PersistentMemoryStore) -> dict:
    """Semantic snapshot of contradiction + quarantine state for comparison.

    Compares (subject, key, value, state) tuples rather than random
    record_ids, so two identically-seeded stores can be compared.
    """
    facts = []
    contradictions = []
    for r in store.all():
        if isinstance(r, CanonicalFactRecord):
            sp = r.content.structured_payload
            facts.append(
                (sp.fact_subject_id, sp.fact_key, sp.fact_value,
                 r.truth.approval_state.value)
            )
        elif isinstance(r, ContradictionRecord):
            sp = r.content.structured_payload
            contradictions.append(
                (sp.contradiction_reason, sp.resolution_state)
            )
    return {
        "facts": sorted(facts),
        "contradictions": sorted(contradictions),
    }


class _ConnectCounter:
    """White-box round-trip counter: wraps store._connect and counts calls."""

    def __init__(self, store: PersistentMemoryStore) -> None:
        self.count = 0
        self._orig = store._connect

        def counting():
            self.count += 1
            return self._orig()

        store._connect = counting  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# SLICE 1 — find_canonical_facts SQL pushdown
# ---------------------------------------------------------------------------

class TestSlice1ConflictScanPushdown:
    def test_differential_identical_to_legacy_python_scan(self, tmp_path) -> None:
        store = _fresh_store(tmp_path)
        _seed_canonical_facts(store, n=500)

        # Mix of hit pairs, quarantined-heavy pairs, and misses.
        probes = [
            ("subject_00", "key_0"),
            ("subject_07", "key_3"),
            ("subject_23", "key_9"),
            ("subject_49", "key_4"),
            ("no_such_subject", "key_0"),
            ("subject_01", "no_such_key"),
        ]
        for subject, key in probes:
            legacy_ids = sorted(
                r.record_id
                for r in _legacy_find_existing_canonical_facts(store, subject, key)
            )
            new_ids = sorted(
                r.record_id for r in store.find_canonical_facts(subject, key)
            )
            assert new_ids == legacy_ids, f"mismatch for {subject}.{key}"

    def test_exclude_quarantined_flag(self, tmp_path) -> None:
        store = _fresh_store(tmp_path)
        _seed_canonical_facts(store, n=500)

        subject, key = "subject_00", "key_0"
        excluded = store.find_canonical_facts(subject, key, exclude_quarantined=True)
        assert all(
            r.truth.approval_state != ApprovalState.QUARANTINED for r in excluded
        )
        included = store.find_canonical_facts(subject, key, exclude_quarantined=False)
        assert len(included) > len(excluded)
        # The legacy path (which always excluded quarantined) matches the
        # default; included is a superset covering the quarantined ones.
        legacy_ids = {
            r.record_id
            for r in _legacy_find_existing_canonical_facts(store, subject, key)
        }
        assert {r.record_id for r in excluded} == legacy_ids
        assert legacy_ids < {r.record_id for r in included}

    def test_sql_injection_safe_subject(self, tmp_path) -> None:
        store = _fresh_store(tmp_path)
        _seed_canonical_facts(store, n=50)
        # Hostile subject/key must not break the query or match anything.
        assert store.find_canonical_facts("x' OR '1'='1", "key_0") == []
        assert store.find_canonical_facts('"); DROP TABLE memory_records; --', "k") == []
        assert store.count() > 0  # table intact

    def test_benchmark_at_least_3x_faster_than_legacy_scan(self, tmp_path) -> None:
        store = _fresh_store(tmp_path)
        _seed_canonical_facts(store, n=500)
        subject, key = "subject_23", "key_3"
        reps = 20

        t0 = time.perf_counter()
        for _ in range(reps):
            _legacy_find_existing_canonical_facts(store, subject, key)
        legacy_elapsed = time.perf_counter() - t0

        t0 = time.perf_counter()
        for _ in range(reps):
            store.find_canonical_facts(subject, key)
        new_elapsed = time.perf_counter() - t0

        assert new_elapsed > 0, "new path took no measurable time?"
        speedup = legacy_elapsed / new_elapsed
        print(f"\nslice1: legacy={legacy_elapsed:.4f}s new={new_elapsed:.4f}s speedup={speedup:.1f}x")
        # Generous bound per plan: at least 3x faster (measured well above).
        assert legacy_elapsed >= 3 * new_elapsed, (
            f"insufficient speedup: legacy={legacy_elapsed:.4f}s "
            f"new={new_elapsed:.4f}s (need >=3x)"
        )


# ---------------------------------------------------------------------------
# SLICE 2 — find_open_contradictions SQL pushdown
# ---------------------------------------------------------------------------

class TestSlice2OpenContradictionsPushdown:
    def _seed_with_contradictions(self, store: PersistentMemoryStore) -> None:
        engine = WritebackEngine(store)
        detector = ContradictionDetector(store)
        pairs = [
            ("gunnar", "location", "mead_hall", "docks"),
            ("sigrid", "role", "warrior", "volva"),
            ("bjorn", "weapon", "axe", "sword"),
            ("astrid", "status", "alive", "wounded"),
        ]
        created = []
        for subject, key, v1, v2 in pairs:
            f1 = engine.write_canonical_fact(
                fact_subject_id=subject, fact_key=key, fact_value=v1, confidence=0.6
            )
            f2 = engine.write_canonical_fact(
                fact_subject_id=subject, fact_key=key, fact_value=v2, confidence=0.9
            )
            created.extend(detector.check_and_record(f2))
        # Resolve one so the store holds both open and resolved states.
        detector.resolve(created[0].record_id, preferred_record_id=created[0].content.structured_payload.claim_a_record_id)
        # Add noise: resolved-by-quarantine path + unrelated record types.
        engine.write_canonical_fact(
            fact_subject_id="gunnar", fact_key="location", fact_value="mead_hall",
            confidence=0.5,
        )
        return created

    def test_differential_identical_to_legacy(self, tmp_path) -> None:
        store = _fresh_store(tmp_path)
        self._seed_with_contradictions(store)

        legacy_ids = sorted(
            r.record_id for r in _legacy_find_open_contradictions(store)
        )
        new_ids = sorted(
            r.record_id for r in store.find_open_contradictions()
        )
        detector_ids = sorted(
            r.record_id
            for r in ContradictionDetector(store).find_open_contradictions()
        )
        assert new_ids == legacy_ids
        assert detector_ids == legacy_ids
        assert len(legacy_ids) == 3  # 4 created, 1 resolved

    def test_single_sql_query(self, tmp_path) -> None:
        store = _fresh_store(tmp_path)
        self._seed_with_contradictions(store)
        counter = _ConnectCounter(store)
        ContradictionDetector(store).find_open_contradictions()
        assert counter.count == 1, f"expected 1 round-trip, got {counter.count}"

    def test_empty_store_returns_empty(self, tmp_path) -> None:
        store = _fresh_store(tmp_path)
        assert store.find_open_contradictions() == []
        assert ContradictionDetector(store).find_open_contradictions() == []


# ---------------------------------------------------------------------------
# SLICE 9 — check_many batched contradiction checking
# ---------------------------------------------------------------------------

class TestSlice9BatchedChecking:
    def _build_scenario(self, tmp_path):
        """Two identically-seeded stores with parallel batch-record lists.

        Returns (store_seq, recs_seq, store_batch, recs_batch).  The batch
        record lists are parallel by index but carry each store's own
        (random) record ids.
        """
        store_seq = PersistentMemoryStore(str(tmp_path / "seq.db"))
        store_batch = PersistentMemoryStore(str(tmp_path / "batch.db"))
        recs_seq: list[CanonicalFactRecord] = []
        recs_batch: list[CanonicalFactRecord] = []
        for store, recs in ((store_seq, recs_seq), (store_batch, recs_batch)):
            engine = WritebackEngine(store)
            # Base facts (already in store).
            engine.write_canonical_fact(
                fact_subject_id="gunnar", fact_key="location",
                fact_value="mead_hall", confidence=0.6,
            )
            engine.write_canonical_fact(
                fact_subject_id="sigrid", fact_key="role",
                fact_value="warrior", confidence=0.95,
            )
            engine.write_canonical_fact(
                fact_subject_id="bjorn", fact_key="weapon",
                fact_value="axe", confidence=0.5,
            )
            # Batch records — added to the store, then checked (self skipped by id).
            for subject, key, value, conf in [
                ("gunnar", "location", "docks", 0.9),      # conflicts with mead_hall; wins
                ("gunnar", "location", "forge", 0.4),      # conflicts with docks; loses
                ("sigrid", "role", "warrior", 0.7),        # same value — no conflict
                ("sigrid", "role", "volva", 0.8),          # conflicts; loses to 0.95 warrior
                ("newcomer", "status", "alive", 0.8),       # novel — no conflict
                ("bjorn", "weapon", "sword", 0.9),          # conflicts with axe; wins
            ]:
                recs.append(engine.write_canonical_fact(
                    fact_subject_id=subject, fact_key=key,
                    fact_value=value, confidence=conf,
                ))
        return store_seq, recs_seq, store_batch, recs_batch

    def test_check_many_matches_sequential_conflicts(self, tmp_path) -> None:
        store_seq, recs_seq, store_batch, recs_batch = self._build_scenario(tmp_path)

        det_seq = ContradictionDetector(store_seq)
        seq_conflicts = []
        for rec in recs_seq:
            seq_conflicts.extend(det_seq.check_and_record(rec))
        seq_sig = [_conflict_signature(store_seq, c) for c in seq_conflicts]

        det_batch = ContradictionDetector(store_batch)
        batch_conflicts = det_batch.check_many(recs_batch)
        batch_sig = [_conflict_signature(store_batch, c) for c in batch_conflicts]

        assert batch_sig == seq_sig, (
            f"conflict mismatch:\nseq={seq_sig}\nbatch={batch_sig}"
        )
        # End-state parity: facts (incl. quarantine states) + contradictions identical.
        assert _store_snapshot(store_batch) == _store_snapshot(store_seq)
        assert len(batch_conflicts) == len(seq_conflicts) > 0

    def test_check_many_fewer_round_trips(self, tmp_path) -> None:
        store_seq, recs_seq, store_batch, recs_batch = self._build_scenario(tmp_path)

        det_seq = ContradictionDetector(store_seq)
        counter_seq = _ConnectCounter(store_seq)
        for rec in recs_seq:
            det_seq.check_and_record(rec)
        seq_trips = counter_seq.count

        det_batch = ContradictionDetector(store_batch)
        counter_batch = _ConnectCounter(store_batch)
        det_batch.check_many(recs_batch)
        batch_trips = counter_batch.count

        print(f"\nslice9: sequential round-trips={seq_trips} batched={batch_trips}")
        # Batched issues ONE multi-key lookup for all 6 records instead of 6.
        assert batch_trips < seq_trips, (
            f"batched ({batch_trips}) not fewer than sequential ({seq_trips})"
        )

    def test_check_many_single_lookup_query(self, tmp_path) -> None:
        store = _fresh_store(tmp_path)
        engine = WritebackEngine(store)
        detector = ContradictionDetector(store)
        engine.write_canonical_fact(
            fact_subject_id="gunnar", fact_key="location",
            fact_value="mead_hall", confidence=0.6,
        )
        recs = [
            engine.write_canonical_fact(
                fact_subject_id="gunnar", fact_key="location",
                fact_value="docks", confidence=0.9,
            ),
            engine.write_canonical_fact(
                fact_subject_id="sigrid", fact_key="role",
                fact_value="warrior", confidence=0.8,
            ),
        ]
        counter = _ConnectCounter(store)
        # Isolate the lookup: count only the multi-key SELECT phase by
        # calling the store helper directly.
        store.find_canonical_facts_many(
            [("gunnar", "location"), ("sigrid", "role"), ("gunnar", "location")]
        )
        assert counter.count == 1

        # Full check_many on an empty batch costs nothing.
        store2 = _fresh_store(tmp_path)
        counter2 = _ConnectCounter(store2)
        assert ContradictionDetector(store2).check_many([]) == []
        assert counter2.count == 0

    def test_check_many_empty_batch(self, tmp_path) -> None:
        store = _fresh_store(tmp_path)
        assert ContradictionDetector(store).check_many([]) == []

    def test_find_canonical_facts_many_differential(self, tmp_path) -> None:
        store = _fresh_store(tmp_path)
        _seed_canonical_facts(store, n=300)
        pairs = [
            ("subject_00", "key_0"),
            ("subject_12", "key_2"),
            ("subject_49", "key_9"),
            ("ghost", "key_0"),
        ]
        got = store.find_canonical_facts_many(pairs)
        assert set(got.keys()) == set(dict.fromkeys(pairs))
        for subject, key in pairs:
            expected = sorted(
                r.record_id
                for r in _legacy_find_existing_canonical_facts(store, subject, key)
            )
            assert sorted(r.record_id for r in got[(subject, key)]) == expected
