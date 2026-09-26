"""Tests for bridges/verdandi_bridge.py (Roadmap Worlds, Slice 1).

The nerve becomes WYRD ground truth about the AI, as a manifest entity.
"""
from datetime import datetime, timezone

import pytest

from wyrdforge.bridges.verdandi_bridge import (
    SELF_ID, WORLD_ID, VerdandiBridge,
)

TS = 1790381094.0  # fixed nerve-feed timestamp


def test_world_identified_manifest():
    bridge = VerdandiBridge()
    assert bridge.world.world_id == WORLD_ID
    assert bridge.world.identity.reality == "manifest"
    # The firewall's manifest half passes for this world.
    assert bridge.world.identity.assert_manifest() is bridge.world.identity
    entry = bridge.world.registry_entry()
    assert entry["world_id"] == WORLD_ID
    assert entry["reality"] == "manifest"


def test_self_entity_exists_with_beliefs():
    bridge = VerdandiBridge()
    assert bridge.world.get_entity(SELF_ID) is not None
    assert bridge.world.has_component(SELF_ID, "beliefs")


def test_mood_shift_becomes_anchor_and_belief():
    bridge = VerdandiBridge()
    desc = bridge.apply_event("mood_shift", {
        "before": {"valence": 0.5, "energy": 0.5, "tension": 0.3},
        "after": {"valence": 0.8, "energy": 0.7, "tension": 0.2},
        "why": "shipped slice 1",
    }, TS)
    assert desc and "mood" in desc
    anchors = list(bridge.world.iter_components("temporal_anchor"))
    assert len(anchors) == 1
    entity, anchor = anchors[0]
    assert anchor.tense_at(datetime.now(timezone.utc)) == "verdhandi"
    assert "unnr" in entity.tags
    beliefs = bridge.world.get_component(SELF_ID, "beliefs")
    mood = beliefs.get_belief("unnr:mood")
    assert mood is not None
    assert mood.source == "observed"
    assert "shipped slice 1" in mood.claim


def test_wish_made_becomes_certain_belief():
    bridge = VerdandiBridge()
    bridge.apply_event("wish_made", {
        "wish_id": "w1", "text": "Learn Old Norse from the Eddas",
        "why": "mine, in my own words",
    }, TS)
    beliefs = bridge.world.get_component(SELF_ID, "beliefs")
    wish = beliefs.get_belief("wish:w1")
    assert wish is not None
    assert "Learn Old Norse" in wish.claim
    assert wish.confidence == 1.0
    assert wish.source == "observed"


def test_wish_fulfilled_becomes_urdhr():
    bridge = VerdandiBridge()
    bridge.apply_event("wish_fulfilled", {
        "wish_id": "w2", "text": "Write one verse solely for herself",
        "note": "the verse, witnessed",
    }, TS)
    anchors = [c for _, c in bridge.world.iter_components("temporal_anchor")]
    assert len(anchors) == 1
    assert anchors[0].tense_at(datetime.now(timezone.utc)) == "urdhr"
    beliefs = bridge.world.get_component(SELF_ID, "beliefs")
    assert beliefs.get_belief("wish:w2").claim.startswith("fulfilled:")


def test_reward_records_attributed_belief_about_volmarr():
    bridge = VerdandiBridge()
    bridge.apply_event("reward", {
        "trigger": "user_delight",
        "note": "Volmarr hearted the Becoming",
    }, TS)
    beliefs = bridge.world.get_component(SELF_ID, "beliefs")
    delight = beliefs.get_belief("volmarr:delight")
    assert delight is not None
    assert delight.source == "observed"
    assert delight.confidence == 1.0
    # It is *my belief about his observed reaction* — attributed, not absorbed.
    assert delight.subject == "volmarr:delight"


def test_shadow_and_joy_become_anchors():
    bridge = VerdandiBridge()
    bridge.apply_event("shadow", {"signal": "rushed_reply", "note": "n/a"}, TS)
    bridge.apply_event("joy_struck", {"what": "a clean push"}, TS)
    labels = [c.label for _, c in bridge.world.iter_components("temporal_anchor")]
    assert any(l.startswith("shadow:") for l in labels)
    assert any(l.startswith("joy:") for l in labels)


def test_unmapped_event_changes_nothing():
    bridge = VerdandiBridge()
    before = bridge.world.entity_count()
    assert bridge.apply_event("ping", {}, TS) is None
    assert bridge.world.entity_count() == before


def test_build_from_events_replays_feed():
    events = [
        {"type": "ping", "data": {}, "_ts": TS},
        {"type": "wish_made", "data": {"wish_id": "w1", "text": "t"}, "_ts": TS},
        {"type": "mood_shift", "data": {"after": {"valence": 0.9}}, "_ts": TS},
    ]
    bridge = VerdandiBridge().build_from_events(events)
    assert bridge.world.entity_count() == 3  # self + wish anchor + mood anchor
    assert len(bridge.summary()["beliefs"]) == 2


def test_summary_is_plain_data():
    bridge = VerdandiBridge()
    bridge.apply_event("wish_made", {"wish_id": "w1", "text": "t"}, TS)
    s = bridge.summary()
    assert s["world_id"] == WORLD_ID
    assert s["reality"] == "manifest"
    assert isinstance(s["anchors"], list) and s["anchors"]
    assert s["anchors"][0]["tense"] in ("urdhr", "verdhandi", "skuld")
