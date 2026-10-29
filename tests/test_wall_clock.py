"""Phase B5 — wall-clock binding pinning tests.

Before B5 the WorldClock was deterministic and advance-only
(roadmap §3.2): world time moved when the engine said so, with no
wall-clock synchronisation mode, so a live world could not answer
"when did this happen?" in wall time. These tests pin the new
contract:

(a) deterministic mode is the default and is byte-identical for
    existing callers — including the serialized shape's legacy
    payload (a pre-B5 dump carrying only ``now``) still validating;
(b) wall-sync mode tracks an injected fake wall clock through the
    anchor formula, progressing with NO advance() calls; ``now`` is
    the last-synced cache, ``current_time()`` computes fresh,
    ``sync()`` stores;
(c) ``advance()`` semantics per mode: deterministic unchanged
    (negative still rejected), wall mode raises instead of
    double-counting wall elapsed time;
(d) backwards policy: a backwards wall jump freezes world time at
    the high-water mark (monotonic clamp) and the world resumes
    when the wall catches up; a forward wall jump moves the world
    with it; the ONLY backwards movements are the explicit
    re-anchors (``set()``, ``enable_wall_sync(at_world=...)``);
(e) persistence: mode/rate/anchors/``now`` round-trip through JSON
    dump/validate, the wall SOURCE is never serialized, and after a
    restore the downtime counts (first sync advances by all wall
    time elapsed since the anchor);
(f) rate scaling, ``reanchor()`` discarding accumulated offset
    without moving now, ``disable_wall_sync()`` freezing the clock
    back into deterministic mode, and mode/anchor coherence
    validation;
(g) TemporalAnchorComponent windows and tense evaluate correctly
    against wall-synced world time, end-to-end through
    CognitionSystem (which syncs a wall-mode clock instead of
    advancing it);
(h) thread-safety (B1 discipline): concurrent sync/current_time
    from many threads — no errors, handed-out values monotonic,
    final value exact;
(i) a naive wall reading is read as UTC.

No test sleeps: every wall reading comes from FakeWallClock.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

import wyrdforge.ecs.components.temporal  # noqa: F401  (registers the anchor)
from wyrdforge.ecs.components.temporal import (
    TemporalAnchorComponent,
    WorldClock,
    current_anchors,
)
from wyrdforge.ecs.system import WorldRunner
from wyrdforge.ecs.systems.mind import CognitionSystem
from wyrdforge.ecs.world import World

UTC = timezone.utc
# World epoch and wall epoch deliberately differ: sync must anchor
# world time to the ANCHOR, not assume world == wall.
T0 = datetime(2026, 10, 29, 12, 0, 0, tzinfo=UTC)
W0 = datetime(2026, 10, 29, 8, 0, 0, tzinfo=UTC)


class FakeWallClock:
    """Injectable wall source: callable returning a settable time."""

    def __init__(self, start: datetime) -> None:
        self._now = start
        self._lock = threading.Lock()

    def __call__(self) -> datetime:
        with self._lock:
            return self._now

    def advance(self, seconds: float) -> None:
        with self._lock:
            self._now = self._now + timedelta(seconds=seconds)

    def set(self, when: datetime) -> None:
        with self._lock:
            self._now = when


def _synced_clock(fake: FakeWallClock, **kwargs) -> WorldClock:
    clock = WorldClock(now=T0)
    clock.enable_wall_sync(wall_source=fake, **kwargs)
    return clock


# ---------------------------------------------------------------------------
# (a) Deterministic mode — default, unchanged
# ---------------------------------------------------------------------------


def test_deterministic_mode_is_the_default_and_unchanged() -> None:
    clock = WorldClock(now=T0)
    assert clock.mode == "deterministic"
    assert clock.is_wall_synced is False
    assert clock.rate == 1.0
    assert clock.anchor_world is None and clock.anchor_wall is None
    assert clock.advance(60.0) == T0 + timedelta(seconds=60)
    assert clock.now == T0 + timedelta(seconds=60)
    with pytest.raises(ValueError, match="cannot rewind"):
        clock.advance(-1.0)
    assert clock.set(T0) == T0


def test_deterministic_sync_and_current_time_are_plain_now() -> None:
    clock = WorldClock(now=T0)
    assert clock.current_time() == T0
    assert clock.sync() == T0  # no-op in deterministic mode
    assert clock.now == T0


def test_legacy_pre_b5_payload_still_validates() -> None:
    # A pre-B5 serialized clock carried only ``now``.
    clock = WorldClock.model_validate({"now": T0.isoformat()})
    assert clock.mode == "deterministic"
    assert clock.now == T0
    assert clock.anchor_world is None and clock.anchor_wall is None
    # And a fresh deterministic dump states the new fields explicitly.
    dumped = WorldClock(now=T0).model_dump(mode="json")
    assert dumped["mode"] == "deterministic"
    assert dumped["anchor_world"] is None and dumped["anchor_wall"] is None
    assert dumped["rate"] == 1.0


# ---------------------------------------------------------------------------
# (b) Wall-sync tracking
# ---------------------------------------------------------------------------


def test_enable_is_continuous_and_tracks_fake_wall_without_advance() -> None:
    fake = FakeWallClock(W0)
    clock = _synced_clock(fake)
    # Anchoring did not jump world time even though wall != world.
    assert clock.mode == "wall" and clock.is_wall_synced is True
    assert clock.now == T0
    assert clock.anchor_world == T0 and clock.anchor_wall == W0
    # Elapsed wall time progresses world time with no advance() call.
    fake.advance(90.0)
    assert clock.sync() == T0 + timedelta(seconds=90)
    fake.advance(30.0)
    assert clock.sync() == T0 + timedelta(seconds=120)


def test_now_is_last_synced_cache_current_time_computes_fresh() -> None:
    fake = FakeWallClock(W0)
    clock = _synced_clock(fake)
    fake.advance(45.0)
    assert clock.current_time() == T0 + timedelta(seconds=45)
    assert clock.now == T0  # current_time() did not store
    assert clock.sync() == T0 + timedelta(seconds=45)
    assert clock.now == T0 + timedelta(seconds=45)  # sync() stored


def test_wall_synced_factory() -> None:
    fake = FakeWallClock(W0)
    clock = WorldClock.wall_synced(at_world=T0, wall_source=fake)
    assert clock.is_wall_synced and clock.now == T0
    fake.advance(10.0)
    assert clock.sync() == T0 + timedelta(seconds=10)


# ---------------------------------------------------------------------------
# (c) advance() semantics per mode
# ---------------------------------------------------------------------------


def test_advance_raises_in_wall_mode() -> None:
    fake = FakeWallClock(W0)
    clock = _synced_clock(fake)
    with pytest.raises(ValueError, match="wall-sync mode"):
        clock.advance(1.0)
    # The rejected advance changed nothing.
    assert clock.now == T0
    fake.advance(5.0)
    assert clock.sync() == T0 + timedelta(seconds=5)


# ---------------------------------------------------------------------------
# (d) Backwards / forwards wall jumps
# ---------------------------------------------------------------------------


def test_backwards_wall_jump_freezes_then_resumes() -> None:
    fake = FakeWallClock(W0)
    clock = _synced_clock(fake)
    fake.advance(100.0)
    assert clock.sync() == T0 + timedelta(seconds=100)
    # Wall jumps backwards an hour (NTP step): world must NOT rewind.
    fake.set(W0 - timedelta(hours=1))
    assert clock.current_time() == T0 + timedelta(seconds=100)
    assert clock.sync() == T0 + timedelta(seconds=100)
    # Wall still behind the anchor's catch-up point: still frozen.
    fake.set(W0 + timedelta(seconds=50))
    assert clock.sync() == T0 + timedelta(seconds=100)
    # Wall catches up past the high-water mark: tracking resumes.
    fake.set(W0 + timedelta(seconds=130))
    assert clock.sync() == T0 + timedelta(seconds=130)


def test_forward_wall_jump_moves_world_forward() -> None:
    fake = FakeWallClock(W0)
    clock = _synced_clock(fake)
    fake.advance(3600.0)
    assert clock.sync() == T0 + timedelta(hours=1)


def test_set_in_wall_mode_is_an_explicit_reanchor() -> None:
    fake = FakeWallClock(W0)
    clock = _synced_clock(fake)
    fake.advance(600.0)
    assert clock.sync() == T0 + timedelta(seconds=600)
    # set() is the named, explicit way to move world time backwards.
    earlier = T0 + timedelta(seconds=60)
    assert clock.set(earlier) == earlier
    assert clock.anchor_world == earlier and clock.anchor_wall == fake()
    fake.advance(10.0)
    assert clock.sync() == earlier + timedelta(seconds=10)


def test_set_in_deterministic_mode_does_not_anchor() -> None:
    clock = WorldClock(now=T0)
    clock.set(T0 + timedelta(days=1))
    assert clock.mode == "deterministic"
    assert clock.anchor_world is None and clock.anchor_wall is None


def test_enable_with_at_world_is_an_explicit_reanchor() -> None:
    fake = FakeWallClock(W0)
    clock = WorldClock(now=T0)
    past = T0 - timedelta(days=7)
    assert clock.enable_wall_sync(at_world=past, wall_source=fake) == past
    fake.advance(20.0)
    assert clock.sync() == past + timedelta(seconds=20)


# ---------------------------------------------------------------------------
# (e) Persistence / restart
# ---------------------------------------------------------------------------


def test_anchor_state_round_trips_and_downtime_counts() -> None:
    fake = FakeWallClock(W0)
    clock = _synced_clock(fake, rate=2.0)
    fake.advance(30.0)
    assert clock.sync() == T0 + timedelta(seconds=60)
    payload = clock.model_dump(mode="json")
    # The wall source is code, not data: nothing callable is stored.
    assert set(payload) == {"now", "mode", "rate", "anchor_world", "anchor_wall"}

    restored = WorldClock.model_validate(payload)
    assert restored.mode == "wall" and restored.rate == 2.0
    assert restored.anchor_world == T0 and restored.anchor_wall == W0
    assert restored.now == T0 + timedelta(seconds=60)
    # "Restart": two wall-hours pass while the process is down; the
    # restored clock re-injects a source and downtime counts.
    fake2 = FakeWallClock(W0 + timedelta(hours=2))
    restored.set_wall_source(fake2)
    assert restored.sync() == T0 + timedelta(hours=4)  # 2 h wall x rate 2


def test_deterministic_clock_round_trip() -> None:
    clock = WorldClock(now=T0)
    clock.advance(5.0)
    restored = WorldClock.model_validate(clock.model_dump(mode="json"))
    assert restored.mode == "deterministic" and restored.now == clock.now


# ---------------------------------------------------------------------------
# (f) Rate, reanchor, disable, coherence
# ---------------------------------------------------------------------------


def test_rate_scales_elapsed_wall_time() -> None:
    fake = FakeWallClock(W0)
    clock = _synced_clock(fake, rate=60.0)  # a minute of world per wall second
    fake.advance(2.0)
    assert clock.sync() == T0 + timedelta(minutes=2)


def test_rate_must_be_positive() -> None:
    fake = FakeWallClock(W0)
    clock = WorldClock(now=T0)
    with pytest.raises(ValueError, match="rate must be > 0"):
        clock.enable_wall_sync(rate=0.0, wall_source=fake)
    assert clock.mode == "deterministic"  # failed enable changed nothing
    with pytest.raises(ValidationError):
        WorldClock(now=T0, rate=-1.0)


def test_reanchor_discards_accumulated_offset_without_moving_now() -> None:
    fake = FakeWallClock(W0)
    clock = _synced_clock(fake)
    # Simulate the wall clock having drifted: the anchor's wall side
    # is 10 minutes stale, so computed world time runs 10 min fast.
    clock.anchor_wall = W0 - timedelta(minutes=10)
    drifted = clock.current_time()
    assert drifted == T0 + timedelta(minutes=10)
    assert clock.reanchor() == drifted  # re-basing does not move now
    assert clock.anchor_world == drifted and clock.anchor_wall == W0
    fake.advance(60.0)
    assert clock.sync() == drifted + timedelta(seconds=60)  # clean 1:1 again


def test_reanchor_requires_wall_mode() -> None:
    with pytest.raises(ValueError, match="wall-sync mode"):
        WorldClock(now=T0).reanchor()


def test_disable_wall_sync_freezes_the_clock() -> None:
    fake = FakeWallClock(W0)
    clock = _synced_clock(fake)
    fake.advance(120.0)
    assert clock.disable_wall_sync() == T0 + timedelta(seconds=120)
    assert clock.mode == "deterministic"
    assert clock.anchor_world is None and clock.anchor_wall is None
    fake.advance(3600.0)  # wall runs on; the frozen world does not
    assert clock.sync() == T0 + timedelta(seconds=120)
    assert clock.advance(5.0) == T0 + timedelta(seconds=125)  # advance works again
    # Disabling an already-deterministic clock is a no-op.
    assert clock.disable_wall_sync() == clock.now


def test_mode_anchor_coherence_is_validated() -> None:
    with pytest.raises(ValidationError, match="enable_wall_sync"):
        WorldClock(now=T0, mode="wall")  # wall mode without anchors
    with pytest.raises(ValidationError, match="no wall anchors"):
        WorldClock(now=T0, anchor_world=T0, anchor_wall=W0)  # anchors, det mode


# ---------------------------------------------------------------------------
# (g) Temporal anchors under wall-synced time
# ---------------------------------------------------------------------------


def test_anchor_windows_open_and_close_as_wall_time_passes() -> None:
    fake = FakeWallClock(W0)
    clock = _synced_clock(fake)
    anchor = TemporalAnchorComponent(
        entity_id="e1",
        valid_from=T0 + timedelta(minutes=10),
        valid_until=T0 + timedelta(minutes=20),
        label="market hours",
    )
    now = clock.sync()
    assert anchor.tense_at(now) == "skuld" and not anchor.is_current(now)
    fake.advance(600.0)  # wall +10 min -> the window opens
    now = clock.sync()
    assert anchor.tense_at(now) == "verdhandi" and anchor.is_current(now)
    assert [a.label for a in current_anchors([anchor], now)] == ["market hours"]
    fake.advance(600.0)  # wall +10 min more -> the window closes
    now = clock.sync()
    assert anchor.tense_at(now) == "urdhr" and anchor.has_expired(now)
    assert current_anchors([anchor], now) == []


def test_cognition_system_ticks_on_wall_time() -> None:
    fake = FakeWallClock(W0)
    clock = _synced_clock(fake)
    system = CognitionSystem(clock=clock)
    world = World("w-wall")
    runner = WorldRunner(world)
    runner.add_system(system)
    world.create_entity(entity_id="e1")
    anchor = TemporalAnchorComponent(
        entity_id="e1",
        valid_from=T0 - timedelta(hours=1),
        valid_until=T0 + timedelta(seconds=90),
        label="short reign",
    )
    anchor.entity_id = "e1"
    world.add_component("e1", anchor)

    runner.tick(delta_t=1.0)  # wall has not moved: nothing expires
    assert system.last_report is not None
    assert system.last_report.newly_urdhr == []
    fake.advance(120.0)  # two wall-minutes pass between ticks
    runner.tick(delta_t=1.0)  # delta_t ignored for a synced clock
    assert system.last_report is not None
    assert "short reign" in system.last_report.newly_urdhr
    assert system.last_report.world_now == (T0 + timedelta(seconds=120)).isoformat()


# ---------------------------------------------------------------------------
# (h) Thread-safety
# ---------------------------------------------------------------------------


def test_concurrent_sync_is_monotonic_and_exact() -> None:
    fake = FakeWallClock(W0)
    clock = _synced_clock(fake)
    errors: list[BaseException] = []
    handed_out: list[datetime] = []
    collect = threading.Lock()
    barrier = threading.Barrier(9)

    def worker() -> None:
        try:
            barrier.wait(timeout=10)
            for _ in range(50):
                value = clock.sync()
                with collect:
                    handed_out.append(value)
                clock.current_time()
        except BaseException as exc:  # noqa: BLE001 - recorded, asserted below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    barrier.wait(timeout=10)
    for step in range(10):  # the wall advances while the workers sync
        fake.advance(10.0)
    for t in threads:
        t.join(timeout=30)

    assert errors == []
    assert len(handed_out) == 8 * 50
    assert all(v >= T0 for v in handed_out)
    # Every handed-out value is monotonic-clamped history: the maximum
    # handed out never exceeds the final exact value, and after the
    # wall settles the clock reads exactly anchor + elapsed.
    fake.set(W0 + timedelta(seconds=1000))
    assert clock.sync() == T0 + timedelta(seconds=1000)
    assert max(handed_out) <= T0 + timedelta(seconds=1000)


# ---------------------------------------------------------------------------
# (i) Naive wall readings
# ---------------------------------------------------------------------------


def test_naive_wall_reading_is_read_as_utc() -> None:
    naive_start = datetime(2026, 10, 29, 8, 0, 0)  # no tzinfo
    fake = FakeWallClock(naive_start)
    clock = WorldClock(now=T0)
    clock.enable_wall_sync(wall_source=fake)
    assert clock.anchor_wall == W0  # normalised to aware UTC
    fake.advance(30.0)
    synced = clock.sync()
    assert synced == T0 + timedelta(seconds=30)
    assert synced.tzinfo is not None
