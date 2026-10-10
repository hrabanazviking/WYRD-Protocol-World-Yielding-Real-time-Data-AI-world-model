"""Forge tests — WritebackEngine idempotency (slice 9).

process_turn(..., idempotency_key=...) replays the cached result for a
repeated key without writing new records; the record is bounded so replay
memory cannot grow without limit.
"""
from __future__ import annotations

import tempfile

from wyrdforge.models.common import StoreName
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.services.writeback_engine import WritebackEngine


def _setup() -> tuple[PersistentMemoryStore, WritebackEngine]:
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    engine = WritebackEngine(store)
    return store, engine


def _hugin_count(store: PersistentMemoryStore) -> int:
    return len(store.all(store=StoreName.HUGIN.value))


def _mimir_count(store: PersistentMemoryStore) -> int:
    return len(store.all(store=StoreName.MIMIR.value))


def test_same_key_twice_returns_identical_ids_and_writes_once() -> None:
    store, engine = _setup()
    facts = [
        {"fact_subject_id": "gunnar", "fact_key": "mood",
         "fact_value": "alert", "confidence": 0.9},
    ]
    first = engine.process_turn(
        user_input="hello", response_text="hi",
        facts=facts, idempotency_key="turn-1",
    )
    second = engine.process_turn(
        user_input="hello", response_text="hi",
        facts=facts, idempotency_key="turn-1",
    )
    # Identical returned ids ...
    assert [r.record_id for r in second["observations"]] == [
        r.record_id for r in first["observations"]
    ]
    assert [r.record_id for r in second["facts"]] == [
        r.record_id for r in first["facts"]
    ]
    # ... and exactly one observation row + one fact row in the stores.
    assert _hugin_count(store) == 1
    assert _mimir_count(store) == 1


def test_different_keys_write_two_rows() -> None:
    store, engine = _setup()
    engine.process_turn(user_input="a", response_text="b", idempotency_key="k-1")
    engine.process_turn(user_input="a", response_text="b", idempotency_key="k-2")
    assert _hugin_count(store) == 2


def test_none_key_always_writes_backward_compatible() -> None:
    store, engine = _setup()
    engine.process_turn(user_input="a", response_text="b")
    engine.process_turn(user_input="a", response_text="b", idempotency_key=None)
    assert _hugin_count(store) == 2


def test_replay_returns_copies_not_shared_lists() -> None:
    _, engine = _setup()
    first = engine.process_turn(
        user_input="a", response_text="b", idempotency_key="k",
    )
    first["observations"].append("MUTATED")
    second = engine.process_turn(
        user_input="a", response_text="b", idempotency_key="k",
    )
    assert "MUTATED" not in second["observations"]
    assert len(second["observations"]) == 1


def test_idempotency_record_is_bounded() -> None:
    store, engine = _setup()
    engine.IDEMPOTENCY_RECORD_CAP = 3  # instance-level; class default untouched
    for i in range(5):
        engine.process_turn(
            user_input="a", response_text="b", idempotency_key=f"k-{i}",
        )
    assert len(engine._idempotency) == 3
    # Oldest evicted: replaying k-0 writes a fresh row now.
    before = _hugin_count(store)
    engine.process_turn(user_input="a", response_text="b", idempotency_key="k-0")
    assert _hugin_count(store) == before + 1
    # Newest still cached: replaying k-4 writes nothing new.
    engine.process_turn(user_input="a", response_text="b", idempotency_key="k-4")
    assert _hugin_count(store) == before + 1


def test_default_cap_is_1024() -> None:
    assert WritebackEngine.IDEMPOTENCY_RECORD_CAP == 1024
