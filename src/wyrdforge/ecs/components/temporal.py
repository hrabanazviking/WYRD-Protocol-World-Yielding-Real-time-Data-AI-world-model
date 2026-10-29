"""Temporal ECS components — time awareness for the WYRD world model.

A world model without time is a photograph; with time it becomes a saga.
These components give every entity and event a place in world-time, using
the three threads of wyrd:

- **Urðr** — that which has become (past: the anchor ended before now)
- **Verðandi** — that which is becoming (present: the anchor holds now)
- **Skuld** — that which shall become (future: the anchor begins after now)

Design rules:
- The :class:`WorldClock` is the world's "now". By default it is
  deterministic and advance-only: systems move it per tick and nothing
  inside the simulation reads wall-clock time (Phase B5 keeps this as
  the default, byte-identical for existing callers).
- A live world may instead opt the clock into **wall-sync mode**
  (Phase B5): the clock anchors world-time to wall time under the
  drift policy stated on :class:`WorldClock`. The mode is explicit —
  a clock is in exactly one mode, and entering/leaving sync mode is
  an API call, never a side effect.
- Anchors carry validity windows (``valid_from`` / ``valid_until``), so
  the oracle can answer "what is true *now*" versus "what was true *then*".
- Fully deterministic in deterministic mode and ECS-compatible — no
  LLM involvement.
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import ClassVar, Literal

from pydantic import Field, PrivateAttr, model_validator

from wyrdforge.ecs.component import Component, register_component
from wyrdforge.models.common import StrictModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


Tense = Literal["urdhr", "verdhandi", "skuld"]

ClockMode = Literal["deterministic", "wall"]

# A wall-clock source: a zero-argument callable returning "now" as a
# datetime. The production source is ``datetime.now(timezone.utc)``
# (via ``_now``); tests inject a fake so no test ever sleeps.
WallClockSource = Callable[[], datetime]


@register_component
class TemporalAnchorComponent(Component):
    """Anchors an entity, fact, or event in world-time.

    Attributes:
        valid_from:  World-time from which this truth holds.
        valid_until: World-time until which it holds. ``None`` = open-ended
                     (still true as far as the world knows).
        observed_at: World-time when the world learned of it (distinct from
                     when it became true — a saga can learn of the past late).
        label:      Short human tag, e.g. "reign of King Hrolf".
    """

    _type_key: ClassVar[str] = "temporal_anchor"
    component_type: Literal["temporal_anchor"] = "temporal_anchor"

    valid_from: datetime = Field(default_factory=_now)
    valid_until: datetime | None = None
    observed_at: datetime = Field(default_factory=_now)
    label: str = ""

    def is_current(self, now: datetime) -> bool:
        """True when this anchor holds at world-time ``now``."""
        if self.valid_from > now:
            return False
        if self.valid_until is not None and self.valid_until <= now:
            return False
        return True

    def has_expired(self, now: datetime) -> bool:
        """True when the anchor's truth has fully passed."""
        return self.valid_until is not None and self.valid_until <= now

    def tense_at(self, now: datetime) -> Tense:
        """Which thread of wyrd this anchor sits on at world-time ``now``."""
        if self.valid_from > now:
            return "skuld"
        if self.has_expired(now):
            return "urdhr"
        return "verdhandi"

    def duration(self) -> timedelta | None:
        """How long the truth holds, or None if open-ended."""
        if self.valid_until is None:
            return None
        return self.valid_until - self.valid_from


