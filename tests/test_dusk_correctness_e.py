"""Dusk forge 2026-10-11 (worker E) — EventBus correctness audits.

Slice 11: re-entrant publish FIFO audit (characterization + the one real
    bug found, fixed in-slice).
Slice 12: replay/live interleaving audit (concurrent characterization).
Slice 13: dead-letter cap exactness.
"""

from __future__ import annotations

import threading

from wyrdforge.runtime.events import EventBus


# ---------------------------------------------------------------------------
# Slice 11 — re-entrant publish FIFO audit
# ---------------------------------------------------------------------------


class TestReentrantPublishFifo:
    def test_cross_topic_reentrant_publish_order_pinned(self):
        """A subscriber publishing to ANOTHER topic from its callback.

        Pinned actual order: the inner envelope (seq 2) is delivered to its
        subscribers before the outer envelope (seq 1) finishes delivery to
        its remaining subscribers. Per-topic FIFO holds for EVERY
        subscriber; the global interleave is documented, allowed behavior.
        """
        bus = EventBus()
        bus.register_topic("t.a")
        bus.register_topic("t.b")
        seen: list = []

        def s1(env):
            seen.append(("s1", env.topic, env.seq))
            if env.topic == "t.a":
                bus.publish("t.b", {"x": 1})  # re-entrant, cross-topic

        def s2(env):
            seen.append(("s2", env.topic, env.seq))

        def tb(env):
            seen.append(("tb", env.topic, env.seq))

        bus.subscribe("t.a", s1)
        bus.subscribe("t.a", s2)
        bus.subscribe("t.b", tb)
        n = bus.publish("t.a", {})
        # Outer publish counts its own two deliveries; the inner publish's
        # delivery is counted by the inner call.
        assert n == 2
        assert seen == [("s1", "t.a", 1), ("tb", "t.b", 2), ("s2", "t.a", 1)]
        # Per-topic FIFO holds for every subscriber.
        for who in ("s1", "s2"):
            seqs = [s for w, t, s in seen if w == who and t == "t.a"]
            assert seqs == sorted(seqs)

    def test_same_topic_reentrant_publish_preserves_fifo(self):
        """AUDIT BUG (fixed in-slice, dusk 2026-10-11): a subscriber
        publishing to the SAME topic from its callback used to invert
        per-topic FIFO for later subscribers — q2 observed
        ``[2, 1]`` because the inner envelope was delivered immediately,
        ahead of the still-in-flight outer envelope.

        Fix: the re-entrant same-topic publish is deferred until the
        outermost delivery completes (still synchronous, before the outer
        publish returns). The deferred call returns 0; its deliveries count
        toward the outermost call's return value.
        """
        bus = EventBus()
        bus.register_topic("t.a")
        seen: list = []
        fired = {"n": 0}

        def q1(env):
            seen.append(("q1", env.seq))
            if fired["n"] == 0:
                fired["n"] += 1
                inner = bus.publish("t.a", {"re": True})
                assert inner == 0  # deferred: deliveries not done yet

        def q2(env):
            seen.append(("q2", env.seq))

        bus.subscribe("t.a", q1)
        bus.subscribe("t.a", q2)
        n = bus.publish("t.a", {})
        assert n == 4  # outer (q1, q2) + deferred inner (q1, q2)
        assert seen == [("q1", 1), ("q2", 1), ("q1", 2), ("q2", 2)]
        snap = bus.snapshot()["t.a"]
        assert snap["published"] == 2
        assert snap["delivered"] == 4
        assert snap["failed"] == 0

    def test_same_topic_reentrant_publish_many_preserves_fifo(self):
        """Same deferral guarantee through publish_many()."""
        bus = EventBus()
        bus.register_topic("t.a")
        seen: list = []
        fired = {"n": 0}

        def r1(env):
            seen.append(("r1", env.seq))
            if fired["n"] == 0:
                fired["n"] += 1
                assert bus.publish("t.a", {}) == 0  # deferred

        def r2(env):
            seen.append(("r2", env.seq))

        bus.subscribe("t.a", r1)
        bus.subscribe("t.a", r2)
        n = bus.publish_many([("t.a", {"k": 1})])
        assert n == 4
        assert seen == [("r1", 1), ("r2", 1), ("r1", 2), ("r2", 2)]

    def test_nested_same_topic_reentrant_publish_preserves_fifo(self):
        """Two levels of same-topic re-entrancy: every subscriber still
        observes envelopes in seq order."""
        bus = EventBus()
        bus.register_topic("t.a")
        seen: list = []
        depth = {"n": 0}

        def d1(env):
            seen.append(("d1", env.seq))
            if depth["n"] < 2:
                depth["n"] += 1
                bus.publish("t.a", {"lvl": depth["n"]})

        def d2(env):
            seen.append(("d2", env.seq))

        bus.subscribe("t.a", d1)
        bus.subscribe("t.a", d2)
        n = bus.publish("t.a", {})
        assert n == 6
        for who in ("d1", "d2"):
            got = [s for w, s in seen if w == who]
            assert got == [1, 2, 3], (who, got)


# ---------------------------------------------------------------------------
# Slice 12 — replay/live interleaving audit
# ---------------------------------------------------------------------------


