"""Phase D2 — sensation state (the Aurelia seam) pinning tests.

Design under test (roadmap §7, ``ecs/components/sensation.py`` +
``services/sensation_engine.py`` + the Oracle's D2 queries):

* Aurelia owns live sensation SIGNALS; WYRD owns remembered
  body-state TRUTH. The SensationComponent holds the latest reading
  per channel (the Verdandi SenseComponent discipline: rewrite,
  never duplicate) — no raw-stream mirror, no control loop.
* Channels are caller-named in the source's taxonomy and intensities
  are carried verbatim in the source's scale (Aurelia's arousal is
  0–10, its state channels 0–1 — verified in the Aurelia tree).
* Provenance is mandatory (C3 extended): a source-less reading, an
  unattributed ``sense.report``, and an unattributed sensation
  observation are all refused before anything is stored; the
  promoter never promotes an unattributed sensation.
* A spike is an observation (bus event + attributed memory record
  when writeback is wired); a persistent state promotes to a fact
  entity carrying a TemporalAnchorComponent expiry (verðandi).
* Oracle answers carry age; stale reads STALE, never current.
* Felt (own, manifest) and reported (another's claim) sensations
  live in separate stores and are served by separate queries.
* No sensation storage for entities that are not embodied.
"""
from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone

import pytest

import wyrdforge.ecs.components.sensation  # noqa: F401  (registry)
import wyrdforge.ecs.components.temporal  # noqa: F401  (registry)
from wyrdforge.ecs.components.sensation import (
    BodyStateFactComponent,
    EmbodimentComponent,
    SensationComponent,
    SensationReading,
    body_state_fact_id,
)
from wyrdforge.ecs.components.temporal import TemporalAnchorComponent
from wyrdforge.ecs.world import World
from wyrdforge.oracle import PassiveOracle
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.persistence.world_store import WorldStore
from wyrdforge.runtime.events import EventBus
from wyrdforge.services.attribution import UnattributedUtteranceError
from wyrdforge.services.memory_promoter import MemoryPromoter
from wyrdforge.services.sensation_engine import (
    NotEmbodiedError,
    SensationEngine,
    SensationProvenanceError,
)
from wyrdforge.services.writeback_engine import WritebackEngine

UTC = timezone.utc
T0 = datetime(2026, 10, 29, 12, 0, 0, tzinfo=UTC)


def _oracle(world: World) -> PassiveOracle:
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    return PassiveOracle(world, store)


def _embodied(world: World, engine: SensationEngine, eid: str = "yrsa") -> str:
    world.create_entity(entity_id=eid)
    engine.embody(eid, body_id="aurelia-main")
    return eid


def _bus_with_sense_topics() -> tuple[EventBus, list]:
    bus = EventBus()
    seen: list = []
    for topic in (
        "sense.reading", "sense.spike", "sense.state_promoted", "sense.state_expired",
    ):
        bus.register_topic(topic)
        bus.subscribe(topic, seen.append)
    return bus, seen


# ---------------------------------------------------------------------------
# Component readings + update semantics
# ---------------------------------------------------------------------------


