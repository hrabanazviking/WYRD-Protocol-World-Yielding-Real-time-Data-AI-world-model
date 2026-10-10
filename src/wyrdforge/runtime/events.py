"""Rúnakefli — Inner-Communications Weave: the EventBus (dusk forge, 2026-10-10).

A typed, thread-safe, in-process event fabric for wyrdforge. Producers opt in
via ``bus=`` keyword arguments; ``bus=None`` (the default everywhere) preserves
the exact old call-only behavior. (Slice list: core fabric = slices 1–10;
slice 20 adds the dead-letter monitoring surface.)

Guarantees:
* Topics are dotted names (``"world.entity_created"``) registered before use.
* Payloads are dicts, optionally validated against a pydantic model or
  dataclass registered per topic (violations → ``TypeError`` naming the topic).
* Delivery is synchronous, in subscription order (exact subscribers first, then
  wildcard subscribers, each in subscription order), and per-topic FIFO by the
  bus-scoped ``seq`` counter.
* One ``threading.RLock`` guards all mutable state; subscribers may
  publish / (un)subscribe re-entrantly.
* A raising subscriber is isolated: the error is logged, recorded in the
  internal failure list (``_take_failures``) and the bounded dead-letter queue
  (slice 6), and remaining subscribers still receive the event. ``publish()``
  returns the count of *successful* deliveries and never raises because of a
  subscriber.
* Slice 7: opt-in per-topic replay ring buffer; new subscribers can backfill.
* Slice 8: per-topic published/delivered/failed metrics + live subscriber count.
* Slice 9: wildcard subscriptions (``"world.*"`` = prefix match on ``"world."``).
* Slice 10: ``close()`` shuts the bus down; further publish/subscribe/register
  raise ``RuntimeError("bus closed")``.
* Slice 20: ``dead_letter_summary()`` (counts by topic + error_type) and
  ``take_dead_letters()`` (drain) — the dead-letter queue's monitoring
  surface.

Subscribers receive an :class:`EventEnvelope` (a ``StrictModel``). It supports
both attribute access (``env.topic``) and mapping access (``env["topic"]``).
"""

from __future__ import annotations

import dataclasses
import logging
import re
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from wyrdforge.models.common import StrictModel

log = logging.getLogger(__name__)

_TOPIC_NAME_RE = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)+$")

Subscriber = Callable[[Any], Any]


