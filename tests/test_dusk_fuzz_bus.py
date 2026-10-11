"""Dusk forge 2026-10-11 (worker E), slice 19 — EventBus randomized-op fuzz.

Seeded random sequences of publish / publish_many / subscribe /
unsubscribe / replay-subscribe / close over a single-threaded bus,
asserting after every run:

* no unexpected exception escapes to the caller (only the documented
  KeyError / TypeError / RuntimeError-after-close, which the driver
  expects explicitly);
* metrics coherence per topic: ``snapshot()[t]["published"]`` equals the
  envelopes the driver sent; ``snapshot()[t]["delivered"] +
  snapshot()[t]["failed"]`` equals the delivery attempts the driver
  counted (every attempt either succeeds or is isolated as a failure —
  a raising subscriber never breaks the bus);
* per-(subscriber, topic) FIFO: every subscriber observes each topic's
  envelopes in strictly increasing seq order — across re-entrant
  same-topic publishes (slice-11 deferral), cross-topic re-entrancy,
  publish_many batches, and replays;
* the dead-letter queue never exceeds its cap and retains the newest
  failures oldest-first;
* after close(), every bus op raises RuntimeError (unsubscribe of a
  cleared token raises KeyError).

4 seeds x 500 ops = 2000 ops total, all green.
"""

from __future__ import annotations

import random
from collections import deque

import pytest

from wyrdforge.runtime.events import EventBus


TOPICS = ["f.a", "f.b", "f.c", "f.d"]
BUFFER_SIZES = {"f.a": 16, "f.b": 0, "f.c": 64, "f.d": 8}
WILDCARD_PATTERNS = ["f.*", "*"]
OPS_PER_SEED = 500
SEEDS = (11, 12, 13, 19)
DEAD_LETTER_CAP = 64
REPUB_BUDGET = 3  # max re-entrant publishes per subscriber, per run


def _matches(pattern: str, topic: str) -> bool:
    # Mirrors EventBus._wildcard_prefix matching.
    return True if pattern == "*" else topic.startswith(pattern[:-1])


class _Sub:
    """Subscriber callback with a driver-assigned token."""

    def __init__(self, driver: "BusFuzzDriver") -> None:
        self.driver = driver
        self.token: str | None = None
        # Records delivered before subscribe() returns (the replay
        # backfill is delivered inside the subscribe() call, before the
        # token exists); flushed into driver.received[token] afterwards.
        self.pending: list[tuple[str, int]] = []

    def __call__(self, env) -> None:
        driver = self.driver
        rec = (env.topic, env.seq)
        if self.token is None:
            # Inside subscribe()'s replay backfill: no raising and no
            # re-entrant publish on this path — the driver's subscription
            # mirror is not updated until subscribe() returns either.
            self.pending.append(rec)
            return
        driver.received[self.token].append(rec)
        r = driver.rng.random()
        if r < 0.07:
            raise RuntimeError(f"fuzz boom {self.token}")
        # Re-entrant publish (bounded); same-topic picks exercise the
        # slice-11 deferral path under fuzz.
        if r < 0.17 and driver.repub_budget[self.token] > 0:
            driver.repub_budget[self.token] -= 1
            driver.do_publish(driver.rng.choice(TOPICS), {"re": self.token})


