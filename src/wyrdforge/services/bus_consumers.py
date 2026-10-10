"""Rúnakefli — Inner-Communications Weave: bus consumers (dusk forge, 2026-10-10).

Slices 18 + 19. Consumers sit *downstream* of the EventBus: they subscribe to
topics and persist what they see into an unwired store. Both classes write
through an INTERNAL :class:`WritebackEngine` constructed with ``bus=None`` —
never over a bus-wired store. A wired store emits ``memory.observation_added``
/ ``memory.fact_added`` on every true insert (slice 14), so writing consumer
audit rows into one would feed the bus with new events on every observation
an event storm. Keep the audit store unwired: ``store._bus is None``.

Both consumers are subscription-only: they never publish, so bus trouble on
their side cannot disturb any producer. A raising handler is isolated by the
bus itself (dead letters); it never aborts delivery to healthy subscribers.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from wyrdforge.services.writeback_engine import WritebackEngine

if TYPE_CHECKING:
    from wyrdforge.runtime.events import EventBus, EventEnvelope
    from wyrdforge.persistence.memory_store import PersistentMemoryStore

log = logging.getLogger(__name__)

#: Slice 18 — the wildcard pattern the audit consumer listens on.
_CONTRADICTION_WILDCARD = "contradiction.*"

_AUDIT_TAGS = ["contradiction-audit"]


class ContradictionAuditConsumer:
    """Persist one audit observation per contradiction detection (slice 18).

    Subscribes to the wildcard ``"contradiction.*"`` and, for each event,
    writes an observation to the given store via an internal unwired
    :class:`WritebackEngine`:

    * ``title``: ``f"contradiction audit seq={env.seq}"``
    * ``summary``: carries the detection ``count``, ``fact_ids``, envelope
      ``seq`` and ``issued_at``
    * ``tags``: ``["contradiction-audit"]``

    The store MUST be unwired (``bus=None``) — see the module docstring.
    """

    def __init__(
        self, bus: "EventBus", store: "PersistentMemoryStore"
    ) -> None:
        self._bus = bus
        self._store = store
        # Internal engine is deliberately unwired: the store's own
        # memory.observation_added emissions must not feed back into the bus.
        self._engine = WritebackEngine(store)
        self._token: str | None = None
        self._detached = False
        self._token = bus.subscribe(_CONTRADICTION_WILDCARD, self._on_event)

    # -- subscription ----------------------------------------------------

    def _on_event(self, env: "EventEnvelope") -> None:
        payload = env.payload if isinstance(env.payload, dict) else {}
        count = payload.get("count")
        fact_ids = payload.get("fact_ids", [])
        self._engine.write_observation(
            title=f"contradiction audit seq={env.seq}",
            summary=(
                f"contradiction audit: count={count} fact_ids={fact_ids} "
                f"seq={env.seq} issued_at={env.issued_at} topic={env.topic}"
            ),
            observation_kind="utterance",
            confidence=0.9,
            tags=list(_AUDIT_TAGS),
        )

    def detach(self) -> None:
        """Unsubscribe; idempotent and safe to call after ``close()``."""
        if self._detached:
            return
        self._detached = True
        token, self._token = self._token, None
        if token is not None:
            try:
                self._bus.unsubscribe(token)
            except Exception:
                pass  # bus closed or token already gone — nothing to do

    def close(self) -> None:
        """Detach from the bus. Alias for :meth:`detach`."""
        self.detach()

    # -- introspection ----------------------------------------------------

    @property
    def store(self) -> "PersistentMemoryStore":
        return self._store

    @property
    def detached(self) -> bool:
        return self._detached

    def __enter__(self) -> "ContradictionAuditConsumer":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.detach()


class ReplayPersistenceBridge:
    """Persist buffered + live envelopes as observations (slice 19).

    For each topic in ``topics`` the bridge subscribes with ``replay=True``:
    every envelope already in that topic's replay buffer is backfilled first
    (FIFO by bus ``seq``), then live publishes flow in as they arrive.

    Each envelope is persisted once as an observation:

    * ``title``: ``f"replay {env.topic} seq={env.seq}"``
    * ``summary``: JSON of ``env.to_dict()``
    * ``tags``: ``["replay-persistence"]``

    A per-topic seen-seq set dedupes redeliveries within this bridge
    instance, so nothing is persisted twice (e.g. if the same envelope is
    both replayed and re-delivered live).

    Like the audit consumer, this bridge writes through an internal UNWIRED
    :class:`WritebackEngine` — the store must be ``bus=None`` wired to avoid
    feeding ``memory.*`` events back into the bus.
    """

    _TAGS = ["replay-persistence"]

    def __init__(
        self,
        bus: "EventBus",
        store: "PersistentMemoryStore",
        topics: list[str],
    ) -> None:
        self._bus = bus
        self._store = store
        # Deliberately unwired — see the module docstring.
        self._engine = WritebackEngine(store)
        self._topics = list(topics)
        self._seen: set[tuple[str, int]] = set()
        self._tokens: list[str] = []
        self._detached = False
        for topic in self._topics:
            try:
                bus.register_topic(topic)
            except ValueError:
                pass  # already registered (or invalid name — subscribe raises)
            self._tokens.append(bus.subscribe(topic, self._on_event, replay=True))

    # -- subscription ----------------------------------------------------

    def _on_event(self, env: "EventEnvelope") -> None:
        key = (env.topic, env.seq)
        if key in self._seen:
            return
        summary = json.dumps(env.to_dict(), sort_keys=True, default=str)
        self._engine.write_observation(
            title=f"replay {env.topic} seq={env.seq}",
            summary=summary,
            observation_kind="utterance",
            confidence=0.9,
            tags=list(self._TAGS),
        )
        self._seen.add(key)

    def detach(self) -> None:
        """Unsubscribe every topic; idempotent."""
        if self._detached:
            return
        self._detached = True
        tokens, self._tokens = self._tokens, []
        for token in tokens:
            try:
                self._bus.unsubscribe(token)
            except Exception:
                pass  # bus closed or token gone — nothing to do

    def close(self) -> None:
        """Detach from the bus. Alias for :meth:`detach`."""
        self.detach()

    # -- introspection ----------------------------------------------------

    @property
    def topics(self) -> list[str]:
        return list(self._topics)

    @property
    def seen_count(self) -> int:
        """Number of (topic, seq) pairs persisted so far."""
        return len(self._seen)

    @property
    def detached(self) -> bool:
        return self._detached

    def __enter__(self) -> "ReplayPersistenceBridge":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.detach()