class EventEnvelope(StrictModel):
    """Immutable-ish carrier for one bus event.

    ``issued_at`` is an ISO-8601 string (UTC) so the envelope serializes
    trivially via :meth:`model_dump` without datetime encoding concerns.
    Mapping access (``env["topic"]``) mirrors attribute access.
    """

    topic: str
    payload: dict[str, Any]
    source: str = ""
    seq: int = 0
    issued_at: str = ""
    turn_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Plain-dict form for logging/persistence."""
        return self.model_dump()

    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key) from None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_topic_name(name: str) -> None:
    if not isinstance(name, str) or not _TOPIC_NAME_RE.match(name):
        raise ValueError(
            f"Invalid topic name {name!r}: must be a dotted name like "
            "'wyrd.turn.started'"
        )


def _validate_schema(schema: type | None) -> None:
    if schema is None:
        return
    if not isinstance(schema, type):
        raise TypeError(
            "payload_schema must be a pydantic model class or dataclass type, "
            f"got {schema!r}"
        )
    if issubclass(schema, BaseModel) or dataclasses.is_dataclass(schema):
        return
    raise TypeError(
        "payload_schema must be a pydantic model class or dataclass type, "
        f"got {schema!r}"
    )


class EventBus:
    """Synchronous, thread-safe in-process event bus (see module docstring)."""

    def __init__(self, dead_letter_cap: int = 256) -> None:
        if dead_letter_cap < 0:
            raise ValueError("dead_letter_cap must be >= 0")
        self._lock = threading.RLock()
        self._schemas: dict[str, type | None] = {}
        self._buffers: dict[str, deque | None] = {}
        self._subs: dict[str, list[tuple[str, Subscriber]]] = {}
        # wildcards: list of (token, pattern, fn), kept in subscription order
        self._wildcards: list[tuple[str, str, Subscriber]] = []
        self._token_topics: dict[str, str] = {}
        self._seq = 0
        self._closed = False
        # Slice 4 — internal failure list, drained via _take_failures().
        self._failures: list[dict[str, Any]] = []
        # Slice 6 — bounded dead-letter queue (oldest dropped on overflow).
        self._dead_letter_cap = dead_letter_cap
        self._dead_letters: deque = deque(maxlen=dead_letter_cap or 1)
        self._drop_on_zero_cap = dead_letter_cap == 0
        # Slice 8 — per-topic metrics.
        self._metrics: dict[str, dict[str, int]] = {}

    # -- internal helpers -------------------------------------------------

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("bus closed")

    @staticmethod
    def _is_wildcard(name: str) -> bool:
        return name == "*" or (name.endswith(".*") and len(name) > 2)

    @staticmethod
    def _wildcard_prefix(pattern: str) -> str:
        # "world.*" -> "world." ; "*" -> "" (matches everything)
        return "" if pattern == "*" else pattern[:-1]

    def _record_failure(
        self, envelope: EventEnvelope, fn: Subscriber, exc: BaseException
    ) -> None:
        name = getattr(fn, "__name__", None) or repr(fn)
        log.exception(
            "EventBus subscriber %s raised on topic %r (seq=%d)",
            name,
            envelope.topic,
            envelope.seq,
        )
        entry = {
            "seq": envelope.seq,
            "topic": envelope.topic,
            "subscriber": name,
            "error_type": type(exc).__name__,
            "message": str(exc),
            "timestamp": _utc_now_iso(),
        }
        self._failures.append(entry)
        if not self._drop_on_zero_cap:
            self._dead_letters.append(dict(entry))
        metrics = self._metrics.get(envelope.topic)
        if metrics is not None:
            metrics["failed"] += 1

    def _deliver(self, fn: Subscriber, envelope: EventEnvelope) -> bool:
        """Deliver one envelope to one subscriber; isolate errors."""
        try:
            fn(envelope)
        except Exception as exc:
            self._record_failure(envelope, fn, exc)
            return False
        return True

    # -- topic registry (slices 1 + 7) -------------------------------------

    def register_topic(
        self,
        name: str,
        payload_schema: type | None = None,
        replay_buffer: int = 100,
    ) -> None:
        """Register a topic.

        Idempotent: re-registering an existing topic is a no-op (the first
        registration's schema and buffer size win). Wildcard patterns can
        never be registered (``KeyError``).
        """
        self._ensure_open()
        if self._is_wildcard(name):
            raise KeyError(f"cannot register wildcard pattern: {name!r}")
        _validate_topic_name(name)
        _validate_schema(payload_schema)
        if replay_buffer < 0:
            raise ValueError("replay_buffer must be >= 0")
        with self._lock:
            if name in self._schemas:
                return
            self._schemas[name] = payload_schema
            self._buffers[name] = (
                deque(maxlen=replay_buffer) if replay_buffer > 0 else None
            )
            self._subs[name] = []
            self._metrics[name] = {"published": 0, "delivered": 0, "failed": 0}

    def topics(self) -> list[str]:
        """Names of registered topics."""
        with self._lock:
            return list(self._schemas)

    # -- subscribe / unsubscribe (slices 2 + 7 + 9) -------------------------

    def subscribe(
        self, topic: str, fn: Subscriber, replay: bool = False
    ) -> str:
        """Subscribe ``fn`` to a topic or wildcard pattern (``"world.*"``).

        Returns an opaque token for :meth:`unsubscribe`. With ``replay=True``,
        buffered envelopes are delivered FIFO to the new subscriber *before*
        any live delivery (for wildcards: across all matching topics ordered
        by envelope seq); failures during replay are isolated like live ones.
        """
        self._ensure_open()
        if not callable(fn):
            raise TypeError("subscriber must be callable")
        wildcard = self._is_wildcard(topic)
        with self._lock:
            if not wildcard and topic not in self._schemas:
                raise KeyError(f"Unknown topic: {topic!r}")
            token = uuid.uuid4().hex
            if wildcard:
                self._wildcards.append((token, topic, fn))
            else:
                self._subs[topic].append((token, fn))
            self._token_topics[token] = topic
            # Slice 7 — replay buffered envelopes FIFO, before live delivery.
            replayed: list[EventEnvelope] = []
            if replay:
                if wildcard:
                    prefix = self._wildcard_prefix(topic)
                    for tname, buf in self._buffers.items():
                        if buf and tname.startswith(prefix):
                            replayed.extend(buf)
                    replayed.sort(key=lambda e: e.seq)
                else:
                    buf = self._buffers[topic]
                    if buf:
                        replayed.extend(buf)
            for envelope in replayed:
                self._deliver(fn, envelope)
            return token

    def unsubscribe(self, token: str) -> None:
        """Remove exactly one subscription; unknown tokens raise ``KeyError``."""
        with self._lock:
            topic = self._token_topics.get(token)
            if topic is None:
                raise KeyError(f"Unknown subscription token: {token!r}")
            if self._is_wildcard(topic):
                self._wildcards = [
                    (t, p, fn) for (t, p, fn) in self._wildcards if t != token
                ]
            else:
                self._subs[topic] = [
                    (t, fn) for (t, fn) in self._subs[topic] if t != token
                ]
            del self._token_topics[token]

    # -- publish (slices 2/3/4/5 + 7 + 8 + 9) --------------------------------

    def _build_envelope(
        self,
        topic: str,
        payload: dict[str, Any],
        source: str,
        turn_id: str | None,
    ) -> EventEnvelope:
        # Slice 3 — payload-type enforcement.
        if not isinstance(payload, dict):
            raise TypeError(
                f"Topic {topic!r}: payload must be a dict, "
                f"got {type(payload).__name__}"
            )
        schema = self._schemas[topic]
        if schema is not None:
            try:
                if issubclass(schema, BaseModel):
                    schema(**payload)  # raises ValidationError on mismatch
                else:  # dataclass
                    schema(**payload)  # raises TypeError on mismatch
            except (ValidationError, TypeError) as exc:
                raise TypeError(
                    f"Topic {topic!r}: payload failed schema validation: {exc}"
                ) from exc
        self._seq += 1
        return EventEnvelope(
            topic=topic,
            payload=payload,
            source=source,
            seq=self._seq,
            issued_at=_utc_now_iso(),
            turn_id=turn_id,
        )

    def publish(
        self,
        topic: str,
        payload: dict[str, Any],
        *,
        source: str = "",
        turn_id: str | None = None,
    ) -> int:
        """Publish an event synchronously.

        Returns the number of *successful* deliveries (0 when there are no
        subscribers). Raises ``KeyError`` for unregistered topics (or
        wildcard patterns) and ``TypeError`` for payloads that fail the
        topic's schema; never raises because of a subscriber exception.
        """
        self._ensure_open()
        if self._is_wildcard(topic):
            raise KeyError(f"cannot publish to wildcard pattern: {topic!r}")
        with self._lock:
            if topic not in self._schemas:
                raise KeyError(f"Unknown topic: {topic!r}")
            envelope = self._build_envelope(topic, payload, source, turn_id)
            metrics = self._metrics[topic]
            metrics["published"] += 1
            buf = self._buffers[topic]
            if buf is not None:
                buf.append(envelope)
            # Snapshot in subscription order: exact first, then wildcards.
            targets: list[Subscriber] = [fn for _, fn in self._subs[topic]]
            for _, pattern, fn in self._wildcards:
                if topic.startswith(self._wildcard_prefix(pattern)):
                    targets.append(fn)
            delivered = 0
            for fn in targets:
                if self._deliver(fn, envelope):
                    delivered += 1
                    metrics["delivered"] += 1
            return delivered

    # -- slice 4 — failure handoff -----------------------------------------

    def _take_failures(self) -> list[dict[str, Any]]:
        """Return and clear the internal subscriber-failure list."""
        with self._lock:
            failures = self._failures
            self._failures = []
            return failures

    # -- slice 6 — dead-letter queue ----------------------------------------

    def dead_letters(self) -> list[dict[str, Any]]:
        """Copies of the dead-letter queue, oldest first."""
        with self._lock:
            return [dict(entry) for entry in self._dead_letters]

    # -- slice 20 — dead-letter observability ------------------------------

    def dead_letter_summary(self) -> dict[str, dict[str, int]]:
        """Counts of dead letters grouped by ``{topic: {error_type: count}}``.

        Read-only: the queue itself is untouched. Useful as a monitoring
        surface — a rising count per topic points at the sick subscriber.
        """
        with self._lock:
            summary: dict[str, dict[str, int]] = {}
            for entry in self._dead_letters:
                per_topic = summary.setdefault(entry["topic"], {})
                per_topic[entry["error_type"]] = (
                    per_topic.get(entry["error_type"], 0) + 1
                )
            return summary

    def take_dead_letters(self) -> list[dict[str, Any]]:
        """Drain the dead-letter queue: return and clear it, oldest first."""
        with self._lock:
            letters = [dict(entry) for entry in self._dead_letters]
            self._dead_letters.clear()
            return letters

    # -- slice 8 — metrics ---------------------------------------------------

    def snapshot(self) -> dict[str, dict[str, int]]:
        """Per-topic ``{published, delivered, failed, subscriber_count}``.

        Returns fresh dicts: mutating the result never affects the bus.
        ``subscriber_count`` is recomputed live (exact subscribers only;
        wildcard subscriptions are not attributed to any single topic).
        """
        with self._lock:
            return {
                name: {
                    "published": rec["published"],
                    "delivered": rec["delivered"],
                    "failed": rec["failed"],
                    "subscriber_count": len(self._subs[name]),
                }
                for name, rec in self._metrics.items()
            }

    def reset_metrics(self) -> None:
        """Zero published/delivered/failed counters (subscriber_count is live)."""
        with self._lock:
            for rec in self._metrics.values():
                rec["published"] = 0
                rec["delivered"] = 0
                rec["failed"] = 0

    # -- slice 10 — shutdown --------------------------------------------------

    def close(self) -> None:
        """Shut the bus down: clears subscribers, buffers, metrics, letters.

        Idempotent — calling twice is fine.
        """
        with self._lock:
            if self._closed:
                return
            self._closed = True
            # Clear contents but keep the topic registry itself, so
            # snapshot()/topics() keep working (empty) after close.
            for lst in self._subs.values():
                lst.clear()
            self._wildcards.clear()
            self._token_topics.clear()
            for buf in self._buffers.values():
                if buf is not None:
                    buf.clear()
            for rec in self._metrics.values():
                rec["published"] = 0
                rec["delivered"] = 0
                rec["failed"] = 0
            self._dead_letters.clear()
            self._failures.clear()

    @property
    def closed(self) -> bool:
        return self._closed
