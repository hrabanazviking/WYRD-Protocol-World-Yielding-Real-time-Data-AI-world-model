"""Track 3 P1 — regression tests for the Slice 6 floor-work validation.

Covers the deeper-work changes (authorized 2026-09-27):

- ``_walk_envelope``: the single-traversal fast path enforcing the
  envelope's size cap and depth limit. Every test pins the contract
  against the old two-pass behavior (``_serialized_within_cap`` +
  ``check_depth``): valid payloads pass unchanged, over-depth reports
  the same field path, oversized / non-serializable / cyclic inputs are
  rejected the same way, and the size error keeps precedence over the
  depth error.
- ``World.create_entity_with_component``: the fused anchor
  registration. Pins equivalence with ``create_entity`` +
  ``add_component``, the duplicate-id and entity-id-mismatch guards,
  tag-set copying, and the single-timestamp contract.
- ``VerdandiBridge._add_anchor``: entity and component share one
  wall-clock stamp (was four separate reads).

These are contract tests, not benchmarks: they fail on behavior drift,
never on timing.
"""

from __future__ import annotations

import json
import random

import pytest

from wyrdforge.bridges.verdandi_bridge import VerdandiBridge
from wyrdforge.ecs.components.temporal import TemporalAnchorComponent
from wyrdforge.ecs.entity import Entity
from wyrdforge.ecs.world import World
from wyrdforge.hardening.input_validation import (
    MAX_EVENT_BYTES,
    MAX_EVENT_DEPTH,
    InputValidationError,
    _fits_byte_cap,
    _serialized_within_cap,
    _walk_envelope,
    check_depth,
    validate_event_envelope,
)


def _rejects(fn, *args, **kwargs) -> InputValidationError:
    with pytest.raises(InputValidationError) as excinfo:
        fn(*args, **kwargs)
    return excinfo.value


# ---------------------------------------------------------------------------
# _walk_envelope: valid-input behavior unchanged
# ---------------------------------------------------------------------------

class TestWalkEnvelopeValid:
    @pytest.mark.parametrize("payload", [
        {},
        {"a": 1},
        {"speaker": "volmarr", "text": "hello", "emotion": ["warm"]},
        {"after": {"valence": 0.6, "energy": 0.5}, "why": "x" * 100},
        {"n": None, "t": True, "f": False, "i": -7, "fl": 2.5,
         "s": "héllo ☃", "l": [1, "two", None], "t2": (1, 2)},
        {"nan": float("nan"), "inf": float("inf"), "ninf": float("-inf")},
        {1: "int-key", 1.5: "float-key", True: "bool-key", None: "none-key"},
    ])
    def test_valid_payloads_pass(self, payload):
        assert _walk_envelope(payload, max_bytes=MAX_EVENT_BYTES,
                              max_depth=MAX_EVENT_DEPTH, field="payload") is True
        assert validate_event_envelope("utterance", payload) is payload

    def test_depth_exactly_at_limit_passes(self):
        # MAX_EVENT_DEPTH nested dicts: depth == limit is allowed.
        payload: dict = {}
        cur = payload
        for _ in range(MAX_EVENT_DEPTH - 1):
            cur["n"] = {}
            cur = cur["n"]
        cur["leaf"] = 1
        assert validate_event_envelope("t", payload) is payload

    def test_size_exactly_at_cap_passes(self):
        # Serialized length exactly MAX_EVENT_BYTES is allowed.
        payload = {"data": ""}
        padding = MAX_EVENT_BYTES - len(json.dumps(payload, default=str))
        payload["data"] = "x" * padding
        assert len(json.dumps(payload, default=str)) == MAX_EVENT_BYTES
        assert validate_event_envelope("t", payload) is payload


# ---------------------------------------------------------------------------
# _walk_envelope: rejection behavior unchanged
# ---------------------------------------------------------------------------

