"""
Tests for WyrdForge Defold extension (Phase 11F).

Python equivalents of the pure C++ functions in src/wyrdforge.cpp,
tested here since we cannot run the Defold native runtime in CI.
These functions are the specification; the C++ implementation must
produce identical output.
"""
from __future__ import annotations

import json
import re


# ---------------------------------------------------------------------------
# Python equivalents of C++ pure functions (mirrors wyrdforge.cpp)
# ---------------------------------------------------------------------------

def escape_json(s: str) -> str:
    """Escape a string for embedding in a JSON string literal."""
    out = []
    for c in s:
        o = ord(c)
        if c == '"':     out.append('\\"')
        elif c == '\\':  out.append('\\\\')
        elif c == '\b':  out.append('\\b')
        elif c == '\f':  out.append('\\f')
        elif c == '\n':  out.append('\\n')
        elif c == '\r':  out.append('\\r')
        elif c == '\t':  out.append('\\t')
        elif o < 0x20:   out.append(f'\\u{o:04x}')
        else:            out.append(c)
    return "".join(out)


def normalize_persona_id(name: str) -> str:
    """Normalize a display name to a WYRD persona_id (snake_case, max 64 chars)."""
    out = []
    last_under = False
    for c in name:
        if c.isalnum():
            out.append(c.lower())
            last_under = False
        elif c == '_':
            out.append('_')
            last_under = True
        elif not last_under:
            out.append('_')
            last_under = True
    result = "".join(out).strip("_")
    return result[:64]


def build_query_body(persona_id: str, user_input: str) -> dict:
    """Build a /query request body dict."""
    return {
        "persona_id": persona_id,
        "user_input": user_input if user_input else "What is the current world state?",
        "use_turn_loop": False,
    }


def build_event_body(event_type: str, payload: dict) -> dict:
    """Build a /event request body dict."""
    return {"event_type": event_type, "payload": payload}


def parse_response(status: int, body: str) -> tuple[bool, dict | None, str | None]:
    """Simulate Lua HTTP response handling logic."""
    if 200 <= status < 300:
        try:
            data = json.loads(body)
            return True, data, None
        except json.JSONDecodeError:
            return False, None, "WyrdForge: invalid JSON response"
    else:
        return False, None, f"WyrdForge: HTTP {status}"


# ---------------------------------------------------------------------------
# escape_json
# ---------------------------------------------------------------------------

class TestEscapeJson:
    def test_plain_string(self):
        assert escape_json("hello") == "hello"

    def test_quotes(self):
        assert escape_json('"hi"') == '\\"hi\\"'

    def test_backslash(self):
        assert escape_json("a\\b") == "a\\\\b"

    def test_newline(self):
        assert escape_json("a\nb") == "a\\nb"

    def test_tab(self):
        assert escape_json("a\tb") == "a\\tb"

    def test_carriage_return(self):
        assert escape_json("a\rb") == "a\\rb"

    def test_control_char(self):
        result = escape_json("\x01")
        assert result == "\\u0001"

    def test_empty(self):
        assert escape_json("") == ""

    def test_unicode_passthrough(self):
        # Non-ASCII printable passes through unchanged
        assert escape_json("æøå") == "æøå"


# ---------------------------------------------------------------------------
# normalize_persona_id
# ---------------------------------------------------------------------------

class TestNormalizePersonaId:
    def test_lowercases(self):
        assert normalize_persona_id("Sigrid") == "sigrid"

    def test_replaces_spaces(self):
        assert normalize_persona_id("Erik Red") == "erik_red"

    def test_collapses_underscores(self):
        assert normalize_persona_id("a  b") == "a_b"

    def test_strips_leading_underscores(self):
        assert normalize_persona_id("_sigrid") == "sigrid"

    def test_strips_trailing_underscores(self):
        assert normalize_persona_id("sigrid_") == "sigrid"

    def test_truncates_at_64(self):
        assert len(normalize_persona_id("x" * 100)) == 64

    def test_empty_string(self):
        assert normalize_persona_id("") == ""

    def test_preserves_numbers(self):
        assert normalize_persona_id("npc_001") == "npc_001"

    def test_replaces_dots(self):
        assert normalize_persona_id("npc.archer") == "npc_archer"

    def test_replaces_dashes(self):
        assert normalize_persona_id("npc-one") == "npc_one"

    def test_already_valid(self):
        assert normalize_persona_id("sigrid") == "sigrid"

    def test_mixed_case_and_spaces(self):
        assert normalize_persona_id("Sigrid Stormborn") == "sigrid_stormborn"

    def test_special_chars(self):
        result = normalize_persona_id("Björn!")
        assert result.startswith("bj")

    def test_only_underscores(self):
        assert normalize_persona_id("___") == ""

    def test_existing_underscore_preserved(self):
        assert normalize_persona_id("my_npc") == "my_npc"