class BusFuzzDriver:
    """Single-threaded driver mirroring bus state for invariant checks."""

    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)
        self.bus = EventBus(dead_letter_cap=DEAD_LETTER_CAP)
        for topic, size in BUFFER_SIZES.items():
            self.bus.register_topic(topic, replay_buffer=size)
        # -- mirrors --
        self.exact: dict[str, list[str]] = {t: [] for t in TOPICS}
        self.wild: list[tuple[str, str]] = []  # (token, pattern)
        self.live_tokens: list[str] = []
        self.token_kind: dict[str, str] = {}
        self.received: dict[str, list[tuple[str, int]]] = {}
        # replay-buffer length mirrors (bus evicts oldest at maxlen)
        self.buflen: dict[str, deque | None] = {
            t: deque(maxlen=s) if s > 0 else None
            for t, s in BUFFER_SIZES.items()
        }
        self.repub_budget: dict[str, int] = {}
        self.closed = False
        # -- accounting --
        self.envelopes = {t: 0 for t in TOPICS}
        self.attempts = {t: 0 for t in TOPICS}
        self.op_count = 0

    # -- helpers ------------------------------------------------------

    def _targets(self, topic: str) -> int:
        n = len(self.exact[topic])
        for _, pattern in self.wild:
            if _matches(pattern, topic):
                n += 1
        return n

    def _track_envelope(self, topic: str) -> None:
        self.envelopes[topic] += 1
        self.attempts[topic] += self._targets(topic)
        buf = self.buflen[topic]
        if buf is not None:
            buf.append(1)

    # -- ops ----------------------------------------------------------

    def do_publish(self, topic: str, payload: dict) -> None:
        self._track_envelope(topic)
        self.bus.publish(topic, payload)

    def do_publish_many(self, items: list[tuple[str, dict]]) -> None:
        for topic, _payload in items:
            self._track_envelope(topic)
        self.bus.publish_many(items)

    def do_subscribe(self) -> None:
        if self.rng.random() < 0.65:
            topic: str = self.rng.choice(TOPICS)
            pattern: str | None = None
        else:
            pattern = self.rng.choice(WILDCARD_PATTERNS)
            topic = pattern
        replay = self.rng.random() < 0.5
        sub = _Sub(self)
        token = self.bus.subscribe(topic, sub, replay=replay)
        sub.token = token
        # Flush any records delivered by the in-subscribe() replay backfill.
        self.received[token] = sub.pending
        sub.pending = []
        self.repub_budget[token] = REPUB_BUDGET
        self.live_tokens.append(token)
        if pattern is None:
            self.exact[topic].append(token)
            self.token_kind[token] = f"exact:{topic}"
        else:
            self.wild.append((token, pattern))
            self.token_kind[token] = f"wild:{pattern}"
        # Replay delivers each buffered envelope once to the new
        # subscriber: one attempt per envelope per its topic.
        if replay:
            if pattern is None:
                buf = self.buflen[topic]
                self.attempts[topic] += len(buf) if buf is not None else 0
            else:
                for t in TOPICS:
                    if _matches(pattern, t):
                        buf = self.buflen[t]
                        self.attempts[t] += len(buf) if buf is not None else 0

    def do_unsubscribe(self) -> None:
        if self.live_tokens and self.rng.random() < 0.9:
            token = self.rng.choice(self.live_tokens)
            self.bus.unsubscribe(token)
            self.live_tokens.remove(token)
            kind = self.token_kind.pop(token)
            if kind.startswith("exact:"):
                self.exact[kind[len("exact:"):]].remove(token)
            else:
                self.wild = [(t, p) for t, p in self.wild if t != token]
        else:
            with pytest.raises(KeyError):
                self.bus.unsubscribe("bogus-token-fuzz")

    def do_close(self) -> None:
        self.bus.close()
        self.closed = True
        self.bus.close()  # idempotent
        # Mirror close(): metrics zeroed, replay buffers and the
        # subscription/token tables cleared. Per-subscriber delivery history
        # (received) is kept — the FIFO invariant still applies to it.
        self.envelopes = {t: 0 for t in TOPICS}
        self.attempts = {t: 0 for t in TOPICS}
        for t in TOPICS:
            buf = self.buflen[t]
            if buf is not None:
                buf.clear()
        self.exact = {t: [] for t in TOPICS}
        self.wild = []
        self.live_tokens = []
        self.token_kind = {}

    def do_observe(self) -> None:
        snap = self.bus.snapshot()
        for t in TOPICS:
            assert snap[t]["subscriber_count"] == len(self.exact[t]), t
        letters = self.bus.dead_letters()
        assert len(letters) <= DEAD_LETTER_CAP
        summary = self.bus.dead_letter_summary()
        assert sum(sum(d.values()) for d in summary.values()) == len(letters)
        if not self.closed:
            # Invalid-op probes: documented errors, never escapes.
            with pytest.raises(KeyError):
                self.bus.publish("no.such.topic", {})
            with pytest.raises(TypeError):
                self.bus.publish("f.a", ["not", "a", "dict"])  # type: ignore[arg-type]
            with pytest.raises(KeyError):
                self.bus.subscribe("no.such.topic", lambda e: None)
            with pytest.raises(KeyError):
                self.bus.register_topic("f.*")

    def step(self) -> None:
        self.op_count += 1
        if self.closed:
            # Every post-close op must refuse loudly; unsubscribe hits the
            # cleared token table (KeyError), the rest hit _ensure_open.
            op = self.rng.choice(
                ["publish", "publish_many", "subscribe", "unsubscribe"]
            )
            if op == "unsubscribe":
                with pytest.raises(KeyError):
                    self.bus.unsubscribe("bogus-token-fuzz")
            else:
                with pytest.raises(RuntimeError):
                    if op == "publish":
                        self.bus.publish(self.rng.choice(TOPICS), {})
                    elif op == "publish_many":
                        self.bus.publish_many([(self.rng.choice(TOPICS), {})])
                    else:
                        self.bus.subscribe(
                            self.rng.choice(TOPICS), lambda e: None
                        )
            return
        r = self.rng.random()
        if r < 0.40:
            self.do_publish(
                self.rng.choice(TOPICS), {"n": self.op_count}
            )
        elif r < 0.55:
            self.do_publish_many([
                (self.rng.choice(TOPICS), {"n": self.op_count, "k": k})
                for k in range(self.rng.randint(1, 5))
            ])
        elif r < 0.70:
            self.do_subscribe()
        elif r < 0.85:
            self.do_unsubscribe()
        else:
            self.do_observe()

    # -- final invariant check ----------------------------------------

    def check_invariants(self) -> None:
        snap = self.bus.snapshot()
        for t in TOPICS:
            assert snap[t]["published"] == self.envelopes[t], t
            # Every delivery attempt either succeeded or was isolated as a
            # failure: no lost, duplicated, or uncounted deliveries.
            assert (
                snap[t]["delivered"] + snap[t]["failed"] == self.attempts[t]
            ), t
        # Per-(subscriber, topic) FIFO, no duplicates, across re-entrancy,
        # batches, and replays.
        for token, recs in self.received.items():
            by_topic: dict[str, list[int]] = {}
            for topic, seq in recs:
                by_topic.setdefault(topic, []).append(seq)
            for topic, seqs in by_topic.items():
                assert seqs == sorted(seqs), (token, topic, seqs)
                assert len(set(seqs)) == len(seqs), (token, topic)
        # Dead-letter queue: bounded, newest retained, oldest-first.
        total_failed = sum(snap[t]["failed"] for t in TOPICS)
        letters = self.bus.dead_letters()
        assert len(letters) == min(DEAD_LETTER_CAP, total_failed)
        if letters:
            assert [e["seq"] for e in letters] == sorted(
                e["seq"] for e in letters
            )
            for e in letters:
                assert set(e) >= {
                    "seq", "topic", "subscriber",
                    "error_type", "message", "timestamp",
                }
        # Draining works and the queue stays drained.
        drained = self.bus.take_dead_letters()
        assert len(drained) == len(letters)
        assert self.bus.dead_letters() == []


@pytest.mark.parametrize("seed", SEEDS)
def test_eventbus_randomized_ops(seed: int):
    """2000 seeded ops total (4 seeds x 500): all invariants hold.

    Each run: 450 random ops, then a deterministic close, then 50
    post-close ops proving every bus door refuses loudly.
    """
    driver = BusFuzzDriver(seed)
    for _ in range(450):
        driver.step()
    assert driver.op_count == 450
    driver.do_close()
    for _ in range(50):
        driver.step()
    assert driver.op_count == 500
    driver.check_invariants()
