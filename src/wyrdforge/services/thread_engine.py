"""ThreadEngine — the fate-weaving mutation service (Phase D4).

The companion to ``ecs/components/metaphysical.py``: components
carry the thread state, this engine performs the named acts —
weaving a thread between two entities, strengthening or charging
it, severing or fulfilling it, and decaying woven threads on a
tick — and announces each act on the EventBus.

The engine composes with the runic foundation
(``services/runic_engine.py``) rather than replacing it: weaving a
thread never touches an endpoint's Hamingja/RunicCharge/Ancestral
components, and runic state is read (by the Oracle) beside thread
state, never copied into it. The one deliberate coupling is at
weaving time: a caller may name the ``rune_name`` a thread is woven
under, recorded on the thread as a reference.

Event topics (house dotted convention, under ``wyrd.``)::

    wyrd.thread_woven       {thread_id, endpoint_ids, kind, strength, wyrd_charge, rune_name}
    wyrd.thread_adjusted    {thread_id, strength, wyrd_charge}
    wyrd.thread_severed     {thread_id, endpoint_ids, kind}
    wyrd.thread_fulfilled   {thread_id, endpoint_ids, kind, prophesied_event}

Bus posture follows the house (CombatEngine precedent): the engine
is bus-optional, registers its topics idempotently, and publishes
AFTER the state mutation — a failing bus never breaks thread
semantics. Severing and fulfilling are terminal transitions of the
component; because the status changes in the same act, a second
sever/fulfill raises (the engagement-lifecycle rule) and can never
emit a second terminal event.

Convergence detection (the Phase 7 plan's ``WyrdThreadSystem``
sketch) is a pure read here: :meth:`detect_convergences` returns
live threads whose derived fate pressure
(``strength * wyrd_charge``) meets the caller's threshold AND whose
endpoints are co-located (share a ``SpatialComponent`` location —
the containment truth; entities with no placement are never
co-located). It emits nothing and mutates nothing.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import wyrdforge.ecs.components.metaphysical  # noqa: F401  (registration)
import wyrdforge.ecs.components.spatial  # noqa: F401  (registration)
from wyrdforge.ecs.components.metaphysical import (
    DEFAULT_THREAD_DECAY_RATE,
    WyrdThreadComponent,
)
from wyrdforge.ecs.components.spatial import SpatialComponent
from wyrdforge.ecs.entity import _new_id
from wyrdforge.ecs.world import World

if TYPE_CHECKING:
    from wyrdforge.runtime.events import EventBus


def _now() -> datetime:
    return datetime.now(timezone.utc)


#: Default fate-pressure threshold for convergence detection.
DEFAULT_CONVERGENCE_THRESHOLD = 0.5

#: Topics emitted by ThreadEngine when wired to an EventBus.
THREAD_TOPICS = (
    "wyrd.thread_woven",
    "wyrd.thread_adjusted",
    "wyrd.thread_severed",
    "wyrd.thread_fulfilled",
)


def _register_thread_topics(bus: "EventBus") -> None:
    """Register the wyrd.* topics once; tolerate double registration."""
    for topic in THREAD_TOPICS:
        try:
            bus.register_topic(topic)
        except (ValueError, KeyError):
            pass  # already registered — another producer got here first


class ThreadEngine:
    """Deterministic mutation service for wyrd thread state.

    Args:
        world: The ECS World to operate on.
        bus:   Optional EventBus for wyrd.* announcements. When
               omitted, no announcements are made — pass a bus
               explicitly so announcement wiring is a stated choice
               (the CombatEngine rule).
    """

    def __init__(self, world: World, *, bus: "EventBus | None" = None) -> None:
        self._world = world
        self._bus = bus
        if self._bus is not None:
            _register_thread_topics(self._bus)

    @property
    def world(self) -> World:
        return self._world

    # ------------------------------------------------------------------
    # Weaving
    # ------------------------------------------------------------------

    def weave(
        self,
        entity_a: str,
        entity_b: str,
        *,
        kind: str = "",
        strength: float = 0.5,
        wyrd_charge: float = 0.0,
        decay_rate: float = DEFAULT_THREAD_DECAY_RATE,
        prophesied_event: str | None = None,
        description: str = "",
        rune_name: str | None = None,
        basis_event_ids: list[str] | None = None,
        at: datetime | None = None,
        thread_id: str | None = None,
    ) -> str:
        """Weave a new thread between two entities; return its id.

        Creates the thread entity (tagged ``wyrd_thread``) carrying
        the WyrdThreadComponent. Endpoints are NOT required to carry
        any runic component — the runic layer is the foundation a
        thread may rest on, not a gate. Weaving a second thread
        between the same pair is allowed (fate is not single-strand);
        each weaving is its own entity. Raises ValueError when the
        two endpoints are the same entity (the component's pair
        validator also refuses it).
        """
        if entity_a == entity_b:
            raise ValueError("a wyrd thread cannot connect an entity to itself")
        tid = thread_id or _new_id()
        woven = at if at is not None else _now()
        self._world.create_entity(entity_id=tid, tags={"wyrd_thread"})
        comp = WyrdThreadComponent(
            entity_id=tid,
            endpoint_ids=[entity_a, entity_b],
            kind=kind,
            strength=strength,
            wyrd_charge=wyrd_charge,
            decay_rate=decay_rate,
            prophesied_event=prophesied_event,
            description=description,
            rune_name=rune_name,
            basis_event_ids=list(basis_event_ids or []),
            woven_at=woven,
        )
        self._world.add_component(tid, comp)
        self._emit("wyrd.thread_woven", {
            "thread_id": tid,
            "endpoint_ids": list(comp.endpoint_ids),
            "kind": kind,
            "strength": comp.strength,
            "wyrd_charge": comp.wyrd_charge,
            "rune_name": rune_name,
        })
        return tid

    # ------------------------------------------------------------------
    # Adjustment — strength / charge on a live thread
    # ------------------------------------------------------------------

    def adjust(
        self,
        thread_id: str,
        *,
        strength_delta: float = 0.0,
        charge_delta: float = 0.0,
    ) -> WyrdThreadComponent:
        """Adjust a LIVE thread's strength and/or wyrd_charge.

        Both values clamp into [0.0, 1.0] (the component fields'
        own bounds). Adjusting a severed/fulfilled thread raises
        ValueError — history is not rewritten; weave a new thread.
        Emits ``wyrd.thread_adjusted`` with the resulting values.
        """
        comp = self._require_thread(thread_id)
        if not comp.is_live:
            raise ValueError(
                f"cannot adjust a {comp.status} thread ('{thread_id}') — weave a new one"
            )
        comp.strength = max(0.0, min(1.0, comp.strength + strength_delta))
        comp.wyrd_charge = max(0.0, min(1.0, comp.wyrd_charge + charge_delta))
        comp.touch()
        self._emit("wyrd.thread_adjusted", {
            "thread_id": thread_id,
            "strength": comp.strength,
            "wyrd_charge": comp.wyrd_charge,
        })
        return comp

    # ------------------------------------------------------------------
    # Terminal acts — sever / fulfill (each announces exactly once)
    # ------------------------------------------------------------------

    def sever(self, thread_id: str, *, at: datetime | None = None) -> WyrdThreadComponent:
        comp = self._require_thread(thread_id)
        comp.sever(at=at)  # raises on a terminal thread — no second event
        self._emit("wyrd.thread_severed", {
            "thread_id": thread_id,
            "endpoint_ids": list(comp.endpoint_ids),
            "kind": comp.kind,
        })
        return comp

    def fulfill(self, thread_id: str, *, at: datetime | None = None) -> WyrdThreadComponent:
        comp = self._require_thread(thread_id)
        comp.fulfill(at=at)  # raises on a terminal thread — no second event
        self._emit("wyrd.thread_fulfilled", {
            "thread_id": thread_id,
            "endpoint_ids": list(comp.endpoint_ids),
            "kind": comp.kind,
            "prophesied_event": comp.prophesied_event,
        })
        return comp

    # ------------------------------------------------------------------
    # Tick — strength decay for woven threads
    # ------------------------------------------------------------------

    def tick(self) -> list[str]:
        """Decay every LIVE thread's strength by its decay_rate.

        Returns the ids of threads whose strength changed, in
        entity_id order. Terminal threads do not decay (their final
        strength is their history), and a thread already at 0.0 is
        unchanged (dormant, not auto-severed — cutting a thread is a
        named act, never a tick side effect).
        """
        changed: list[str] = []
        pairs = [
            (entity, comp)
            for entity, comp in self._world.iter_components("wyrd_thread")
            if isinstance(comp, WyrdThreadComponent)
        ]
        for entity, comp in sorted(pairs, key=lambda pair: pair[0].entity_id):
            if not comp.is_live or comp.decay_rate == 0.0 or comp.strength == 0.0:
                continue
            comp.strength = max(0.0, comp.strength - comp.decay_rate)
            comp.touch()
            changed.append(entity.entity_id)
        return changed

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def threads_for(self, entity_id: str, *, live_only: bool = True) -> list[WyrdThreadComponent]:
        """Threads involving an entity, in thread_id order."""
        out: list[WyrdThreadComponent] = []
        for _entity, comp in self._world.iter_components("wyrd_thread"):
            if not isinstance(comp, WyrdThreadComponent):
                continue
            if not comp.involves(entity_id):
                continue
            if live_only and not comp.is_live:
                continue
            out.append(comp)
        out.sort(key=lambda c: c.entity_id)
        return out

    def threads_between(self, entity_a: str, entity_b: str, *, live_only: bool = True) -> list[WyrdThreadComponent]:
        """Threads connecting exactly this pair, in thread_id order."""
        return [
            comp for comp in self.threads_for(entity_a, live_only=live_only)
            if comp.other_endpoint(entity_a) == entity_b
        ]

    def detect_convergences(
        self, *, threshold: float = DEFAULT_CONVERGENCE_THRESHOLD
    ) -> list[WyrdThreadComponent]:
        """Live, co-located, high-pressure threads (plan §7.2 sketch).

        A convergence is a LIVE thread whose derived fate pressure
        (``strength * wyrd_charge``) is at or above ``threshold``
        AND whose endpoints share a location (``SpatialComponent``
        most-specific id, equal and non-None). Sorted by
        ``(-convergence_score, thread_id)`` — strongest pressure
        first, deterministic. Pure read: nothing is emitted or
        mutated.
        """
        if threshold < 0:
            raise ValueError(f"threshold must be non-negative, got {threshold}")
        found: list[WyrdThreadComponent] = []
        for _entity, comp in self._world.iter_components("wyrd_thread"):
            if not isinstance(comp, WyrdThreadComponent):
                continue
            if not comp.is_convergence(threshold):
                continue
            if self._co_located(comp.endpoint_ids[0], comp.endpoint_ids[1]):
                found.append(comp)
        found.sort(key=lambda c: (-c.convergence_score, c.entity_id))
        return found

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _co_located(self, entity_a: str, entity_b: str) -> bool:
        a = self._world.get_component(entity_a, "spatial")
        b = self._world.get_component(entity_b, "spatial")
        if not isinstance(a, SpatialComponent) or not isinstance(b, SpatialComponent):
            return False
        loc_a = a.most_specific_id()
        return loc_a is not None and loc_a == b.most_specific_id()

    def _require_thread(self, thread_id: str) -> WyrdThreadComponent:
        comp = self._world.get_component(thread_id, "wyrd_thread")
        if not isinstance(comp, WyrdThreadComponent):
            raise KeyError(f"entity '{thread_id}' is not a wyrd thread")
        return comp

    def _emit(self, topic: str, payload: dict) -> None:
        """Publish after mutation; a failing bus never breaks threads."""
        if self._bus is None:
            return
        try:
            self._bus.publish(topic, payload, source="thread.engine")
        except Exception:
            pass
