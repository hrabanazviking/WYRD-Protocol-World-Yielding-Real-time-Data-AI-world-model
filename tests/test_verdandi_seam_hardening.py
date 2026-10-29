"""Phase D6 tests — Verdandi seam hardening.

The seam between Verðandi (nervous system) and WYRD (world model) is a
contract, not a habit. D6 pins its four hardening items:

1. **Versioned nerve-feed schema** — the event→mutation translation
   table is explicit (``NERVE_FEED_TRANSLATION_TABLE``) and pinned
   against the live handler map and the benchmark fixture builders;
   the pre-version feed shape IS schema v1 and keeps replaying;
   entries declaring an unsupported/malformed version are quarantined
   loudly (recorded verbatim + counted), never silently
   mis-translated.
2. **Shared contract tests** — ``tests/fixtures/nerve_feed_contract_v1.json``
   carries one case per mapped event kind (envelope → mirror
   mutations), written in plain JSON so the Verðandi repo's suite can
   run the same fixtures (see docs/specs/verdandi-nerve-feed.md for
   the adoption path). These tests live in ``tests/``, which the
   repo's CI already runs (``pytest tests/`` in ci.yml — manual-only
   per Volmarr's standing rule; no trigger was touched).
3. **Mirror-lag health metric** — ``mirror_health()`` reports seen /
   mapped / unmapped / refused / torn / quarantined counts plus the
   newest feed vs mirror watermarks and the lag between them.
4. **Pinned replay determinism** — the same feed window replays to
   the same mirror, twice, and after intervening unrelated state:
   the projection doctrine's load-bearing claim, as a test.

Identity law held throughout (§8): Verðandi stays world-agnostic,
WYRD stays nerve-agnostic, the EventBus never crosses the boundary,
and no signature changed anywhere.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.perf_fixtures import _payload_builders
from wyrdforge.bridges import verdandi_bridge as vb
from wyrdforge.bridges.verdandi_bridge import (
    SELF_ID,
    VerdandiBridge,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "nerve_feed_contract_v1.json"
TS = 1790381094.0  # fixed nerve-feed timestamp (2026-09-26)
# Tense expectations are judged well after every fixture timestamp, so
# verdhandi (open-ended) and urdhr (ended-at-start) read stably.
EVAL_AT = datetime(2027, 1, 1, tzinfo=timezone.utc)


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. The versioned schema: constants, validation, translation table
# ---------------------------------------------------------------------------

def test_schema_constants_pin_v1():
    assert vb.NERVE_FEED_SCHEMA_NAME == "wyrd-nerve-feed"
    assert vb.NERVE_FEED_SCHEMA_VERSION == 1
    assert vb.SUPPORTED_NERVE_FEED_SCHEMA_VERSIONS == (1,)
    assert vb.FEED_SCHEMA_FIELD == "schema"


def test_validate_feed_entry_accepts_the_v1_shape():
    # Undeclared — the shape every existing feed file has.
    assert vb.validate_feed_entry({"type": "wish_made", "data": {}}) == 1
    # Explicitly declared v1.
    assert vb.validate_feed_entry({"schema": 1, "type": "ping"}) == 1
    # The hub-stamped envelope, exactly as nervous_system.py writes it.
    assert vb.validate_feed_entry({
        "type": "utterance", "data": {"speaker": "volmarr"},
        "source": "wyrd_bridge", "_seq": 7, "_ts": TS,
        "_iso": "2026-09-26T00:44:54+00:00"}) == 1


@pytest.mark.parametrize("entry", [
    {"schema": 2}, {"schema": 99}, {"schema": 0}, {"schema": -1},
    {"schema": "1"}, {"schema": 1.0}, {"schema": True}, {"schema": None},
])
def test_validate_feed_entry_refuses_unsupported_or_malformed(entry):
    with pytest.raises(vb.UnsupportedFeedSchemaError):
        vb.validate_feed_entry(entry)


def test_validate_feed_entry_refuses_torn_entries():
    for torn in (None, "a line of text", 42, ["type", "wish_made"]):
        with pytest.raises(ValueError):
            vb.validate_feed_entry(torn)


def test_translation_table_matches_live_handlers():
    """The contract and the implementation cannot drift apart: the
    table's event types are exactly the bridge's handler map, and each
    row names the very method the map dispatches to."""
    bridge = VerdandiBridge()
    handlers = bridge._handlers()
    table = {t.event_type: t for t in vb.NERVE_FEED_TRANSLATION_TABLE}
    assert set(table) == set(handlers)
    for event_type, row in table.items():
        assert getattr(VerdandiBridge, row.handler) is \
            handlers[event_type].__func__, event_type
        assert vb.translation_for(event_type) is row
    assert vb.translation_for("ping") is None


def test_translation_table_matches_benchmark_feed_builders():
    """The B1 benchmark feed claims to cover 'every mapped type' — pin
    that claim against the schema table so the budget path and the
    contract can never quietly cover different seams."""
    assert set(_payload_builders()) == {
        t.event_type for t in vb.NERVE_FEED_TRANSLATION_TABLE}


def test_deliberately_unmapped_types_are_not_mapped():
    handlers = VerdandiBridge()._handlers()
    for event_type in vb.DELIBERATELY_UNMAPPED_FEED_TYPES:
        assert event_type not in handlers
        assert vb.is_deliberately_unmapped(event_type)
    for prefix in vb.DELIBERATELY_UNMAPPED_FEED_PREFIXES:
        assert vb.is_deliberately_unmapped(prefix + "anything")
        assert not any(t.startswith(prefix) for t in handlers)
    assert not vb.is_deliberately_unmapped("wish_made")


# ---------------------------------------------------------------------------
# 2. Shared contract fixture: envelope → mirror mutations, per event kind
# ---------------------------------------------------------------------------

def test_fixture_declares_the_v1_schema():
    fixture = _fixture()
    assert fixture["schema"] == vb.NERVE_FEED_SCHEMA_NAME
    assert fixture["schema_version"] == vb.NERVE_FEED_SCHEMA_VERSION
    assert {c["entry"]["type"] for c in fixture["cases"]} == {
        t.event_type for t in vb.NERVE_FEED_TRANSLATION_TABLE}


def _check_case(bridge: VerdandiBridge, case: dict) -> None:
    expect = case["expect"]
    desc = bridge.apply_feed_entry(case["entry"])
    assert desc == expect["description"], case["name"]
    anchors = [(c.label, c.tense_at(EVAL_AT))
               for _, c in bridge.world.iter_components("temporal_anchor")]
    assert anchors == [(a["label"], a["tense"])
                       for a in expect["anchors"]], case["name"]
    beliefs = bridge.world.get_component(SELF_ID, "beliefs")
    got = [(b.subject, b.claim, b.confidence, b.source)
           for b in beliefs.beliefs]
    assert got == [(b["subject"], b["claim"], b["confidence"],
                    b["source"]) for b in expect["beliefs"]], case["name"]
    if "utterance" in expect:
        utterances = [c for _, c in
                      bridge.world.iter_components("utterance")]
        assert len(utterances) == 1
        u = utterances[0]
        assert (u.speaker, u.text, u.emotions) == (
            expect["utterance"]["speaker"], expect["utterance"]["text"],
            expect["utterance"]["emotions"])
    if "reflection" in expect:
        comp = bridge.world.get_component(
            expect["reflection"]["entity_id"], "reflection")
        assert comp is not None
        assert comp.thought == expect["reflection"]["thought"]
        assert comp.depth == expect["reflection"]["depth"]
        assert comp.seq == expect["reflection"]["seq"]
        assert list(comp.about) == expect["reflection"]["about"]


def test_contract_cases_individually():
    for case in _fixture()["cases"]:
        _check_case(VerdandiBridge(), case)


def test_contract_cases_replay_together():
    """The whole fixture through build_from_events (the replay path):
    every case maps, nothing is unmapped/refused/quarantined, and the
    combined mirror holds the case count of anchors."""
    fixture = _fixture()
    entries = [c["entry"] for c in fixture["cases"]]
    bridge = VerdandiBridge().build_from_events(entries)
    health = bridge.mirror_health()
    assert health["feed_events_seen"] == len(entries)
    assert health["feed_events_mapped"] == len(entries)
    assert health["feed_events_unmapped"] == 0
    assert health["feed_events_refused"] == 0
    assert health["feed_events_quarantined"] == 0
    assert len(bridge.summary()["anchors"]) == len(entries)
    # 21 anchors + the self entity + the reflection entity.
    assert bridge.world.entity_count() == len(entries) + 2


def test_contract_unmapped_cases_change_nothing():
    for case in _fixture()["unmapped_cases"]:
        bridge = VerdandiBridge()
        assert bridge.apply_feed_entry(case["entry"]) is None, case["name"]
        assert bridge.world.entity_count() == 1  # the self entity only
        assert bridge.mirror_health()["feed_events_unmapped"] == 1


def test_contract_quarantine_cases_are_loud_and_held():
    for case in _fixture()["quarantine_cases"]:
        bridge = VerdandiBridge()
        assert bridge.apply_feed_entry(case["entry"]) is None, case["name"]
        # Nothing was mapped — no belief, no anchor, no entity.
        assert bridge.world.entity_count() == 1
        assert bridge.summary()["beliefs"] == []
        # And the refusal is a trace, not a silence: verbatim record,
        # declared version, and a reason naming the schema.
        assert len(bridge.feed_quarantine) == 1
        record = bridge.feed_quarantine[0]
        assert record["declared_schema"] == case["declared_schema"]
        assert record["event_type"] == case["entry"]["type"]
        assert record["entry"] is case["entry"]
        assert "schema" in record["reason"]
        health = bridge.mirror_health()
        assert health["feed_events_quarantined"] == 1
        assert health["quarantined_entries"] == 1


def test_pre_version_feed_files_keep_replaying():
    """Backwards compatibility is the v1 pin: a feed in the exact
    pre-D6 shape (no schema field anywhere) replays identically
    through both the replay path and the runner's per-event door."""
    events = [
        {"type": "wish_made",
         "data": {"wish_id": "w1", "text": "Learn Old Norse"},
         "_ts": TS, "_seq": 1},
        {"type": "mood_shift", "data": {"after": {"valence": 0.9}},
         "_ts": TS, "_seq": 2},
    ]
    replayed = VerdandiBridge().build_from_events(events)
    live = VerdandiBridge()
    for entry in events:
        live.apply_event(entry["type"], entry["data"], entry["_ts"])
    assert replayed.summary() == live.summary()
    assert replayed.mirror_health()["feed_events_mapped"] == 2


