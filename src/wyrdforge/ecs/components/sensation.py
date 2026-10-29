"""Sensation state components — Phase D2 (roadmap §7 / §9-D2).

The Aurelia seam. Boundary doctrine (roadmap §7): Aurelia owns live
sensation *signals* — high-rate, ephemeral, hers. WYRD owns remembered
body-state *truth* — durable, queryable, cited with provenance and
age. Neither reaches into the other's store. This module is the WYRD
side of that seam: the remembered body, at sampling grain.

Design, following the house patterns of the phases before it:

- **The Verdandi precedent.** ``bridges/verdandi_bridge.py``'s
  ``SenseComponent`` / ``SenseReading`` model senses as
  provenance-carrying component readings that are *rewritten, never
  duplicated* — one current reading per metric, replaced on update.
  :class:`SensationComponent` follows that shape exactly: one current
  reading per channel, replaced on update. WYRD holds the *latest
  remembered* reading per channel — it does NOT mirror Aurelia's raw
  stream (no per-tick history, no control loop; roadmap §7's explicit
  "must not").
- **Channel taxonomy is the source's, not WYRD's.** Verified from the
  Aurelia tree (2026-10-29): Aurelia's ``StateVector``
  (``female_motivation/core/state.py``) is *caller-named* float
  channels clamped to [0, 1] — there is no fixed channel enum to
  copy. Aurelia's own WYRD bridge
  (``female_motivation/adapters/wyrd_bridge.py``) names the body
  channels it mirrors: ``arousal`` (**0–10** — physiology's single
  source of truth is a 0–10 scale), ``soreness``, ``lubrication``,
  ``afterglow``, ``fatigue``, ``nipple_erection`` (all 0–1),
  ``phase`` (categorical, e.g. ``"quiet"``) and ``refractory``
  (boolean); mood/desire ride their own vectors (``valence``,
  ``total_desire``, …). So this component takes **caller-named
  channel ids** and carries each reading's intensity *verbatim in
  the source's own scale* (named on the reading via ``scale``):
  clamping everything to [0, 1] would falsify Aurelia's arousal the
  moment it crossed the seam. Categorical/boolean source values
  (phase, refractory, tingle bands) ride as the source's own
  judgment string in ``source_status`` — WYRD reuses the source's
  judgments, it does not invent thresholds of its own.
- **Embodiment is explicit.** A :class:`SensationComponent` may only
  exist where a body does: the entity must carry an
  :class:`EmbodimentComponent`. The enforcement lives in
  ``services/sensation_engine.SensationEngine`` (the mutation
  service, as combat's health requirement lives in CombatEngine) —
  the component classes themselves stay plain data, exactly as
  ``HealthComponent`` does.
- **Felt vs. reported — the MTOM firewall at storage level.** A
  *felt* reading is the embodied entity's own sensation: manifest
  reality, stored in ``readings``. A *reported* reading is another's
  claim about this body: it must name its reporter and is stored in
  the SEPARATE ``reported_readings`` list. The two never share a
  slot, never overwrite each other, and the Oracle serves them from
  separate queries — a report can never pose as a feeling.
- **Freshness is part of the data.** Every reading carries
  ``updated_at``; age and staleness are computed at query time
  against a caller-named window (:data:`DEFAULT_FRESHNESS_WINDOW_SECONDS`
  is only a default, overridable per query — the window is a query
  contract, not a sensation threshold). A stale reading reads as
  STALE, never as current (the Oracle's D2 contract; Aurelia's own
  AUR-20 freshness discipline is the precedent).

Persistence: all components here persist generically through
``WorldStore`` like B3's ``PositionComponent`` and D1's combat
components — no schema change, no migration.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import ClassVar, Literal

from pydantic import Field, field_validator

from wyrdforge.ecs.component import Component, register_component
from wyrdforge.models.common import StrictModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


#: Default freshness window for Oracle sensation answers, in seconds.
#: A reading older than this at query time is reported STALE. This is
#: a *query* default only — every Oracle sensation query accepts an
#: override, and the window judges the age of WYRD's memory, never
#: the sensation itself (WYRD invents no sensation thresholds).
DEFAULT_FRESHNESS_WINDOW_SECONDS = 60.0

#: The two origins a sensation reading can have. ``felt`` = the
#: embodied entity's own sensation (manifest reality). ``reported`` =
#: another entity's claim about this body (a claim, never a feeling).
SensationOrigin = Literal["felt", "reported"]


def body_state_fact_id(entity_id: str, channel: str) -> str:
    """Deterministic entity id of a channel's promoted body-state fact.

    Promotion (see ``services/sensation_engine``) is idempotent per
    (entity, channel, episode) because the fact entity's id is a
    pure function of the pair — a re-promotion updates the same
    entity instead of minting a second fact.
    """
    return f"body-fact:{entity_id}:{channel}"


# ---------------------------------------------------------------------------
# Embodiment — the marker that a body exists here
# ---------------------------------------------------------------------------


@register_component
class EmbodimentComponent(Component):
    """Marks an entity as embodied — a body exists here.

    Sensation state may only be recorded for entities carrying this
    component (roadmap §7: "no sensation storage for entities that
    are not embodied — the component exists only where a body does").
    The component is deliberately small: it names the body and the
    body provider, nothing more. Body *truth* stays with the
    provider (Aurelia); this is the seam's anchor point in the world.

    Attributes:
        body_id: The provider-side body identifier, when the body
                 has one (e.g. an Aurelia agent/profile id).
        source:  The body provider. ``"aurelia"`` is the seam this
                 phase builds; the field is a plain string so other
                 embodiment providers can name themselves.
        label:   Short human tag, e.g. "Yrsa's body (Mimir)".
    """

    _type_key: ClassVar[str] = "embodiment"
    component_type: Literal["embodiment"] = "embodiment"

    body_id: str = ""
    source: str = "aurelia"
    label: str = ""


# ---------------------------------------------------------------------------
# Readings
# ---------------------------------------------------------------------------


class SensationReading(StrictModel):
    """One remembered sensation reading on one channel.

    The ``SenseReading`` precedent (Verdandi bridge), specialised to
    the Aurelia seam: the reading carries its provenance (``source``),
    the source's own judgment verbatim (``source_status`` — e.g. a
    phase name, a tingle band, a status word; WYRD never re-judges
    it), and its scale, because Aurelia's channels do not share one
    (arousal is 0–10, the state channels are 0–1).

    Attributes:
        channel:           Caller-named channel id, in the source's
                           taxonomy (e.g. ``"arousal"``,
                           ``"soreness"``, a per-zone id).
        intensity:         The source's value, verbatim. Must be a
                           finite, non-negative number. Categorical
                           channels carry ``0.0`` here and their value
                           in ``source_status``.
        scale:             The source scale for ``intensity``
                           (``"0-1"``, ``"0-10"``, …); ``""`` when the
                           source did not name one.
        source:            Provenance — who produced this reading.
                           ``"aurelia"`` on this seam. Never empty on
                           a reading the engine accepted (the engine
                           refuses provenance-less readings).
        source_status:     The source's own judgment, verbatim.
        origin:            ``"felt"`` (the entity's own) or
                           ``"reported"`` (another's claim).
        reporter_id:       For ``reported`` readings: the entity
                           making the claim. Required there, and
                           never the embodied entity itself. Always
                           None on felt readings.
        updated_at:        When the source produced this reading
                           (the reading's own stamp — freshness is
                           judged from this, never from arrival).
        episode_started_at: When the current continuous episode of
                           this channel began (the first reading of
                           an unbroken run of positive intensity).
                           Maintained by
                           :meth:`SensationComponent.set_reading`;
                           promotion to a body-state fact is judged
                           from episode age.
    """

    channel: str
    intensity: float = 0.0
    scale: str = ""
    source: str = "aurelia"
    source_status: str = ""
    origin: SensationOrigin = "felt"
    reporter_id: str | None = None
    updated_at: datetime = Field(default_factory=_now)
    episode_started_at: datetime = Field(default_factory=_now)

    @field_validator("intensity")
    @classmethod
    def _intensity_is_finite(cls, value: float) -> float:
        # Aurelia's own boundary lesson (its API rejects NaN/Inf
        # explicitly because pydantic accepts them by default): a
        # non-finite or negative sensation value is not a reading.
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(
                f"sensation intensity must be finite and non-negative, got {value!r}"
            )
        return value

    def age_seconds_at(self, now: datetime) -> float:
        """The reading's age at ``now``, in seconds (never negative).

        A reading stamped in the future (clock skew between the
        body provider and WYRD) has age 0 — it is fresh, not
        negative-aged.
        """
        return max(0.0, (now - self.updated_at).total_seconds())

    def is_stale_at(self, now: datetime, window_seconds: float) -> bool:
        """True when the reading is older than ``window_seconds`` at ``now``."""
        return self.age_seconds_at(now) > window_seconds

    def episode_age_seconds_at(self, now: datetime) -> float:
        """How long the current episode has run at ``now`` (never negative)."""
        return max(0.0, (now - self.episode_started_at).total_seconds())


# ---------------------------------------------------------------------------
# The component — current remembered body state of one embodied entity
# ---------------------------------------------------------------------------


@register_component
class SensationComponent(Component):
    """Current remembered sensation state of one embodied entity.

    One component per embodied entity, holding the LATEST reading
    per channel — the SenseComponent discipline (rewrite, never
    duplicate). There is deliberately no history list here: WYRD
    samples state and significant transitions (spikes become
    observations through the engine; persistent states promote to
    facts), it does not mirror the raw stream.

    Felt readings live in ``readings``; reported readings live in
    ``reported_readings``, keyed by (channel, reporter). The lists
    are separate stores, so no code path can accidentally serve a
    report as a feeling.
    """

    _type_key: ClassVar[str] = "sensation"
    component_type: Literal["sensation"] = "sensation"

    readings: list[SensationReading] = Field(default_factory=list)
    reported_readings: list[SensationReading] = Field(default_factory=list)

    # -- felt ---------------------------------------------------------

    def set_reading(self, reading: SensationReading) -> SensationReading:
        """Add or replace the FELT reading for its channel.

        Episode bookkeeping: a positive-intensity reading that
        follows a positive-intensity reading on the same channel
        continues that channel's episode (``episode_started_at`` is
        carried over); any other case — first reading, or a return
        from zero — starts a new episode at this reading's stamp.
        A zero-intensity reading closes the episode (the next
        positive reading starts a new one).
        """
        if reading.origin != "felt":
            raise ValueError(
                "set_reading holds felt readings only; use set_reported_reading "
                "for another's claim (the felt/reported firewall is structural)"
            )
        previous = self.get_reading(reading.channel)
        if (
            previous is not None
            and previous.intensity > 0.0
            and reading.intensity > 0.0
        ):
            reading.episode_started_at = previous.episode_started_at
        else:
            reading.episode_started_at = reading.updated_at
        self.readings = [r for r in self.readings if r.channel != reading.channel]
        self.readings.append(reading)
        self.touch()
        return reading

    def get_reading(self, channel: str) -> SensationReading | None:
        """The current felt reading for ``channel``, or None."""
        for reading in self.readings:
            if reading.channel == channel:
                return reading
        return None

    def channels(self) -> list[str]:
        """Felt channel ids with a current reading, sorted."""
        return sorted(r.channel for r in self.readings)

    # -- reported -------------------------------------------------------

    def set_reported_reading(self, reading: SensationReading) -> SensationReading:
        """Add or replace a REPORTED reading for (channel, reporter).

        A report is a claim: it must name its reporter, and the
        reporter may not be the embodied entity itself (one's own
        sensation is felt, not reported). Reports never touch the
        felt store.
        """
        if reading.origin != "reported":
            raise ValueError(
                "set_reported_reading holds reported claims only; use "
                "set_reading for the entity's own felt sensation"
            )
        reporter = (reading.reporter_id or "").strip()
        if not reporter:
            raise ValueError(
                "a reported sensation must name its reporter — an "
                "unattributed claim about a body is not recordable"
            )
        if reporter == self.entity_id:
            raise ValueError(
                "an entity cannot report its own sensation: its own "
                "sensation is felt (origin='felt'), not reported"
            )
        self.reported_readings = [
            r
            for r in self.reported_readings
            if not (r.channel == reading.channel and r.reporter_id == reading.reporter_id)
        ]
        self.reported_readings.append(reading)
        self.touch()
        return reading

    def get_reported(
        self, channel: str, reporter_id: str | None = None
    ) -> list[SensationReading]:
        """Reported readings for ``channel`` (optionally one reporter)."""
        return [
            r
            for r in self.reported_readings
            if r.channel == channel
            and (reporter_id is None or r.reporter_id == reporter_id)
        ]


# ---------------------------------------------------------------------------
# Promoted body-state facts — persistent sensation, as an entity (D1 pattern)
# ---------------------------------------------------------------------------


@register_component
class BodyStateFactComponent(Component):
    """A persistent sensation state, promoted to a remembered fact.

    Lives on a dedicated fact ENTITY (id:
    :func:`body_state_fact_id`), exactly as D1's effects live on
    their own entities: the fact entity ALSO carries a
    ``TemporalAnchorComponent`` whose validity window is the fact's
    span — ``valid_from`` is the episode's start, ``valid_until``
    its expiry. Body states are verðandi (becoming), never urðr
    (settled): the anchor says so, and once it lapses the fact is no
    longer current truth about the body.

    Attributes:
        subject_entity_id: The embodied entity the fact is about.
        channel:           The sensation channel.
        intensity:         The reading's intensity at promotion
                           (verbatim, in ``scale``).
        scale:             The source scale (see SensationReading).
        source:            Provenance of the underlying readings.
        since:             Episode start (the anchor's valid_from).
        promoted_at:       When promotion happened.
        expiry_announced:  Once-guard for the ``sense.state_expired``
                           announcement (the CombatEngine.tick_effects
                           precedent): the engine flips this when it
                           emits, so expiry is announced exactly once.
    """

    _type_key: ClassVar[str] = "body_state_fact"
    component_type: Literal["body_state_fact"] = "body_state_fact"

    subject_entity_id: str = ""
    channel: str = ""
    intensity: float = 0.0
    scale: str = ""
    source: str = "aurelia"
    since: datetime = Field(default_factory=_now)
    promoted_at: datetime = Field(default_factory=_now)
    expiry_announced: bool = False
