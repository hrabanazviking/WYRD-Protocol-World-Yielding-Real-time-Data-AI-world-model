"""SensationEngine — the Aurelia seam's mutation service (Phase D2).

The companion to ``ecs/components/sensation.py``: components carry
the state, this engine performs the seam's named acts — embodying an
entity, recording readings, ingesting ``sense.*`` bus reports,
promoting persistent states to anchored facts, and announcing
expiries — following the CombatEngine/RunicEngine house shape
(bus-optional, topics registered idempotently, publishes after
mutation, a failing bus never breaks the semantics).

Boundary doctrine (roadmap §7): Aurelia owns live sensation
*signals*; WYRD owns remembered body-state *truth*. Concretely:

- **Sampling, not streaming.** The engine records the latest reading
  per channel and the transitions that matter (spikes, promotions,
  expiries). It never mirrors a raw stream into SQLite and runs no
  control loop — Aurelia's rates are hers.
- **Provenance is mandatory (C3, extended).** Every accepted reading
  names its source (``"aurelia"`` on this seam). A reading offered
  with no source — or a reported reading with no reporter — is
  refused with :class:`SensationProvenanceError` (a subclass of
  C3's ``UnattributedUtteranceError``: refused the same way, at the
  same kind of boundary, before any state changes). A spike that is
  written to memory goes through ``WritebackEngine`` as a
  ``sensation``-kind observation, where the C3 gate and the
  MemoryPromoter's second gate apply unchanged.
- **Spikes are observations; persistent states are facts.** A spike
  (caller-flagged, or a jump of at least ``spike_delta`` on a felt
  channel when that caller-configured delta is set — WYRD sets no
  delta of its own) is announced on ``sense.spike`` and, when a
  writeback engine is wired, written as an attributed observation.
  A felt channel whose episode has run for at least
  ``persistence_window_seconds`` (caller-configured) promotes to a
  body-state FACT: a dedicated entity carrying a
  ``BodyStateFactComponent`` and a ``TemporalAnchorComponent`` whose
  ``valid_until`` is the fact's expiry — body states are verðandi
  (becoming), and the tense system says so.
- **Embodiment is required.** Readings are recorded only for
  entities carrying an ``EmbodimentComponent``; anything else is
  refused with :class:`NotEmbodiedError` and nothing is stored.

Event topics (house dotted convention, ``sense.`` prefix)::

    sense.report            (INBOUND — the ingestion topic; payload:
                             entity_id, channel, intensity, source,
                             and optionally scale, source_status,
                             origin, reporter_id, at, spike)
    sense.reading           {entity_id, channel, intensity, scale,
                             source, origin, reporter_id, at}
    sense.spike             {entity_id, channel, intensity,
                             previous_intensity, source, origin,
                             reporter_id, at}
    sense.state_promoted    {fact_id, entity_id, channel, intensity,
                             since, expires_at}
    sense.state_expired     {fact_id, entity_id, channel, expired_at}
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

import wyrdforge.ecs.components.sensation  # noqa: F401  (registration)
import wyrdforge.ecs.components.temporal  # noqa: F401  (registration)
from wyrdforge.ecs.components.sensation import (
    BodyStateFactComponent,
    EmbodimentComponent,
    SensationComponent,
    SensationReading,
    body_state_fact_id,
)
from wyrdforge.ecs.components.temporal import TemporalAnchorComponent
from wyrdforge.ecs.world import World
from wyrdforge.services.attribution import UnattributedUtteranceError

if TYPE_CHECKING:
    from wyrdforge.runtime.events import EventBus, EventEnvelope
    from wyrdforge.services.writeback_engine import WritebackEngine


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(when: datetime) -> datetime:
    """Read a naive datetime as UTC (the B5 wall-source precedent)."""
    if when.tzinfo is None:
        return when.replace(tzinfo=timezone.utc)
    return when


class NotEmbodiedError(ValueError):
    """Sensation was offered for an entity with no body.

    Raised BEFORE anything is stored: an entity without an
    ``EmbodimentComponent`` has no body, so there is nothing for a
    sensation reading to be true *of* (roadmap §7).
    """


class SensationProvenanceError(UnattributedUtteranceError):
    """A sensation reading was offered with no provenance.

    A subclass of C3's refusal error on purpose: an unattributed
    sensation is refused *the same way* as an unattributed
    utterance — at the boundary, before any write.
    """


#: Topics the engine emits (sense.report is the inbound topic, below).
SENSE_TOPICS = (
    "sense.reading",
    "sense.spike",
    "sense.state_promoted",
    "sense.state_expired",
)

#: The inbound ingestion topic: sensation transitions arrive here.
SENSE_REPORT_TOPIC = "sense.report"


def _register_sense_topics(bus: "EventBus") -> None:
    """Register the sense.* topics once; tolerate double registration."""
    for topic in (SENSE_REPORT_TOPIC, *SENSE_TOPICS):
        try:
            bus.register_topic(topic)
        except (ValueError, KeyError):
            pass  # already registered — another producer got here first


class SensationEngine:
    """Deterministic mutation service for sensation state.

    Args:
        world: The ECS World to operate on.
        bus:   Optional EventBus for ``sense.*`` announcements and
               (via :meth:`attach_to_bus`) ingestion. When omitted,
               the World's own bus is NOT silently reused — pass a
               bus explicitly so wiring is a stated choice.
        writeback: Optional WritebackEngine. When wired, spikes are
               also written to memory as attributed ``sensation``
               observations (the C3 gates apply there unchanged).
               When omitted, spikes are bus events only.
        persistence_window_seconds: How long a felt channel's
               episode must run before it counts as a *persistent
               state* eligible for promotion. Caller-configured —
               WYRD sets no sensation thresholds of its own.
        spike_delta: Optional caller-configured jump size: a felt
               reading whose intensity differs from the channel's
               previous reading by at least this much is a spike.
               ``None`` (the default) disables delta detection —
               spikes then come only from the caller's ``spike``
               flag (the source's own judgment).
        fact_ttl_seconds: Lifetime of a promoted body-state fact,
               counted from promotion; becomes the fact anchor's
               ``valid_until``.
    """

    def __init__(
        self,
        world: World,
        *,
        bus: "EventBus | None" = None,
        writeback: "WritebackEngine | None" = None,
        persistence_window_seconds: float = 60.0,
        spike_delta: float | None = None,
        fact_ttl_seconds: float = 600.0,
    ) -> None:
        if persistence_window_seconds < 0:
            raise ValueError("persistence_window_seconds must be non-negative")
        if spike_delta is not None and spike_delta <= 0:
            raise ValueError("spike_delta must be positive when set")
        if fact_ttl_seconds <= 0:
            raise ValueError("fact_ttl_seconds must be positive")
        self._world = world
        self._bus = bus
        self._writeback = writeback
        self._persistence_window = float(persistence_window_seconds)
        self._spike_delta = spike_delta
        self._fact_ttl = float(fact_ttl_seconds)
        #: Bus-ingestion refusals, recorded (never raised into the
        #: bus): each entry names the payload's entity/channel and
        #: the refusal reason — the trace that a refusal happened.
        self.refusals: list[dict[str, Any]] = []
        if self._bus is not None:
            _register_sense_topics(self._bus)

    @property
    def world(self) -> World:
        return self._world

    # ------------------------------------------------------------------
    # Embodiment
    # ------------------------------------------------------------------

    def embody(
        self, entity_id: str, *, body_id: str = "", source: str = "aurelia", label: str = ""
    ) -> EmbodimentComponent:
        """Mark an entity embodied (or refresh its embodiment)."""
        comp = EmbodimentComponent(
            entity_id=entity_id, body_id=body_id, source=source, label=label
        )
        self._world.add_component(entity_id, comp)
        return comp

    def is_embodied(self, entity_id: str) -> bool:
        return isinstance(
            self._world.get_component(entity_id, "embodiment"), EmbodimentComponent
        )

    def _require_embodied(self, entity_id: str) -> None:
        if self._world.get_entity(entity_id) is None:
            raise KeyError(f"entity '{entity_id}' does not exist in this world")
        if not self.is_embodied(entity_id):
            raise NotEmbodiedError(
                f"entity '{entity_id}' is not embodied: sensation state "
                "exists only where a body does (no EmbodimentComponent)"
            )

    # ------------------------------------------------------------------
    # Recording readings
    # ------------------------------------------------------------------

    def record_reading(
        self,
        entity_id: str,
        channel: str,
        intensity: float,
        *,
        at: datetime | None = None,
        source: str | None = "aurelia",
        scale: str = "",
        source_status: str = "",
        origin: str = "felt",
        reporter_id: str | None = None,
        spike: bool = False,
    ) -> SensationReading:
        """Record one sensation reading on an embodied entity.

        Refusals (all BEFORE any state changes): unknown entity →
        ``KeyError``; entity not embodied → :class:`NotEmbodiedError`;
        no/blank source, a reported reading with no reporter, a
        reporter naming the embodied entity itself, or a felt reading
        carrying a different reporter → :class:`SensationProvenanceError`
        / ``ValueError`` from the component's own guards.

        On a spike, emits ``sense.spike`` (after ``sense.reading``)
        and, when a writeback engine is wired, writes the spike to
        memory as an attributed ``sensation`` observation.
        """
        clean_source = (source or "").strip()
        if not clean_source:
            raise SensationProvenanceError(
                "refusing a sensation reading with no provenance: every "
                "sensation observation must name its source (Phase C3 "
                "provenance enforcement, extended to sensations by D2)"
            )
        if origin not in ("felt", "reported"):
            raise ValueError(f"origin must be 'felt' or 'reported', got {origin!r}")
        clean_reporter = (reporter_id or "").strip() or None
        if origin == "reported" and clean_reporter is None:
            raise SensationProvenanceError(
                "refusing a reported sensation with no reporter: a claim "
                "about a body must name who claims it"
            )
        if origin == "felt" and clean_reporter is not None and clean_reporter != entity_id:
            raise ValueError(
                "a felt reading cannot carry another entity as reporter — "
                "that is a reported sensation (origin='reported')"
            )
        self._require_embodied(entity_id)

        when = _as_utc(at) if at is not None else _now()
        comp = self._world.get_component(entity_id, "sensation")
        if not isinstance(comp, SensationComponent):
            comp = SensationComponent(entity_id=entity_id)
            self._world.add_component(entity_id, comp)

        previous = comp.get_reading(channel) if origin == "felt" else None
        reading = SensationReading(
            channel=channel,
            intensity=float(intensity),
            scale=scale,
            source=clean_source,
            source_status=source_status,
            origin=origin,  # type: ignore[arg-type]
            reporter_id=clean_reporter if origin == "reported" else None,
            updated_at=when,
            episode_started_at=when,
        )
        if origin == "felt":
            comp.set_reading(reading)
        else:
            comp.set_reported_reading(reading)

        self._emit("sense.reading", {
            "entity_id": entity_id,
            "channel": channel,
            "intensity": reading.intensity,
            "scale": scale,
            "source": clean_source,
            "origin": origin,
            "reporter_id": reading.reporter_id,
            "at": when.isoformat(),
        })

        is_spike = bool(spike) or (
            origin == "felt"
            and self._spike_delta is not None
            and previous is not None
            and abs(reading.intensity - previous.intensity) >= self._spike_delta
        )
        if is_spike:
            self._emit("sense.spike", {
                "entity_id": entity_id,
                "channel": channel,
                "intensity": reading.intensity,
                "previous_intensity": previous.intensity if previous is not None else None,
                "source": clean_source,
                "origin": origin,
                "reporter_id": reading.reporter_id,
                "at": when.isoformat(),
            })
            self._write_spike_observation(
                entity_id,
                reading,
                previous_intensity=previous.intensity if previous is not None else None,
            )
        return reading

    def _write_spike_observation(
        self,
        entity_id: str,
        reading: SensationReading,
        *,
        previous_intensity: float | None,
    ) -> None:
        """A spike is an observation — written through the usual rules.

        Goes through WritebackEngine as a ``sensation``-kind
        observation, attributed (speaker = the feeler for a felt
        spike, the reporter for a reported one), so the C3 writeback
        gate and the promoter's second gate apply exactly as they do
        to utterances. No-op when no writeback engine is wired.
        """
        if self._writeback is None:
            return
        speaker = reading.reporter_id if reading.origin == "reported" else entity_id
        prev = "none" if previous_intensity is None else f"{previous_intensity:g}"
        self._writeback.write_observation(
            title=f"sensation spike: {reading.channel}",
            summary=(
                f"{entity_id} {reading.origin} sensation spike on channel "
                f"'{reading.channel}': intensity {reading.intensity:g} "
                f"(previous {prev}), source {reading.source}"
            ),
            observation_kind="sensation",
            speaker_id=speaker,
            participants=[entity_id],
            salience=0.8,
            tags=["sensation", "spike", reading.channel],
        )

    # ------------------------------------------------------------------
    # Bus ingestion — sense.report
    # ------------------------------------------------------------------

    def handle_event(self, payload: dict[str, Any], *, source: str = "") -> SensationReading:
        """Ingest one ``sense.report`` payload (the direct-call form).

        The payload names entity_id / channel / intensity and its
        provenance: its own ``source`` field wins, else the
        transport-level ``source`` (e.g. the bus envelope's). With
        neither, the report is refused with
        :class:`SensationProvenanceError` and nothing is recorded —
        unattributed sensation observations are refused the same way
        unattributed utterances are (C3). ``at`` may be a datetime or
        an ISO-8601 string; a naive stamp is read as UTC.
        """
        if not isinstance(payload, dict):
            raise ValueError("sense.report payload must be a mapping")
        entity_id = payload.get("entity_id")
        channel = payload.get("channel")
        if not entity_id or not channel or payload.get("intensity") is None:
            raise ValueError(
                "sense.report payload requires entity_id, channel and intensity"
            )
        effective_source = str(payload.get("source") or source or "")
        at_raw = payload.get("at", payload.get("updated_at"))
        at: datetime | None = None
        if isinstance(at_raw, datetime):
            at = at_raw
        elif isinstance(at_raw, str) and at_raw.strip():
            at = datetime.fromisoformat(at_raw.strip().replace("Z", "+00:00"))
        return self.record_reading(
            str(entity_id),
            str(channel),
            float(payload["intensity"]),
            at=at,
            source=effective_source,
            scale=str(payload.get("scale") or ""),
            source_status=str(payload.get("source_status") or ""),
            origin=str(payload.get("origin") or "felt"),
            reporter_id=payload.get("reporter_id"),
            spike=bool(payload.get("spike", False)),
        )

    def attach_to_bus(self, bus: "EventBus | None" = None) -> None:
        """Subscribe this engine to ``sense.report`` on a bus.

        Uses ``bus`` when given, else the engine's own bus. Ingestion
        failures (refusals, malformed payloads) are recorded in
        :attr:`refusals` and never raised into the bus — the bus's
        own isolation would dead-letter them, but a refusal is an
        expected seam event, not a delivery failure, and the engine
        keeps the trace itself.
        """
        target = bus if bus is not None else self._bus
        if target is None:
            raise ValueError("attach_to_bus needs a bus (none given, engine has none)")
        _register_sense_topics(target)
        target.subscribe(SENSE_REPORT_TOPIC, self._on_sense_report)

    def _on_sense_report(self, envelope: "EventEnvelope") -> None:
        try:
            self.handle_event(dict(envelope.payload), source=envelope.source)
        except Exception as exc:  # refusal/malformed — recorded, not raised
            payload = envelope.payload if isinstance(envelope.payload, dict) else {}
            self.refusals.append({
                "entity_id": payload.get("entity_id"),
                "channel": payload.get("channel"),
                "reason": f"{type(exc).__name__}: {exc}",
            })

    # ------------------------------------------------------------------
    # Promotion — persistent states become anchored facts
    # ------------------------------------------------------------------

    def promote_persistent_states(
        self, now: datetime, *, ttl_seconds: float | None = None
    ) -> list[str]:
        """Promote every newly-persistent felt state to a fact.

        A felt channel is *persistent* at ``now`` when its current
        reading is positive and its episode has run for at least the
        engine's persistence window. Promotion creates (or, for a
        new episode, refreshes) the deterministic fact entity
        (:func:`body_state_fact_id`) carrying a
        ``BodyStateFactComponent`` plus a ``TemporalAnchorComponent``
        spanning [episode start, promotion + ttl]. Returns the fact
        ids promoted by THIS call, in (entity, channel) order.
        Re-running over the same episode promotes nothing twice.
        """
        now = _as_utc(now)
        ttl = self._fact_ttl if ttl_seconds is None else float(ttl_seconds)
        if ttl <= 0:
            raise ValueError("ttl_seconds must be positive")
        promoted: list[str] = []
        pairs = [
            (entity, comp)
            for entity, comp in self._world.iter_components("sensation")
            if isinstance(comp, SensationComponent)
        ]
        for entity, comp in sorted(pairs, key=lambda pair: pair[0].entity_id):
            for reading in sorted(comp.readings, key=lambda r: r.channel):
                if reading.intensity <= 0.0:
                    continue
                if reading.episode_age_seconds_at(now) < self._persistence_window:
                    continue
                fact_id = body_state_fact_id(entity.entity_id, reading.channel)
                existing = self._world.get_component(fact_id, "body_state_fact")
                if (
                    isinstance(existing, BodyStateFactComponent)
                    and existing.since == reading.episode_started_at
                ):
                    continue  # this episode already promoted
                expires = now + timedelta(seconds=ttl)
                if self._world.get_entity(fact_id) is None:
                    self._world.create_entity(entity_id=fact_id, tags={"body_state_fact"})
                self._world.add_component(fact_id, BodyStateFactComponent(
                    entity_id=fact_id,
                    subject_entity_id=entity.entity_id,
                    channel=reading.channel,
                    intensity=reading.intensity,
                    scale=reading.scale,
                    source=reading.source,
                    since=reading.episode_started_at,
                    promoted_at=now,
                ))
                self._world.add_component(fact_id, TemporalAnchorComponent(
                    entity_id=fact_id,
                    valid_from=reading.episode_started_at,
                    valid_until=expires,
                    observed_at=now,
                    label=f"sensation:{reading.channel}",
                ))
                promoted.append(fact_id)
                self._emit("sense.state_promoted", {
                    "fact_id": fact_id,
                    "entity_id": entity.entity_id,
                    "channel": reading.channel,
                    "intensity": reading.intensity,
                    "since": reading.episode_started_at.isoformat(),
                    "expires_at": expires.isoformat(),
                })
        return promoted

    def tick_expired(self, now: datetime) -> list[str]:
        """Announce promoted facts whose anchor has lapsed at ``now``.

        Each expiry is announced exactly once via
        ``sense.state_expired`` (the fact component's
        ``expiry_announced`` flag is the once-guard — the
        CombatEngine.tick_effects precedent). Returns the fact ids
        expired by THIS tick, in fact-id order. The fact entity and
        its anchor remain — an expired body-state fact is history
        (urðr), not a deletion.
        """
        now = _as_utc(now)
        expired_now: list[str] = []
        pairs = [
            (entity, comp)
            for entity, comp in self._world.iter_components("body_state_fact")
            if isinstance(comp, BodyStateFactComponent)
        ]
        for entity, comp in sorted(pairs, key=lambda pair: pair[0].entity_id):
            if comp.expiry_announced:
                continue
            anchor = self._world.get_component(entity.entity_id, "temporal_anchor")
            if isinstance(anchor, TemporalAnchorComponent):
                lapsed = anchor.has_expired(now)
            else:
                continue  # no anchor, no expiry — the anchor is the tense truth
            if lapsed:
                comp.expiry_announced = True
                comp.touch()
                expired_now.append(entity.entity_id)
                self._emit("sense.state_expired", {
                    "fact_id": entity.entity_id,
                    "entity_id": comp.subject_entity_id,
                    "channel": comp.channel,
                    "expired_at": now.isoformat(),
                })
        return expired_now

    def promoted_fact_for(
        self, entity_id: str, channel: str
    ) -> BodyStateFactComponent | None:
        """The promoted fact component for (entity, channel), or None."""
        comp = self._world.get_component(
            body_state_fact_id(entity_id, channel), "body_state_fact"
        )
        return comp if isinstance(comp, BodyStateFactComponent) else None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _emit(self, topic: str, payload: dict) -> None:
        """Publish after mutation; a failing bus never breaks sensation."""
        if self._bus is None:
            return
        try:
            self._bus.publish(topic, payload, source="sensation.engine")
        except Exception:
            pass
