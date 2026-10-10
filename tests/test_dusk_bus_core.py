"""BUS CORE — slices 1–5 acceptance tests.

Slice 1: EventEnvelope + topic registry.
Slice 2: subscribe / unsubscribe / publish.
Slice 3: Payload-type enforcement.
Slice 4: Subscriber error isolation + _take_failures().
Slice 5: Thread safety + FIFO seq ordering.
"""

from __future__ import annotations

import dataclasses
import logging
import threading
from datetime import datetime

import pytest
from pydantic import BaseModel

from wyrdforge.runtime.events import EventBus, EventEnvelope


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def turn_bus(bus: EventBus) -> EventBus:
    bus.register_topic("wyrd.turn.started")
    return bus


class TurnPayload(BaseModel):
    turn: int
    scene: str


@dataclasses.dataclass
class SealPayload:
    seal: str
    power: int = 0


# ---------------------------------------------------------------------------
# Slice 1 — EventEnvelope + topic registry
# ---------------------------------------------------------------------------


class TestEventEnvelope:
    def test_defaults(self):
        env = EventEnvelope(topic="a.b", payload={"k": 1})
        assert env.topic == "a.b"
        assert env.payload == {"k": 1}
        assert env.source == ""
        assert env.seq == 0
        assert env.issued_at == ""
        assert env.turn_id is None

    def test_all_fields_set(self):
        env = EventEnvelope(
            topic="wyrd.turn.started",
            payload={"turn": 3},
            source="seidr",
            seq=42,
            issued_at="2026-10-10T12:00:00+00:00",
            turn_id="t-1",
        )
        assert env.seq == 42
        assert env.turn_id == "t-1"

    def test_forbids_extra_fields(self):
        with pytest.raises(Exception):
            EventEnvelope(topic="a.b", payload={}, bogus="x")  # type: ignore[call-arg]

    def test_payload_must_be_dict(self):
        with pytest.raises(Exception):
            EventEnvelope(topic="a.b", payload=[1, 2])  # type: ignore[arg-type]

    def test_model_dump_round_trip(self):
        env = EventEnvelope(
            topic="a.b", payload={"x": [1, 2]}, source="s", seq=7,
            issued_at="2026-10-10T00:00:00+00:00", turn_id="t",
        )
        data = env.to_dict()
        assert data["topic"] == "a.b"
        assert data["payload"] == {"x": [1, 2]}
        assert data["seq"] == 7
        assert EventEnvelope(**data) == env

    def test_register_topic_lists_it(self, bus):
        bus.register_topic("wyrd.turn.started")
        assert "wyrd.turn.started" in bus.topics()

    def test_duplicate_registration_is_idempotent(self, bus):
        # Dusk merge decision: re-registering is a no-op (first registration
        # wins) so multiple opt-in producers can share one bus safely.
        bus.register_topic("wyrd.turn.started")
        bus.register_topic("wyrd.turn.started")  # no error
        assert bus.topics().count("wyrd.turn.started") == 1

    def test_invalid_topic_name_raises_value_error(self, bus):
        with pytest.raises(ValueError):
            bus.register_topic("notdotted")

    def test_invalid_schema_raises_type_error(self, bus):
        with pytest.raises(TypeError):
            bus.register_topic("wyrd.turn.started", payload_schema=int)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            bus.register_topic("wyrd.turn.started", payload_schema="TurnPayload")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Slice 2 — subscribe / unsubscribe / publish
# ---------------------------------------------------------------------------


