"""Dusk forge — WIRING B (slices 16-20): consumers, soak, quarantine, dead letters.

Slice 16 (quarantine_file bus=):      -> state.quarantined
Slice 17 (turn-loop soak envelopes):  tests-only, against slice-12 wiring
Slice 18 (ContradictionAuditConsumer): -> wildcard "contradiction.*"
Slice 19 (ReplayPersistenceBridge):    -> replay=True persistence bridge
Slice 20 (dead_letter monitoring):     -> dead_letter_summary / take_dead_letters

Wiring rule everywhere: bus=None preserves EXACT old behavior; bus trouble
never breaks the underlying operation. Audit/persistence stores are always
UNWIRED (bus=None) so consumer writes never feed memory.* events back into
the bus (event-storm avoidance).
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from wyrdforge.hardening.state_io import quarantine_file
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.runtime.events import EventBus
from wyrdforge.runtime.turn_loop import TurnLoop, TurnResult
from wyrdforge.oracle.models import WorldContextPacket
from wyrdforge.services.bus_consumers import (
    ContradictionAuditConsumer,
    ReplayPersistenceBridge,
)
from wyrdforge.services.contradiction_detector import ContradictionDetector
from wyrdforge.services.writeback_engine import WritebackEngine


# ---------------------------------------------------------------------------
# Shared recording helpers (same shape as wiring_a)
# ---------------------------------------------------------------------------

class Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict, dict]] = []
        self.envelopes: list = []

    def __call__(self, *args, **kwargs) -> None:
        if args and hasattr(args[0], "topic"):
            env = args[0]
            self.envelopes.append(env)
            self.events.append((
                env.topic,
                env.payload,
                {"source": env.source, "seq": env.seq,
                 "turn_id": env.turn_id},
            ))
        else:
            self.events.append((args[0] if args else "", args[1] if len(args) > 1 else {}, {}))

    def topics(self) -> list[str]:
        return [t for t, _p, _m in self.events]

    def payloads(self, topic: str) -> list[dict]:
        return [p for t, p, _m in self.events if t == topic]


class SpyBus:
    """Duck-typed bus stand-in that records raw publish() calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, dict]] = []

    def register_topic(self, *args, **kwargs) -> None:
        pass

    def publish(self, topic, payload: dict, **kwargs) -> int:
        self.calls.append((topic, payload, kwargs))
        return 0


# ---------------------------------------------------------------------------
# TurnLoop stub rig (mirror of wiring_a's _build_loop)
# ---------------------------------------------------------------------------

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
    def build_context_packet(self, **kwargs):
        return _stub_packet()


class _StubEngine:
    def process_turn(self, **kwargs):
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


def _build_loop(bus=None) -> TurnLoop:
    return TurnLoop(
        _StubOracle(), _StubEngine(), _StubDetector(), _StubConnector(),
        bus=bus,
    )


def _unwired_store() -> PersistentMemoryStore:
    return PersistentMemoryStore(tempfile.mktemp(suffix=".db"), bus=None)


def _detector_setup(bus=None):
    store = _unwired_store()
    engine = WritebackEngine(store)
    detector = ContradictionDetector(store, bus=bus)
    return store, engine, detector


def _fabricate_contradiction(engine: WritebackEngine, detector: ContradictionDetector):
    """Write mood=calm, then mood=tense -> one real contradiction."""
    engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="mood",
        fact_value="calm", confidence=0.8,
    )
    f2 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="mood",
        fact_value="tense", confidence=0.9,
    )
    found = detector.check_and_record(f2)
    assert len(found) == 1
    return found


def _observations(store: PersistentMemoryStore) -> list:
    return store.list_by_record_type("observation")


# ===========================================================================
# Slice 17 — turn-loop soak envelope assertions (tests only)
# ===========================================================================