# ---------------------------------------------------------------------------
# 3. Mirror-lag health metric
# ---------------------------------------------------------------------------

def test_mirror_health_on_a_fresh_bridge():
    health = VerdandiBridge().mirror_health()
    assert health["world_id"] == vb.WORLD_ID
    assert health["reality"] == "manifest"
    assert health["schema"] == "wyrd-nerve-feed"
    assert health["schema_version"] == 1
    for key in ("feed_events_seen", "feed_events_mapped",
                "feed_events_unmapped", "feed_events_refused",
                "feed_events_torn", "feed_events_quarantined",
                "quarantined_entries"):
        assert health[key] == 0, key
    assert health["newest_feed_at"] is None
    assert health["newest_mirrored_at"] is None
    assert health["mirror_lag_seconds"] is None
    assert health["mirror_lag_events"] is None
    assert health["entities"] == 1


def test_mirror_health_counts_every_outcome():
    bridge = VerdandiBridge()
    bridge.apply_feed_entry(
        {"type": "wish_made", "data": {"wish_id": "w1", "text": "t"},
         "_ts": TS, "_seq": 1})                       # mapped
    bridge.apply_feed_entry(
        {"type": "ping", "data": {}, "_ts": TS, "_seq": 2})  # unmapped
    bridge.apply_feed_entry(
        {"type": "self_reflection", "data": {"thought": "x", "depth": 2},
         "_ts": TS, "_seq": 3})                       # refused (depth guard)
    bridge.apply_feed_entry("a torn line")            # torn
    bridge.apply_feed_entry(
        {"type": "wish_made", "data": {"wish_id": "w2", "text": "t"},
         "_ts": TS, "_seq": 4, "schema": 2})          # quarantined
    health = bridge.mirror_health()
    assert health["feed_events_seen"] == 5
    assert health["feed_events_mapped"] == 1
    assert health["feed_events_unmapped"] == 1
    assert health["feed_events_refused"] == 1
    assert health["feed_events_torn"] == 1
    assert health["feed_events_quarantined"] == 1
    assert health["quarantined_entries"] == 1