class TestSubscribePublish:
    def test_subscribe_returns_token(self, turn_bus):
        token = turn_bus.subscribe("wyrd.turn.started", lambda e: None)
        assert isinstance(token, str) and token

    def test_publish_delivers_envelope(self, turn_bus):
        seen = []
        turn_bus.subscribe("wyrd.turn.started", seen.append)
        n = turn_bus.publish("wyrd.turn.started", {"turn": 1}, source="hugin")
        assert n == 1
        (env,) = seen
        assert isinstance(env, EventEnvelope)
        assert env.topic == "wyrd.turn.started"
        assert env.payload == {"turn": 1}
        assert env.source == "hugin"
        assert env.seq == 1
        assert env.turn_id is None

    def test_publish_subscription_order(self, turn_bus):
        order = []
        turn_bus.subscribe("wyrd.turn.started", lambda e: order.append("first"))
        turn_bus.subscribe("wyrd.turn.started", lambda e: order.append("second"))
        turn_bus.publish("wyrd.turn.started", {})
        assert order == ["first", "second"]

    def test_publish_returns_delivered_count(self, turn_bus):
        turn_bus.subscribe("wyrd.turn.started", lambda e: None)
        turn_bus.subscribe("wyrd.turn.started", lambda e: None)
        assert turn_bus.publish("wyrd.turn.started", {}) == 2

    def test_publish_no_subscribers_is_noop_returning_zero(self, turn_bus):
        assert turn_bus.publish("wyrd.turn.started", {"turn": 9}) == 0

    def test_publish_unknown_topic_raises_key_error(self, bus):
        with pytest.raises(KeyError):
            bus.publish("wyrd.missing.topic", {})

    def test_subscribe_unknown_topic_raises_key_error(self, bus):
        with pytest.raises(KeyError):
            bus.subscribe("wyrd.missing.topic", lambda e: None)

    def test_unsubscribe_stops_delivery(self, turn_bus):
        seen = []
        token = turn_bus.subscribe("wyrd.turn.started", seen.append)
        turn_bus.unsubscribe(token)
        assert turn_bus.publish("wyrd.turn.started", {}) == 0
        assert seen == []

    def test_unsubscribe_unknown_token_raises_key_error(self, turn_bus):
        with pytest.raises(KeyError):
            turn_bus.unsubscribe("nope")

    def test_turn_id_and_source_carried(self, turn_bus):
        seen = []
        turn_bus.subscribe("wyrd.turn.started", seen.append)
        turn_bus.publish("wyrd.turn.started", {}, source="mimir", turn_id="turn-42")
        assert seen[0].turn_id == "turn-42"
        assert seen[0].source == "mimir"

    def test_seq_is_bus_scoped_across_topics(self, bus):
        bus.register_topic("wyrd.turn.started")
        bus.register_topic("wyrd.turn.ended")
        bus.publish("wyrd.turn.started", {})
        bus.publish("wyrd.turn.ended", {})
        bus.publish("wyrd.turn.started", {})
        seqs = []
        bus.subscribe("wyrd.turn.started", lambda e: seqs.append(e.seq))
        bus.publish("wyrd.turn.started", {})
        assert seqs == [4]

    def test_issued_at_is_iso8601(self, turn_bus):
        seen = []
        turn_bus.subscribe("wyrd.turn.started", seen.append)
        turn_bus.publish("wyrd.turn.started", {})
        datetime.fromisoformat(seen[0].issued_at)  # must parse


# ---------------------------------------------------------------------------
# Slice 3 — payload-type enforcement
# ---------------------------------------------------------------------------


class TestPayloadSchemas:
    def test_pydantic_schema_valid_payload(self, bus):
        bus.register_topic("wyrd.turn.started", payload_schema=TurnPayload)
        seen = []
        bus.subscribe("wyrd.turn.started", seen.append)
        assert bus.publish("wyrd.turn.started", {"turn": 2, "scene": "hall"}) == 1
        assert seen[0].payload == {"turn": 2, "scene": "hall"}

    def test_pydantic_schema_invalid_payload_names_topic(self, bus):
        bus.register_topic("wyrd.turn.started", payload_schema=TurnPayload)
        with pytest.raises(TypeError) as excinfo:
            bus.publish("wyrd.turn.started", {"turn": "not-an-int", "scene": "hall"})
        assert "wyrd.turn.started" in str(excinfo.value)

    def test_pydantic_schema_missing_field(self, bus):
        bus.register_topic("wyrd.turn.started", payload_schema=TurnPayload)
        with pytest.raises(TypeError):
            bus.publish("wyrd.turn.started", {"turn": 1})

    def test_dataclass_schema_valid_and_invalid(self, bus):
        bus.register_topic("seidr.seal.cast", payload_schema=SealPayload)
        seen = []
        bus.subscribe("seidr.seal.cast", seen.append)
        assert bus.publish("seidr.seal.cast", {"seal": "algiz"}) == 1
        with pytest.raises(TypeError) as excinfo:
            bus.publish("seidr.seal.cast", {})
        assert "seidr.seal.cast" in str(excinfo.value)

    def test_no_schema_accepts_any_dict(self, turn_bus):
        seen = []
        turn_bus.subscribe("wyrd.turn.started", seen.append)
        assert turn_bus.publish("wyrd.turn.started", {"anything": [1, {"goes": True}]}) == 1

    def test_non_dict_payload_raises_type_error(self, bus):
        bus.register_topic("wyrd.turn.started", payload_schema=TurnPayload)
        with pytest.raises(TypeError):
            bus.publish("wyrd.turn.started", [1, 2, 3])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Slice 4 — subscriber error isolation