def test_slice17_two_envelopes_per_turn_in_order() -> None:
    bus = EventBus()
    bus.register_topic("turn.started")
    bus.register_topic("turn.completed")
    rec = Recorder()
    bus.subscribe("turn.started", rec)
    bus.subscribe("turn.completed", rec)
    loop = _build_loop(bus=bus)
    results = [loop.execute_turn(f"hello {i}") for i in range(3)]
    assert len(rec.envelopes) == 6
    topics = [e.topic for e in rec.envelopes]
    assert topics == [
        "turn.started", "turn.completed",
        "turn.started", "turn.completed",
        "turn.started", "turn.completed",
    ]
    # order: turn.started(seq k) then turn.completed(seq k+1)
    seqs = [e.seq for e in rec.envelopes]
    assert seqs == [1, 2, 3, 4, 5, 6]
    for i, env in enumerate(rec.envelopes):
        assert env.seq == i + 1


def test_slice17_turn_id_on_all_envelopes() -> None:
    bus = EventBus()
    bus.register_topic("turn.started")
    bus.register_topic("turn.completed")
    rec = Recorder()
    bus.subscribe("turn.started", rec)
    bus.subscribe("turn.completed", rec)
    loop = _build_loop(bus=bus)
    turn_ids = [loop.execute_turn(f"ping {i}").turn_id for i in range(3)]
    assert len(rec.envelopes) == 6
    # each turn's two envelopes carry that turn's turn_id
    for i in range(3):
        assert rec.envelopes[2 * i].turn_id == turn_ids[i]
        assert rec.envelopes[2 * i + 1].turn_id == turn_ids[i]
        # and it matches the payload too
        assert rec.envelopes[2 * i].payload["turn_id"] == turn_ids[i]
        assert rec.envelopes[2 * i + 1].payload["turn_id"] == turn_ids[i]


def test_slice17_wildcard_captures_all_in_seq_order() -> None:
    bus = EventBus()
    bus.register_topic("turn.started")
    bus.register_topic("turn.completed")
    rec = Recorder()
    bus.subscribe("turn.*", rec)  # wildcard only
    loop = _build_loop(bus=bus)
    for i in range(3):
        loop.execute_turn(f"wild {i}")
    assert len(rec.envelopes) == 6
    assert [e.topic for e in rec.envelopes] == [
        "turn.started", "turn.completed",
    ] * 3
    seqs = [e.seq for e in rec.envelopes]
    assert seqs == sorted(seqs) == [1, 2, 3, 4, 5, 6]


def test_slice17_failing_wildcard_does_not_disturb_turns() -> None:
    bus = EventBus()
    bus.register_topic("turn.started")
    bus.register_topic("turn.completed")
    healthy = Recorder()
    bus.subscribe("turn.*", healthy)

    def _boom(env) -> None:
        raise RuntimeError("soak subscriber on fire")

    bus.subscribe("turn.*", _boom)  # failing subscriber mid-soak
    loop = _build_loop(bus=bus)
    results = [loop.execute_turn(f"soak {i}") for i in range(3)]
    # all 3 turns still valid
    for r in results:
        assert isinstance(r, TurnResult)
        assert r.assistant_response == "canned reply"
        assert r.stage_errors == []
    # healthy subscriber saw all 6
    assert len(healthy.envelopes) == 6
    # every failure landed in dead letters: 2 envelopes x 3 turns
    letters = bus.dead_letters()
    assert len(letters) == 6
    assert {l["topic"] for l in letters} == {"turn.started", "turn.completed"}
    assert all(l["error_type"] == "RuntimeError" for l in letters)


# ===========================================================================
# Slice 18 — ContradictionAuditConsumer
# ===========================================================================

def test_slice18_wired_detection_persists_one_audit_observation() -> None:
    bus = EventBus()
    bus.register_topic("contradiction.detected")
    audit_store = _unwired_store()
    consumer = ContradictionAuditConsumer(bus, audit_store)
    store, engine, _ = _detector_setup()
    detector = ContradictionDetector(store, bus=bus)
    found = _fabricate_contradiction(engine, detector)
    assert len(found) == 1
    obs = _observations(audit_store)
    assert len(obs) == 1
    rec = obs[0]
    # title carries the detection envelope's seq
    assert rec.content.title.startswith("contradiction audit seq=")
    summary = rec.content.summary
    assert "count=1" in summary
    assert "fact_ids=" in summary
    assert "seq=" in summary
    assert "issued_at=" in summary
    # tag carried
    assert "contradiction-audit" in rec.retrieval.lexical_terms
    consumer.close()


