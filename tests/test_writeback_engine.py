"""Tests for WritebackEngine — all five record-type writers + process_turn."""
from __future__ import annotations

import tempfile

import pytest

from wyrdforge.models.common import RetentionClass, StoreName, WritePolicy
from wyrdforge.models.memory import (
    CanonicalFactRecord,
    EpisodeSummaryRecord,
    ObservationRecord,
    PolicyRecord,
)
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.services.writeback_engine import WritebackEngine


def _setup() -> tuple[PersistentMemoryStore, WritebackEngine]:
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    engine = WritebackEngine(store)
    return store, engine


# ---------------------------------------------------------------------------
# write_observation
# ---------------------------------------------------------------------------

def test_write_observation_returns_observation_record() -> None:
    store, engine = _setup()
    record = engine.write_observation(title="Gunnar speaks", summary="He said hello")
    assert isinstance(record, ObservationRecord)


def test_write_observation_persists_to_store() -> None:
    store, engine = _setup()
    record = engine.write_observation(title="Gunnar speaks", summary="He said hello")
    loaded = store.get(record.record_id)
    assert loaded is not None
    assert loaded.record_id == record.record_id


def test_write_observation_uses_hugin_store() -> None:
    store, engine = _setup()
    engine.write_observation(title="Gunnar speaks", summary="He said hello")
    hugin_records = store.all(store=StoreName.HUGIN.value)
    assert len(hugin_records) >= 1


def test_write_observation_is_ephemeral() -> None:
    store, engine = _setup()
    record = engine.write_observation(title="Test", summary="Test summary")
    assert record.lifecycle.write_policy == WritePolicy.EPHEMERAL


def test_write_observation_short_retention() -> None:
    store, engine = _setup()
    record = engine.write_observation(title="Test", summary="Test summary")
    assert record.lifecycle.retention_class == RetentionClass.SHORT


def test_write_observation_sets_participants() -> None:
    store, engine = _setup()
    record = engine.write_observation(
        title="Council", summary="They met", participants=["gunnar", "sigrid"]
    )
    assert "gunnar" in record.content.structured_payload.participants
    assert "sigrid" in record.content.structured_payload.participants


def test_write_observation_sets_place_id() -> None:
    store, engine = _setup()
    record = engine.write_observation(
        title="Meeting", summary="At the hall", place_id="mead_hall"
    )
    assert record.content.structured_payload.place_id == "mead_hall"


def test_write_observation_salience_sets_priority() -> None:
    store, engine = _setup()
    record = engine.write_observation(title="T", summary="S", salience=0.9)
    assert record.retrieval.default_priority == 0.9


# ---------------------------------------------------------------------------
# write_episode_summary
# ---------------------------------------------------------------------------

def test_write_episode_summary_returns_episode_record() -> None:
    store, engine = _setup()
    record = engine.write_episode_summary(title="The Raid", summary="Gunnar led a raid")
    assert isinstance(record, EpisodeSummaryRecord)


def test_write_episode_summary_persists_to_store() -> None:
    store, engine = _setup()
    record = engine.write_episode_summary(title="The Raid", summary="Gunnar led a raid")
    loaded = store.get(record.record_id)
    assert loaded is not None


def test_write_episode_summary_uses_munin_store() -> None:
    store, engine = _setup()
    engine.write_episode_summary(title="The Raid", summary="Gunnar led a raid")
    munin_records = store.all(store=StoreName.MUNIN.value)
    assert len(munin_records) >= 1


def test_write_episode_summary_carries_major_events() -> None:
    store, engine = _setup()
    events = ["Gunnar won the duel", "Hall burned"]
    record = engine.write_episode_summary(
        title="Episode 1", summary="Things happened", major_events=events
    )
    assert record.content.structured_payload.major_events == events


def test_write_episode_summary_carries_open_threads() -> None:
    store, engine = _setup()
    threads = ["Who lit the fire?"]
    record = engine.write_episode_summary(
        title="Episode 1", summary="Things happened", open_threads=threads
    )
    assert record.content.structured_payload.open_threads == threads


# ---------------------------------------------------------------------------
# write_canonical_fact
# ---------------------------------------------------------------------------

def test_write_canonical_fact_returns_canonical_fact_record() -> None:
    store, engine = _setup()
    record = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="faction", fact_value="thornholt"
    )
    assert isinstance(record, CanonicalFactRecord)


def test_write_canonical_fact_persists_to_store() -> None:
    store, engine = _setup()
    record = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="faction", fact_value="thornholt"
    )
    loaded = store.get(record.record_id)
    assert loaded is not None


def test_write_canonical_fact_uses_mimir_store() -> None:
    store, engine = _setup()
    engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="faction", fact_value="thornholt"
    )
    mimir_records = store.all(store=StoreName.MIMIR.value)
    assert len(mimir_records) >= 1


