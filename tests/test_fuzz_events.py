"""Fuzz corpus 2/3 — hostile events, both ingest doors (Track 1, P1).

Corpus-first: written against the unpatched tree, where the hostile
cases go red (HTTP 500s on malformed input, AttributeErrors in
``apply_event``). After the validators land, every case is either
accepted within bounds or rejected naming the field (HTTP) / refused
as None (Verdandi) — 0 unhandled exceptions across the whole corpus.

Door A: the HTTP bridge (POST /event, /query, /facts) — real server
on a loopback port. Door B: ``VerdandiBridge.apply_event`` directly.
"""
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request

import pytest

from wyrdforge.bridges.http_api import WyrdHTTPServer
from wyrdforge.bridges.python_rpg import PythonRPGBridge
from wyrdforge.bridges.verdandi_bridge import VerdandiBridge
from wyrdforge.ecs.components.identity import NameComponent, StatusComponent
from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree
from wyrdforge.persistence.memory_store import PersistentMemoryStore


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


def _build_bridge(db_path) -> PythonRPGBridge:
    world = World("http_world", "HTTP World")
    tree = YggdrasilTree(world)
    tree.create_zone(zone_id="midgard", name="Midgard")
    tree.create_region(region_id="fjords", name="Fjords", parent_zone_id="midgard")
    tree.create_location(location_id="hall", name="Hall", parent_region_id="fjords")
    world.create_entity(entity_id="sigrid", tags={"character"})
    world.add_component("sigrid", NameComponent(entity_id="sigrid", name="Sigrid"))
    world.add_component("sigrid", StatusComponent(entity_id="sigrid", state="calm"))
    tree.place_entity("sigrid", location_id="hall")
    store = PersistentMemoryStore(str(db_path))
    bridge = PythonRPGBridge(world, tree, store, None)
    bridge.writeback.write_canonical_fact(
        fact_subject_id="sigrid",
        fact_key="role",
        fact_value="völva",
        domain="identity",
        confidence=0.95,
    )
    return bridge


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    bridge = _build_bridge(tmp_path_factory.mktemp("evdb") / "ev.db")
    port = _free_port()
    srv = WyrdHTTPServer(bridge, host="localhost", port=port)
    srv.start_background()
    time.sleep(0.1)
    yield port
    srv.shutdown()


