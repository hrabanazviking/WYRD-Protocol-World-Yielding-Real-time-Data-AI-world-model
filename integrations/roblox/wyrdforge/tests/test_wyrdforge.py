"""
test_wyrdforge.py — Python mirror tests for WyrdForge Roblox Luau integration.

Tests the pure-logic functions from WyrdMapper.lua without requiring a
Roblox runtime or Luau interpreter.

Same strategy as integrations/minecraft and integrations/defold — mirror the
Luau logic in Python and run with pytest.
"""

import pytest
import json
import re


# ---------------------------------------------------------------------------
# Python mirrors of Luau WyrdMapper functions
# ---------------------------------------------------------------------------

def escape_json(s) -> str:
    """Mirror of WyrdMapper.escapeJson()"""
    if s is None:
        return ""
    s = str(s)
    out = []
    for c in s:
        if   c == '\\': out.append('\\\\')
        elif c == '"':  out.append('\\"')
        elif c == '\b': out.append('\\b')
        elif c == '\f': out.append('\\f')
        elif c == '\n': out.append('\\n')
        elif c == '\r': out.append('\\r')
        elif c == '\t': out.append('\\t')
        elif ord(c) < 0x20:
            out.append(f'\\u{ord(c):04x}')
        else:
            out.append(c)
    return ''.join(out)


def normalize_persona_id(name: str) -> str:
    """Mirror of WyrdMapper.normalizePersonaId()"""
    if not name:
        return ""
    result = name.lower()
    result = re.sub(r'[^a-z0-9_]', '_', result)
    result = re.sub(r'_+', '_', result)
    result = result.strip('_')
    return result[:64]


def build_query_body(persona_id: str, user_input: str) -> str:
    """Mirror of WyrdMapper.buildQueryBody()"""
    if not user_input or not user_input.strip():
        user_input = "What is the current world state?"
    return (f'{{"persona_id":"{escape_json(persona_id)}",'
            f'"user_input":"{escape_json(user_input)}",'
            f'"use_turn_loop":false}}')


def build_observation_body(title: str, summary: str) -> str:
    """Mirror of WyrdMapper.buildObservationBody()"""
    return (f'{{"event_type":"observation",'
            f'"payload":{{"title":"{escape_json(title)}",'
            f'"summary":"{escape_json(summary)}"}}}}')


def build_fact_body(subject_id: str, key: str, value: str) -> str:
    """Mirror of WyrdMapper.buildFactBody()"""
    return (f'{{"event_type":"fact",'
            f'"payload":{{"subject_id":"{escape_json(subject_id)}",'
            f'"key":"{escape_json(key)}",'
            f'"value":"{escape_json(value)}"}}}}')


def to_facts(npc_name: str, npc_id: str,
             place_id: str | None,
             custom_facts: dict | None) -> list[dict]:
    """Mirror of WyrdMapper.toFacts()"""
    facts = []
    if npc_name:
        facts.append({"key": "name", "value": npc_name})
    if npc_id:
        facts.append({"key": "npc_id", "value": str(npc_id)})
    if place_id:
        facts.append({"key": "place_id", "value": str(place_id)})
    if custom_facts:
        for k, v in custom_facts.items():
            if k and v is not None and v != "":
                facts.append({"key": k, "value": str(v)})
    return facts


def parse_response(body: str) -> str:
    """Mirror of WyrdMapper.parseResponse() — uses json.loads like the Python version."""
    fallback = "The spirits whisper nothing of note."
    if not body or not body.strip():
        return fallback
    try:
        data = json.loads(body)
        val = data.get("response", "")
        return val if val else fallback
    except json.JSONDecodeError:
        return fallback


# ===========================================================================
# Tests — EscapeJson
# ===========================================================================