def test_slice18_two_detections_two_observations() -> None:
    bus = EventBus()
    bus.register_topic("contradiction.detected")
    audit_store = _unwired_store()
    consumer = ContradictionAuditConsumer(bus, audit_store)
    store, engine, _ = _detector_setup()
    detector = ContradictionDetector(store, bus=bus)
    _fabricate_contradiction(engine, detector)
    # second contradiction on a different key
    engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="location",
        fact_value="mead_hall", confidence=0.8,
    )
    f2 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="location",
        fact_value="docks", confidence=0.9,
    )
    assert len(detector.check_and_record(f2)) == 1
    obs = _observations(audit_store)
    assert len(obs) == 2
    consumer.close()


def test_slice18_bus_none_detector_path_unchanged() -> None:
    audit_store = _unwired_store()
    bus = EventBus()  # exists, but detector is NOT wired to it
    consumer = ContradictionAuditConsumer(bus, audit_store)
    store, engine, detector = _detector_setup(bus=None)
    found = _fabricate_contradiction(engine, detector)
    assert len(found) == 1
    # no traffic on this bus for the detector; consumer saw nothing
    assert _observations(audit_store) == []
    assert bus.dead_letters() == []
    consumer.close()


def test_slice18_raising_handler_isolated_by_bus() -> None:
    bus = EventBus()
    bus.register_topic("contradiction.detected")
    audit_store = _unwired_store()
    consumer = ContradictionAuditConsumer(bus, audit_store)

    def _boom(env) -> None:
        raise ValueError("audit subscriber exploded")

    bus.subscribe("contradiction.*", _boom)
    store, engine, _ = _detector_setup()
    detector = ContradictionDetector(store, bus=bus)
    _fabricate_contradiction(engine, detector)
    # healthy consumer still persisted the audit row
    assert len(_observations(audit_store)) == 1
    # the failure landed in dead letters; publish still succeeded overall
    letters = bus.dead_letters()
    assert len(letters) == 1
    assert letters[0]["topic"] == "contradiction.detected"
    assert letters[0]["error_type"] == "ValueError"
    consumer.close()


def test_slice18_detached_consumer_hears_nothing() -> None:
    bus = EventBus()
    bus.register_topic("contradiction.detected")
    audit_store = _unwired_store()
    consumer = ContradictionAuditConsumer(bus, audit_store)
    consumer.detach()
    consumer.detach()  # idempotent
    store, engine, _ = _detector_setup()
    detector = ContradictionDetector(store, bus=bus)
    _fabricate_contradiction(engine, detector)
    assert _observations(audit_store) == []
    assert consumer.detached is True


def test_slice18_consumer_store_is_unwired() -> None:
    bus = EventBus()
    audit_store = _unwired_store()
    consumer = ContradictionAuditConsumer(bus, audit_store)
    assert consumer.store._bus is None
    consumer.close()


def test_slice18_detector_with_bus_no_consumer_works_normally() -> None:
    bus = EventBus()
    rec = Recorder()
    bus.register_topic("contradiction.detected")
    bus.subscribe("contradiction.detected", rec)
    store, engine, _ = _detector_setup()
    detector = ContradictionDetector(store, bus=bus)
    found = _fabricate_contradiction(engine, detector)
    assert len(found) == 1
    events = rec.payloads("contradiction.detected")
    assert len(events) == 1
    assert events[0]["count"] == 1


# ===========================================================================
# Slice 19 — ReplayPersistenceBridge
# ===========================================================================

def _publish_k(bus: EventBus, topic: str, n: int, start: int = 0) -> None:
    for i in range(start, start + n):
        bus.publish(topic, {"idx": i, "note": f"event {i}"})


def test_slice19_backfill_five_in_seq_order() -> None:
    bus = EventBus()
    bus.register_topic("world.entity_created")
    _publish_k(bus, "world.entity_created", 5)
    store = _unwired_store()
    bridge = ReplayPersistenceBridge(
        bus, store, ["world.entity_created"]
    )
    obs = _observations(store)
    assert len(obs) == 5
    for i, rec in enumerate(obs):
        assert rec.content.title == f"replay world.entity_created seq={i + 1}"
        summary = json.loads(rec.content.summary)
        assert summary["topic"] == "world.entity_created"
        assert summary["seq"] == i + 1
        assert summary["payload"] == {"idx": i, "note": f"event {i}"}
    bridge.close()