# ---------------------------------------------------------------------------


class TestErrorIsolation:
    def test_raising_subscriber_does_not_break_publish(self, turn_bus, caplog):
        def boom(env):
            raise RuntimeError("seal backfired")

        good = []
        turn_bus.subscribe("wyrd.turn.started", boom)
        turn_bus.subscribe("wyrd.turn.started", good.append)
        with caplog.at_level(logging.ERROR, logger="wyrdforge.runtime.events"):
            n = turn_bus.publish("wyrd.turn.started", {})
        assert n == 1  # only the survivor counts as delivered
        assert len(good) == 1  # survivor still received
        assert any("boom" in rec.message or "seal backfired" in rec.getMessage()
                   for rec in caplog.records)

    def test_failure_recorded_in_take_failures(self, turn_bus):
        def boom(env):
            raise RuntimeError("seal backfired")

        turn_bus.subscribe("wyrd.turn.started", boom)
        turn_bus.publish("wyrd.turn.started", {}, turn_id="t-9")
        failures = turn_bus._take_failures()
        assert len(failures) == 1
        (f,) = failures
        assert f["seq"] == 1
        assert f["topic"] == "wyrd.turn.started"
        assert f["subscriber"] == "boom"
        assert f["error_type"] == "RuntimeError"
        assert f["message"] == "seal backfired"
        datetime.fromisoformat(f["timestamp"])

    def test_take_failures_clears_list(self, turn_bus):
        turn_bus.subscribe("wyrd.turn.started", lambda e: 1 / 0)
        turn_bus.publish("wyrd.turn.started", {})
        assert len(turn_bus._take_failures()) == 1
        assert turn_bus._take_failures() == []

    def test_anonymous_subscriber_gets_name(self, turn_bus):
        turn_bus.subscribe("wyrd.turn.started", lambda e: (_ for _ in ()).throw(ValueError("x")))
        turn_bus.publish("wyrd.turn.started", {})
        (f,) = turn_bus._take_failures()
        assert f["error_type"] == "ValueError"

    def test_multiple_failures_accumulate_in_order(self, turn_bus):
        def bad1(env):
            raise KeyError("one")

        def bad2(env):
            raise IndexError("two")

        turn_bus.subscribe("wyrd.turn.started", bad1)
        turn_bus.subscribe("wyrd.turn.started", bad2)
        turn_bus.publish("wyrd.turn.started", {})
        failures = turn_bus._take_failures()
        assert [f["error_type"] for f in failures] == ["KeyError", "IndexError"]


# ---------------------------------------------------------------------------
# Slice 5 — thread safety + FIFO
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_publish_fifo_per_subscriber(self):
        bus = EventBus()
        bus.register_topic("wyrd.turn.started")
        got_a, got_b = [], []
        lock_a, lock_b = threading.Lock(), threading.Lock()

        def sub_a(env):
            with lock_a:
                got_a.append(env.seq)

        def sub_b(env):
            with lock_b:
                got_b.append(env.seq)

        bus.subscribe("wyrd.turn.started", sub_a)
        bus.subscribe("wyrd.turn.started", sub_b)

        threads = [
            threading.Thread(
                target=lambda: [bus.publish("wyrd.turn.started", {"i": i}) for i in range(200)]
            )
            for _ in range(8)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(got_a) == 1600
        assert len(got_b) == 1600
        assert got_a == sorted(got_a), "subscriber A did not see FIFO seq order"
        assert got_b == sorted(got_b), "subscriber B did not see FIFO seq order"
        assert len(set(got_a)) == 1600, "duplicate seq values observed"
        assert got_a == list(range(1, 1601))

    def test_concurrent_subscribe_unsubscribe_no_crash(self, turn_bus):
        errors = []

        def churn():
            try:
                for _ in range(50):
                    tok = turn_bus.subscribe("wyrd.turn.started", lambda e: None)
                    turn_bus.unsubscribe(tok)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=churn) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []

    def test_publish_inside_subscriber_is_reentrant(self, turn_bus):
        bus = turn_bus
        bus.register_topic("wyrd.turn.ended")
        seen = []

        def first(env):
            seen.append(env.topic)
            bus.publish("wyrd.turn.ended", {})

        def second(env):
            seen.append(env.topic)

        bus.subscribe("wyrd.turn.started", first)
        bus.subscribe("wyrd.turn.ended", second)
        bus.publish("wyrd.turn.started", {})
        assert seen == ["wyrd.turn.started", "wyrd.turn.ended"]