def test_write_canonical_fact_payload_fields() -> None:
    store, engine = _setup()
    record = engine.write_canonical_fact(
        fact_subject_id="sigrid", fact_key="role", fact_value="völva", domain="character"
    )
    payload = record.content.structured_payload
    assert payload.fact_subject_id == "sigrid"
    assert payload.fact_key == "role"
    assert payload.fact_value == "völva"
    assert payload.domain == "character"


def test_write_canonical_fact_confidence() -> None:
    store, engine = _setup()
    record = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="status", fact_value="alive", confidence=0.95
    )
    assert record.truth.confidence == 0.95


def test_write_canonical_fact_long_retention() -> None:
    store, engine = _setup()
    record = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="status", fact_value="alive"
    )
    assert record.lifecycle.retention_class == RetentionClass.LONG


# ---------------------------------------------------------------------------
# write_policy
# ---------------------------------------------------------------------------

def test_write_policy_returns_policy_record() -> None:
    store, engine = _setup()
    record = engine.write_policy(
        title="No lying", rule_text="Characters must not speak falsehood"
    )
    assert isinstance(record, PolicyRecord)


def test_write_policy_persists_to_store() -> None:
    store, engine = _setup()
    record = engine.write_policy(
        title="No lying", rule_text="Characters must not speak falsehood"
    )
    loaded = store.get(record.record_id)
    assert loaded is not None


def test_write_policy_uses_orlog_store() -> None:
    store, engine = _setup()
    engine.write_policy(title="No lying", rule_text="Characters must not speak falsehood")
    orlog_records = store.all(store=StoreName.ORLOG.value)
    assert len(orlog_records) >= 1


def test_write_policy_is_immutable() -> None:
    store, engine = _setup()
    record = engine.write_policy(
        title="Honor rule", rule_text="Always act with honor"
    )
    assert record.lifecycle.write_policy == WritePolicy.IMMUTABLE


def test_write_policy_high_confidence() -> None:
    store, engine = _setup()
    record = engine.write_policy(
        title="Honor rule", rule_text="Always act with honor"
    )
    assert record.truth.confidence >= 0.9


def test_write_policy_applies_to_domains() -> None:
    store, engine = _setup()
    record = engine.write_policy(
        title="Combat rule",
        rule_text="No surprise attacks at feasts",
        applies_to_domains=["combat", "social"],
    )
    payload = record.content.structured_payload
    assert "combat" in payload.applies_to_domains
    assert "social" in payload.applies_to_domains


# ---------------------------------------------------------------------------
# process_turn
# ---------------------------------------------------------------------------

def test_process_turn_returns_dict_with_observations_and_facts() -> None:
    store, engine = _setup()
    result = engine.process_turn(
        user_input="Gunnar walks in",
        response_text="He nods at the fire",
    )
    assert "observations" in result
    assert "facts" in result


def test_process_turn_always_creates_observation() -> None:
    store, engine = _setup()
    result = engine.process_turn(
        user_input="Something happened",
        response_text="And something was said",
    )
    assert len(result["observations"]) == 1
    assert isinstance(result["observations"][0], ObservationRecord)


def test_process_turn_no_facts_by_default() -> None:
    store, engine = _setup()
    result = engine.process_turn(
        user_input="Hello",
        response_text="Hello back",
    )
    assert result["facts"] == []


def test_process_turn_writes_provided_facts() -> None:
    store, engine = _setup()
    result = engine.process_turn(
        user_input="Gunnar is a warrior",
        response_text="Noted",
        facts=[
            {"fact_subject_id": "gunnar", "fact_key": "role", "fact_value": "warrior"},
            {"fact_subject_id": "gunnar", "fact_key": "faction", "fact_value": "thornholt"},
        ],
    )
    assert len(result["facts"]) == 2
    assert all(isinstance(f, CanonicalFactRecord) for f in result["facts"])


def test_process_turn_facts_use_provided_confidence() -> None:
    store, engine = _setup()
    result = engine.process_turn(
        user_input="Test",
        response_text="Test",
        facts=[
            {
                "fact_subject_id": "gunnar",
                "fact_key": "status",
                "fact_value": "alive",
                "confidence": 0.99,
            }
        ],
    )
    assert result["facts"][0].truth.confidence == 0.99


def test_process_turn_persists_all_records() -> None:
    store, engine = _setup()
    result = engine.process_turn(
        user_input="Turn text",
        response_text="Response text",
        facts=[
            {"fact_subject_id": "sigrid", "fact_key": "location", "fact_value": "hall"}
        ],
    )
    obs_id = result["observations"][0].record_id
    fact_id = result["facts"][0].record_id
    assert store.get(obs_id) is not None
    assert store.get(fact_id) is not None