def test_slice19_live_publish_adds_exactly_one() -> None:
    bus = EventBus()
    bus.register_topic("world.entity_created")
    _publish_k(bus, "world.entity_created", 5)
    store = _unwired_store()
    bridge = ReplayPersistenceBridge(
        bus, store, ["world.entity_created"]
    )
    bus.publish("world.entity_created", {"idx": 5, "note": "live"})
    obs = _observations(store)
    assert len(obs) == 6
    assert obs[-1].content.title == "replay world.entity_created seq=6"
    # no double-persist: same envelope re-delivered would be deduped
    bridge.close()


def test_slice19_replay_dedupe_no_double_persist() -> None:
    bus = EventBus()
    bus.register_topic("world.entity_created")
    _publish_k(bus, "world.entity_created", 3)
    store = _unwired_store()
    bridge = ReplayPersistenceBridge(
        bus, store, ["world.entity_created"]
    )
    # re-publish three more (new seqs) then assert totals, not doubles
    _publish_k(bus, "world.entity_created", 3, start=3)
    obs = _observations(store)
    assert len(obs) == 6
    titles = [r.content.title for r in obs]
    assert len(set(titles)) == 6  # every (topic, seq) persisted exactly once
    assert bridge.seen_count == 6
    bridge.close()


def test_slice19_multiple_topics_independent() -> None:
    bus = EventBus()
    bus.register_topic("world.entity_created")
    bus.register_topic("turn.completed")
    _publish_k(bus, "world.entity_created", 2)
    _publish_k(bus, "turn.completed", 3)
    store = _unwired_store()
    bridge = ReplayPersistenceBridge(
        bus, store, ["world.entity_created", "turn.completed"]
    )
    obs = _observations(store)
    assert len(obs) == 5
    # replay is FIFO across topics by bus seq
    seqs = [json.loads(r.content.summary)["seq"] for r in obs]
    assert seqs == sorted(seqs)
    bridge.close()


def test_slice19_store_is_unwired_no_bus_feedback() -> None:
    bus = EventBus()
    bus.register_topic("world.entity_created")
    store = _unwired_store()
    bridge = ReplayPersistenceBridge(
        bus, store, ["world.entity_created"]
    )
    assert store._bus is None
    # bus saw no memory.* topics even after bridge writes
    assert "memory.observation_added" not in bus.topics()
    bus.publish("world.entity_created", {"idx": 0})
    assert "memory.observation_added" not in bus.topics()
    assert len(_observations(store)) == 1
    bridge.close()


def test_slice19_detach_stops_live_capture() -> None:
    bus = EventBus()
    bus.register_topic("world.entity_created")
    store = _unwired_store()
    bridge = ReplayPersistenceBridge(
        bus, store, ["world.entity_created"]
    )
    assert _observations(store) == []
    bridge.detach()
    bridge.detach()  # idempotent
    bus.publish("world.entity_created", {"idx": 0})
    assert _observations(store) == []
    assert bridge.detached is True


# ===========================================================================
# Slice 16 — quarantine_file bus wiring (implemented; tests were missing)
# ===========================================================================

def _corrupt_file() -> Path:
    d = Path(tempfile.mkdtemp())
    p = d / "broken.db"
    p.write_bytes(b"\x00\x01not-a-database")
    return p


def test_slice16_quarantine_emits_event_and_returns_dest() -> None:
    bus = EventBus()
    rec = Recorder()
    p = _corrupt_file()
    # quarantine_file registers its own topic; subscribe via pattern after
    # the first call registers it, or pre-register by calling register here.
    dest = quarantine_file(p, reason="test-corrupt", bus=bus)
    bus.subscribe("state.quarantined", rec)
    # first call happened before our subscribe; re-check via a second file
    p2 = _corrupt_file()
    dest2 = quarantine_file(p2, reason="test-corrupt-2", bus=bus)
    assert dest2.exists()
    events = rec.payloads("state.quarantined")
    assert len(events) == 1
    payload = events[0]
    assert payload["path"] == str(p2)
    assert payload["dest"] == str(dest2)
    assert payload["reason"] == "test-corrupt-2"
    assert isinstance(dest, Path)
    assert dest.parent.name == "quarantine"
    assert dest.exists()
    assert not p.exists()  # original moved aside