class TestWalkEnvelopeReject:
    def test_over_depth_field_path_preserved(self):
        err = _rejects(validate_event_envelope, "t",
                       {"a": {"b": [{"c": 1}]}},
                       max_depth=2)
        assert err.field == "payload.a.b"
        assert err.reason == "nesting depth exceeds 2"

    def test_over_depth_root_path(self):
        err = _rejects(validate_event_envelope, "t", {"a": 1}, max_depth=0)
        assert err.field == "payload"
        assert err.reason == "nesting depth exceeds 0"

    def test_one_over_depth_limit_rejected(self):
        payload: dict = {}
        cur = payload
        for _ in range(MAX_EVENT_DEPTH):
            cur["n"] = {}
            cur = cur["n"]
        cur["leaf"] = 1
        err = _rejects(validate_event_envelope, "t", payload)
        assert err.reason == f"nesting depth exceeds {MAX_EVENT_DEPTH}"

    def test_oversized_rejected(self):
        err = _rejects(validate_event_envelope, "t",
                       {"data": "x" * (MAX_EVENT_BYTES + 1)})
        assert err.field == "payload"
        assert err.reason == f"exceeds {MAX_EVENT_BYTES} bytes serialized"

    def test_non_serializable_rejected_as_oversized(self):
        # default=str cannot stringify a tuple key: dumps raises TypeError.
        err = _rejects(validate_event_envelope, "t", {"data": {(1, 2): 3}})
        assert err.field == "payload"
        assert err.reason == f"exceeds {MAX_EVENT_BYTES} bytes serialized"

    def test_cyclic_rejected(self):
        cyc: dict = {}
        cyc["self"] = cyc
        err = _rejects(validate_event_envelope, "t", {"data": cyc})
        # Unchanged from the two-pass behavior: the circular reference
        # makes json.dumps raise ValueError, which the size gate treats
        # as over the cap — before the depth walk ever runs.
        assert err.field == "payload"
        assert err.reason == f"exceeds {MAX_EVENT_BYTES} bytes serialized"

    def test_size_error_takes_precedence_over_depth(self):
        payload = {"data": "x" * (MAX_EVENT_BYTES + 1)}
        deep: dict = payload
        for _ in range(MAX_EVENT_DEPTH + 5):
            deep["n"] = {}
            deep = deep["n"]
        err = _rejects(validate_event_envelope, "t", payload)
        assert err.reason == f"exceeds {MAX_EVENT_BYTES} bytes serialized"

    def test_non_dict_payload_rejected(self):
        err = _rejects(validate_event_envelope, "t", [1, 2, 3])
        assert err.field == "payload"
        assert "must be a JSON object" in err.reason

    def test_empty_event_type_rejected(self):
        _rejects(validate_event_envelope, "", {"a": 1})


# ---------------------------------------------------------------------------
# _walk_envelope: the inconclusive path falls back exactly
# ---------------------------------------------------------------------------

