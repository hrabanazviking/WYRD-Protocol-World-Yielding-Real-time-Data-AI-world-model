"""Phase A3 — turn-atomic writeback.

Roadmap A3: a turn's observation+facts must land as one recoverable
unit, not as sequential per-record transactions that can commit a
fractured turn when something fails mid-turn.

Design under test (smallest sound mechanism):
- ``WritebackEngine.process_turn`` STAGES the whole turn first
  (builds the observation and every fact record, writing nothing),
  then COMMITS through ``PersistentMemoryStore.add_many`` — one
  SQLite transaction for the entire turn.
- A failure during staging (malformed fact dict) therefore happens
  before any write; a failure inside the commit rolls the whole
  batch back. Either way: no partial turn in the store.
- The idempotency record is only populated after a successful
  commit, so a failed turn stays retryable under the same key.

Bond half of A3 — investigated finding, pinned here:
``TurnLoop`` has NO bond mutation path. Its constructor takes only
oracle/engine/detector/connector (+ context scalars + bus), its
``execute_turn`` takes only user_input/location_id/extra_facts, it
holds no BondGraphService or PersistentBondStore reference, and
``writeback_engine`` contains no bond-store calls at all (verified
by inspection 2026-10-29). Bond durability therefore cannot be
"enforced by the TurnLoop" — there is nothing in the loop that
mutates bonds. A3 is scoped to writeback atomicity; the tests at
the bottom pin that absence so a future bond path, if one is ever
added, fails loudly here and forces the sync-enforcement design
to be revisited deliberately.
"""
from __future__ import annotations

import inspect
import tempfile

import pytest

from wyrdforge.models.common import StoreName
from wyrdforge.models.memory import CanonicalFactRecord, ObservationRecord
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.runtime import turn_loop as turn_loop_module
from wyrdforge.runtime.events import EventBus
from wyrdforge.runtime.turn_loop import TurnLoop
from wyrdforge.services import writeback_engine as writeback_module
from wyrdforge.services.writeback_engine import WritebackEngine


def _setup() -> tuple[PersistentMemoryStore, WritebackEngine]:
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    engine = WritebackEngine(store)
    return store, engine


_FACTS = [
    {"fact_subject_id": "gunnar", "fact_key": "role", "fact_value": "warrior"},
    {"fact_subject_id": "gunnar", "fact_key": "faction", "fact_value": "thornholt"},
]


def _counts(store: PersistentMemoryStore) -> tuple[int, int]:
    return (
        len(store.all(store=StoreName.HUGIN.value)),
        len(store.all(store=StoreName.MIMIR.value)),
    )


# ---------------------------------------------------------------------------
# (a) Mid-turn failure leaves NO partial turn committed
# ---------------------------------------------------------------------------

def test_malformed_second_fact_leaves_no_partial_turn() -> None:
    """Staging failure: the second fact dict is missing fact_value.

    Pre-A3, process_turn wrote the observation and the first fact
    (each its own transaction) before reaching the broken fact —
    a fractured turn. Now nothing may be in the store.
    """
    store, engine = _setup()
    bad_facts = [
        {"fact_subject_id": "gunnar", "fact_key": "role", "fact_value": "warrior"},
        {"fact_subject_id": "gunnar", "fact_key": "faction"},  # no fact_value
    ]
    with pytest.raises(KeyError):
        engine.process_turn(speaker_id="gunnar",
            user_input="Gunnar is a warrior of Thornholt",
            response_text="Noted",
            facts=bad_facts,
        )
    assert _counts(store) == (0, 0)
    assert store.count() == 0
    assert store.all() == []


def test_store_failure_mid_commit_rolls_back_whole_turn(monkeypatch) -> None:
    """Commit failure: the store dies inserting the SECOND record.

    The observation insert already executed inside the batch
    transaction; the rollback must erase it — the store must hold
    no part of the turn afterwards.
    """
    store, engine = _setup()
    original = PersistentMemoryStore._insert_on_conn
    calls = {"n": 0}

    def failing_insert(self, record, conn):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated store failure mid-turn")
        return original(self, record, conn)

    monkeypatch.setattr(
        PersistentMemoryStore, "_insert_on_conn", failing_insert
    )
    with pytest.raises(RuntimeError, match="mid-turn"):
        engine.process_turn(speaker_id="gunnar",
            user_input="hello", response_text="hi", facts=_FACTS
        )
    assert calls["n"] == 2  # failure really was mid-batch, not at staging
    assert store.count() == 0
    assert store.all() == []
    assert _counts(store) == (0, 0)