class TestEscapeJson:
    def test_plain_string(self):
        assert escape_json("hello") == "hello"

    def test_double_quote(self):
        assert escape_json('"') == '\\"'

    def test_backslash(self):
        assert escape_json('\\') == '\\\\'

    def test_newline(self):
        assert escape_json('\n') == '\\n'

    def test_carriage_return(self):
        assert escape_json('\r') == '\\r'

    def test_tab(self):
        assert escape_json('\t') == '\\t'

    def test_backspace(self):
        assert escape_json('\b') == '\\b'

    def test_formfeed(self):
        assert escape_json('\f') == '\\f'

    def test_control_char(self):
        assert escape_json('\x01') == '\\u0001'

    def test_empty(self):
        assert escape_json("") == ""

    def test_none(self):
        assert escape_json(None) == ""

    def test_unicode_safe(self):
        assert escape_json("Sigríðr") == "Sigríðr"

    def test_mixed(self):
        result = escape_json('say "hello"\nworld')
        assert result == 'say \\"hello\\"\\nworld'

    def test_backslash_before_quote(self):
        # Ensure backslash is escaped before quote (order matters)
        result = escape_json('\\"')
        assert result == '\\\\\\"'


# ===========================================================================
# Tests — NormalizePersonaId
# ===========================================================================

class TestNormalizePersonaId:
    def test_lowercases(self):
        assert normalize_persona_id("Sigrid") == "sigrid"

    def test_replaces_spaces(self):
        assert normalize_persona_id("Sigrid Stormborn") == "sigrid_stormborn"

    def test_collapses_spaces(self):
        assert normalize_persona_id("a  b") == "a_b"

    def test_strips_leading_underscore(self):
        assert normalize_persona_id("_Sigrid") == "sigrid"

    def test_strips_trailing_underscore(self):
        assert normalize_persona_id("Sigrid_") == "sigrid"

    def test_truncates_at_64(self):
        assert len(normalize_persona_id("a" * 100)) == 64

    def test_empty(self):
        assert normalize_persona_id("") == ""

    def test_preserves_numbers(self):
        assert normalize_persona_id("npc_001") == "npc_001"

    def test_replaces_dots(self):
        assert normalize_persona_id("First.Last") == "first_last"

    def test_already_valid(self):
        assert normalize_persona_id("sigrid") == "sigrid"

    def test_roblox_display_name(self):
        # Roblox display names can have spaces and mixed case
        assert normalize_persona_id("CoolViking47") == "coolviking47"

    def test_replaces_dash(self):
        assert normalize_persona_id("Eirik-the-Red") == "eirik_the_red"

    def test_all_non_alpha(self):
        assert normalize_persona_id("!!!") == ""

    def test_preserves_underscores(self):
        assert normalize_persona_id("npc_sigrid_01") == "npc_sigrid_01"

    def test_number_only(self):
        # Numeric Roblox UserId
        assert normalize_persona_id("123456") == "123456"


# ===========================================================================
# Tests — BuildQueryBody
# ===========================================================================

class TestBuildQueryBody:
    def test_basic(self):
        body = build_query_body("sigrid", "Hello")
        parsed = json.loads(body)
        assert parsed["persona_id"] == "sigrid"
        assert parsed["user_input"] == "Hello"
        assert parsed["use_turn_loop"] is False

    def test_empty_input_defaults(self):
        body = build_query_body("sigrid", "")
        parsed = json.loads(body)
        assert parsed["user_input"] == "What is the current world state?"

    def test_whitespace_input_defaults(self):
        body = build_query_body("sigrid", "   ")
        parsed = json.loads(body)
        assert parsed["user_input"] == "What is the current world state?"

    def test_special_chars_in_input(self):
        body = build_query_body("sigrid", 'Say "hello"')
        parsed = json.loads(body)
        assert parsed["user_input"] == 'Say "hello"'

    def test_valid_json(self):
        body = build_query_body("gunnar", "What happened?")
        json.loads(body)  # must not raise

    def test_multiword_query(self):
        body = build_query_body("astrid", "What do the runes say about Yggdrasil?")
        parsed = json.loads(body)
        assert "Yggdrasil" in parsed["user_input"]

    def test_persona_id_in_body(self):
        body = build_query_body("leif_eriksson", "")
        parsed = json.loads(body)
        assert parsed["persona_id"] == "leif_eriksson"


# ===========================================================================
# Tests — BuildObservationBody
# ===========================================================================