def test_mirror_lag_measures_the_unmirrored_tail():
    """Lag is the gap between the feed's head and the mirror's head:
    a mapped head means zero lag; an unmirrored tail (unmapped,
    quarantined) holds the mirror's watermark back by exactly the
    tail's span — in seconds and in hub sequence numbers."""
    caught_up = VerdandiBridge().build_from_events([
        {"type": "wish_made", "data": {"wish_id": "w1", "text": "t"},
         "_ts": TS, "_seq": 1},
        {"type": "joy_struck", "data": {"what": "x"},
         "_ts": TS + 60, "_seq": 2},
    ])
    health = caught_up.mirror_health()
    assert health["mirror_lag_seconds"] == 0.0
    assert health["mirror_lag_events"] == 0
    assert health["newest_mirrored_seq"] == 2

    behind = VerdandiBridge().build_from_events([
        {"type": "wish_made", "data": {"wish_id": "w1", "text": "t"},
         "_ts": TS, "_seq": 1},
        {"type": "ping", "data": {}, "_ts": TS + 120, "_seq": 2},
        {"type": "wish_made", "data": {"wish_id": "w2", "text": "t"},
         "_ts": TS + 300, "_seq": 3, "schema": 2},
    ])
    health = behind.mirror_health()
    assert health["newest_feed_seq"] == 3
    assert health["newest_mirrored_seq"] == 1
    assert health["mirror_lag_events"] == 2
    assert health["mirror_lag_seconds"] == 300.0
    assert health["newest_feed_at"] == \
        datetime.fromtimestamp(TS + 300, tz=timezone.utc).isoformat()
    assert health["newest_mirrored_at"] == \
        datetime.fromtimestamp(TS, tz=timezone.utc).isoformat()


