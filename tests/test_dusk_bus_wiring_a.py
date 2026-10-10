"""Dusk forge — WIRING A (slices 11-15): wire real producers to the EventBus.

Slice 11: World(..., bus=None)           -> world.entity_created/removed,
                                             world.component_added/removed
Slice 12: TurnLoop(..., bus=None)        -> turn.started / turn.completed
Slice 13: WritebackEngine(..., bus=None) -> writeback.written / writeback.replay
Slice 14: PersistentMemoryStore(..., bus=None) -> memory.observation_added /
                                                  memory.fact_added
Slice 15: ContradictionDetector(..., bus=None) -> contradiction.detected

Wiring rule for every slice: bus=None preserves EXACT old behavior.
With a bus, topics are registered once (double registration tolerated)
and event envelopes are published with the slice's source tag.

These tests import the real EventBus from wyrdforge.runtime.events
(merged in by the bus-contract worker).  The recording subscriber is
written defensively (*args/**kwargs) so it tolerates the merged bus's
exact subscriber callback signature.
"""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from types import SimpleNamespace

from wyrdforge.ecs.components.identity import NameComponent
from wyrdforge.ecs.world import World
from wyrdforge.oracle.models import WorldContextPacket
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.runtime.events import EventBus
from wyrdforge.runtime.turn_loop import TurnLoop, TurnResult
from wyrdforge.services.contradiction_detector import ContradictionDetector
from wyrdforge.services.writeback_engine import WritebackEngine


# ---------------------------------------------------------------------------
# Recording helpers
# ---------------------------------------------------------------------------

class Recorder:
    """Collects (topic, payload, meta) from a bus subscription.

    The callback signature is deliberately tolerant: it works whether the
    bus delivers an EventEnvelope (attribute or mapping access), calls
    fn(topic, payload, meta), fn(topic, payload), or passes keywords.
    """

    def __init__(self) -> None:
        self.events: list[tuple[str, dict, dict]] = []

    def __call__(self, *args, **kwargs) -> None:
        if args and hasattr(args[0], "topic"):
            env = args[0]
            topic = env.topic
            payload = env.payload
            meta = {"source": env.source, "seq": env.seq, "turn_id": env.turn_id}
        elif args and isinstance(args[0], dict) and "topic" in args[0]:
            env = args[0]
            topic = env["topic"]
            payload = env["payload"]
            meta = {"source": env.get("source", ""), "seq": env.get("seq", 0),
                    "turn_id": env.get("turn_id")}
        else:
            topic = args[0] if len(args) > 0 else kwargs.get("topic", "")
            payload = args[1] if len(args) > 1 else kwargs.get("payload", {})
            meta = args[2] if len(args) > 2 else {
                k: v for k, v in kwargs.items() if k not in ("topic", "payload")
            }
        self.events.append((topic, payload, meta if isinstance(meta, dict) else {}))

    def topics(self) -> list[str]:
        return [t for t, _p, _m in self.events]

    def payloads(self, topic: str) -> list[dict]:
        return [p for t, p, _m in self.events if t == topic]


def _wired_bus(*topics: str) -> tuple[EventBus, Recorder]:
    bus = EventBus()
    rec = Recorder()
    for topic in topics:
        try:
            bus.register_topic(topic)
        except ValueError:
            pass
        bus.subscribe(topic, rec)
    return bus, rec