class TestBuildObservationBody:
    def test_basic(self):
        body = build_observation_body("Player joined", "Sigrid entered the realm.")
        parsed = json.loads(body)
        assert parsed["event_type"] == "observation"
        assert parsed["payload"]["title"] == "Player joined"
        assert parsed["payload"]["summary"] == "Sigrid entered the realm."

    def test_valid_json(self):
        body = build_observation_body("Test", "Summary here.")
        json.loads(body)

    def test_special_chars(self):
        body = build_observation_body('He said "hi"', "Line1\nLine2")
        json.loads(body)

    def test_event_type_is_observation(self):
        body = build_observation_body("A", "B")
        assert '"event_type":"observation"' in body

    def test_roblox_specific(self):
        body = build_observation_body("Player touched altar", "Player 123456 interacted with RuneStone.")
        parsed = json.loads(body)
        assert "RuneStone" in parsed["payload"]["summary"]


# ===========================================================================
# Tests — BuildFactBody
# ===========================================================================

class TestBuildFactBody:
    def test_basic(self):
        body = build_fact_body("sigrid", "place_id", "12345678")
        parsed = json.loads(body)
        assert parsed["event_type"] == "fact"
        assert parsed["payload"]["subject_id"] == "sigrid"
        assert parsed["payload"]["key"] == "place_id"
        assert parsed["payload"]["value"] == "12345678"

    def test_valid_json(self):
        body = build_fact_body("npc_001", "role", "seer")
        json.loads(body)

    def test_special_chars_in_value(self):
        body = build_fact_body("x", "note", 'She said "skål"')
        json.loads(body)

    def test_event_type_is_fact(self):
        body = build_fact_body("a", "b", "c")
        assert '"event_type":"fact"' in body

    def test_subject_id_in_payload(self):
        body = build_fact_body("eirik", "rank", "jarl")
        parsed = json.loads(body)
        assert parsed["payload"]["subject_id"] == "eirik"


# ===========================================================================
# Tests — ToFacts
# ===========================================================================

class TestToFacts:
    def test_name_included(self):
        facts = to_facts("Sigrid", "12345", None, None)
        assert any(f["key"] == "name" and f["value"] == "Sigrid" for f in facts)

    def test_npc_id_included(self):
        facts = to_facts("X", "67890", None, None)
        assert any(f["key"] == "npc_id" and f["value"] == "67890" for f in facts)

    def test_place_id_included(self):
        facts = to_facts("X", "id", "987654321", None)
        assert any(f["key"] == "place_id" and f["value"] == "987654321" for f in facts)

    def test_place_id_omitted_when_none(self):
        facts = to_facts("X", "id", None, None)
        assert not any(f["key"] == "place_id" for f in facts)

    def test_custom_facts_included(self):
        facts = to_facts("X", "id", None, {"role": "seer"})
        assert any(f["key"] == "role" and f["value"] == "seer" for f in facts)

    def test_none_custom_value_omitted(self):
        facts = to_facts("X", "id", None, {"role": None})
        assert not any(f["key"] == "role" for f in facts)

    def test_empty_name_omitted(self):
        facts = to_facts("", "id", None, None)
        assert not any(f["key"] == "name" for f in facts)

    def test_multiple_custom_facts(self):
        facts = to_facts("Sigrid", "id", "12345",
                         {"rank": "jarl", "clan": "ravens"})
        keys = [f["key"] for f in facts]
        assert "rank" in keys
        assert "clan" in keys


# ===========================================================================
# Tests — ParseResponse
# ===========================================================================

class TestParseResponse:
    def test_extracts_response_field(self):
        body = '{"response":"The hall is quiet."}'
        assert parse_response(body) == "The hall is quiet."

    def test_empty_body_returns_fallback(self):
        assert parse_response("") == "The spirits whisper nothing of note."

    def test_none_body_returns_fallback(self):
        assert parse_response(None) == "The spirits whisper nothing of note."

    def test_missing_response_key(self):
        body = '{"status":"ok"}'
        assert parse_response(body) == "The spirits whisper nothing of note."

    def test_empty_response_value(self):
        body = '{"response":""}'
        assert parse_response(body) == "The spirits whisper nothing of note."

    def test_response_with_unicode(self):
        body = '{"response":"Skål, adventurer!"}'
        assert parse_response(body) == "Skål, adventurer!"

    def test_invalid_json_returns_fallback(self):
        assert parse_response("not json at all") == "The spirits whisper nothing of note."

    def test_long_response(self):
        long_text = "A" * 500
        body = json.dumps({"response": long_text})
        assert parse_response(body) == long_text

    def test_response_with_quotes(self):
        body = json.dumps({"response": 'She said "hello"'})
        assert 'hello' in parse_response(body)