class TestSensationComponent:
    def test_reading_update_replaces_never_duplicates(self):
        world = World("w")
        engine = SensationEngine(world)
        _embodied(world, engine)
        engine.record_reading("yrsa", "arousal", 3.0, at=T0, scale="0-10")
        engine.record_reading("yrsa", "arousal", 7.5, at=T0 + timedelta(seconds=5), scale="0-10")
        comp = world.get_component("yrsa", "sensation")
        assert isinstance(comp, SensationComponent)
        assert len(comp.readings) == 1  # rewritten, never duplicated
        reading = comp.get_reading("arousal")
        assert reading is not None
        assert reading.intensity == 7.5 and reading.scale == "0-10"
        assert reading.source == "aurelia" and reading.origin == "felt"
        assert reading.updated_at == T0 + timedelta(seconds=5)

    def test_verbatim_scales_coexist(self):
        # Aurelia's verified scales: arousal 0-10, state channels 0-1.
        # A 0-1 clamp would falsify arousal; both must survive verbatim.
        world = World("w")
        engine = SensationEngine(world)
        _embodied(world, engine)
        engine.record_reading("yrsa", "arousal", 8.25, at=T0, scale="0-10")
        engine.record_reading("yrsa", "soreness", 0.4, at=T0, scale="0-1")
        comp = world.get_component("yrsa", "sensation")
        assert isinstance(comp, SensationComponent)
        assert comp.channels() == ["arousal", "soreness"]
        assert comp.get_reading("arousal").intensity == 8.25
        assert comp.get_reading("soreness").intensity == 0.4

    def test_categorical_channel_rides_source_status(self):
        # Aurelia's `phase` is categorical ("quiet", ...): the value
        # rides as the source's own judgment, never re-judged by WYRD.
        world = World("w")
        engine = SensationEngine(world)
        _embodied(world, engine)
        engine.record_reading(
            "yrsa", "phase", 0.0, at=T0, source_status="plateau"
        )
        reading = world.get_component("yrsa", "sensation").get_reading("phase")
        assert reading.source_status == "plateau"

    def test_non_finite_or_negative_intensity_refused(self):
        with pytest.raises(ValueError):
            SensationReading(channel="arousal", intensity=float("nan"))
        with pytest.raises(ValueError):
            SensationReading(channel="arousal", intensity=float("inf"))
        with pytest.raises(ValueError):
            SensationReading(channel="arousal", intensity=-1.0)

    def test_episode_continuity_and_reset(self):
        comp = SensationComponent(entity_id="yrsa")
        comp.set_reading(SensationReading(
            channel="soreness", intensity=0.3, updated_at=T0, episode_started_at=T0))
        second = comp.set_reading(SensationReading(
            channel="soreness", intensity=0.5,
            updated_at=T0 + timedelta(seconds=30),
            episode_started_at=T0 + timedelta(seconds=30)))
        assert second.episode_started_at == T0  # same episode continues
        comp.set_reading(SensationReading(
            channel="soreness", intensity=0.0,
            updated_at=T0 + timedelta(seconds=40),
            episode_started_at=T0 + timedelta(seconds=40)))
        third = comp.set_reading(SensationReading(
            channel="soreness", intensity=0.2,
            updated_at=T0 + timedelta(seconds=50),
            episode_started_at=T0 + timedelta(seconds=50)))
        assert third.episode_started_at == T0 + timedelta(seconds=50)  # new episode


# ---------------------------------------------------------------------------
# Embodiment gate
# ---------------------------------------------------------------------------


class TestEmbodimentGate:
    def test_non_embodied_entity_refused_and_stores_nothing(self):
        world = World("w")
        engine = SensationEngine(world)
        world.create_entity(entity_id="rock")
        with pytest.raises(NotEmbodiedError):
            engine.record_reading("rock", "temperature", 0.5, at=T0)
        assert world.get_component("rock", "sensation") is None

    def test_unknown_entity_raises_key_error(self):
        world = World("w")
        engine = SensationEngine(world)
        with pytest.raises(KeyError):
            engine.record_reading("ghost", "arousal", 1.0, at=T0)

    def test_embody_marks_and_engine_recognises(self):
        world = World("w")
        engine = SensationEngine(world)
        world.create_entity(entity_id="yrsa")
        assert not engine.is_embodied("yrsa")
        comp = engine.embody("yrsa", body_id="aurelia-main", label="Mimir body")
        assert isinstance(comp, EmbodimentComponent)
        assert comp.source == "aurelia" and comp.body_id == "aurelia-main"
        assert engine.is_embodied("yrsa")


# ---------------------------------------------------------------------------
# Provenance (C3 extended to sensations)
# ---------------------------------------------------------------------------


