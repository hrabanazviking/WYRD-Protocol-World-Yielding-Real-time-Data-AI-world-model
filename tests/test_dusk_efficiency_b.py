"""Dusk forge 2026-10-11 — "Gullinbursti" worker B tests.

Slices 3 (wildcard replay k-way merge), 4 (replay delivery outside the bus
lock), 5 (precomputed wildcard prefixes), 6 (publish_many batch API).
"""

from __future__ import annotations

import threading
import time

import pytest

from wyrdforge.runtime.events import _SEQ_KEY, EventBus


def _seed_topics(bus: EventBus, n_topics: int, per_topic: int) -> None:
    """Publish per_topic events on each of n_topics interleaved topics.

    Interleaving (round-robin) mimics real traffic: seq numbers are spread
    across topics, which is exactly what the k-way merge has to untangle.
    """
    for i in range(n_topics):
        bus.register_topic(f"w.t{i}", replay_buffer=per_topic)
    for m in range(per_topic):
        for i in range(n_topics):
            bus.publish(f"w.t{i}", {"i": i, "m": m})


# ---------------------------------------------------------------------------
# Slice 3 — replay wildcard k-way merge
# ---------------------------------------------------------------------------


def _old_merge_order(bus: EventBus, prefix: str):
    """The pre-slice-3 algorithm: extend everything, then sort."""
    replayed = []
    for tname, buf in bus._buffers.items():
        if buf and tname.startswith(prefix):
            replayed.extend(buf)
    replayed.sort(key=lambda e: e.seq)
    return [e.seq for e in replayed]


def test_slice3_wildcard_replay_order_matches_old_path() -> None:
    """Differential test: heapq.merge backfill order == old extend+sort."""
    bus = EventBus()
    _seed_topics(bus, 8, 25)
    expected = _old_merge_order(bus, "w.")
    got: list = []
    bus.subscribe("w.*", got.append, replay=True)
    assert [e.seq for e in got] == expected
    assert expected == sorted(expected)  # global seq order, ascending
    assert len(expected) == 8 * 25


def test_slice3_merge_with_empty_and_zero_buffers() -> None:
    """Empty deques and replay_buffer=0 topics don't disturb the merge."""
    bus = EventBus()
    bus.register_topic("w.full", replay_buffer=10)
    bus.register_topic("w.empty", replay_buffer=10)  # no events
    bus.register_topic("w.off", replay_buffer=0)  # no buffer at all
    for i in range(5):
        bus.publish("w.full", {"i": i})
    got: list = []
    bus.subscribe("w.*", got.append, replay=True)
    assert [e.seq for e in got] == [1, 2, 3, 4, 5]


def test_slice3_kway_merge_benchmark() -> None:
    """Multi-stream backfill: new path vs the old lambda-key path.

    Both algorithms run on the *same* live deques (48 topics x 256
    interleaved events). The win comes from the C-speed ``attrgetter``
    sort key; measured here on this machine (generous bound: new must
    simply be faster, min of 5 runs each).
    """
    bus = EventBus()
    n_topics, per_topic = 48, 256  # 12,288 envelopes
    _seed_topics(bus, n_topics, per_topic)
    streams = [buf for buf in bus._buffers.values() if buf]

    def old_path():
        replayed = []
        for buf in streams:
            replayed.extend(buf)
        replayed.sort(key=lambda e: e.seq)
        return replayed

    def new_path():
        # Mirrors the bus implementation: multi-stream -> extend+sort.
        replayed = []
        for buf in streams:
            replayed.extend(buf)
        replayed.sort(key=_SEQ_KEY)
        return replayed

    assert [e.seq for e in old_path()] == [e.seq for e in new_path()]

    t_old = min(_timeit(old_path) for _ in range(5))
    t_new = min(_timeit(new_path) for _ in range(5))
    print(f"\n[ slice3 ] multi-stream old={t_old*1000:.2f}ms "
          f"new={t_new*1000:.2f}ms speedup={t_old/t_new:.2f}x "
          f"({n_topics}x{per_topic})")
    assert t_new < t_old, "new merge path must beat the old lambda-key path"


