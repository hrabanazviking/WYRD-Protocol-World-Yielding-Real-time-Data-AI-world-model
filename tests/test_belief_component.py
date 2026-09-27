"""Track 3 P1 (Slice 6 D1-A) — regression tests for the O(1) BeliefComponent.

SLICE6-F1 replaced the linear-scan belief list with a private
subject-keyed ordered dict (the public ``beliefs`` list is now a
computed view). These tests pin the behavior contract so the
optimization cannot silently change semantics:

- lookup by subject (get_belief)
- revision replaces and moves the belief to the end (order)
- retraction removes and reports correctly
- JSON serialization shape is unchanged ({"beliefs": [...]})
- deserialization (world_store round-trip) rebuilds the index
- duplicate subjects in stored data: last wins, moved to end
"""

from __future__ import annotations

import json

from wyrdforge.ecs.component import deserialize_component
from wyrdforge.ecs.components.theory_of_mind import BeliefComponent


def _make() -> BeliefComponent:
    bc = BeliefComponent(entity_id="e1")
    bc.update_belief("s1", "claim one", 0.9, "observed")
    bc.update_belief("s2", "claim two", 0.5, "assumed")
    return bc


def test_lookup_hit_and_miss():
    bc = _make()
    assert bc.get_belief("s1").claim == "claim one"
    assert bc.get_belief("s2").confidence == 0.5
    assert bc.get_belief("nope") is None


def test_revision_replaces_and_moves_to_end():
    bc = _make()
    bc.update_belief("s1", "claim one revised", 0.8, "observed")
    # Same observable order as the old remove-then-append.
    assert [b.subject for b in bc.beliefs] == ["s2", "s1"]
    assert bc.get_belief("s1").claim == "claim one revised"
    assert bc.get_belief("s1").confidence == 0.8
    assert len(bc.beliefs) == 2  # replaced, not duplicated


def test_retraction():
    bc = _make()
    assert bc.retract_belief("s1") is True
    assert bc.get_belief("s1") is None
    assert [b.subject for b in bc.beliefs] == ["s2"]
    assert bc.retract_belief("s1") is False  # already gone


def test_serialization_shape_unchanged():
    bc = _make()
    data = json.loads(bc.model_dump_json())
    assert set(data) >= {"component_type", "entity_id", "beliefs"}
    assert data["component_type"] == "beliefs"
    assert isinstance(data["beliefs"], list)
    assert [b["subject"] for b in data["beliefs"]] == ["s1", "s2"]


def test_deserialization_rebuilds_index():
    bc = _make()
    bc.update_belief("s1", "revised", 0.8, "observed")
    data = json.loads(bc.model_dump_json())
    bc2 = deserialize_component(data)
    assert isinstance(bc2, BeliefComponent)
    # Index works immediately after the round-trip — no lazy rebuild.
    assert bc2.get_belief("s1").claim == "revised"
    assert bc2.get_belief("s2").claim == "claim two"
    assert [b.subject for b in bc2.beliefs] == ["s2", "s1"]
    # And it stays writable.
    bc2.update_belief("s3", "new", 1.0, "observed")
    assert bc2.get_belief("s3").claim == "new"


def test_deserialization_duplicate_subjects_last_wins():
    bc = _make()
    data = json.loads(bc.model_dump_json())
    # Corrupt the stored list the way the old code never could produce
    # but a hand-edited store might: duplicate subject.
    data["beliefs"].append(dict(data["beliefs"][0]))
    bc2 = deserialize_component(data)
    assert len(bc2.beliefs) == 2
    assert [b.subject for b in bc2.beliefs] == ["s2", "s1"]


def test_model_validate_plain_dict_without_beliefs():
    bc = BeliefComponent.model_validate(
        {"component_type": "beliefs", "entity_id": "e9"})
    assert bc.get_belief("anything") is None
    assert bc.beliefs == []


def test_shallow_copy_isolated():
    # update_belief / retract_belief mutate the private store in place,
    # so a shallow copy must carry its own dict — mutating the copy
    # must not corrupt the original (the old list-rebind writes were
    # copy-safe; this pins that property).
    import copy as _copy

    bc = _make()
    for clone in (bc.model_copy(), _copy.copy(bc)):
        clone.update_belief("s1", "mutated", 0.1, "told")
        clone.retract_belief("s2")
        assert bc.get_belief("s1").claim == "claim one"
        assert bc.get_belief("s2").claim == "claim two"
        assert [b.subject for b in bc.beliefs] == ["s1", "s2"]