def test_add_many_mid_batch_failure_rolls_back_everything(monkeypatch) -> None:
    """Store-level pin: add_many is one transaction, all-or-nothing."""
    store, engine = _setup()
    fabricator_store, fabricator = _setup()
    records = [
        fabricator.write_observation(speaker_id="gunnar", title="one", summary="first"),
        fabricator.write_canonical_fact(
            fact_subject_id="gunnar", fact_key="role", fact_value="warrior"
        ),
        fabricator.write_canonical_fact(
            fact_subject_id="gunnar", fact_key="faction", fact_value="thornholt"
        ),
    ]
    original = PersistentMemoryStore._insert_on_conn
    calls = {"n": 0}

    def failing_insert(self, record, conn):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("boom on third")
        return original(self, record, conn)

    monkeypatch.setattr(
        PersistentMemoryStore, "_insert_on_conn", failing_insert
    )
    with pytest.raises(RuntimeError, match="boom on third"):
        store.add_many(records)
    assert store.count() == 0
    assert store.all() == []


def test_failed_turn_does_not_consume_idempotency_key() -> None:
    """A failed turn must stay retryable under the same key."""
    store, engine = _setup()
    bad_facts = [{"fact_subject_id": "gunnar", "fact_key": "faction"}]
    with pytest.raises(KeyError):
        engine.process_turn(speaker_id="gunnar",
            user_input="hi", response_text="hello",
            facts=bad_facts, idempotency_key="turn-retry",
        )
    assert store.count() == 0
    # Retry, corrected, under the SAME key: must actually write.
    result = engine.process_turn(speaker_id="gunnar",
        user_input="hi", response_text="hello",
        facts=_FACTS, idempotency_key="turn-retry",
    )
    assert len(result["observations"]) == 1
    assert len(result["facts"]) == 2
    assert _counts(store) == (1, 2)


# ---------------------------------------------------------------------------
# (b) Happy path: exactly the same records as the pre-A3 behaviour
# ---------------------------------------------------------------------------

def test_successful_turn_commits_exactly_the_staged_records() -> None:
    store, engine = _setup()
    result = engine.process_turn(
        user_input="Gunnar walks in",
        response_text="He nods at the fire",
        participants=["gunnar", "sigrid"],
        place_id="mead_hall",
        facts=_FACTS,
    )
    assert len(result["observations"]) == 1
    assert len(result["facts"]) == 2
    assert isinstance(result["observations"][0], ObservationRecord)
    assert all(isinstance(f, CanonicalFactRecord) for f in result["facts"])
    assert _counts(store) == (1, 2)
    assert store.count() == 3

    obs = store.get(result["observations"][0].record_id)
    assert obs is not None
    assert obs.content.title == "Turn: Gunnar walks in"
    assert obs.content.summary == (
        "User: Gunnar walks in | Response: He nods at the fire"
    )
    assert obs.content.structured_payload.participants == ["gunnar", "sigrid"]
    assert obs.content.structured_payload.place_id == "mead_hall"

    for returned, fact_def in zip(result["facts"], _FACTS):
        loaded = store.get(returned.record_id)
        assert loaded is not None
        payload = loaded.content.structured_payload
        assert payload.fact_subject_id == fact_def["fact_subject_id"]
        assert payload.fact_key == fact_def["fact_key"]
        assert payload.fact_value == fact_def["fact_value"]
        assert loaded.truth.confidence == 0.75  # process_turn default


def test_add_many_matches_sequential_adds() -> None:
    """Batch commit produces the same store content as add() x N."""
    _, fabricator = _setup()
    records = [
        fabricator.write_observation(speaker_id="gunnar", title="t", summary="s"),
        fabricator.write_canonical_fact(
            fact_subject_id="gunnar", fact_key="mood", fact_value="calm"
        ),
    ]
    sequential = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    for record in records:
        sequential.add(record)
    batched = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    batched.add_many(records)

    seq_dump = sorted(
        r.model_dump_json() for r in sequential.all(exclude_expired=False)
    )
    batch_dump = sorted(
        r.model_dump_json() for r in batched.all(exclude_expired=False)
    )
    assert batch_dump == seq_dump
    # FTS index is synced identically: search finds the batched fact.
    assert [r.record_id for r in batched.search("gunnar")] == [
        r.record_id for r in sequential.search("gunnar")
    ]


def test_add_many_empty_batch_is_a_noop() -> None:
    store, _engine = _setup()
    store.add_many([])
    assert store.count() == 0