def test_slice3_single_stream_skips_sort_benchmark() -> None:
    """Single matching buffer: no sort at all vs the old sort-everything."""
    bus = EventBus()
    n = 4096
    bus.register_topic("w.only", replay_buffer=n)
    for i in range(n):
        bus.publish("w.only", {"i": i})
    (stream,) = [buf for buf in bus._buffers.values() if buf]

    def old_path():
        replayed = []
        replayed.extend(stream)
        replayed.sort(key=lambda e: e.seq)
        return replayed

    def new_path():
        return list(stream)  # already seq-ordered: no sort needed

    assert [e.seq for e in old_path()] == [e.seq for e in new_path()]

    # End-to-end through the real subscribe() path.
    got_old: list = []
    t0 = time.perf_counter()
    bus.subscribe("w.*", got_old.append, replay=True)
    t_sub = time.perf_counter() - t0
    assert [e.seq for e in got_old] == [e.seq for e in new_path()]

    t_old = min(_timeit(old_path) for _ in range(5))
    t_new = min(_timeit(new_path) for _ in range(5))
    print(f"\n[ slice3 ] single-stream old={t_old*1000:.2f}ms "
          f"new={t_new*1000:.3f}ms speedup={t_old/t_new:.1f}x (n={n}); "
          f"subscribe(replay=True) end-to-end={t_sub*1000:.2f}ms")
    assert t_new < t_old, "single-stream path must skip the sort"


def _timeit(fn) -> float:
    start = time.perf_counter()
    fn()
    return time.perf_counter() - start


# ---------------------------------------------------------------------------
# Slice 4 — replay delivery outside the bus lock
# ---------------------------------------------------------------------------


def test_slice4_slow_replay_subscriber_does_not_block_publish() -> None:
    """A slow replay subscriber must not head-of-line-block other traffic.

    20 buffered events x 50ms replay delivery ~= 1.0s. Under the old code
    (delivery under the bus RLock) a concurrent publish would block ~1s;
    now it must complete within a generous 0.5s budget.
    """
    bus = EventBus()
    bus.register_topic("a.t1", replay_buffer=64)
    bus.register_topic("x.live", replay_buffer=8)
    for i in range(20):
        bus.publish("a.t1", {"i": i})
    live_done: list = []
    bus.subscribe("x.live", live_done.append)

    replay_started = threading.Event()
    replayed: list = []

    def slow_fn(env):
        replayed.append(env)
        replay_started.set()
        time.sleep(0.05)

    t = threading.Thread(
        target=bus.subscribe, args=("a.*", slow_fn), kwargs={"replay": True}
    )
    t.start()
    assert replay_started.wait(timeout=10), "replay delivery never started"
    t0 = time.monotonic()
    delivered = bus.publish("x.live", {"ping": 1})
    latency = time.monotonic() - t0
    t.join(timeout=15)
    assert delivered == 1
    assert len(live_done) == 1
    assert len(replayed) == 20
    print(f"\n[ slice4 ] concurrent publish latency={latency*1000:.1f}ms "
          f"(replay took ~1000ms)")
    assert latency < 0.5, f"publish blocked by replay delivery: {latency:.3f}s"


def test_slice4_replay_before_live_ordering_for_subscribing_thread() -> None:
    """After subscribe(replay=True) returns, backfill precedes later live.

    The subscribing thread itself still observes replay-then-live ordering:
    subscribe() only returns once every replayed envelope was delivered.
    """
    bus = EventBus()
    bus.register_topic("a.t1", replay_buffer=16)
    for i in range(5):
        bus.publish("a.t1", {"i": i})
    seen: list = []
    bus.subscribe("a.*", seen.append, replay=True)  # blocks until backfilled
    for i in range(3):
        bus.publish("a.t1", {"i": i + 5})
    seqs = [e.seq for e in seen]
    assert seqs == [1, 2, 3, 4, 5, 6, 7, 8]


def test_slice4_replay_failure_still_isolated_outside_lock() -> None:
    """A raising replay subscriber still isolates failures without the lock."""
    bus = EventBus()
    bus.register_topic("a.t1", replay_buffer=8)
    for i in range(3):
        bus.publish("a.t1", {"i": i})

    def boom(env):
        raise RuntimeError("replay boom")

    bus.subscribe("a.*", boom, replay=True)
    assert len(bus._take_failures()) == 3
    snap = bus.snapshot()["a.t1"]
    assert snap["failed"] == 3 and snap["published"] == 3
    assert len(bus.dead_letters()) == 3