class TestProvenance:
    def test_sourceless_reading_refused(self):
        world = World("w")
        engine = SensationEngine(world)
        _embodied(world, engine)
        for bad_source in (None, "", "   "):
            with pytest.raises(SensationProvenanceError):
                engine.record_reading("yrsa", "arousal", 1.0, at=T0, source=bad_source)
        # The refusal is C3's refusal: same error family.
        with pytest.raises(UnattributedUtteranceError):
            engine.record_reading("yrsa", "arousal", 1.0, at=T0, source=None)
        assert world.get_component("yrsa", "sensation") is None

    def test_reported_reading_requires_reporter(self):
        world = World("w")
        engine = SensationEngine(world)
        _embodied(world, engine)
        with pytest.raises(SensationProvenanceError):
            engine.record_reading(
                "yrsa", "soreness", 0.5, at=T0, origin="reported", reporter_id=None
            )

    def test_sense_report_ingestion_and_provenance_refusal(self):
        world = World("w")
        engine = SensationEngine(world)
        _embodied(world, engine)
        reading = engine.handle_event(
            {"entity_id": "yrsa", "channel": "arousal", "intensity": 4.0,
             "scale": "0-10", "at": T0.isoformat()},
            source="aurelia",
        )
        assert reading.intensity == 4.0 and reading.updated_at == T0
        # Payload-carried provenance also works.
        engine.handle_event(
            {"entity_id": "yrsa", "channel": "fatigue", "intensity": 0.2,
             "source": "aurelia"}
        )
        # No provenance anywhere: refused, and nothing new is stored.
        with pytest.raises(SensationProvenanceError):
            engine.handle_event(
                {"entity_id": "yrsa", "channel": "arousal", "intensity": 9.0}
            )
        comp = world.get_component("yrsa", "sensation")
        assert comp.get_reading("arousal").intensity == 4.0
        # Malformed payloads are refused too.
        with pytest.raises(ValueError):
            engine.handle_event({"entity_id": "yrsa"}, source="aurelia")

    def test_bus_ingestion_records_refusals_without_raising(self):
        world = World("w")
        bus = EventBus()
        engine = SensationEngine(world, bus=bus)
        _embodied(world, engine)
        engine.attach_to_bus(bus)
        bus.publish(
            "sense.report",
            {"entity_id": "yrsa", "channel": "arousal", "intensity": 2.0},
            source="aurelia",
        )
        bus.publish(
            "sense.report",
            {"entity_id": "yrsa", "channel": "arousal", "intensity": 9.0},
            source="",
        )
        comp = world.get_component("yrsa", "sensation")
        assert comp.get_reading("arousal").intensity == 2.0  # only the attributed one
        assert len(engine.refusals) == 1
        assert "Provenance" in engine.refusals[0]["reason"]

    def test_unattributed_sensation_observation_refused_by_writeback_and_promoter(self):
        store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
        writeback = WritebackEngine(store)
        # The writeback boundary (C3 gate, D2-extended kind):
        with pytest.raises(UnattributedUtteranceError):
            writeback.write_observation(
                title="sensation spike: arousal",
                summary="an unattributed spike",
                observation_kind="sensation",
            )
        assert store.all() == []
        # Attributed writes land...
        record = writeback.write_observation(
            title="sensation spike: arousal",
            summary="yrsa felt sensation spike on 'arousal'",
            observation_kind="sensation",
            speaker_id="yrsa",
            participants=["yrsa"],
        )
        record.truth.confidence = 0.95
        record.lifecycle.access_count = 5
        store.add(record)
        assert MemoryPromoter(store).is_eligible(record)
        # ...but strip the attribution and the promoter gate refuses,
        # however the record reached the store (the second gate).
        record.content.structured_payload.speaker_id = None
        record.content.structured_payload.participants = []
        store.add(record)
        assert not MemoryPromoter(store).is_eligible(record)


# ---------------------------------------------------------------------------
# Spikes (observations) vs persistent states (anchored facts)
# ---------------------------------------------------------------------------