class SpyBus:
    """Duck-typed bus stand-in that records raw publish() calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, dict]] = []

    def register_topic(self, *args, **kwargs) -> None:
        pass

    def publish(self, topic, payload: dict, **kwargs) -> int:
        self.calls.append((topic, payload, kwargs))
        return 0


# ===========================================================================
# Slice 11 — World
# ===========================================================================

def test_world_bus_none_old_behavior() -> None:
    w = World("w1")
    e = w.create_entity(entity_id="e1", tags={"a", "b"})
    assert w.entity_count() == 1
    w.add_component("e1", NameComponent(entity_id="e1", name="Gunnar"))
    assert w.get_component("e1", "name").name == "Gunnar"
    w.remove_component("e1", "name")
    assert w.get_component("e1", "name") is None
    w.remove_entity("e1")
    assert w.entity_count() == 0
    assert e.entity_id == "e1"


def test_world_entity_created_event() -> None:
    bus, rec = _wired_bus("world.entity_created")
    w = World("w1", bus=bus)
    w.create_entity(entity_id="e1", tags={"b", "a"})
    payloads = rec.payloads("world.entity_created")
    assert len(payloads) == 1
    assert payloads[0] == {"entity_id": "e1", "tags": ["a", "b"]}
    # source tag on the envelope
    assert rec.events[0][2].get("source") == "ecs.world"


def test_world_entity_removed_event() -> None:
    bus, rec = _wired_bus("world.entity_removed")
    w = World("w1", bus=bus)
    w.create_entity(entity_id="e1")
    w.remove_entity("e1")
    payloads = rec.payloads("world.entity_removed")
    assert payloads == [{"entity_id": "e1"}]


def test_world_component_added_and_removed_events() -> None:
    bus, rec = _wired_bus("world.component_added", "world.component_removed")
    w = World("w1", bus=bus)
    w.create_entity(entity_id="e1")
    w.add_component("e1", NameComponent(entity_id="e1", name="Gunnar"))
    w.remove_component("e1", "name")
    assert rec.payloads("world.component_added") == [
        {"entity_id": "e1", "component_type": "name"}
    ]
    assert rec.payloads("world.component_removed") == [
        {"entity_id": "e1", "component_type": "name"}
    ]


def test_world_create_entity_with_component_emits_both() -> None:
    bus, rec = _wired_bus("world.entity_created", "world.component_added")
    w = World("w1", bus=bus)
    w.create_entity_with_component(
        entity_id="e1", tags={"x"},
        component=NameComponent(entity_id="e1", name="Runa"),
    )
    assert rec.payloads("world.entity_created") == [
        {"entity_id": "e1", "tags": ["x"]}
    ]
    assert rec.payloads("world.component_added") == [
        {"entity_id": "e1", "component_type": "name"}
    ]


def test_world_no_event_on_missing_component_removal() -> None:
    bus, rec = _wired_bus("world.component_removed")
    w = World("w1", bus=bus)
    w.create_entity(entity_id="e1")
    w.remove_component("e1", "name")  # absent -> no-op, no event
    assert rec.events == []


def test_world_two_worlds_share_bus_no_double_register() -> None:
    bus, rec = _wired_bus("world.entity_created")
    w1 = World("w1", bus=bus)
    w2 = World("w2", bus=bus)  # must not raise on re-registration
    w1.create_entity(entity_id="e1")
    w2.create_entity(entity_id="e2")
    assert len(rec.payloads("world.entity_created")) == 2


# ===========================================================================
# Slice 12 — TurnLoop
# ===========================================================================

def _stub_packet() -> WorldContextPacket:
    return WorldContextPacket(
        query_timestamp=datetime.now(timezone.utc),
        world_id="stub_world",
        focus_entities=[],
        location_context=None,
        present_entities=[],
        canonical_facts={},
        active_policies=[],
        recent_observations=[],
        open_contradiction_count=0,
        formatted_for_llm="stub context",
    )


class _StubOracle:
    def __init__(self, order=None, fail=None) -> None:
        self.order = order
        self.fail = fail

    def build_context_packet(self, **kwargs):
        if self.order is not None:
            self.order.append("oracle")
        if self.fail is not None:
            raise self.fail
        return _stub_packet()


class _StubEngine:
    def __init__(self, fail=None) -> None:
        self.fail = fail

    def process_turn(self, **kwargs):
        if self.fail is not None:
            raise self.fail
        return {
            "observations": [SimpleNamespace(record_id="obs_1")],
            "facts": [SimpleNamespace(record_id="fact_1")],
        }


class _StubDetector:
    def check_and_record(self, fact_record):
        return []


class _StubConnector:
    def chat(self, messages, **kwargs):
        return "canned reply"


def _build_loop(bus=None, **overrides) -> TurnLoop:
    return TurnLoop(
        overrides.get("oracle", _StubOracle()),
        overrides.get("engine", _StubEngine()),
        overrides.get("detector", _StubDetector()),
        overrides.get("connector", _StubConnector()),
        bus=bus,
    )


def test_turn_loop_bus_none_old_behavior() -> None:
    loop = _build_loop()
    result = loop.execute_turn("hello")
    assert isinstance(result, TurnResult)
    assert result.assistant_response == "canned reply"
    assert result.written_record_ids == {"observations": ["obs_1"], "facts": ["fact_1"]}
    assert result.stage_errors == []
    assert loop.history_turn_count() == 1


def test_turn_started_fires_before_oracle() -> None:
    # Prove ordering with an oracle stub that records when it runs relative
    # to the turn.started delivery.
    order: list[str] = []
    started_seen: list[bool] = []

    class _OrderOracle(_StubOracle):
        def build_context_packet(self, **kwargs):
            order.append("oracle")
            return _stub_packet()

    class _OrderRec(Recorder):
        def __call__(self, *args, **kwargs):
            super().__call__(*args, **kwargs)
            first = args[0] if args else None
            topic = (
                first.topic if hasattr(first, "topic")
                else first.get("topic") if isinstance(first, dict)
                else kwargs.get("topic")
            )
            if topic == "turn.started":
                started_seen.append("oracle" in order)

    bus = EventBus()
    bus.register_topic("turn.started")
    bus.register_topic("turn.completed")
    orec = _OrderRec()
    bus.subscribe("turn.started", orec)
    rec = Recorder()
    bus.subscribe("turn.started", rec)
    bus.subscribe("turn.completed", rec)
    loop = TurnLoop(
        _OrderOracle(order=order), _StubEngine(), _StubDetector(),
        _StubConnector(), bus=bus,
    )
    result = loop.execute_turn("hi")
    assert order == ["oracle"]
    assert started_seen == [False]  # started fired BEFORE oracle ran
    # payload shape
    started = rec.payloads("turn.started")
    assert len(started) == 1
    assert started[0]["turn_id"] == result.turn_id
    assert started[0]["run_id"] == loop.run_id
    assert started[0]["input_len"] == len("hi")


def test_turn_completed_payload_healthy_turn() -> None:
    bus, rec = _wired_bus("turn.started", "turn.completed")
    loop = _build_loop(bus=bus)
    result = loop.execute_turn("hello")
    completed = rec.payloads("turn.completed")
    assert len(completed) == 1
    p = completed[0]
    assert p["turn_id"] == result.turn_id
    assert p["run_id"] == loop.run_id
    assert p["contradictions_found"] == 0
    assert p["stage_errors"] == []
    assert p["degraded"] is False


def test_turn_completed_fires_on_degraded_turn() -> None:
    bus, rec = _wired_bus("turn.completed")
    loop = _build_loop(
        bus=bus, oracle=_StubOracle(fail=RuntimeError("memory exploded"))
    )
    result = loop.execute_turn("hello")
    completed = rec.payloads("turn.completed")
    assert len(completed) == 1
    assert completed[0]["degraded"] is True
    assert completed[0]["stage_errors"] == [
        "build_context_packet: RuntimeError: memory exploded"
    ]
    assert completed[0]["turn_id"] == result.turn_id


def test_turn_bus_errors_never_abort_turn() -> None:
    class _BoomBus(SpyBus):
        def publish(self, topic, payload, **kwargs):
            raise RuntimeError("bus is on fire")

    loop = _build_loop(bus=_BoomBus())
    result = loop.execute_turn("hello")
    assert isinstance(result, TurnResult)
    assert result.assistant_response == "canned reply"


def test_turn_completed_turn_id_passed_through() -> None:
    spy = SpyBus()
    loop = _build_loop(bus=spy)
    result = loop.execute_turn("hello")
    completed = [c for c in spy.calls if c[0] == "turn.completed"]
    assert len(completed) == 1
    assert completed[0][2].get("turn_id") == result.turn_id
    assert completed[0][2].get("source") == "runtime.turn_loop"


# ===========================================================================
# Slice 13 — WritebackEngine
# ===========================================================================

def _fresh_store(bus=None) -> PersistentMemoryStore:
    return PersistentMemoryStore(tempfile.mktemp(suffix=".db"), bus=bus)


def test_writeback_bus_none_old_behavior() -> None:
    store = _fresh_store()
    engine = WritebackEngine(store)
    result = engine.process_turn(
        user_input="hello", response_text="hi",
        facts=[{"fact_subject_id": "gunnar", "fact_key": "mood", "fact_value": "calm"}],
    )
    assert len(result["observations"]) == 1
    assert len(result["facts"]) == 1
    assert store.get(result["observations"][0].record_id) is not None


def test_writeback_written_event() -> None:
    store = _fresh_store()
    bus, rec = _wired_bus("writeback.written")
    engine = WritebackEngine(store, bus=bus)
    result = engine.process_turn(
        user_input="hello", response_text="hi",
        facts=[{"fact_subject_id": "gunnar", "fact_key": "mood", "fact_value": "calm"}],
    )
    written = rec.payloads("writeback.written")
    assert len(written) == 1
    assert written[0]["record_ids"] == {
        "observations": [result["observations"][0].record_id],
        "facts": [result["facts"][0].record_id],
    }
    assert written[0]["idempotency_key"] is None
    assert rec.events[0][2].get("source") == "services.writeback"


def test_writeback_written_event_carries_key() -> None:
    store = _fresh_store()
    bus, rec = _wired_bus("writeback.written")
    engine = WritebackEngine(store, bus=bus)
    engine.process_turn(
        user_input="hello", response_text="hi", idempotency_key="key-1"
    )
    assert rec.payloads("writeback.written")[0]["idempotency_key"] == "key-1"


def test_writeback_replay_event_instead_of_written() -> None:
    store = _fresh_store()
    bus, rec = _wired_bus("writeback.written", "writeback.replay")
    engine = WritebackEngine(store, bus=bus)
    first = engine.process_turn(
        user_input="hello", response_text="hi", idempotency_key="key-9"
    )
    second = engine.process_turn(
        user_input="hello", response_text="hi", idempotency_key="key-9"
    )
    assert [r.record_id for r in first["observations"]] == [
        r.record_id for r in second["observations"]
    ]
    assert len(rec.payloads("writeback.written")) == 1  # no duplicate written
    replays = rec.payloads("writeback.replay")
    assert replays == [{"idempotency_key": "key-9"}]


def test_writeback_replay_writes_no_new_records() -> None:
    store = _fresh_store()
    engine = WritebackEngine(store)
    before = store.list_by_record_type("observation")
    engine.process_turn(user_input="a", response_text="b", idempotency_key="k")
    after_first = store.list_by_record_type("observation")
    engine.process_turn(user_input="a", response_text="b", idempotency_key="k")
    after_replay = store.list_by_record_type("observation")
    assert len(after_first) == len(before) + 1
    assert len(after_replay) == len(after_first)


# ===========================================================================
# Slice 14 — PersistentMemoryStore write path
# ===========================================================================

def _fabricate_records(store: PersistentMemoryStore):
    """Build real observation + fact + policy records via an unwired engine."""
    fabricator = WritebackEngine(
        PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    )
    obs = fabricator.write_observation(title="t", summary="s")
    fact = fabricator.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="mood", fact_value="calm"
    )
    policy = fabricator.write_policy(title="p", rule_text="be kind")
    return obs, fact, policy


def test_memory_store_bus_none_old_behavior() -> None:
    store = _fresh_store()
    obs, fact, _policy = _fabricate_records(store)
    store.add(obs)
    fetched = store.get(obs.record_id)
    assert fetched is not None
    assert fetched.record_id == obs.record_id


def test_memory_observation_added_event() -> None:
    store = _fresh_store()
    bus, rec = _wired_bus("memory.observation_added")
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"), bus=bus)
    obs, _fact, _policy = _fabricate_records(store)
    store.add(obs)
    assert rec.payloads("memory.observation_added") == [
        {"record_id": obs.record_id}
    ]


def test_memory_fact_added_event() -> None:
    store = _fresh_store()
    bus, rec = _wired_bus("memory.fact_added")
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"), bus=bus)
    _obs, fact, _policy = _fabricate_records(store)
    store.add(fact)
    assert rec.payloads("memory.fact_added") == [{"record_id": fact.record_id}]


def test_memory_no_event_on_readd_same_record_id() -> None:
    store = _fresh_store()
    bus, rec = _wired_bus("memory.observation_added", "memory.fact_added")
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"), bus=bus)
    obs, fact, _policy = _fabricate_records(store)
    store.add(obs)
    store.add(obs)   # replace, not a real insert
    store.add(fact)
    store.add(fact)  # replace, not a real insert
    assert len(rec.payloads("memory.observation_added")) == 1
    assert len(rec.payloads("memory.fact_added")) == 1


def test_memory_no_event_on_read_or_other_types() -> None:
    store = _fresh_store()
    bus, rec = _wired_bus("memory.observation_added", "memory.fact_added")
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"), bus=bus)
    obs, _fact, policy = _fabricate_records(store)
    store.add(obs)
    store.get(obs.record_id)          # read -> nothing
    store.add(policy)                 # policy -> nothing
    assert len(rec.payloads("memory.observation_added")) == 1
    assert rec.payloads("memory.fact_added") == []


# ===========================================================================
# Slice 15 — ContradictionDetector
# ===========================================================================

def _detector_setup(bus=None):
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    engine = WritebackEngine(store)
    detector = ContradictionDetector(store, bus=bus)
    return store, engine, detector


def test_detector_bus_none_old_behavior() -> None:
    _store, engine, detector = _detector_setup()
    f1 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="location", fact_value="mead_hall"
    )
    assert detector.check_and_record(f1) == []


def test_contradiction_detected_event() -> None:
    _store, engine, detector = _detector_setup()
    bus, rec = _wired_bus("contradiction.detected")
    detector = ContradictionDetector(_store, bus=bus)
    f1 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="location",
        fact_value="mead_hall", confidence=0.8,
    )
    f2 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="location",
        fact_value="docks", confidence=0.9,
    )
    contradictions = detector.check_and_record(f2)
    assert len(contradictions) == 1
    events = rec.payloads("contradiction.detected")
    assert len(events) == 1
    assert events[0]["count"] == 1
    assert events[0]["fact_ids"] == [f2.record_id, f1.record_id]
    assert rec.events[0][2].get("source") == "services.contradiction_detector"


def test_contradiction_no_event_zero_findings() -> None:
    _store, engine, detector = _detector_setup()
    bus, rec = _wired_bus("contradiction.detected")
    detector = ContradictionDetector(_store, bus=bus)
    f1 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="faction", fact_value="thornholt"
    )
    f2 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="faction", fact_value="thornholt"
    )
    assert detector.check_and_record(f2) == []
    assert rec.events == []


def test_contradiction_multiple_conflicts_count() -> None:
    _store, engine, detector = _detector_setup()
    bus, rec = _wired_bus("contradiction.detected")
    detector = ContradictionDetector(_store, bus=bus)
    f1 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="location",
        fact_value="mead_hall", confidence=0.5,
    )
    f2 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="location",
        fact_value="docks", confidence=0.6,
    )
    f3 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="location",
        fact_value="forge", confidence=0.9,
    )
    contradictions = detector.check_and_record(f3)
    events = rec.payloads("contradiction.detected")
    assert len(events) == 1
    assert events[0]["count"] == len(contradictions) == 2
    assert f3.record_id in events[0]["fact_ids"]
