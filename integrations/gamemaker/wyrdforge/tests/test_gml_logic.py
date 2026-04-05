"""
Tests for WyrdForge GameMaker Studio 2 integration (Phase 11C).
Python equivalents of GML pure functions tested here as specification.
"""
from __future__ import annotations

import json


# ---------------------------------------------------------------------------
# Python equivalents of GML pure functions
# ---------------------------------------------------------------------------

def wyrd_normalize_persona_id(name: str) -> str:
    result = name.lower()
    out = []
    last_under = False
    for c in result:
        o = ord(c)
        if (97 <= o <= 122) or (48 <= o <= 57) or o == 95:
            out.append(c)
            last_under = (o == 95)
        elif not last_under:
            out.append("_")
            last_under = True
    s = "".join(out).strip("_")
    return s[:64]


def wyrd_build_query_body(persona_id: str, user_input: str) -> dict:
    return {
        "persona_id": persona_id,
        "user_input": user_input if user_input else "What is the current world state?",
        "use_turn_loop": False,
    }


def wyrd_build_observation_body(title: str, summary: str) -> dict:
    return {"event_type": "observation", "payload": {"title": title, "summary": summary}}


def wyrd_build_fact_body(subject_id: str, key: str, value: str) -> dict:
    return {"event_type": "fact", "payload": {"subject_id": subject_id, "key": key, "value": value}}


def wyrd_handle_response_result(status: int, http_status: int, body: str) -> dict:
    """Simulates wyrd_handle_response() processing."""
    if status != 0:
        return {"error": f"Request failed (status={status})"}
    if 200 <= http_status < 300:
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"error": "Invalid JSON"}
    return {"error": f"HTTP {http_status}"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWyrdNormalizePersonaId:
    def test_lowercases(self): assert wyrd_normalize_persona_id("Sigrid") == "sigrid"
    def test_spaces(self): assert wyrd_normalize_persona_id("Erik Red") == "erik_red"
    def test_collapses(self): assert wyrd_normalize_persona_id("a  b") == "a_b"
    def test_truncates(self): assert len(wyrd_normalize_persona_id("x" * 100)) == 64
    def test_empty(self): assert wyrd_normalize_persona_id("") == ""
    def test_numbers(self): assert wyrd_normalize_persona_id("obj_001") == "obj_001"


class TestWyrdBuildQueryBody:
    def test_persona_id(self): assert wyrd_build_query_body("sigrid", "")["persona_id"] == "sigrid"
    def test_custom_input(self): assert wyrd_build_query_body("x", "hello")["user_input"] == "hello"
    def test_default_input(self): assert "world state" in wyrd_build_query_body("x", "")["user_input"].lower()
    def test_use_turn_loop_false(self): assert wyrd_build_query_body("x", "")["use_turn_loop"] is False
    def test_serializes(self): assert json.dumps(wyrd_build_query_body("x", "hi"))


class TestWyrdBuildObservationBody:
    def test_event_type(self): assert wyrd_build_observation_body("x", "y")["event_type"] == "observation"
    def test_payload_title(self): assert wyrd_build_observation_body("Storm", "Rain")["payload"]["title"] == "Storm"
    def test_payload_summary(self): assert wyrd_build_observation_body("T", "Summary")["payload"]["summary"] == "Summary"


class TestWyrdBuildFactBody:
    def test_event_type(self): assert wyrd_build_fact_body("x", "k", "v")["event_type"] == "fact"
    def test_subject_id(self): assert wyrd_build_fact_body("sigrid", "k", "v")["payload"]["subject_id"] == "sigrid"
    def test_key(self): assert wyrd_build_fact_body("x", "role", "v")["payload"]["key"] == "role"
    def test_value(self): assert wyrd_build_fact_body("x", "k", "seer")["payload"]["value"] == "seer"


class TestWyrdHandleResponseResult:
    def test_success_parses_json(self):
        r = wyrd_handle_response_result(0, 200, '{"response": "context"}')
        assert r["response"] == "context"

    def test_non_zero_status_error(self):
        r = wyrd_handle_response_result(1, 0, "")
        assert "error" in r

    def test_http_error_code(self):
        r = wyrd_handle_response_result(0, 500, '{"error": "server error"}')
        assert "error" in r
        assert "500" in r["error"]

    def test_invalid_json(self):
        r = wyrd_handle_response_result(0, 200, "not-json")
        assert "error" in r

    def test_ok_true_passthrough(self):
        r = wyrd_handle_response_result(0, 200, '{"ok": true}')
        assert r.get("ok") is True
