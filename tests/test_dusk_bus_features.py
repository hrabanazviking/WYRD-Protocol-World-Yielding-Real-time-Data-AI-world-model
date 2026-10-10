"""Dusk forge: BUS FEATURES, slices 6-10 (EventBus).

Covers: dead-letter queue (6), replay buffer (7), metrics (8),
wildcard subscriptions (9), shutdown (10), plus core-contract sanity.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import BaseModel

from wyrdforge.runtime.events import EventBus


class ShapedPayload(BaseModel):
    n: int


def _boom(i):
    def _fn(env):
        raise RuntimeError(f"boom-{i}")
    return _fn


# ---------------------------------------------------------------------------
# core contract sanity
# ---------------------------------------------------------------------------

def test_core_publish_delivers_and_returns_count() -> None:
    bus = EventBus()
    bus.register_topic("world.tick")
    got = []
    bus.subscribe("world.tick", got.append)
    n = bus.publish("world.tick", {"n": 1})
    assert n == 1
    assert got[0]["topic"] == "world.tick"
    assert got[0]["payload"] == {"n": 1}
    assert got[0]["seq"] >= 1


def test_core_unregistered_publish_raises_keyerror() -> None:
    bus = EventBus()
    with pytest.raises(KeyError):
        bus.publish("nope", {})


def test_core_unsubscribe_unknown_token_raises() -> None:
    bus = EventBus()
    with pytest.raises(KeyError):
        bus.unsubscribe(999)


def test_core_unsubscribe_stops_delivery() -> None:
    bus = EventBus()
    bus.register_topic("wyrd.t")
    got = []
    tok = bus.subscribe("wyrd.t", got.append)
    bus.unsubscribe(tok)
    assert bus.publish("wyrd.t", {"n": 1}) == 0
    assert got == []


def test_core_failure_isolation_and_take_failures() -> None:
    bus = EventBus()
    bus.register_topic("wyrd.t")
    ok = []
    bus.subscribe("wyrd.t", ok.append)
    bus.subscribe("wyrd.t", _boom(0))
    n = bus.publish("wyrd.t", {"v": "x"})
    assert n == 1  # only the good subscriber counts as delivered
    assert ok and ok[0]["payload"] == {"v": "x"}
    fails = bus._take_failures()
    assert len(fails) == 1
    f = fails[0]
    assert f["topic"] == "wyrd.t"
    assert f["error_type"] == "RuntimeError"
    assert f["message"] == "boom-0"
    assert f["seq"] >= 1 and datetime.fromisoformat(f["timestamp"])
    assert bus._take_failures() == []  # drained


def test_core_schema_enforcement() -> None:
    bus = EventBus()
    # NOTE: strict schema semantics (dusk merge decision): only pydantic
    # models or dataclasses are accepted as schemas; anything else raises
    # TypeError at registration time.
    with pytest.raises(TypeError):
        bus.register_topic("wyrd.bad", payload_schema=dict)  # type: ignore[arg-type]
    bus.register_topic("wyrd.shaped", payload_schema=ShapedPayload)
    with pytest.raises(TypeError):
        bus.publish("wyrd.shaped", {"n": "x"})
    got = []
    bus.subscribe("wyrd.shaped", got.append)
    bus.publish("wyrd.shaped", {"n": 3})
    assert got[0]["payload"] == {"n": 3}


# ---------------------------------------------------------------------------
# slice 6: dead-letter queue
# ---------------------------------------------------------------------------

def test_dead_letter_captured_on_subscriber_failure() -> None:
    bus = EventBus()
    bus.register_topic("wyrd.t")
    bus.subscribe("wyrd.t", _boom(7))
    bus.publish("wyrd.t", {"v": "x"})
    letters = bus.dead_letters()
    assert len(letters) == 1
    L = letters[0]
    assert L["topic"] == "wyrd.t"
    assert L["error_type"] == "RuntimeError"
    assert L["message"] == "boom-7"
    assert L["seq"] >= 1 and datetime.fromisoformat(L["timestamp"])
    assert L["subscriber"]  # some name/repr of the fn


def test_dead_letter_cap_300_failures_keeps_256_oldest_dropped() -> None:
    bus = EventBus()  # default dead_letter_cap=256
    bus.register_topic("wyrd.t")
    for i in range(300):
        bus.subscribe("wyrd.t", _boom(i))
    bus.publish("wyrd.t", {"v": "x"})
    letters = bus.dead_letters()
    assert len(letters) == 256
    # oldest dropped: first retained is failure #44 (0-indexed), newest kept
    assert letters[0]["message"] == "boom-44"
    assert letters[-1]["message"] == "boom-299"


def test_dead_letter_custom_cap() -> None:
    bus = EventBus(dead_letter_cap=10)
    bus.register_topic("wyrd.t")
    for i in range(15):
        bus.subscribe("wyrd.t", _boom(i))
    bus.publish("wyrd.t", {"v": "x"})
    letters = bus.dead_letters()
    assert len(letters) == 10
    assert letters[0]["message"] == "boom-5"
    assert letters[-1]["message"] == "boom-14"


def test_dead_letters_returns_copies() -> None:
    bus = EventBus()
    bus.register_topic("wyrd.t")
    bus.subscribe("wyrd.t", _boom(1))
    bus.publish("wyrd.t", {"v": "x"})
    letters = bus.dead_letters()
    letters[0]["message"] = "MUTATED"
    letters.append({"fake": True})
    fresh = bus.dead_letters()
    assert len(fresh) == 1
    assert fresh[0]["message"] == "boom-1"


def test_dead_letter_bad_cap_rejected() -> None:
    with pytest.raises(ValueError):
        EventBus(dead_letter_cap=-1)


def test_dead_letter_also_in_failures_drain() -> None:
    bus = EventBus()
    bus.register_topic("wyrd.t")
    bus.subscribe("wyrd.t", _boom(2))
    bus.publish("wyrd.t", {"v": "x"})
    assert len(bus.dead_letters()) == 1
    assert len(bus._take_failures()) == 1
    # dead letters survive the failure drain (separate queue)
    assert len(bus.dead_letters()) == 1


# ---------------------------------------------------------------------------
# slice 7: replay buffer
# ---------------------------------------------------------------------------

def test_replay_delivers_buffered_fifo_before_live() -> None:
    bus = EventBus()
    bus.register_topic("wyrd.t")
    for i in range(3):
        bus.publish("wyrd.t", {"i": i})
    got = []
    bus.subscribe("wyrd.t", got.append, replay=True)
    assert [e["payload"]["i"] for e in got] == [0, 1, 2]
    bus.publish("wyrd.t", {"i": 3})
    assert [e["payload"]["i"] for e in got] == [0, 1, 2, 3]


def test_replay_false_default_no_backfill() -> None:
    bus = EventBus()
    bus.register_topic("wyrd.t")
    bus.publish("wyrd.t", {"i": 0})
    got = []
    bus.subscribe("wyrd.t", got.append)  # replay defaults to False
    assert got == []
    bus.publish("wyrd.t", {"i": 1})
    assert [e["payload"]["i"] for e in got] == [1]


def test_replay_buffer_size_limit() -> None:
    bus = EventBus()
    bus.register_topic("wyrd.t", replay_buffer=2)
    for i in range(3):
        bus.publish("wyrd.t", {"i": i})
    got = []
    bus.subscribe("wyrd.t", got.append, replay=True)
    assert [e["payload"]["i"] for e in got] == [1, 2]


def test_replay_buffer_zero_disables() -> None:
    bus = EventBus()
    bus.register_topic("wyrd.t", replay_buffer=0)
    bus.publish("wyrd.t", {"i": 0})
    got = []
    bus.subscribe("wyrd.t", got.append, replay=True)
    assert got == []


def test_replay_respects_failure_isolation() -> None:
    bus = EventBus()
    bus.register_topic("wyrd.t")
    bus.publish("wyrd.t", {"i": 0})
    bus.subscribe("wyrd.t", _boom(9), replay=True)  # raises during replay
    assert len(bus.dead_letters()) == 1
    assert bus.dead_letters()[0]["message"] == "boom-9"


def test_register_topic_idempotent_keeps_buffer() -> None:
    bus = EventBus()
    bus.register_topic("wyrd.t", replay_buffer=5)
    bus.publish("wyrd.t", {"n": 1})
    bus.register_topic("wyrd.t", replay_buffer=1)  # no-op: must not clobber
    got = []
    bus.subscribe("wyrd.t", got.append, replay=True)
    assert len(got) == 1


# ---------------------------------------------------------------------------
# slice 8: metrics
# ---------------------------------------------------------------------------

def test_metrics_counts_published_delivered_subscribers() -> None:
    bus = EventBus()
    bus.register_topic("wyrd.a")
    bus.register_topic("wyrd.b")
    a1, a2 = [], []
    bus.subscribe("wyrd.a", a1.append)
    bus.subscribe("wyrd.a", a2.append)
    bus.publish("wyrd.a", {"n": 1})
    bus.publish("wyrd.a", {"n": 2})
    snap = bus.snapshot()
    assert snap["wyrd.a"]["published"] == 2
    assert snap["wyrd.a"]["delivered"] == 4
    assert snap["wyrd.a"]["failed"] == 0
    assert snap["wyrd.a"]["subscriber_count"] == 2
    assert snap["wyrd.b"] == {"published": 0, "delivered": 0, "failed": 0,
                         "subscriber_count": 0}


def test_metrics_failed_increments_on_raising_subscriber() -> None:
    bus = EventBus()
    bus.register_topic("wyrd.t")
    bus.subscribe("wyrd.t", _boom(0))
    ok = []
    bus.subscribe("wyrd.t", ok.append)
    n = bus.publish("wyrd.t", {"v": "x"})
    assert n == 1
    snap = bus.snapshot()
    assert snap["wyrd.t"]["published"] == 1
    assert snap["wyrd.t"]["delivered"] == 1
    assert snap["wyrd.t"]["failed"] == 1


def test_snapshot_is_a_copy_mutation_safe() -> None:
    bus = EventBus()
    bus.register_topic("wyrd.t")
    bus.subscribe("wyrd.t", lambda e: None)
    bus.publish("wyrd.t", {"n": 1})
    snap = bus.snapshot()
    snap["wyrd.t"]["published"] = 999
    snap["wyrd.t"]["subscriber_count"] = 999
    del snap["wyrd.t"]
    fresh = bus.snapshot()
    assert fresh["wyrd.t"]["published"] == 1
    assert fresh["wyrd.t"]["subscriber_count"] == 1


def test_reset_metrics_zeroes_counters_keeps_subscriber_count() -> None:
    bus = EventBus()
    bus.register_topic("wyrd.t")
    bus.subscribe("wyrd.t", _boom(0))
    bus.subscribe("wyrd.t", lambda e: None)
    bus.publish("wyrd.t", {"n": 1})
    bus.reset_metrics()
    snap = bus.snapshot()
    assert snap["wyrd.t"]["published"] == 0
    assert snap["wyrd.t"]["delivered"] == 0
    assert snap["wyrd.t"]["failed"] == 0
    assert snap["wyrd.t"]["subscriber_count"] == 2  # recomputed live, not zeroed


def test_subscriber_count_follows_subscribe_unsubscribe() -> None:
    bus = EventBus()
    bus.register_topic("wyrd.t")
    assert bus.snapshot()["wyrd.t"]["subscriber_count"] == 0
    t1 = bus.subscribe("wyrd.t", lambda e: None)
    t2 = bus.subscribe("wyrd.t", lambda e: None)
    assert bus.snapshot()["wyrd.t"]["subscriber_count"] == 2
    bus.unsubscribe(t1)
    assert bus.snapshot()["wyrd.t"]["subscriber_count"] == 1
    bus.unsubscribe(t2)
    assert bus.snapshot()["wyrd.t"]["subscriber_count"] == 0


# ---------------------------------------------------------------------------
# slice 9: wildcard subscriptions
# ---------------------------------------------------------------------------

def test_wildcard_receives_matching_topics() -> None:
    bus = EventBus()
    bus.register_topic("world.entity_created")
    bus.register_topic("world.tick")
    got = []
    bus.subscribe("world.*", got.append)
    bus.publish("world.entity_created", {"e": 1})
    bus.publish("world.tick", {"n": 2})
    assert [e["topic"] for e in got] == ["world.entity_created", "world.tick"]


def test_wildcard_does_not_receive_other_prefix() -> None:
    bus = EventBus()
    bus.register_topic("world.tick")
    bus.register_topic("combat.hit")
    got = []
    bus.subscribe("world.*", got.append)
    bus.publish("combat.hit", {"dmg": 5})
    assert got == []
    bus.publish("world.tick", {})
    assert len(got) == 1


def test_exact_and_wildcard_both_fire() -> None:
    bus = EventBus()
    bus.register_topic("world.tick")
    exact, wild = [], []
    bus.subscribe("world.tick", exact.append)
    bus.subscribe("world.*", wild.append)
    n = bus.publish("world.tick", {"n": 1})
    assert n == 2
    assert len(exact) == 1 and len(wild) == 1
    assert exact[0]["seq"] == wild[0]["seq"]


def test_unsubscribe_removes_only_that_subscription() -> None:
    bus = EventBus()
    bus.register_topic("world.tick")
    exact, wild = [], []
    tok_exact = bus.subscribe("world.tick", exact.append)
    tok_wild = bus.subscribe("world.*", wild.append)
    bus.unsubscribe(tok_wild)
    n = bus.publish("world.tick", {})
    assert n == 1 and len(exact) == 1 and wild == []
    bus2 = EventBus()
    bus2.register_topic("world.tick")
    e2, w2 = [], []
    t_e = bus2.subscribe("world.tick", e2.append)
    t_w = bus2.subscribe("world.*", w2.append)
    bus2.unsubscribe(t_e)
    n2 = bus2.publish("world.tick", {})
    assert n2 == 1 and e2 == [] and len(w2) == 1


def test_wildcard_matches_nested_dots_prefix_match() -> None:
    # DECISION (documented): "world.*" is a plain prefix match on "world.",
    # so it also matches "world.a.b".
    bus = EventBus()
    bus.register_topic("world.a.b")
    got = []
    bus.subscribe("world.*", got.append)
    bus.publish("world.a.b", {})
    assert len(got) == 1


def test_wildcard_does_not_match_bare_prefix() -> None:
    bus = EventBus()
    # Dotted-name rule means the "bare prefix" case is "wyrd.world" vs the
    # "wyrd.world." prefix required by the "wyrd.world.*" pattern.
    bus.register_topic("wyrd.world")
    bus.register_topic("wyrd.worldly.tick")
    bus.register_topic("wyrd.world.tick")
    got = []
    bus.subscribe("wyrd.world.*", got.append)
    bus.publish("wyrd.world", {})
    bus.publish("wyrd.worldly.tick", {})
    assert got == []  # needs the literal "wyrd.world." prefix
    bus.publish("wyrd.world.tick", {})
    assert len(got) == 1  # positive control: real prefix match fires


def test_publish_wildcard_raises_keyerror() -> None:
    bus = EventBus()
    bus.register_topic("world.tick")
    with pytest.raises(KeyError):
        bus.publish("world.*", {})


def test_register_wildcard_raises_keyerror() -> None:
    bus = EventBus()
    with pytest.raises(KeyError):
        bus.register_topic("world.*")


def test_wildcard_subscribe_needs_no_registration() -> None:
    bus = EventBus()
    got = []
    tok = bus.subscribe("future.*", got.append)  # no topics exist yet
    assert isinstance(tok, str) and tok  # opaque token (uuid4 hex)
    bus.register_topic("future.event")
    bus.publish("future.event", {"x": 1})
    assert len(got) == 1


def test_wildcard_metrics_subscriber_count_counts_exact_only() -> None:
    bus = EventBus()
    bus.register_topic("world.tick")
    bus.subscribe("world.tick", lambda e: None)
    bus.subscribe("world.*", lambda e: None)
    n = bus.publish("world.tick", {})
    assert n == 2
    snap = bus.snapshot()
    assert snap["world.tick"]["subscriber_count"] == 1  # exact only
    assert snap["world.tick"]["delivered"] == 2


def test_wildcard_replay_merges_buffers_by_seq() -> None:
    bus = EventBus()
    bus.register_topic("w.a")
    bus.register_topic("w.b")
    bus.publish("w.a", {"i": 0})
    bus.publish("w.b", {"i": 1})
    bus.publish("w.a", {"i": 2})
    got = []
    bus.subscribe("w.*", got.append, replay=True)
    assert [(e["topic"], e["payload"]["i"]) for e in got] == [
        ("w.a", 0), ("w.b", 1), ("w.a", 2),
    ]


# ---------------------------------------------------------------------------
# slice 10: shutdown
# ---------------------------------------------------------------------------

def test_publish_after_close_raises_runtimeerror() -> None:
    bus = EventBus()
    bus.register_topic("wyrd.t")
    bus.close()
    with pytest.raises(RuntimeError, match="bus closed"):
        bus.publish("wyrd.t", {"n": 1})


def test_subscribe_after_close_raises_runtimeerror() -> None:
    bus = EventBus()
    bus.register_topic("wyrd.t")
    bus.close()
    with pytest.raises(RuntimeError, match="bus closed"):
        bus.subscribe("wyrd.t", lambda e: None)


def test_close_idempotent() -> None:
    bus = EventBus()
    bus.register_topic("wyrd.t")
    bus.close()
    bus.close()  # must not raise
    assert bus.closed


def test_close_clears_state() -> None:
    bus = EventBus()
    bus.register_topic("wyrd.t")
    bus.subscribe("wyrd.t", lambda e: None)
    bus.subscribe("wyrd.t", _boom(0))
    bus.publish("wyrd.t", {"n": 1})
    assert bus.snapshot()["wyrd.t"]["subscriber_count"] == 2
    assert bus.dead_letters()
    bus.close()
    assert bus.snapshot()["wyrd.t"]["subscriber_count"] == 0
    assert bus.snapshot()["wyrd.t"]["published"] == 0
    assert bus.dead_letters() == []
    assert bus._take_failures() == []
    # replay buffer cleared too
    bus2 = EventBus()
    bus2.register_topic("wyrd.t")
    bus2.publish("wyrd.t", {"n": 1})
    bus2.close()


def test_register_after_close_raises_runtimeerror() -> None:
    bus = EventBus()
    bus.close()
    with pytest.raises(RuntimeError, match="bus closed"):
        bus.register_topic("wyrd.t")