class TestSpikeAndPromotion:
    def test_spike_emits_event_and_writes_attributed_observation(self):
        world = World("w")
        bus, seen = _bus_with_sense_topics()
        store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
        engine = SensationEngine(
            world, bus=bus, writeback=WritebackEngine(store), spike_delta=0.5
        )
        _embodied(world, engine)
        engine.record_reading("yrsa", "arousal", 2.0, at=T0, scale="0-10")
        engine.record_reading("yrsa", "arousal", 2.2, at=T0 + timedelta(seconds=5), scale="0-10")
        engine.record_reading("yrsa", "arousal", 8.0, at=T0 + timedelta(seconds=9), scale="0-10")
        topics = [env.topic for env in seen]
        assert topics.count("sense.reading") == 3
        assert topics.count("sense.spike") == 1  # only the 2.2 -> 8.0 jump
        spike_env = next(env for env in seen if env.topic == "sense.spike")
        assert spike_env.payload["previous_intensity"] == 2.2
        assert spike_env.payload["intensity"] == 8.0
        records = store.all()
        assert len(records) == 1  # the spike, and only the spike, is an observation
        payload = records[0].content.structured_payload
        assert payload.observation_kind.value == "sensation"
        assert payload.speaker_id == "yrsa"

    def test_caller_flagged_spike_without_delta_configuration(self):
        world = World("w")
        bus, seen = _bus_with_sense_topics()
        engine = SensationEngine(world, bus=bus)  # no spike_delta: WYRD sets none
        _embodied(world, engine)
        engine.record_reading("yrsa", "tingle:left_thigh", 0.3, at=T0)
        engine.record_reading("yrsa", "tingle:left_thigh", 0.4, at=T0, spike=True)
        topics = [env.topic for env in seen]
        assert topics.count("sense.spike") == 1

    def test_persistent_state_promotes_to_anchored_fact_exactly_once(self):
        world = World("w")
        bus, seen = _bus_with_sense_topics()
        engine = SensationEngine(
            world, bus=bus, persistence_window_seconds=60.0, fact_ttl_seconds=600.0
        )
        _embodied(world, engine)
        engine.record_reading("yrsa", "soreness", 0.4, at=T0, scale="0-1")
        # Not yet persistent at +30s; a spike alone never promotes.
        assert engine.promote_persistent_states(T0 + timedelta(seconds=30)) == []
        engine.record_reading("yrsa", "soreness", 0.5, at=T0 + timedelta(seconds=45), scale="0-1")
        promoted = engine.promote_persistent_states(T0 + timedelta(seconds=61))
        fact_id = body_state_fact_id("yrsa", "soreness")
        assert promoted == [fact_id]
        fact = world.get_component(fact_id, "body_state_fact")
        assert isinstance(fact, BodyStateFactComponent)
        assert fact.subject_entity_id == "yrsa" and fact.channel == "soreness"
        assert fact.since == T0  # the episode start, not the latest reading
        anchor = world.get_component(fact_id, "temporal_anchor")
        assert isinstance(anchor, TemporalAnchorComponent)
        assert anchor.valid_from == T0
        assert anchor.valid_until == T0 + timedelta(seconds=61 + 600)
        # Verðandi while the window holds; urðr once it lapses.
        assert anchor.tense_at(T0 + timedelta(seconds=120)) == "verdhandi"
        assert anchor.tense_at(T0 + timedelta(seconds=700)) == "urdhr"
        # Idempotent: the same episode never promotes twice.
        assert engine.promote_persistent_states(T0 + timedelta(seconds=90)) == []
        assert [e.topic for e in seen].count("sense.state_promoted") == 1

    def test_zero_reading_never_promotes(self):
        world = World("w")
        engine = SensationEngine(world, persistence_window_seconds=10.0)
        _embodied(world, engine)
        engine.record_reading("yrsa", "fatigue", 0.0, at=T0)
        assert engine.promote_persistent_states(T0 + timedelta(seconds=3600)) == []

    def test_promoted_fact_expires_exactly_once(self):
        world = World("w")
        bus, seen = _bus_with_sense_topics()
        engine = SensationEngine(
            world, bus=bus, persistence_window_seconds=60.0, fact_ttl_seconds=120.0
        )
        _embodied(world, engine)
        engine.record_reading("yrsa", "afterglow", 0.7, at=T0, scale="0-1")
        fact_id = body_state_fact_id("yrsa", "afterglow")
        assert engine.promote_persistent_states(T0 + timedelta(seconds=60)) == [fact_id]
        # Anchor lapses at T0+180; before that, nothing expires.
        assert engine.tick_expired(T0 + timedelta(seconds=179)) == []
        assert engine.tick_expired(T0 + timedelta(seconds=180)) == [fact_id]
        assert engine.tick_expired(T0 + timedelta(seconds=240)) == []  # exactly once
        assert [e.topic for e in seen].count("sense.state_expired") == 1
        # The expired fact remains as history — expiry is not deletion.
        assert isinstance(
            world.get_component(fact_id, "body_state_fact"), BodyStateFactComponent
        )