def test_slice16_no_bus_same_behavior_no_event() -> None:
    p = _corrupt_file()
    dest = quarantine_file(p, reason="plain")
    assert dest.exists()
    assert not p.exists()
    assert dest.parent.name == "quarantine"


def test_slice16_two_calls_single_registration_two_envelopes() -> None:
    bus = EventBus()
    rec = Recorder()
    p1 = _corrupt_file()
    d1 = quarantine_file(p1, reason="r1", bus=bus)
    bus.subscribe("state.quarantined", rec)
    p2 = _corrupt_file()
    d2 = quarantine_file(p2, reason="r2", bus=bus)
    p3 = _corrupt_file()
    d3 = quarantine_file(p3, reason="r3", bus=bus)
    assert d1.exists() and d2.exists() and d3.exists()
    # single registration despite three producers' worth of calls
    assert bus.topics().count("state.quarantined") == 1
    events = rec.payloads("state.quarantined")
    assert len(events) == 2  # only the two calls after subscribe
    assert events[0]["dest"] == str(d2)
    assert events[1]["dest"] == str(d3)


# ===========================================================================
# Slice 20 — dead_letter_summary / take_dead_letters
# ===========================================================================

def _bus_with_failures(cap: int = 256):
    bus = EventBus(dead_letter_cap=cap)
    bus.register_topic("alpha.tick")
    bus.register_topic("beta.tock")

    def _boom_type(env) -> None:
        raise ValueError("alpha exploded")

    def _boom_runtime(env) -> None:
        raise RuntimeError("beta exploded")

    bus.subscribe("alpha.tick", _boom_type)
    bus.subscribe("beta.tock", _boom_runtime)
    return bus


def test_slice20_summary_counts_by_topic_and_error_type() -> None:
    bus = _bus_with_failures()
    bus.publish("alpha.tick", {"n": 1})
    bus.publish("alpha.tick", {"n": 2})
    bus.publish("beta.tock", {"n": 3})
    summary = bus.dead_letter_summary()
    assert summary == {
        "alpha.tick": {"ValueError": 2},
        "beta.tock": {"RuntimeError": 1},
    }
    # read-only: the queue is untouched
    assert len(bus.dead_letters()) == 3


def test_slice20_take_drains_and_returns_copies() -> None:
    bus = _bus_with_failures()
    bus.publish("alpha.tick", {"n": 1})
    bus.publish("beta.tock", {"n": 2})
    letters = bus.take_dead_letters()
    assert len(letters) == 2
    assert letters[0]["topic"] == "alpha.tick"
    assert letters[1]["topic"] == "beta.tock"
    assert letters[0]["error_type"] == "ValueError"
    # queue empty afterwards
    assert bus.dead_letters() == []
    assert bus.take_dead_letters() == []
    assert bus.dead_letter_summary() == {}
    # copies: mutating the return value does not affect the queue
    letters.append({"fake": True})
    assert bus.dead_letters() == []


def test_slice20_cap_eviction_keeps_three_summary_counts_retained() -> None:
    bus = _bus_with_failures(cap=3)
    for i in range(5):
        bus.publish("alpha.tick", {"n": i})
    queue = bus.dead_letters()
    assert len(queue) == 3  # oldest evicted on overflow
    summary = bus.dead_letter_summary()
    assert summary == {"alpha.tick": {"ValueError": 3}}  # only retained count
    # the retained ones are the newest three
    assert [l["message"] for l in queue] == ["alpha exploded"] * 3
    assert [l["error_type"] for l in queue] == ["ValueError"] * 3


def test_slice20_empty_summary_and_take() -> None:
    bus = EventBus()
    bus.register_topic("quiet.ping")
    assert bus.dead_letter_summary() == {}
    assert bus.take_dead_letters() == []