class TestWalkEnvelopeFallback:
    def test_exotic_but_small_and_valid_is_accepted(self):
        # object() defeats the bound (default=str applies) — the exact
        # measurement must then accept it, exactly as the two-pass code did.
        payload = {"data": object()}
        assert _walk_envelope(payload, max_bytes=MAX_EVENT_BYTES,
                              max_depth=MAX_EVENT_DEPTH,
                              field="payload") is False
        assert validate_event_envelope("t", payload) is payload

    def test_bound_never_under_estimates(self):
        # Property: whenever the fast path says "fits", the exact
        # measurement agrees. (The reverse need not hold — the bound
        # over-estimates by design.)
        rng = random.Random(20260927)

        def rand(d=0):
            r = rng.random()
            if d > 3 or r < 0.4:
                return rng.choice([None, True, False, 0, 5, 2.5,
                                   float("nan"), "", "x" * rng.randint(0, 30)])
            if r < 0.7:
                return {f"k{i}": rand(d + 1)
                        for i in range(rng.randint(0, 4))}
            return [rand(d + 1) for _ in range(rng.randint(0, 4))]

        for _ in range(500):
            payload = {"data": rand()}
            exact = len(json.dumps(payload, default=str))
            if _fits_byte_cap(payload, MAX_EVENT_BYTES):
                assert exact <= MAX_EVENT_BYTES
            assert (_serialized_within_cap(payload, MAX_EVENT_BYTES)
                    == (exact <= MAX_EVENT_BYTES))

    def test_walk_agrees_with_two_pass_on_adversarial(self):
        # Differential: the fused walk's verdict (True/False/raise) must
        # match the old two-pass sequence on hostile shapes.
        def old_verdict(payload, **kw):
            try:
                if not _serialized_within_cap(
                        payload, kw.get("max_bytes", MAX_EVENT_BYTES)):
                    return ("err", "payload",
                            f"exceeds {kw.get('max_bytes', MAX_EVENT_BYTES)} "
                            "bytes serialized")
                check_depth(payload,
                            max_depth=kw.get("max_depth", MAX_EVENT_DEPTH),
                            field="payload")
                return ("ok",)
            except InputValidationError as e:
                return ("err", e.field, e.reason)

        def new_verdict(payload, **kw):
            try:
                fast = _walk_envelope(
                    payload,
                    max_bytes=kw.get("max_bytes", MAX_EVENT_BYTES),
                    max_depth=kw.get("max_depth", MAX_EVENT_DEPTH),
                    field="payload")
                return ("fast-ok",) if fast else ("inconclusive",)
            except InputValidationError as e:
                return ("err", e.field, e.reason)

        cyc: dict = {}
        cyc["self"] = cyc
        cases = [
            ({"a": 1}, {}),
            ({"a": {"b": {"c": 1}}}, {"max_depth": 2}),
            ({"data": "x" * 3000}, {"max_bytes": 100}),
            ({"data": cyc}, {}),
            ({"data": {(1, 2): 3}}, {}),
            ({"data": object()}, {}),
        ]
        for payload, kw in cases:
            old = old_verdict(payload, **kw)
            new = new_verdict(payload, **kw)
            if new[0] == "fast-ok":
                # Fast path accepted: the two-pass code must accept too.
                assert old[0] == "ok", (payload, kw, old, new)
            elif new[0] == "err":
                # Fast path raised: identical error to the two-pass code.
                assert old == new, (payload, kw, old, new)
            # "inconclusive" must resolve through the exact path to the
            # same final verdict as the two-pass code:
            try:
                validate_event_envelope("t", payload, **kw)
                assert old[0] == "ok", (payload, kw, old, new)
            except InputValidationError as e:
                assert old == ("err", e.field, e.reason), (payload, kw, old, new)


# ---------------------------------------------------------------------------
# World.create_entity_with_component
# ---------------------------------------------------------------------------