# ---------------------------------------------------------------------------
# Oracle freshness honesty
# ---------------------------------------------------------------------------


class TestOracleFreshness:
    def test_fresh_answer_carries_age(self):
        world = World("w")
        engine = SensationEngine(world)
        _embodied(world, engine)
        engine.record_reading("yrsa", "arousal", 5.0, at=T0, scale="0-10")
        result = _oracle(world).get_sensation(
            "yrsa", "arousal", now=T0 + timedelta(seconds=10)
        )
        assert result is not None
        assert result.intensity == 5.0 and result.age_seconds == 10.0
        assert result.status == "fresh" and result.is_stale is False
        assert result.source == "aurelia"

    def test_stale_answer_reads_stale_never_current(self):
        world = World("w")
        engine = SensationEngine(world)
        _embodied(world, engine)
        engine.record_reading("yrsa", "arousal", 5.0, at=T0, scale="0-10")
        oracle = _oracle(world)
        later = T0 + timedelta(minutes=5)
        result = oracle.get_sensation("yrsa", "arousal", now=later)
        assert result is not None
        assert result.age_seconds == 300.0
        assert result.status == "stale" and result.is_stale is True
        # A caller-named wider window honestly re-judges the same age.
        wide = oracle.get_sensation(
            "yrsa", "arousal", now=later, stale_after_seconds=600.0
        )
        assert wide is not None and wide.status == "fresh" and wide.age_seconds == 300.0

    def test_missing_and_unembodied_read_as_absent(self):
        world = World("w")
        engine = SensationEngine(world)
        _embodied(world, engine)
        world.create_entity(entity_id="statue")
        oracle = _oracle(world)
        assert oracle.get_sensation("yrsa", "arousal", now=T0) is None
        assert oracle.get_sensations("yrsa", now=T0) == []
        assert oracle.get_sensation("statue", "arousal", now=T0) is None
        assert oracle.get_reported_sensations("statue", now=T0) == []

    def test_get_sensations_lists_all_felt_with_promoted_until(self):
        world = World("w")
        engine = SensationEngine(world, persistence_window_seconds=60.0)
        _embodied(world, engine)
        engine.record_reading("yrsa", "soreness", 0.4, at=T0, scale="0-1")
        # Arousal's episode starts later, so at promotion time only
        # soreness's episode is old enough to count as persistent.
        engine.record_reading(
            "yrsa", "arousal", 3.0, at=T0 + timedelta(seconds=30), scale="0-10"
        )
        engine.promote_persistent_states(T0 + timedelta(seconds=61))
        results = _oracle(world).get_sensations("yrsa", now=T0 + timedelta(seconds=70))
        assert [r.channel for r in results] == ["arousal", "soreness"]
        by_channel = {r.channel: r for r in results}
        assert by_channel["arousal"].promoted_until is None
        assert by_channel["soreness"].promoted_until == T0 + timedelta(seconds=61 + 600)


# ---------------------------------------------------------------------------
# Felt vs reported — the MTOM firewall
# ---------------------------------------------------------------------------


