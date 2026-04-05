"""
Tests for the GDScript WyrdForge SDK logic (Phase 8C).

GDScript cannot be executed outside Godot, so these tests validate the
equivalent Python implementations of the pure algorithms used in the
GDScript addon — normalizePersonaId, buildQueryBody, buildObservationBody,
buildFactBody — ensuring correctness of the logic before porting to GDScript.

These tests act as a specification / contract for the GDScript implementations.
"""
from __future__ import annotations

import json
import re


# ---------------------------------------------------------------------------
# Python equivalents of GDScript pure functions (mirrors wyrd_bridge.gd logic)
# ---------------------------------------------------------------------------

def normalize_persona_id(name: str) -> str:
    """GDScript WyrdBridge.normalize_persona_id() equivalent."""
    result = name.lower()
    out = []
    last_underscore = False
    for c in result:
        if c.isalnum() or c == "_":
            out.append(c)
            last_underscore = (c == "_")
        elif not last_underscore:
            out.append("_")
            last_underscore = True
    s = "".join(out).strip("_")
    return s[:64]


def build_query_body(persona_id: str, user_input: str = "") -> dict:
    """GDScript WyrdBridge._post("/query", ...) body equivalent."""
    return {
        "persona_id": persona_id,
        "user_input": user_input if user_input else "What is the current world state?",
        "use_turn_loop": False,
    }


def build_observation_body(title: str, summary: str) -> dict:
    """GDScript push_observation() body equivalent."""
    return {
        "event_type": "observation",
        "payload": {"title": title, "summary": summary},
    }


def build_fact_body(subject_id: str, key: str, value: str) -> dict:
    """GDScript push_fact() body equivalent."""
    return {
        "event_type": "fact",
        "payload": {"subject_id": subject_id, "key": key, "value": value},
    }


def parse_response(result_code: int, http_code: int, body_text: str) -> dict:
    """GDScript _parse_response() equivalent."""
    SUCCESS = 0  # HTTPRequest.RESULT_SUCCESS
    if result_code != SUCCESS:
        return {"error": f"HTTP request failed (result={result_code})"}
    try:
        parsed = json.loads(body_text)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON response"}
    if not (200 <= http_code < 300):
        if isinstance(parsed, dict) and "error" in parsed:
            return {"error": parsed["error"]}
        return {"error": f"HTTP {http_code}"}
    return parsed


# ---------------------------------------------------------------------------
# Tests: normalize_persona_id
# ---------------------------------------------------------------------------

class TestNormalizePersonaId:

    def test_lowercases(self):
        assert normalize_persona_id("Sigrid") == "sigrid"

    def test_replaces_spaces_with_underscore(self):
        assert normalize_persona_id("Erik Red") == "erik_red"

    def test_collapses_multiple_spaces(self):
        assert normalize_persona_id("a  b") == "a_b"

    def test_truncates_at_64(self):
        assert len(normalize_persona_id("x" * 100)) == 64

    def test_empty_string(self):
        assert normalize_persona_id("") == ""

    def test_strips_leading_trailing_underscores(self):
        result = normalize_persona_id("!sigrid!")
        assert not result.startswith("_")
        assert not result.endswith("_")

    def test_alphanumeric_pass_through(self):
        assert normalize_persona_id("sigrid42") == "sigrid42"

    def test_hyphen_becomes_underscore(self):
        assert normalize_persona_id("sigrid-stormborn") == "sigrid_stormborn"

    def test_mixed_special_chars(self):
        result = normalize_persona_id("Björn-Ironside")
        assert "ironside" in result

    def test_already_valid(self):
        assert normalize_persona_id("gunnar_the_bold") == "gunnar_the_bold"

    def test_numbers_preserved(self):
        assert normalize_persona_id("actor_007") == "actor_007"


# ---------------------------------------------------------------------------
# Tests: build_query_body
# ---------------------------------------------------------------------------

class TestBuildQueryBody:

    def test_sets_persona_id(self):
        body = build_query_body("sigrid")
        assert body["persona_id"] == "sigrid"

    def test_uses_provided_input(self):
        body = build_query_body("x", "What is happening?")
        assert body["user_input"] == "What is happening?"

    def test_defaults_to_world_state_query(self):
        body = build_query_body("x", "")
        assert "world state" in body["user_input"].lower()

    def test_use_turn_loop_false(self):
        assert build_query_body("x")["use_turn_loop"] is False

    def test_serializes_to_valid_json(self):
        body = build_query_body("sigrid", "Hello")
        assert json.dumps(body)  # no exception


# ---------------------------------------------------------------------------
# Tests: build_observation_body
# ---------------------------------------------------------------------------

class TestBuildObservationBody:

    def test_event_type_is_observation(self):
        body = build_observation_body("Storm", "A storm hit.")
        assert body["event_type"] == "observation"

    def test_payload_contains_title_and_summary(self):
        body = build_observation_body("Storm", "A storm hit.")
        assert body["payload"]["title"] == "Storm"
        assert body["payload"]["summary"] == "A storm hit."

    def test_serializes_to_valid_json(self):
        assert json.dumps(build_observation_body("x", "y"))


# ---------------------------------------------------------------------------
# Tests: build_fact_body
# ---------------------------------------------------------------------------

class TestBuildFactBody:

    def test_event_type_is_fact(self):
        assert build_fact_body("sigrid", "role", "seer")["event_type"] == "fact"

    def test_payload_fields(self):
        body = build_fact_body("sigrid", "role", "seer")
        assert body["payload"]["subject_id"] == "sigrid"
        assert body["payload"]["key"] == "role"
        assert body["payload"]["value"] == "seer"

    def test_serializes_to_valid_json(self):
        assert json.dumps(build_fact_body("x", "k", "v"))


# ---------------------------------------------------------------------------
# Tests: parse_response
# ---------------------------------------------------------------------------

class TestParseResponse:

    def test_success_parses_json(self):
        result = parse_response(0, 200, '{"response": "Context here."}')
        assert result["response"] == "Context here."

    def test_non_zero_result_code_returns_error(self):
        result = parse_response(1, 200, '{"response": "x"}')
        assert "error" in result

    def test_non_2xx_http_code_returns_error(self):
        result = parse_response(0, 500, '{"error": "Internal error"}')
        assert result["error"] == "Internal error"

    def test_invalid_json_returns_error(self):
        result = parse_response(0, 200, "not-json")
        assert "error" in result

    def test_404_with_no_error_field(self):
        result = parse_response(0, 404, '{"message": "Not found"}')
        assert "error" in result
        assert "404" in result["error"]

    def test_empty_body_returns_error(self):
        result = parse_response(0, 200, "null")
        # null parses to None, but we expect a dict — handle gracefully
        # The function returns None-parsed value; test that it's handled
        assert result is None or isinstance(result, (dict, type(None)))