class TestCreateEntityWithComponent:
    def test_equivalent_to_create_plus_add(self):
        from datetime import datetime, timezone
        now = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)

        w1 = World("w1")
        e1 = w1.create_entity(entity_id="e", tags={"a", "b"})
        c1 = TemporalAnchorComponent(entity_id="e", valid_from=now,
                                    observed_at=now, label="x")
        w1.add_component("e", c1)

        w2 = World("w2")
        c2 = TemporalAnchorComponent(entity_id="e", valid_from=now,
                                    observed_at=now, label="x")
        e2 = w2.create_entity_with_component(
            entity_id="e", tags={"a", "b"}, component=c2)

        assert e2.entity_id == e1.entity_id == "e"
        assert e2.tags == e1.tags == {"a", "b"}
        # Both paths stamp via default_factory — datetimes, not the
        # component's stamps.
        assert isinstance(e2.created_at, type(e1.created_at))
        assert isinstance(e2.updated_at, type(e1.updated_at))
        assert w2.get_component("e", "temporal_anchor") is c2
        assert w1.get_component("e", "temporal_anchor") is c1
        # index entries identical
        assert w2._tag_index["a"] == w1._tag_index["a"] == {"e"}
        assert w2._comp_type_index["temporal_anchor"] == \
            w1._comp_type_index["temporal_anchor"] == {"e"}

    def test_stamp_unifies_entity_timestamps(self):
        # Volmarr-authorized 2026-09-27: when a stamp is provided, the
        # entity's created_at and updated_at are BOTH that stamp — one
        # read, not two default-factory reads. The identity check
        # (`is`) pins that no extra datetime was constructed.
        from datetime import datetime, timezone
        stamp = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
        w = World("w")
        comp = TemporalAnchorComponent(entity_id="e", label="x")
        entity = w.create_entity_with_component(
            entity_id="e", tags=set(), component=comp, stamp=stamp)
        assert entity.created_at is stamp
        assert entity.updated_at is stamp
        assert w.get_component("e", "temporal_anchor") is comp

    def test_no_stamp_uses_default_factories(self):
        # Without a stamp the dataclass default factories do their own
        # reads, exactly like create_entity — the old observable
        # behavior is preserved for callers that don't opt in.
        from datetime import datetime, timezone
        before = datetime.now(timezone.utc)
        w = World("w")
        comp = TemporalAnchorComponent(entity_id="e", label="x")
        comp_created = comp.created_at
        entity = w.create_entity_with_component(
            entity_id="e", tags=set(), component=comp)
        after = datetime.now(timezone.utc)
        # Entity timestamps came from default_factory (wall-clock at
        # construction), not from the component's stamps.
        assert before <= entity.created_at <= after
        assert before <= entity.updated_at <= after
        # Component keeps its own construction-time stamps.
        assert comp.created_at == comp_created
        assert w.get_component("e", "temporal_anchor") is comp

    def test_duplicate_entity_id_rejected(self):
        w = World("w")
        comp = TemporalAnchorComponent(entity_id="e")
        w.create_entity_with_component(entity_id="e", tags=set(),
                                       component=comp)
        comp2 = TemporalAnchorComponent(entity_id="e")
        with pytest.raises(ValueError, match="already exists"):
            w.create_entity_with_component(entity_id="e", tags=set(),
                                           component=comp2)

    def test_component_entity_id_mismatch_rejected(self):
        w = World("w")
        comp = TemporalAnchorComponent(entity_id="other")
        with pytest.raises(ValueError, match="does not match"):
            w.create_entity_with_component(entity_id="e", tags=set(),
                                           component=comp)
        assert w.get_entity("e") is None

    def test_tags_are_copied(self):
        w = World("w")
        tags = {"a"}
        comp = TemporalAnchorComponent(entity_id="e")
        entity = w.create_entity_with_component(entity_id="e", tags=tags,
                                                component=comp)
        tags.add("mutated-after")
        assert entity.tags == {"a"}
        assert w._tag_index["a"] == {"e"}
        assert "mutated-after" not in w._tag_index


# ---------------------------------------------------------------------------
# VerdandiBridge._add_anchor: one stamp, not four
# ---------------------------------------------------------------------------

class TestAddAnchorTimestamp:
    def test_anchor_unifies_timestamps(self):
        # Volmarr-authorized 2026-09-27: _add_anchor does ONE wall-clock
        # read and assigns it to all four timestamps (entity
        # created/updated, component created/updated). The
        # microsecond differences between the old four separate reads
        # are implementation noise, not a contract — the meaning
        # ("when the anchor was created") is unchanged. The identity
        # checks pin that no extra datetimes were constructed.
        from datetime import datetime, timezone
        bridge = VerdandiBridge()
        at = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
        before = datetime.now(timezone.utc)
        eid = bridge._add_anchor("test label", at, tags={"t"})
        after = datetime.now(timezone.utc)
        entity = bridge.world.get_entity(eid)
        comp = bridge.world.get_component(eid, "temporal_anchor")
        assert isinstance(entity, Entity)
        assert isinstance(comp, TemporalAnchorComponent)
        assert comp.label == "test label"
        assert comp.valid_from == at
        assert comp.observed_at == at
        # One read shared by all four fields.
        assert entity.created_at is entity.updated_at
        assert comp.created_at is comp.updated_at
        assert entity.created_at is comp.created_at
        assert before <= entity.created_at <= after
        assert eid in bridge.world._tag_index["anchor"]
        assert eid in bridge.world._tag_index["t"]