class TestFeltVsReported:
    def test_report_never_overwrites_or_poses_as_felt(self):
        world = World("w")
        engine = SensationEngine(world)
        _embodied(world, engine)
        engine.record_reading("yrsa", "soreness", 0.2, at=T0, scale="0-1")
        engine.record_reading(
            "yrsa", "soreness", 0.9, at=T0, origin="reported", reporter_id="volmarr"
        )
        comp = world.get_component("yrsa", "sensation")
        assert comp.get_reading("soreness").intensity == 0.2  # felt untouched
        reported = comp.get_reported("soreness")
        assert len(reported) == 1 and reported[0].reporter_id == "volmarr"
        oracle = _oracle(world)
        felt = oracle.get_sensation("yrsa", "soreness", now=T0)
        assert felt is not None and felt.intensity == 0.2
        claims = oracle.get_reported_sensations("yrsa", now=T0)
        assert len(claims) == 1
        assert claims[0].intensity == 0.9 and claims[0].reporter_id == "volmarr"
        # get_sensations (felt surface) contains no reported claim.
        assert [r.channel for r in oracle.get_sensations("yrsa", now=T0)] == ["soreness"]
        assert oracle.get_sensations("yrsa", now=T0)[0].intensity == 0.2

    def test_self_report_and_reporterless_claims_refused(self):
        comp = SensationComponent(entity_id="yrsa")
        with pytest.raises(ValueError):
            comp.set_reported_reading(SensationReading(
                channel="soreness", intensity=0.5, origin="reported",
                reporter_id="yrsa", updated_at=T0))
        with pytest.raises(ValueError):
            comp.set_reported_reading(SensationReading(
                channel="soreness", intensity=0.5, origin="reported",
                reporter_id=None, updated_at=T0))
        # And a felt reading cannot be smuggled into the reported store.
        with pytest.raises(ValueError):
            comp.set_reported_reading(SensationReading(
                channel="soreness", intensity=0.5, origin="felt", updated_at=T0))


# ---------------------------------------------------------------------------
# Persistence round-trip
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_full_body_state_round_trips(self, tmp_path):
        world = World("w")
        engine = SensationEngine(world, persistence_window_seconds=60.0)
        _embodied(world, engine)
        engine.record_reading("yrsa", "arousal", 6.5, at=T0, scale="0-10")
        engine.record_reading("yrsa", "soreness", 0.4, at=T0, scale="0-1")
        engine.record_reading(
            "yrsa", "soreness", 0.9, at=T0, origin="reported", reporter_id="volmarr"
        )
        fact_id = body_state_fact_id("yrsa", "soreness")
        # Both positive channels' episodes are 61 s old at promotion
        # time, so both promote (channel-sorted fact ids).
        assert engine.promote_persistent_states(T0 + timedelta(seconds=61)) == [
            body_state_fact_id("yrsa", "arousal"),
            fact_id,
        ]

        store = WorldStore(str(tmp_path / "world.db"))
        store.save(world)
        loaded = store.load("w")

        embodiment = loaded.get_component("yrsa", "embodiment")
        assert isinstance(embodiment, EmbodimentComponent)
        assert embodiment.body_id == "aurelia-main"
        comp = loaded.get_component("yrsa", "sensation")
        assert isinstance(comp, SensationComponent)
        assert comp.get_reading("arousal").intensity == 6.5
        assert comp.get_reading("arousal").scale == "0-10"
        assert comp.get_reading("soreness").episode_started_at == T0
        assert comp.get_reported("soreness")[0].reporter_id == "volmarr"
        fact = loaded.get_component(fact_id, "body_state_fact")
        assert isinstance(fact, BodyStateFactComponent)
        assert fact.subject_entity_id == "yrsa" and fact.since == T0
        anchor = loaded.get_component(fact_id, "temporal_anchor")
        assert isinstance(anchor, TemporalAnchorComponent)
        assert anchor.valid_until == T0 + timedelta(seconds=61 + 600)
        # Freshness still computes honestly off the restored stamps.
        result = PassiveOracle(
            loaded, PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
        ).get_sensation("yrsa", "arousal", now=T0 + timedelta(seconds=30))
        assert result is not None and result.status == "fresh"
        assert result.age_seconds == 30.0