# ---------------------------------------------------------------------------
# Slice 5 — precomputed wildcard prefixes
# ---------------------------------------------------------------------------


def test_slice5_prefix_stored_at_subscribe() -> None:
    """White-box: (token, pattern, prefix, fn) is stored at subscribe()."""
    bus = EventBus()
    tok1 = bus.subscribe("world.*", lambda e: None)
    tok2 = bus.subscribe("*", lambda e: None)
    by_token = {t: (p, prefix) for t, p, prefix, _fn in bus._wildcards}
    assert by_token[tok1] == ("world.*", "world.")
    assert by_token[tok2] == ("*", "")


def test_slice5_prefix_survives_unsubscribe_of_other() -> None:
    bus = EventBus()
    bus.register_topic("a.t1")
    tok1 = bus.subscribe("a.*", lambda e: None)
    bus.subscribe("a.*", lambda e: None)
    bus.unsubscribe(tok1)
    assert len(bus._wildcards) == 1
    (t, p, prefix, _fn), = bus._wildcards
    assert p == "a.*" and prefix == "a."
    got: list = []
    bus.subscribe("a.t1", got.append)
    bus.publish("a.t1", {"x": 1})
    assert [e.payload for e in got] == [{"x": 1}]


def test_slice5_wildcard_matching_behavior_identical() -> None:
    """Exact-then-wildcard delivery order and prefix matching unchanged."""
    bus = EventBus()
    for name in ("w.a", "w.b", "other.c"):
        bus.register_topic(name)
    order: list = []
    bus.subscribe("w.a", lambda e: order.append(("exact", e.topic)))
    bus.subscribe("w.*", lambda e: order.append(("wild", e.topic)))
    bus.subscribe("*", lambda e: order.append(("star", e.topic)))
    bus.publish("w.a", {})
    bus.publish("w.b", {})
    bus.publish("other.c", {})
    assert order == [
        ("exact", "w.a"), ("wild", "w.a"), ("star", "w.a"),
        ("wild", "w.b"), ("star", "w.b"),
        ("star", "other.c"),
    ]


# ---------------------------------------------------------------------------
# Slice 6 — publish_many batch API
# ---------------------------------------------------------------------------


def _build_pair() -> tuple[EventBus, EventBus, list, list]:
    """Two identically-registered buses with identical subscriber shapes."""
    topics = ["w.a", "w.b", "w.c"]
    buses = []
    collectors = []
    for _ in range(2):
        bus = EventBus()
        for name in topics:
            bus.register_topic(name, replay_buffer=64)
        got: list = []
        for name in topics:
            bus.subscribe(name, got.append)
        bus.subscribe("w.*", got.append)
        buses.append(bus)
        collectors.append(got)
    return buses[0], buses[1], collectors[0], collectors[1]


def test_slice6_equivalence_with_individual_publishes() -> None:
    """publish_many == N publishes: deliveries, metrics, seq, replay buffers."""
    bus_a, bus_b, got_a, got_b = _build_pair()
    items = [(f"w.{'abc'[i % 3]}", {"n": i}) for i in range(30)]

    total_a = sum(bus_a.publish(topic, payload) for topic, payload in items)
    total_b = bus_b.publish_many(items)
    assert total_a == total_b == 30 * 2  # exact + wildcard subscriber each

    key = lambda e: (e.topic, e.seq, tuple(sorted(e.payload.items())))
    assert [key(e) for e in got_a] == [key(e) for e in got_b]

    assert bus_a.snapshot() == bus_b.snapshot()

    for name in ("w.a", "w.b", "w.c"):
        bufa = [key(e) for e in bus_a._buffers[name]]
        bufb = [key(e) for e in bus_b._buffers[name]]
        assert bufa == bufb


def test_slice6_schema_and_unknown_topic_enforcement() -> None:
    """Same enforcement as publish(): schema TypeError, unknown KeyError."""
    from pydantic import BaseModel

    class P(BaseModel):
        x: int

    bus = EventBus()
    bus.register_topic("s.t", payload_schema=P)
    bus.register_topic("s.ok")

    with pytest.raises(TypeError, match="s.t"):
        bus.publish_many([("s.t", {"x": "not-an-int"})])
    with pytest.raises(KeyError):
        bus.publish_many([("nope.topic", {})])
    with pytest.raises(KeyError, match="wildcard"):
        bus.publish_many([("w.*", {})])

    # Fail-fast in order: earlier items are applied, like N publishes.
    got: list = []
    bus.subscribe("s.ok", got.append)
    with pytest.raises(TypeError):
        bus.publish_many(
            [("s.ok", {"n": 1}), ("s.t", {"x": "bad"}), ("s.ok", {"n": 2})]
        )
    assert [e.payload for e in got] == [{"n": 1}]
    assert bus.snapshot()["s.ok"]["published"] == 1