def test_add_many_bus_events_match_add_semantics() -> None:
    """True inserts emit once each, after commit; re-adds emit nothing."""
    bus = EventBus()
    seen: list[tuple[str, dict]] = []

    def recorder(env):
        seen.append((env.topic, env.payload))

    for topic in ("memory.observation_added", "memory.fact_added"):
        try:
            bus.register_topic(topic)
        except ValueError:
            pass
        bus.subscribe(topic, recorder)

    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"), bus=bus)
    engine = WritebackEngine(store)
    result = engine.process_turn(speaker_id="gunnar",
        user_input="hi", response_text="hello", facts=_FACTS[:1]
    )
    obs_id = result["observations"][0].record_id
    fact_id = result["facts"][0].record_id
    assert ("memory.observation_added", {"record_id": obs_id}) in seen
    assert ("memory.fact_added", {"record_id": fact_id}) in seen
    assert len(seen) == 2

    # Re-adding the same records (replaces) emits nothing new.
    store.add_many(result["observations"] + result["facts"])
    assert len(seen) == 2


def test_add_many_failure_emits_no_bus_events(monkeypatch) -> None:
    """A rolled-back batch must not announce inserts that never landed."""
    bus = EventBus()
    seen: list = []

    def recorder(env):
        seen.append(env)

    for topic in ("memory.observation_added", "memory.fact_added"):
        try:
            bus.register_topic(topic)
        except ValueError:
            pass
        bus.subscribe(topic, recorder)

    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"), bus=bus)
    engine = WritebackEngine(store)
    original = PersistentMemoryStore._insert_on_conn
    calls = {"n": 0}

    def failing_insert(self, record, conn):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("mid-batch failure")
        return original(self, record, conn)

    monkeypatch.setattr(
        PersistentMemoryStore, "_insert_on_conn", failing_insert
    )
    with pytest.raises(RuntimeError):
        engine.process_turn(speaker_id="gunnar", user_input="hi", response_text="hello", facts=_FACTS[:1])
    assert seen == []
    assert store.count() == 0


def test_standalone_writers_still_write_singly() -> None:
    """write_* happy path unchanged: one record per call, via add()."""
    store, engine = _setup()
    obs = engine.write_observation(speaker_id="gunnar", title="Solo", summary="single write")
    fact = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="status", fact_value="alive"
    )
    assert store.get(obs.record_id) is not None
    assert store.get(fact.record_id) is not None
    assert _counts(store) == (1, 1)


# ---------------------------------------------------------------------------
# (c) Idempotency still dedupes replays of a committed turn
# ---------------------------------------------------------------------------

def test_idempotent_replay_after_atomic_commit_writes_nothing_new() -> None:
    store, engine = _setup()
    first = engine.process_turn(speaker_id="gunnar",
        user_input="hello", response_text="hi",
        facts=_FACTS, idempotency_key="a3-turn-1",
    )
    second = engine.process_turn(speaker_id="gunnar",
        user_input="hello", response_text="hi",
        facts=_FACTS, idempotency_key="a3-turn-1",
    )
    assert [r.record_id for r in second["observations"]] == [
        r.record_id for r in first["observations"]
    ]
    assert [r.record_id for r in second["facts"]] == [
        r.record_id for r in first["facts"]
    ]
    assert _counts(store) == (1, 2)
    assert store.count() == 3


# ---------------------------------------------------------------------------
# Bond finding pins: TurnLoop has no bond mutation path (see module docstring)
# ---------------------------------------------------------------------------

def test_turn_loop_constructor_and_turn_have_no_bond_parameters() -> None:
    init_params = set(inspect.signature(TurnLoop.__init__).parameters)
    turn_params = set(inspect.signature(TurnLoop.execute_turn).parameters)
    assert not any("bond" in name for name in init_params)
    assert not any("bond" in name for name in turn_params)


def test_turn_loop_and_writeback_hold_no_bond_references() -> None:
    # Neither module imports or names a bond store/service at all:
    # there is no bond object for a sync step to be enforced on.
    assert not hasattr(turn_loop_module, "PersistentBondStore")
    assert not hasattr(turn_loop_module, "BondGraphService")
    assert not hasattr(writeback_module, "PersistentBondStore")
    assert not hasattr(writeback_module, "BondGraphService")
    engine_attrs = set(vars(WritebackEngine.__new__(WritebackEngine)))
    assert not any("bond" in name for name in engine_attrs)