class WorldClock(StrictModel):
    """World-time, in one of two modes.

    **Deterministic mode** (``mode="deterministic"``, the default —
    the pre-B5 behaviour, unchanged): ``now`` moves only when a system
    calls :meth:`advance`. Nothing reads the wall clock.

    **Wall-sync mode** (``mode="wall"``, Phase B5, opt-in via
    :meth:`enable_wall_sync`): world-time is anchored to wall time.

    Drift policy (the stated contract of wall-sync mode):

    - **Anchor math.** The clock stores an anchor pair
      (``anchor_world``, ``anchor_wall``) and a ``rate``. World-time
      is ``anchor_world + (wall_now - anchor_wall) * rate``. With the
      default ``rate=1.0`` world-time tracks wall time one-to-one;
      ``rate`` scales elapsed wall time (2.0 = world runs twice as
      fast) and is validated ``> 0``.
    - **Drift.** There is no periodic correction and no second
      opinion: between anchors, world-time inherits the wall clock's
      own accuracy and drift exactly (scaled by ``rate``).
      :meth:`reanchor` re-bases the anchor pair at the *current*
      computed world-time, discarding accumulated offset error
      without moving ``now``.
    - **Backwards movement.** World-time never moves backwards
      silently. A wall clock that jumps backwards (NTP step, manual
      change) does not rewind the world: the computed time is
      clamped at the highest value the clock has handed out (the
      cached ``now`` is the high-water mark), so world-time freezes
      until the wall catches up. A wall jump *forwards* moves the
      world forwards with it — that is what sync means. The only
      ways world-time moves backwards are the explicit re-anchor
      APIs a caller must name: :meth:`set` and
      ``enable_wall_sync(at_world=...)``.
    - **``advance()`` in wall-sync mode raises** ``ValueError``:
      wall elapsed time already moves the clock, so an explicit
      advance would double-count. Use :meth:`sync` to refresh, or
      :meth:`set` / :meth:`reanchor` to move the anchor on purpose.
    - **Save / load / restart.** ``mode``, ``rate``, both anchors and
      ``now`` are plain model fields, so they round-trip through
      ``model_dump`` / ``model_validate`` (JSON included). The wall
      *source* is code, not data, and is never serialised: after a
      restore the real wall clock applies until
      :meth:`set_wall_source` re-injects one. Because the anchors
      persist, **downtime counts**: the first :meth:`sync` after a
      restore advances world-time by all the wall time that passed
      while the process was down. A deployment that wants the world
      frozen across a restart instead calls
      :meth:`disable_wall_sync` before saving, or :meth:`set` after
      loading — that is a caller's stated choice, never a surprise.
    - **Pull-based; no threads.** The clock spawns nothing. In
      wall-sync mode the ``now`` field is the last-synced cache (and
      the monotonic high-water mark); :meth:`current_time` computes
      the fresh value without storing it and :meth:`sync` computes,
      stores, and returns it. Callers pull — e.g.
      ``CognitionSystem.tick`` syncs a wall-mode clock instead of
      advancing it.
    - **Thread-safety (B1 discipline).** All public methods serialise
      on one internal ``RLock``; a shared clock can be read and
      synced from many threads and every handed-out value is
      monotonic. The wall source is invoked *under* that lock, so a
      source must be cheap and must not call back into the clock.
    - **Wall readings.** A source returning a naive datetime is read
      as UTC (the engine's house timezone); the default source
      returns an aware UTC datetime.
    """

    now: datetime = Field(default_factory=_now)
    mode: ClockMode = "deterministic"
    rate: float = Field(default=1.0, gt=0.0)
    anchor_world: datetime | None = None
    anchor_wall: datetime | None = None

    _wall_source: WallClockSource | None = PrivateAttr(default=None)
    _lock: threading.RLock = PrivateAttr(default_factory=threading.RLock)

    @model_validator(mode="after")
    def _check_anchor_coherence(self) -> WorldClock:
        """Mode and anchors must agree: wall mode is anchored, the
        deterministic mode carries no anchors. Entering wall mode is
        :meth:`enable_wall_sync`'s job, not a bare field assignment
        that forgot the anchors."""
        if self.mode == "wall" and (self.anchor_world is None or self.anchor_wall is None):
            raise ValueError(
                "wall-sync mode requires anchor_world and anchor_wall; "
                "use enable_wall_sync() to enter it")
        if self.mode == "deterministic" and (
            self.anchor_world is not None or self.anchor_wall is not None
        ):
            raise ValueError("deterministic mode carries no wall anchors")
        return self

    # -- wall source ---------------------------------------------------

    def set_wall_source(self, source: WallClockSource | None) -> None:
        """Inject the wall-clock source (tests: a fake clock).

        ``None`` restores the real wall clock
        (``datetime.now(timezone.utc)``). The source is never
        serialised; a restored clock uses the real wall clock until
        a source is re-injected."""
        with self._lock:
            self._wall_source = source

    def _wall_reading(self) -> datetime:
        """One reading from the wall source, normalised to aware UTC
        when the source returned a naive datetime (read as UTC)."""
        source = self._wall_source if self._wall_source is not None else _now
        reading = source()
        if reading.tzinfo is None:
            reading = reading.replace(tzinfo=timezone.utc)
        return reading

    # -- mode queries ----------------------------------------------------

    @property
    def is_wall_synced(self) -> bool:
        """True when the clock is in wall-sync mode."""
        return self.mode == "wall"

    def _computed_wall_now(self) -> datetime:
        """The wall-sync formula against one fresh wall reading,
        clamped at the high-water mark. Caller holds ``_lock`` and
        the clock is in wall mode."""
        assert self.anchor_world is not None and self.anchor_wall is not None
        elapsed = (self._wall_reading() - self.anchor_wall).total_seconds()
        candidate = self.anchor_world + timedelta(seconds=elapsed * self.rate)
        # Monotonic clamp: a backwards wall jump freezes world-time
        # at the high-water mark instead of rewinding it.
        return candidate if candidate > self.now else self.now

    def current_time(self) -> datetime:
        """The world's current time, computed fresh.

        Deterministic mode: returns ``now``. Wall-sync mode: applies
        the anchor formula to a fresh wall reading (monotonic-clamped)
        WITHOUT storing it — ``now`` keeps its last-synced value."""
        with self._lock:
            if self.mode == "wall":
                return self._computed_wall_now()
            return self.now

    def sync(self) -> datetime:
        """Refresh ``now`` from the mode's source and return it.

        Wall-sync mode: ``now`` becomes the freshly computed
        (monotonic-clamped) wall-anchored time — this is how elapsed
        wall time, including process downtime, enters the world.
        Deterministic mode: a no-op returning ``now`` (nothing to
        sync to)."""
        with self._lock:
            if self.mode == "wall":
                self.now = self._computed_wall_now()
            return self.now

    # -- mode transitions -----------------------------------------------

    def enable_wall_sync(
        self,
        *,
        at_world: datetime | None = None,
        rate: float | None = None,
        wall_source: WallClockSource | None = None,
    ) -> datetime:
        """Enter (or re-enter) wall-sync mode and return world-now.

        The anchor pair is set to (``at_world`` or the clock's
        current time, one wall reading taken now). With no
        ``at_world`` the transition is continuous — world-time does
        not jump; naming an ``at_world`` in the past is an explicit
        re-anchor and the one sanctioned way this method moves
        world-time backwards. ``rate`` (must be > 0) replaces the
        scale; ``wall_source`` injects the wall source (see
        :meth:`set_wall_source`)."""
        with self._lock:
            if wall_source is not None:
                self._wall_source = wall_source
            if rate is not None:
                if rate <= 0:
                    raise ValueError("WorldClock rate must be > 0")
                self.rate = rate
            base = self._computed_wall_now() if self.mode == "wall" else self.now
            self.anchor_wall = self._wall_reading()
            self.anchor_world = at_world if at_world is not None else base
            self.mode = "wall"
            self.now = self.anchor_world
            return self.now

    def disable_wall_sync(self) -> datetime:
        """Leave wall-sync mode, freezing world-time where it is.

        The freshly computed wall time is stored into ``now``, the
        anchors are cleared, and the clock is deterministic from
        here: it moves only via :meth:`advance` / :meth:`set`.
        In deterministic mode this is a no-op returning ``now``."""
        with self._lock:
            if self.mode == "wall":
                self.now = self._computed_wall_now()
                self.mode = "deterministic"
                self.anchor_world = None
                self.anchor_wall = None
            return self.now

    def reanchor(self) -> datetime:
        """Re-base the wall anchor at the current computed time.

        Discards any accumulated offset/drift error without moving
        world-time: afterwards ``anchor_world`` is the current
        world-time and ``anchor_wall`` is a fresh wall reading.
        Wall-sync mode only."""
        with self._lock:
            if self.mode != "wall":
                raise ValueError(
                    "reanchor() requires wall-sync mode; a deterministic "
                    "clock has no wall anchor")
            current = self._computed_wall_now()
            self.anchor_world = current
            self.anchor_wall = self._wall_reading()
            self.now = current
            return self.now

    @classmethod
    def wall_synced(
        cls,
        *,
        at_world: datetime | None = None,
        rate: float = 1.0,
        wall_source: WallClockSource | None = None,
    ) -> WorldClock:
        """Build a clock already in wall-sync mode.

        ``at_world`` is the world-time the anchor starts from
        (default: the real wall time at construction)."""
        clock = cls(now=at_world) if at_world is not None else cls()
        clock.enable_wall_sync(rate=rate, wall_source=wall_source)
        return clock

    # -- deterministic movement ------------------------------------------

    def advance(self, seconds: float) -> datetime:
        """Move world-time forward. Negative deltas are rejected: wyrd does
        not rewind — to revisit the past, query anchors, don't move the clock.

        Deterministic mode only: in wall-sync mode wall elapsed time
        already moves the clock, so advancing would double-count —
        the call raises ``ValueError`` (see the class drift policy)."""
        with self._lock:
            if self.mode == "wall":
                raise ValueError(
                    "WorldClock is in wall-sync mode: world time is driven "
                    "by the wall clock — call sync() to refresh it, or set() "
                    "/ reanchor() to move the anchor explicitly; advance() "
                    "is deterministic-mode only")
            if seconds < 0:
                raise ValueError("WorldClock cannot rewind; query TemporalAnchors for the past")
            self.now = self.now + timedelta(seconds=seconds)
            return self.now

    def set(self, when: datetime) -> datetime:
        """Set world-time explicitly (scenario setup / save-load only).

        In wall-sync mode this is an explicit re-anchor: the anchor
        pair becomes (``when``, a fresh wall reading), so subsequent
        syncs track the wall from ``when``. It may move world-time
        backwards — deliberately, by the caller's named act, never
        as a silent side effect of wall movement."""
        with self._lock:
            if self.mode == "wall":
                self.anchor_world = when
                self.anchor_wall = self._wall_reading()
            self.now = when
            return self.now


def current_anchors(anchors: list[TemporalAnchorComponent], now: datetime) -> list[TemporalAnchorComponent]:
    """Return only the anchors that hold at world-time ``now``."""
    return [a for a in anchors if a.is_current(now)]