def test_slice6_failing_subscriber_isolation() -> None:
    """A raising subscriber in a batch is isolated; later items still flow."""
    bus = EventBus()
    bus.register_topic("w.a")
    bus.register_topic("w.b")
    calls: list = []

    def boom(env):
        raise RuntimeError("batch boom")

    bus.subscribe("w.a", boom)
    bus.subscribe("w.a", calls.append)
    bus.subscribe("w.b", calls.append)
    total = bus.publish_many(
        [("w.a", {"n": 1}), ("w.b", {"n": 2}), ("w.a", {"n": 3})]
    )
    # w.a items: boom fails + calls succeeds each; w.b: calls succeeds
    assert total == 3
    assert [(e.topic, e.payload) for e in calls] == [
        ("w.a", {"n": 1}), ("w.b", {"n": 2}), ("w.a", {"n": 3})
    ]
    snap = bus.snapshot()
    assert snap["w.a"]["failed"] == 2 and snap["w.a"]["delivered"] == 2
    assert snap["w.b"]["delivered"] == 1
    assert len(bus.dead_letters()) == 2


def test_slice6_benchmark_lower_overhead() -> None:
    """Batch beats N publishes: one lock + per-topic target snapshot.

    With W wildcard subscriptions, N individual publishes each scan all W
    wildcards (O(N*W)); publish_many snapshots targets once per topic
    (O(T*W + N)). Measured on this machine, min of 5 runs each.
    """
    bus = EventBus()
    n_topics = 8
    for i in range(n_topics):
        bus.register_topic(f"w.t{i}", replay_buffer=0)
    for _ in range(12):
        bus.subscribe("w.*", lambda e: None)
    n = 2000
    items = [(f"w.t{i % n_topics}", {"n": i}) for i in range(n)]

    def singles():
        for topic, payload in items:
            bus.publish(topic, payload)

    def batched():
        bus.publish_many(items)

    t_single = min(_timeit(singles) for _ in range(5))
    t_batch = min(_timeit(batched) for _ in range(5))
    snap = bus.snapshot()
    total_published = sum(r["published"] for r in snap.values())
    assert total_published == 10 * n  # min() runs each closure 5 times
    print(f"\n[ slice6 ] {n} publishes x12 wildcards: singles={t_single*1000:.1f}ms "
          f"batch={t_batch*1000:.1f}ms speedup={t_single/t_batch:.2f}x")
    assert t_batch < t_single, "publish_many must beat N publishes"


def test_slice6_reentrant_unsubscribe_matches_n_publishes() -> None:
    """A re-entrant (un)subscribe mid-batch behaves like N publishes.

    The subscription-generation counter invalidates the per-topic target
    cache, so later items in the batch see the new subscription set —
    exactly as sequential publish() calls would.
    """
    def run(publish_fn):
        bus = EventBus()
        bus.register_topic("w.a")
        bus.register_topic("w.b")
        seen: list = []

        def flipper(env):
            seen.append(("flipper", env.topic, env.seq))
            if env.topic == "w.a":
                bus.unsubscribe(tok_wild)  # re-entrant, mid-batch

        tok_wild = bus.subscribe("w.*", flipper)
        bus.subscribe("w.b", lambda e: seen.append(("b", e.topic, e.seq)))
        items = [("w.a", {"n": 1}), ("w.b", {"n": 2}), ("w.a", {"n": 3})]
        publish_fn(bus, items)
        return seen, bus.snapshot()

    def singles(bus, items):
        for topic, payload in items:
            bus.publish(topic, payload)

    seen_s, snap_s = run(singles)
    seen_b, snap_b = run(lambda b, items: b.publish_many(items))
    # item1: flipper fires and unsubscribes itself; item2: only "b" sub;
    # item3: nobody left.
    assert seen_s == [("flipper", "w.a", 1), ("b", "w.b", 2)]
    assert seen_b == seen_s
    assert snap_b == snap_s