def test_mirror_health_tracks_the_apply_event_path():
    """The production runner (Verðandi's wyrd_bridge.py) drives the
    bridge through apply_event, not feed entries — the health metric
    must be truthful on that path too. Sequence-based lag is absent
    there (apply_event carries no _seq) and reports None, never an
    invented number."""
    bridge = VerdandiBridge()
    bridge.apply_event("wish_made", {"wish_id": "w1", "text": "t"}, TS)
    bridge.apply_event("ping", {}, TS + 30)
    health = bridge.mirror_health()
    assert health["feed_events_seen"] == 2
    assert health["feed_events_mapped"] == 1
    assert health["feed_events_unmapped"] == 1
    assert health["mirror_lag_seconds"] == 30.0
    assert health["newest_feed_seq"] is None
    assert health["mirror_lag_events"] is None


# ---------------------------------------------------------------------------
# 4. Pinned replay determinism: same feed window → same mirror
# ---------------------------------------------------------------------------

def _determinism_feed() -> list[dict]:
    """One entry per mapped kind, plus noise and a torn line — the
    full projection surface in one window."""
    entries = [dict(c["entry"]) for c in _fixture()["cases"]]
    entries += [dict(c["entry"]) for c in _fixture()["unmapped_cases"]]
    entries.append("a torn line, as the feed occasionally holds")
    return entries


def _mirror_fingerprint(bridge: VerdandiBridge) -> dict:
    """Everything the mirror claims, in plain data: the summary plus
    the health watermarks (which are part of the projection's state,
    and equally deterministic)."""
    health = bridge.mirror_health()
    health.pop("entities")  # already inside the summary's world view
    return {"summary": bridge.summary(), "health": health}


def test_replay_determinism_same_feed_same_mirror():
    feed = _determinism_feed()
    first = VerdandiBridge().build_from_events(feed)
    second = VerdandiBridge().build_from_events(feed)
    assert _mirror_fingerprint(first) == _mirror_fingerprint(second)


def test_replay_determinism_survives_intervening_state():
    """The projection is pure: a bridge that has lived another life
    first still rebuilds the identical mirror from the same window —
    nothing accumulates across replays."""
    feed = _determinism_feed()
    baseline = VerdandiBridge().build_from_events(feed)
    lived = VerdandiBridge()
    lived.apply_event("wish_made",
                      {"wish_id": "other", "text": "unrelated"}, TS - 500)
    lived.apply_event("joy_struck", {"what": "noise"}, TS - 400)
    rebuilt = lived.build_from_events(feed)
    assert _mirror_fingerprint(rebuilt) == _mirror_fingerprint(baseline)
    # And rebuilding from the rebuilt bridge changes nothing either.
    assert _mirror_fingerprint(
        rebuilt.build_from_events(feed)) == _mirror_fingerprint(baseline)


def test_replay_determinism_at_benchmark_scale():
    """Determinism is not a small-feed accident: the B1 benchmark
    feed (every mapped type, 2,000 events) replays to the same mirror
    twice. (2k, not 20k, keeps this a test rather than a benchmark;
    the budget test owns the 20k measurement.)"""
    from tests.perf_fixtures import make_feed
    feed = make_feed(2000)
    first = VerdandiBridge().build_from_events(feed)
    second = VerdandiBridge().build_from_events(feed)
    assert _mirror_fingerprint(first) == _mirror_fingerprint(second)
    assert first.mirror_health()["feed_events_mapped"] > 0
