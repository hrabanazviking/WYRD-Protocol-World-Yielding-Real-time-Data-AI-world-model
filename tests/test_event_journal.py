"""Phase B4 — durable event journal pinning tests.

Before B4 the EventBus's two histories were volatile: the replay ring
buffers and the dead-letter queue lived in memory only, so a restart
erased what happened and what failed (roadmap §2.4/§2.6). These tests
pin the new contract:

(a) append-only journaling with monotonic ``journal_seq`` and the
    bus's own ``seq`` preserved; kind classification
    (observation/fact/event);
(b) persistence across close/reopen — journal entries AND dead
    letters survive a restart, and survive ``EventBus.close()``
    clearing the in-memory queue;
(c) durable dead-letter summary/drain semantics matching the bus's;
(d) replay reconstruction — ``reconstruct_snapshot`` folds the
    journal exactly (whole, mid-stream prefix, after reopen);
    ``replay_to_bus`` rebuilds downstream projections (the
    ReplayPersistenceBridge's record set) through a fresh bus;
(e) journaling OFF (the default) = zero behaviour change;
(f) journal write failure is isolated — publish/delivery unaffected,
    failure counted, never raised;
(g) no deadlock with a re-entering subscriber (journal flushes
    outside the bus lock); ordering/completeness under concurrent
    publishers;
(h) ReplayPersistenceBridge interplay — both active at once, each
    envelope recorded exactly once in each store (disjoint stores,
    no double-record).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from wyrdforge.persistence.event_journal import EventJournal
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.runtime.events import EventBus, EventEnvelope
from wyrdforge.services.bus_consumers import ReplayPersistenceBridge

TOPIC_A = "world.entity_created"
TOPIC_B = "turn.completed"


def _journal(tmp_path: Path, name: str = "journal.db") -> EventJournal:
    return EventJournal(tmp_path / name)


def _bus_with_journal(journal: EventJournal) -> EventBus:
    bus = EventBus(journal=journal)
    bus.register_topic(TOPIC_A)
    bus.register_topic(TOPIC_B)
    bus.register_topic("memory.observation_added")
    bus.register_topic("memory.fact_added")
    return bus


# ---------------------------------------------------------------------------
# (a) Append + sequence monotonicity + classification
# ---------------------------------------------------------------------------


def test_append_assigns_monotonic_journal_seq_and_preserves_bus_seq(tmp_path):
    journal = _journal(tmp_path)
    bus = _bus_with_journal(journal)
    for i in range(5):
        bus.publish(TOPIC_A, {"idx": i}, source="test")
    bus.publish(TOPIC_B, {"idx": 99})
    entries = journal.entries()
    assert [e.journal_seq for e in entries] == [1, 2, 3, 4, 5, 6]
    assert [e.bus_seq for e in entries] == [1, 2, 3, 4, 5, 6]
    assert [e.payload["idx"] for e in entries] == [0, 1, 2, 3, 4, 99]
    assert journal.count() == 6
    assert journal.latest_journal_seq() == 6
    # Verbatim envelope round-trip.
    env = entries[0].to_envelope()
    assert isinstance(env, EventEnvelope)
    assert env.topic == TOPIC_A and env.seq == 1 and env.source == "test"


def test_kind_classification_observation_fact_event(tmp_path):
    journal = _journal(tmp_path)
    bus = _bus_with_journal(journal)
    bus.publish("memory.observation_added", {"record_id": "r1"})
    bus.publish("memory.fact_added", {"record_id": "f1"})
    bus.publish(TOPIC_A, {"entity_id": "e1"})
    kinds = {e.topic: e.kind for e in journal.entries()}
    assert kinds["memory.observation_added"] == "observation"
    assert kinds["memory.fact_added"] == "fact"
    assert kinds[TOPIC_A] == "event"


def test_direct_append_and_append_many(tmp_path):
    journal = _journal(tmp_path)
    env = EventEnvelope(topic=TOPIC_A, payload={"x": 1}, seq=7, source="direct")
    seq = journal.append(env)
    assert seq == 1
    seqs = journal.append_many(
        [EventEnvelope(topic=TOPIC_B, payload={"x": i}, seq=10 + i) for i in range(3)]
    )
    assert seqs == [2, 3, 4]
    entries = journal.entries(topic=TOPIC_B)
    assert [e.bus_seq for e in entries] == [10, 11, 12]
    windowed = journal.entries(after_journal_seq=1, through_journal_seq=3)
    assert [e.journal_seq for e in windowed] == [2, 3]


def test_publish_many_is_journaled_in_order(tmp_path):
    journal = _journal(tmp_path)
    bus = _bus_with_journal(journal)
    bus.publish_many([(TOPIC_A, {"i": 0}), (TOPIC_B, {"i": 1}), (TOPIC_A, {"i": 2})])
    entries = journal.entries()
    assert [e.topic for e in entries] == [TOPIC_A, TOPIC_B, TOPIC_A]
    assert [e.bus_seq for e in entries] == [1, 2, 3]


# ---------------------------------------------------------------------------
# (b) Persistence across close/reopen; DLQ survives bus close
# ---------------------------------------------------------------------------


def test_journal_and_dead_letters_survive_reopen(tmp_path):
    path = tmp_path / "journal.db"
    journal = EventJournal(path)
    bus = _bus_with_journal(journal)

    def bad(env):
        raise RuntimeError("boom")

    bus.subscribe(TOPIC_A, bad)
    bus.publish(TOPIC_A, {"idx": 0})
    bus.publish(TOPIC_B, {"idx": 1})
    assert journal.count() == 2
    assert journal.dead_letter_count() == 1

    # "Restart": a brand-new journal object over the same file.
    reopened = EventJournal(path)
    assert reopened.count() == 2
    assert [e.payload["idx"] for e in reopened.entries()] == [0, 1]
    letters = reopened.dead_letters()
    assert len(letters) == 1
    assert letters[0]["topic"] == TOPIC_A
    assert letters[0]["error_type"] == "RuntimeError"
    assert letters[0]["seq"] == 1
    assert reopened.integrity_check()


def test_persisted_dead_letters_survive_bus_close(tmp_path):
    journal = _journal(tmp_path)
    bus = _bus_with_journal(journal)

    def bad(env):
        raise ValueError("nope")

    bus.subscribe(TOPIC_A, bad)
    bus.publish(TOPIC_A, {"idx": 0})
    assert len(bus.dead_letters()) == 1
    bus.close()
    # The in-memory queue is cleared by close(); the durable copy is not.
    assert bus.dead_letters() == []
    assert journal.dead_letter_count() == 1
    assert journal.dead_letter_summary() == {TOPIC_A: {"ValueError": 1}}


# ---------------------------------------------------------------------------
# (c) Durable DLQ summary / drain semantics
# ---------------------------------------------------------------------------


def test_dead_letter_summary_and_drain_match_bus_semantics(tmp_path):
    journal = _journal(tmp_path)
    bus = _bus_with_journal(journal)

    def bad(env):
        raise RuntimeError("x")

    bus.subscribe(TOPIC_A, bad)
    bus.subscribe(TOPIC_B, bad)
    bus.publish(TOPIC_A, {})
    bus.publish(TOPIC_A, {})
    bus.publish(TOPIC_B, {})
    # Summary is read-only on both surfaces and has the same shape.
    assert journal.dead_letter_summary() == bus.dead_letter_summary()
    assert journal.dead_letter_count() == 3
    assert journal.dead_letter_summary() == journal.dead_letter_summary()
    # Drain returns oldest first and removes — durably.
    drained = journal.take_dead_letters()
    assert [d["topic"] for d in drained] == [TOPIC_A, TOPIC_A, TOPIC_B]
    assert journal.dead_letter_count() == 0
    assert journal.take_dead_letters() == []
    reopened = EventJournal(journal.db_path)
    assert reopened.dead_letter_count() == 0  # the drain itself persisted
    # The bus's own in-memory queue is untouched by the journal drain.
    assert len(bus.dead_letters()) == 3


# ---------------------------------------------------------------------------
# (d) Replay reconstruction
# ---------------------------------------------------------------------------


def _record_stream(journal: EventJournal) -> EventBus:
    bus = _bus_with_journal(journal)
    bus.publish(TOPIC_A, {"idx": 0}, source="origin")
    bus.publish(TOPIC_B, {"idx": 1}, source="origin")
    bus.publish(TOPIC_A, {"idx": 2}, source="origin")
    bus.publish(TOPIC_A, {"idx": 3}, source="origin")
    return bus


def test_reconstruct_snapshot_whole_and_midstream(tmp_path):
    journal = _journal(tmp_path)
    _record_stream(journal)
    whole = journal.reconstruct_snapshot()
    assert whole.per_topic_counts == {TOPIC_A: 3, TOPIC_B: 1}
    assert whole.max_bus_seq == 4
    assert whole.latest_by_topic[TOPIC_A].payload == {"idx": 3}
    # Mid-stream: folding exactly the first two entries.
    mid = journal.reconstruct_snapshot(through_journal_seq=2)
    assert [e.journal_seq for e in mid.entries] == [1, 2]
    assert mid.per_topic_counts == {TOPIC_A: 1, TOPIC_B: 1}
    assert mid.latest_by_topic[TOPIC_A].payload == {"idx": 0}
    # The prefix snapshot equals a snapshot of a journal that only
    # ever recorded that prefix.
    other = _journal(tmp_path, "prefix.db")
    bus2 = _bus_with_journal(other)
    bus2.publish(TOPIC_A, {"idx": 0}, source="origin")
    bus2.publish(TOPIC_B, {"idx": 1}, source="origin")
    prefix = other.reconstruct_snapshot()
    # Cross-bus comparison excludes issued_at (each bus stamps its
    # own wall-clock time); topic/seq/payload/source are the record.
    def _identity(entries):
        return [
            (e.topic, e.bus_seq, e.payload, e.source) for e in entries
        ]

    assert _identity(mid.entries) == _identity(prefix.entries)
    assert mid.per_topic_counts == prefix.per_topic_counts


def test_reconstruct_snapshot_stable_across_reopen(tmp_path):
    journal = _journal(tmp_path)
    _record_stream(journal)
    before = journal.reconstruct_snapshot()
    reopened = EventJournal(journal.db_path)
    after = reopened.reconstruct_snapshot()
    assert [e.envelope for e in after.entries] == [e.envelope for e in before.entries]
    assert after.per_topic_counts == before.per_topic_counts
    assert after.max_bus_seq == before.max_bus_seq


def test_replay_to_bus_rebuilds_bridge_record_set(tmp_path):
    journal = _journal(tmp_path)
    bus = _bus_with_journal(journal)
    live_store = PersistentMemoryStore(tmp_path / "live.db", bus=None)
    bridge = ReplayPersistenceBridge(bus, live_store, [TOPIC_A])
    for i in range(4):
        bus.publish(TOPIC_A, {"idx": i, "note": f"event {i}"}, source="origin")
    bridge.close()
    live_obs = live_store.list_by_record_type("observation")
    assert len(live_obs) == 4

    # Replay the journal into a FRESH bus + bridge + store: the same
    # projection rebuilds itself through its normal subscription.
    fresh_bus = EventBus()
    fresh_store = PersistentMemoryStore(tmp_path / "fresh.db", bus=None)
    fresh_bridge = ReplayPersistenceBridge(fresh_bus, fresh_store, [TOPIC_A])
    report = journal.replay_to_bus(fresh_bus)
    fresh_bridge.close()
    assert report.replayed == 4
    fresh_obs = fresh_store.list_by_record_type("observation")
    assert len(fresh_obs) == 4
    # Same titles (topic+seq coincide: full unfiltered replay from
    # seq 1 into a fresh bus) and same payloads inside the summaries.
    assert [r.content.title for r in fresh_obs] == [r.content.title for r in live_obs]
    for fresh_rec, live_rec in zip(fresh_obs, live_obs):
        fresh_summary = json.loads(fresh_rec.content.summary)
        live_summary = json.loads(live_rec.content.summary)
        assert fresh_summary["topic"] == live_summary["topic"]
        assert fresh_summary["payload"] == live_summary["payload"]
        assert fresh_summary["source"] == live_summary["source"]


def test_replay_to_bus_window_and_topic_filter(tmp_path):
    journal = _journal(tmp_path)
    _record_stream(journal)
    target = EventBus()
    seen: list[EventEnvelope] = []
    target.register_topic(TOPIC_A)
    target.subscribe(TOPIC_A, seen.append)
    report = journal.replay_to_bus(target, topics=[TOPIC_A], through_journal_seq=3)
    assert report.replayed == 2
    assert [e.payload["idx"] for e in seen] == [0, 2]


# ---------------------------------------------------------------------------
# (e) Journaling off = zero behaviour change
# ---------------------------------------------------------------------------


def test_no_journal_bus_behaves_as_before(tmp_path):
    bus = EventBus()  # no journal: the default everywhere
    bus.register_topic(TOPIC_A)
    assert bus.journal is None
    assert bus.journal_status() == {
        "attached": False,
        "journaled": 0,
        "errors": 0,
        "pending": 0,
    }
    got: list[EventEnvelope] = []
    bus.subscribe(TOPIC_A, got.append)
    assert bus.publish(TOPIC_A, {"idx": 0}) == 1
    assert len(got) == 1
    assert bus.snapshot()[TOPIC_A]["published"] == 1
    # No journal file appears anywhere as a side effect.
    assert list(tmp_path.iterdir()) == []


def test_attach_and_detach_journal(tmp_path):
    journal = _journal(tmp_path)
    bus = EventBus()
    bus.register_topic(TOPIC_A)
    bus.publish(TOPIC_A, {"idx": 0})  # before attach: not journaled
    bus.attach_journal(journal)
    bus.publish(TOPIC_A, {"idx": 1})
    detached = bus.detach_journal()
    assert detached is journal
    bus.publish(TOPIC_A, {"idx": 2})  # after detach: not journaled
    assert [e.payload["idx"] for e in journal.entries()] == [1]
    assert bus.journal_status()["attached"] is False


# ---------------------------------------------------------------------------
# (f) Journal write failure isolation
# ---------------------------------------------------------------------------


class _FailingJournal:
    """A journal whose writes always raise (a dead disk, simulated)."""

    def append(self, envelope):
        raise OSError("disk on fire")

    def record_dead_letter(self, entry):
        raise OSError("disk on fire")


def test_journal_write_failure_never_breaks_publish(tmp_path):
    bus = EventBus(journal=_FailingJournal())
    bus.register_topic(TOPIC_A)
    got: list[EventEnvelope] = []
    bus.subscribe(TOPIC_A, got.append)

    def bad(env):
        raise RuntimeError("subscriber boom")

    bus.subscribe(TOPIC_A, bad)
    # One healthy + one failing subscriber: delivery count and the
    # publish return are exactly as without a journal.
    assert bus.publish(TOPIC_A, {"idx": 0}) == 1
    assert len(got) == 1
    status = bus.journal_status()
    assert status["attached"] is True
    assert status["journaled"] == 0
    # Two failures counted: the envelope append + the dead letter.
    assert status["errors"] == 2
    # In-memory surfaces are unaffected by the journal's failure.
    assert len(bus.dead_letters()) == 1


# ---------------------------------------------------------------------------
# (g) Re-entrancy + concurrency
# ---------------------------------------------------------------------------


def test_reentering_subscriber_with_journal_no_deadlock(tmp_path):
    journal = _journal(tmp_path)
    bus = _bus_with_journal(journal)
    seen: list[int] = []

    def republisher(env):
        seen.append(env.seq)
        if env.payload.get("idx", 0) < 2:
            # Re-entrant SAME-topic publish from inside delivery: the
            # bus defers it; the journal flush must not deadlock.
            bus.publish(TOPIC_A, {"idx": env.payload["idx"] + 1})

    bus.subscribe(TOPIC_A, republisher)
    bus.publish(TOPIC_A, {"idx": 0})
    assert seen == [1, 2, 3]
    # Outer + both deferred envelopes all journaled, in bus order.
    entries = journal.entries()
    assert [e.bus_seq for e in entries] == [1, 2, 3]
    assert [e.payload["idx"] for e in entries] == [0, 1, 2]


def test_concurrent_publishers_all_journaled_exactly_once(tmp_path):
    journal = _journal(tmp_path)
    bus = _bus_with_journal(journal)
    n_threads, per_thread = 8, 25
    barrier = threading.Barrier(n_threads)
    errors: list[BaseException] = []

    def worker(tid: int) -> None:
        try:
            barrier.wait(timeout=30)
            for i in range(per_thread):
                bus.publish(TOPIC_A, {"thread": tid, "i": i})
        except BaseException as exc:  # recorded, asserted below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not errors
    total = n_threads * per_thread
    assert journal.count() == total
    entries = journal.entries()
    # journal_seq is a contiguous 1..N (append-only, never reused) and
    # every bus seq in 1..N appears exactly once (none lost, none dup).
    assert [e.journal_seq for e in entries] == list(range(1, total + 1))
    assert sorted(e.bus_seq for e in entries) == list(range(1, total + 1))
    assert bus.journal_status()["errors"] == 0


# ---------------------------------------------------------------------------
# (h) ReplayPersistenceBridge interplay
# ---------------------------------------------------------------------------


def test_bridge_and_journal_both_active_no_double_record(tmp_path):
    journal = _journal(tmp_path)
    bus = _bus_with_journal(journal)
    store = PersistentMemoryStore(tmp_path / "mem.db", bus=None)
    bridge = ReplayPersistenceBridge(bus, store, [TOPIC_A])
    for i in range(3):
        bus.publish(TOPIC_A, {"idx": i})
    bridge.close()
    # Disjoint stores: exactly one journal entry AND exactly one
    # bridge observation per envelope — neither path double-records.
    assert journal.count(topic=TOPIC_A) == 3
    obs = store.list_by_record_type("observation")
    assert len(obs) == 3
    assert bridge.seen_count == 3