class TestReplayLiveInterleaving:
    def test_replay_before_live_after_subscribe_returns(self):
        """Deterministic pin: once subscribe(replay=True) has returned, the
        backfill is fully delivered, so a later publish is always observed
        after the replayed envelopes."""
        bus = EventBus()
        bus.register_topic("t.e", replay_buffer=64)
        for i in range(10):
            bus.publish("t.e", {"i": i})
        got: list = []
        bus.subscribe("t.e", got.append, replay=True)
        bus.publish("t.e", {"i": 10})
        assert [e.seq for e in got] == list(range(1, 12))

    def test_concurrent_publish_during_replay_subscribe(self):
        """Hammer publishes from another thread while subscribe(replay=True)
        runs. Documented guarantee pinned:

        * every envelope is delivered to the new subscriber EXACTLY once
          (a publish either lands in the replay snapshot or is delivered
          live — the subscribe lock section serializes the two);
        * envelopes that were already buffered (seq <= K) are delivered in
          seq order among themselves (the replay path is seq-ordered);
        * live envelopes may interleave arbitrarily with the replay —
          that interleave is documented, not a FIFO violation.
        """
        bus = EventBus()
        bus.register_topic("t.c", replay_buffer=4096)
        K, M = 200, 300
        for i in range(K):
            bus.publish("t.c", {"i": i})

        received: list = []
        rlock = threading.Lock()

        def cb(env):
            with rlock:
                received.append(env.seq)

        def publisher():
            for i in range(M):
                bus.publish("t.c", {"i": K + i})

        t = threading.Thread(target=publisher, name="fuzz-publisher")
        t.start()
        bus.subscribe("t.c", cb, replay=True)
        t.join(timeout=60)
        assert not t.is_alive()

        # Exactly-once delivery of every envelope.
        assert sorted(received) == list(range(1, K + M + 1))
        assert len(set(received)) == len(received)
        # Replayed envelopes (seq <= K, all pre-subscribe) keep seq order
        # among themselves even under the concurrent live stream.
        pos = {seq: i for i, seq in enumerate(received)}
        replayed_positions = [pos[s] for s in range(1, K + 1)]
        assert replayed_positions == sorted(replayed_positions)

    def test_concurrent_publish_during_wildcard_replay_subscribe(self):
        """Same pin through the wildcard merge path (extend+sort)."""
        bus = EventBus()
        bus.register_topic("w.a", replay_buffer=2048)
        bus.register_topic("w.b", replay_buffer=2048)
        K = 120
        for i in range(K):
            bus.publish("w.a" if i % 2 == 0 else "w.b", {"i": i})

        received: list = []
        rlock = threading.Lock()

        def cb(env):
            with rlock:
                received.append((env.topic, env.seq))

        def publisher():
            for i in range(K):
                bus.publish("w.a" if i % 2 == 0 else "w.b", {"j": i})

        t = threading.Thread(target=publisher, name="fuzz-wild-publisher")
        t.start()
        bus.subscribe("w.*", cb, replay=True)
        t.join(timeout=60)
        assert not t.is_alive()

        seqs = [s for _, s in received]
        assert sorted(seqs) == list(range(1, 2 * K + 1))
        assert len(set(seqs)) == len(seqs)
        # Per-topic FIFO holds for the wildcard subscriber too.
        for topic in ("w.a", "w.b"):
            got = [s for tp, s in received if tp == topic]
            assert got == sorted(got), topic


# ---------------------------------------------------------------------------
# Slice 13 — dead-letter cap exactness
# ---------------------------------------------------------------------------


class TestDeadLetterCapExactness:
    def _failing_bus(self, cap: int) -> EventBus:
        bus = EventBus(dead_letter_cap=cap)
        bus.register_topic("t.f")

        def boom(env):
            raise RuntimeError("nope")

        bus.subscribe("t.f", boom)
        return bus

    def test_300_failing_deliveries_retain_exactly_256(self):
        """300 failing deliveries -> exactly 256 retained, oldest dropped
        first (bounded deque semantics, no off-by-one)."""
        bus = self._failing_bus(256)
        for i in range(300):
            assert bus.publish("t.f", {"i": i}) == 0
        letters = bus.dead_letters()
        assert len(letters) == 256
        # Oldest 44 dropped; the retained 256 are the NEWEST, still ordered
        # oldest-first.
        assert [e["seq"] for e in letters] == list(range(45, 301))
        assert letters[0]["error_type"] == "RuntimeError"
        assert letters[0]["topic"] == "t.f"
        summary = bus.dead_letter_summary()
        assert summary == {"t.f": {"RuntimeError": 256}}
        snap = bus.snapshot()["t.f"]
        assert snap["published"] == 300
        assert snap["failed"] == 300
        assert snap["delivered"] == 0
        # Draining works and leaves the queue empty.
        drained = bus.take_dead_letters()
        assert len(drained) == 256
        assert bus.dead_letters() == []

    def test_exactly_at_cap_boundary(self):
        bus = self._failing_bus(256)
        for i in range(256):
            bus.publish("t.f", {"i": i})
        letters = bus.dead_letters()
        assert len(letters) == 256
        assert [e["seq"] for e in letters] == list(range(1, 257))

    def test_cap_zero_retains_nothing(self):
        bus = self._failing_bus(0)
        for i in range(10):
            bus.publish("t.f", {"i": i})
        assert bus.dead_letters() == []
        assert bus.snapshot()["t.f"]["failed"] == 10