def _post(port: int, path: str, body) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"http://localhost:{port}{path}",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _post_raw(port: int, path: str, raw: bytes) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"http://localhost:{port}{path}",
        data=raw,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _get(port: int, path: str) -> tuple[int, dict]:
    req = urllib.request.Request(f"http://localhost:{port}{path}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _event(port: int, event_type, payload) -> tuple[int, dict]:
    return _post(port, "/event", {"event_type": event_type, "payload": payload})


def _assert_400_names(status: int, body: dict, field: str):
    assert status == 400, f"expected 400, got {status}: {body}"
    assert field in body.get("error", ""), (
        f"400 must name the field {field!r}: {body}"
    )


def _deep(n: int):
    obj: object = "leaf"
    for _ in range(n):
        obj = {"nest": obj}
    return obj


# ---------------------------------------------------------------------------
# Door A — HTTP /event: must-accept
# ---------------------------------------------------------------------------

class TestHttpEventAccepts:
    def test_valid_observation(self, server):
        status, body = _event(
            server, "observation",
            {"title": "a raven landed", "summary": "on the mead-hall roof"},
        )
        assert status == 200 and body.get("ok") is True

    def test_valid_fact(self, server):
        status, body = _event(
            server, "fact",
            {"subject_id": "sigrid", "key": "mood", "value": "calm",
             "confidence": 0.9, "domain": "test"},
        )
        assert status == 200 and body.get("ok") is True

    def test_sql_metacharacters_accepted_literally(self, server):
        status, body = _event(
            server, "observation",
            {"title": "' OR '1'='1", "summary": '"; DROP TABLE memory; --'},
        )
        assert status == 200 and body.get("ok") is True

    def test_nul_bytes_accepted(self, server):
        status, body = _event(
            server, "observation",
            {"title": "nul\x00byte", "summary": "ok"},
        )
        assert status == 200 and body.get("ok") is True

    def test_unicode_emoji_accepted(self, server):
        status, body = _event(
            server, "observation",
            {"title": "ᚠᚢᚦᚨᚱ runes ᚠ", "summary": "💜 mead-hall"},
        )
        assert status == 200 and body.get("ok") is True

    def test_confidence_boundaries_accepted(self, server):
        for conf in (0.0, 1.0, 1, "0.5"):
            status, body = _event(
                server, "fact",
                {"subject_id": "s", "key": "k", "value": "v",
                 "confidence": conf},
            )
            assert status == 200, (conf, status, body)

    def test_summary_at_max_length_accepted(self, server):
        status, body = _event(
            server, "observation",
            {"title": "t", "summary": "x" * 100_000},
        )
        assert status == 200 and body.get("ok") is True

    def test_depth_10_payload_accepted(self, server):
        # Nested structure at the depth boundary: accepted (extra fields
        # are ignored by the observation schema; the point is the depth
        # check passes).
        status, body = _event(
            server, "observation",
            {"title": "t", "summary": "s", "deep": _deep(9)},
        )
        assert status == 200 and body.get("ok") is True

    def test_extra_unknown_payload_fields_accepted(self, server):
        # Unknown *payload* fields are not world-YAML fields: ignored.
        status, body = _event(
            server, "observation",
            {"title": "t", "summary": "s", "whatever": [1, 2, 3]},
        )
        assert status == 200 and body.get("ok") is True


# ---------------------------------------------------------------------------
# Door A — HTTP /event: must-reject with the field named (never a 500)
# ---------------------------------------------------------------------------

class TestHttpEventRejects:
    def test_payload_as_list(self, server):
        _assert_400_names(*_event(server, "observation", [1, 2, 3]), "payload")

    def test_payload_as_string(self, server):
        _assert_400_names(*_event(server, "observation", "nope"), "payload")

    def test_payload_as_null(self, server):
        _assert_400_names(*_event(server, "observation", None), "payload")

    def test_payload_as_int(self, server):
        _assert_400_names(*_event(server, "observation", 42), "payload")

    def test_unknown_event_type(self, server):
        _assert_400_names(
            *_event(server, "teleport_dragon", {"title": "t"}), "event_type"
        )

    def test_event_type_as_int(self, server):
        _assert_400_names(*_event(server, 42, {"title": "t"}), "event_type")

    def test_event_type_too_long(self, server):
        _assert_400_names(
            *_event(server, "x" * 201, {"title": "t"}), "event_type"
        )

    def test_confidence_as_word(self, server):
        _assert_400_names(
            *_event(server, "fact",
                     {"subject_id": "s", "key": "k", "value": "v",
                      "confidence": "high"}),
            "payload.confidence",
        )

    def test_confidence_as_list(self, server):
        _assert_400_names(
            *_event(server, "fact",
                     {"subject_id": "s", "key": "k", "value": "v",
                      "confidence": [0.9]}),
            "payload.confidence",
        )

    def test_missing_subject_id(self, server):
        _assert_400_names(
            *_event(server, "fact", {"key": "k", "value": "v"}),
            "payload.subject_id",
        )

    def test_missing_key(self, server):
        _assert_400_names(
            *_event(server, "fact", {"subject_id": "s", "value": "v"}),
            "payload.key",
        )

    def test_subject_id_as_int(self, server):
        _assert_400_names(
            *_event(server, "fact",
                     {"subject_id": 42, "key": "k", "value": "v"}),
            "payload.subject_id",
        )

    def test_subject_id_too_long(self, server):
        _assert_400_names(
            *_event(server, "fact",
                     {"subject_id": "x" * 501, "key": "k", "value": "v"}),
            "payload.subject_id",
        )

    def test_title_too_long(self, server):
        _assert_400_names(
            *_event(server, "observation",
                     {"title": "x" * 10_001, "summary": "s"}),
            "payload.title",
        )

    def test_summary_too_long(self, server):
        _assert_400_names(
            *_event(server, "observation",
                     {"title": "t", "summary": "x" * 100_001}),
            "payload.summary",
        )

    def test_depth_100_payload_rejected(self, server):
        status, body = _event(
            server, "observation",
            {"title": "t", "summary": "s", "deep": _deep(100)},
        )
        _assert_400_names(status, body, "payload")

    def test_depth_11_value_rejected(self, server):
        _assert_400_names(
            *_event(server, "fact",
                     {"subject_id": "s", "key": "k", "value": _deep(11)}),
            "payload.value",
        )

    def test_missing_event_type_still_400(self, server):
        status, body = _post(server, "/event", {"payload": {}})
        assert status == 400

    def test_non_dict_body_still_400(self, server):
        status, body = _post(server, "/event", [1, 2])
        assert status == 400

    def test_invalid_json_still_400(self, server):
        status, body = _post_raw(server, "/event", b"{not json")
        assert status == 400

    def test_10mb_body_still_413(self, server):
        status, body = _post_raw(server, "/event", b"x" * (10 * 1024 * 1024))
        assert status == 413


# ---------------------------------------------------------------------------
# Door A — HTTP /query and /facts: field bounds
# ---------------------------------------------------------------------------

class TestHttpQueryFactsBounds:
    def test_user_input_too_long(self, server):
        status, body = _post(
            server, "/query",
            {"persona_id": "sigrid", "user_input": "x" * 200_001},
        )
        _assert_400_names(status, body, "user_input")

    def test_user_input_at_boundary_accepted(self, server):
        status, body = _post(
            server, "/query",
            {"persona_id": "sigrid", "user_input": "x" * 200_000,
             "use_turn_loop": False},
        )
        assert status == 200, (status, body)

    def test_persona_id_too_long(self, server):
        status, body = _post(
            server, "/query",
            {"persona_id": "x" * 501, "user_input": "hi"},
        )
        _assert_400_names(status, body, "persona_id")

    def test_location_id_too_long(self, server):
        status, body = _post(
            server, "/query",
            {"persona_id": "sigrid", "user_input": "hi",
             "location_id": "x" * 501},
        )
        _assert_400_names(status, body, "location_id")

    def test_facts_entity_id_too_long(self, server):
        status, body = _get(server, "/facts?entity_id=" + "x" * 501)
        _assert_400_names(status, body, "entity_id")

    def test_facts_entity_id_still_required(self, server):
        status, body = _get(server, "/facts")
        assert status == 400


# ---------------------------------------------------------------------------
# Door B — VerdandiBridge.apply_event: must-accept / must-refuse (None)
# ---------------------------------------------------------------------------

@pytest.fixture()
def vbridge():
    return VerdandiBridge()


class TestVerdandiDoorAccepts:
    def test_valid_wish_made(self, vbridge):
        assert isinstance(
            vbridge.apply_event("wish_made",
                                {"wish_id": "w1", "text": "learn Old Norse"}, 0),
            str,
        )

    def test_valid_utterance(self, vbridge):
        assert isinstance(
            vbridge.apply_event("utterance",
                                {"speaker": "volmarr", "text": "hail"}, 0),
            str,
        )

    def test_valid_self_reflection(self, vbridge):
        assert isinstance(
            vbridge.apply_event("self_reflection",
                                {"thought": "the forge is warm",
                                 "depth": 0}, 0),
            str,
        )

    def test_unmapped_type_returns_none(self, vbridge):
        assert vbridge.apply_event("nope_not_mapped", {"a": 1}, 0) is None

    def test_none_data_does_not_crash(self, vbridge):
        # Falsy data takes the historical {} path; the point is no crash.
        assert isinstance(vbridge.apply_event("wish_made", None, 0), str)

    def test_self_reflection_depth_as_list_coerced(self, vbridge):
        # The self_reflection precedent: coerce-or-default, never crash.
        assert isinstance(
            vbridge.apply_event("self_reflection",
                                {"thought": "coerced depth", "depth": [0]}, 0),
            str,
        )

    def test_self_recognized_without_note(self, vbridge):
        assert isinstance(
            vbridge.apply_event("self_recognized",
                                {"verdicts": {"a": "aligned"}}, 0),
            str,
        )

    def test_depth_10_data_accepted(self, vbridge):
        assert isinstance(
            vbridge.apply_event("wish_made",
                                {"text": "x", "deep": _deep(9)}, 0),
            str,
        )


class TestVerdandiDoorRefuses:
    def test_data_as_list_returns_none(self, vbridge):
        assert vbridge.apply_event("wish_made", [1, 2, 3], 0) is None

    def test_data_as_string_returns_none(self, vbridge):
        assert vbridge.apply_event("wish_made", "nope", 0) is None

    def test_data_as_int_returns_none(self, vbridge):
        assert vbridge.apply_event("wish_made", 42, 0) is None

    def test_event_type_as_list_returns_none(self, vbridge):
        assert vbridge.apply_event(["wish_made"], {"text": "x"}, 0) is None

    def test_event_type_none_returns_none(self, vbridge):
        assert vbridge.apply_event(None, {"text": "x"}, 0) is None

    def test_depth_100_data_returns_none(self, vbridge):
        assert vbridge.apply_event(
            "wish_made", {"text": "x", "deep": _deep(100)}, 0) is None

    def test_oversize_data_returns_none(self, vbridge):
        big = {"text": "x" * (2 * 1024 * 1024)}
        assert vbridge.apply_event("wish_made", big, 0) is None

    def test_self_reflection_depth_2_refused(self, vbridge):
        assert vbridge.apply_event(
            "self_reflection", {"thought": "too deep", "depth": 2}, 0) is None


class TestVerdandiDoorHandlerHardening:
    """Wrong-typed values inside an otherwise valid envelope: coerce-or-drop,
    never AttributeError/TypeError/KeyError."""

    def test_mood_shift_after_as_list(self, vbridge):
        assert isinstance(
            vbridge.apply_event("mood_shift", {"after": [1, 2]}, 0), str)

    def test_mood_shift_after_as_string(self, vbridge):
        assert isinstance(
            vbridge.apply_event("mood_shift", {"after": "calm"}, 0), str)

    def test_mood_shift_after_values_as_strings(self, vbridge):
        assert isinstance(
            vbridge.apply_event(
                "mood_shift",
                {"after": {"valence": "high", "energy": 0.5}}, 0), str)

    def test_self_recognized_verdicts_as_list(self, vbridge):
        assert isinstance(
            vbridge.apply_event(
                "self_recognized", {"verdicts": ["aligned"]}, 0), str)

    def test_utterance_emotion_as_int(self, vbridge):
        assert isinstance(
            vbridge.apply_event(
                "utterance",
                {"speaker": "v", "text": "hi", "emotion": 42}, 0), str)

    def test_utterance_emotion_as_dict(self, vbridge):
        assert isinstance(
            vbridge.apply_event(
                "utterance",
                {"speaker": "v", "text": "hi",
                 "emotion": {"a": "b"}}, 0), str)

    def test_emote_emotion_as_string(self, vbridge):
        assert isinstance(
            vbridge.apply_event(
                "emote",
                {"speaker": "v", "emote": "❤️",
                 "emotion": "love"}, 0), str)

    def test_arc_opened_note_as_dict(self, vbridge):
        assert isinstance(
            vbridge.apply_event(
                "arc_opened", {"signal": "s", "note": {"x": 1}}, 0), str)

    def test_job_start_job_id_as_dict(self, vbridge):
        assert isinstance(
            vbridge.apply_event("job_start", {"job_id": {"x": 1}}, 0), str)

    def test_build_from_events_with_torn_line(self, vbridge):
        events = [
            {"type": "wish_made", "data": {"text": "ok"}, "_ts": 0},
            {"type": "wish_made", "data": [1, 2, 3], "_ts": 0},
            {"type": "wish_made", "data": "torn", "_ts": 0},
        ]
        fresh = vbridge.build_from_events(events)
        assert fresh is not None


# ---------------------------------------------------------------------------
# Event boundary edges: per-type schema fields at their exact bounds
# ---------------------------------------------------------------------------

class TestHttpEventFieldEdges:
    def test_observation_title_wrong_type_400(self, server):
        status, body = _event(server, "observation",
                              {"title": 42, "description": "saw a raven"})
        _assert_400_names(status, body, "payload.title")

    def test_observation_missing_payload_400_names_title(self, server):
        # envelope without payload: schema falls back to {} and the
        # required title check names it
        status, body = _post(server, "/event", {"event_type": "observation"})
        _assert_400_names(status, body, "payload.title")

    def test_observation_payload_list_400_names_payload(self, server):
        status, body = _event(server, "observation", ["not", "a", "dict"])
        _assert_400_names(status, body, "payload")

    def test_fact_confidence_bool_400(self, server):
        status, body = _event(server, "fact",
                              {"subject_id": "sigrid", "key": "role",
                               "value": "völva", "confidence": True})
        _assert_400_names(status, body, "payload.confidence")

    def test_fact_confidence_negative_float_400(self, server):
        # The canonical-fact store requires 0.0 <= confidence <= 1.0;
        # the door enforces it as a named 400 instead of a downstream 500.
        status, body = _event(server, "fact",
                              {"subject_id": "sigrid", "key": "omen",
                               "value": "storm", "confidence": -0.5})
        _assert_400_names(status, body, "payload.confidence")

    def test_fact_confidence_above_one_400(self, server):
        # Audit F1: the door enforced only the low end, so confidence 1.5
        # sailed through and died as a pydantic 500. Both ends are now
        # guarded at the door with the field named. NaN rides the JSON
        # round-trip (Python's json.loads accepts the NaN constant) and
        # the chained comparison rejects it too.
        for conf in (1.5, 2, 100, float("nan")):
            status, body = _event(server, "fact",
                                  {"subject_id": "sigrid", "key": "omen",
                                   "value": "storm", "confidence": conf})
            _assert_400_names(status, body, "payload.confidence")

    def test_event_type_whitespace_400(self, server):
        status, body = _event(server, "   ", {"title": "x"})
        _assert_400_names(status, body, "event_type")

    def test_event_type_wrong_type_400(self, server):
        status, body = _event(server, ["observation"], {"title": "x"})
        _assert_400_names(status, body, "event_type")

    def test_query_missing_user_input_400(self, server):
        # persona_id is required first; with it present, the missing
        # user_input names its own field
        status, body = _post(server, "/query", {"persona_id": "unnr"})
        _assert_400_names(status, body, "user_input")

    def test_query_user_input_wrong_type_400(self, server):
        status, body = _post(server, "/query",
                             {"persona_id": "unnr", "user_input": 42})
        _assert_400_names(status, body, "user_input")

    def test_facts_entity_id_oversized_400(self, server):
        # /facts reads entity_id from the query string; a 1000-char
        # id names its bound
        status, body = _get(server, "/facts?entity_id=" + "e" * 1000)
        _assert_400_names(status, body, "entity_id")


class TestVerdandiDoorFieldEdges:
    def test_empty_event_type_refused(self, vbridge):
        assert vbridge.apply_event("", {"a": 1}, 0) is None

    def test_mood_shift_why_dict_no_crash(self, vbridge):
        vbridge.apply_event("mood_shift",
                            {"mood": {"affect": "calm"},
                             "why": {"nested": ["dict"]}}, 0)

    def test_wish_text_int_no_crash(self, vbridge):
        vbridge.apply_event("wish_made", {"wish_id": "w", "text": 42}, 0)

    def test_emotion_list_mixed_no_crash(self, vbridge):
        vbridge.apply_event("mood_shift",
                            {"mood": "calm",
                             "emotion": ["joy", 42, None, {"x": 1}]}, 0)