# ---------------------------------------------------------------------------
# build_query_body
# ---------------------------------------------------------------------------

class TestBuildQueryBody:
    def test_persona_id(self):
        assert build_query_body("sigrid", "hello")["persona_id"] == "sigrid"

    def test_custom_input(self):
        assert build_query_body("x", "What is happening?")["user_input"] == "What is happening?"

    def test_default_input_on_empty(self):
        body = build_query_body("x", "")
        assert "world state" in body["user_input"].lower()

    def test_use_turn_loop_false(self):
        assert build_query_body("x", "hi")["use_turn_loop"] is False

    def test_json_serializable(self):
        body = build_query_body("sigrid", "Hello")
        assert json.dumps(body)

    def test_exact_keys(self):
        keys = sorted(build_query_body("x", "y").keys())
        assert keys == ["persona_id", "use_turn_loop", "user_input"]

    def test_empty_persona_id(self):
        body = build_query_body("", "test")
        assert body["persona_id"] == ""


# ---------------------------------------------------------------------------
# build_event_body — observation
# ---------------------------------------------------------------------------

class TestBuildEventBodyObservation:
    def test_event_type(self):
        b = build_event_body("observation", {"title": "Storm", "summary": "Rain fell."})
        assert b["event_type"] == "observation"

    def test_payload_title(self):
        b = build_event_body("observation", {"title": "Storm", "summary": "Rain fell."})
        assert b["payload"]["title"] == "Storm"

    def test_payload_summary(self):
        b = build_event_body("observation", {"title": "Storm", "summary": "Rain fell."})
        assert b["payload"]["summary"] == "Rain fell."

    def test_json_serializable(self):
        b = build_event_body("observation", {"title": "x", "summary": "y"})
        assert json.dumps(b)


# ---------------------------------------------------------------------------
# build_event_body — fact
# ---------------------------------------------------------------------------

class TestBuildEventBodyFact:
    def test_event_type(self):
        b = build_event_body("fact", {"subject_id": "sigrid", "key": "role", "value": "seer"})
        assert b["event_type"] == "fact"

    def test_subject_id(self):
        b = build_event_body("fact", {"subject_id": "sigrid", "key": "role", "value": "seer"})
        assert b["payload"]["subject_id"] == "sigrid"

    def test_key(self):
        b = build_event_body("fact", {"subject_id": "x", "key": "location", "value": "hall"})
        assert b["payload"]["key"] == "location"

    def test_value(self):
        b = build_event_body("fact", {"subject_id": "x", "key": "k", "value": "mead_hall"})
        assert b["payload"]["value"] == "mead_hall"

    def test_json_serializable(self):
        b = build_event_body("fact", {"subject_id": "x", "key": "k", "value": "v"})
        assert json.dumps(b)


# ---------------------------------------------------------------------------
# parse_response (mirrors Defold http callback logic in wyrdforge.lua)
# ---------------------------------------------------------------------------

class TestParseResponse:
    def test_200_valid_json(self):
        ok, data, err = parse_response(200, '{"response": "Hall is quiet."}')
        assert ok is True
        assert data["response"] == "Hall is quiet."
        assert err is None

    def test_200_invalid_json(self):
        ok, data, err = parse_response(200, "not-json")
        assert ok is False
        assert "JSON" in err

    def test_404_error(self):
        ok, data, err = parse_response(404, '{"error": "not found"}')
        assert ok is False
        assert "404" in err

    def test_500_error(self):
        ok, data, err = parse_response(500, '{}')
        assert ok is False
        assert "500" in err

    def test_201_accepted(self):
        ok, data, err = parse_response(201, '{"ok": true}')
        assert ok is True
        assert data.get("ok") is True

    def test_empty_body_200(self):
        ok, data, err = parse_response(200, '{}')
        assert ok is True
        assert data == {}
