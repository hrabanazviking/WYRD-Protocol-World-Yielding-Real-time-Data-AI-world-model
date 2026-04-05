"""
test_wyrdforge.py — Python mirror tests for WyrdForge Unreal Engine 5 plugin.

Tests the pure-logic functions from WyrdHelpers.cpp without requiring
Unreal Engine build tools or a UE5 runtime.
"""

import pytest
import json
import re


# ---------------------------------------------------------------------------
# Python mirrors of WyrdHelpers C++ functions
# ---------------------------------------------------------------------------

def escape_json(s) -> str:
    if s is None: return ""
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
        elif ord(c) < 0x20: out.append(f'\\u{ord(c):04x}')
        else: out.append(c)
    return ''.join(out)


def normalize_persona_id(name: str) -> str:
    if not name: return ""
    out, last_under = [], False
    for c in name.lower():
        if c.isascii() and c.isalnum():
            out.append(c)
            last_under = False
        elif not last_under:
            out.append('_')
            last_under = True
    result = ''.join(out).strip('_')
    return result[:64]


def build_query_body(persona_id: str, user_input: str) -> str:
    if not user_input or not user_input.strip():
        user_input = "What is the current world state?"
    return (f'{{"persona_id":"{escape_json(persona_id)}",'
            f'"user_input":"{escape_json(user_input)}",'
            f'"use_turn_loop":false}}')


def build_observation_body(title: str, summary: str) -> str:
    return (f'{{"event_type":"observation",'
            f'"payload":{{"title":"{escape_json(title)}",'
            f'"summary":"{escape_json(summary)}"}}}}')


def build_fact_body(subject_id: str, key: str, value: str) -> str:
    return (f'{{"event_type":"fact",'
            f'"payload":{{"subject_id":"{escape_json(subject_id)}",'
            f'"key":"{escape_json(key)}",'
            f'"value":"{escape_json(value)}"}}}}')


def to_facts(entity_name: str, entity_id: str, level_name: str | None,
             custom_facts: list[tuple] | None) -> list[dict]:
    facts = []
    if entity_name: facts.append({"key": "name",      "value": entity_name})
    if entity_id:   facts.append({"key": "entity_id", "value": entity_id})
    if level_name:  facts.append({"key": "level",     "value": level_name})
    if custom_facts:
        for k, v in custom_facts:
            if k and v: facts.append({"key": k, "value": v})
    return facts


def parse_response(body: str) -> str:
    fallback = "The spirits whisper nothing of note."
    if not body or not body.strip(): return fallback
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
    def test_plain(self):         assert escape_json("hello") == "hello"
    def test_double_quote(self):  assert escape_json('"') == '\\"'
    def test_backslash(self):     assert escape_json('\\') == '\\\\'
    def test_newline(self):       assert escape_json('\n') == '\\n'
    def test_carriage_return(self): assert escape_json('\r') == '\\r'
    def test_tab(self):           assert escape_json('\t') == '\\t'
    def test_backspace(self):     assert escape_json('\b') == '\\b'
    def test_formfeed(self):      assert escape_json('\f') == '\\f'
    def test_control(self):       assert escape_json('\x01') == '\\u0001'
    def test_empty(self):         assert escape_json("") == ""
    def test_none(self):          assert escape_json(None) == ""
    def test_unicode_passthru(self): assert escape_json("Sigríðr") == "Sigríðr"
    def test_mixed(self):
        assert escape_json('say "hi"\nworld') == 'say \\"hi\\"\\nworld'


# ===========================================================================
# Tests — NormalizePersonaId
# ===========================================================================

class TestNormalizePersonaId:
    def test_lowercases(self):               assert normalize_persona_id("Sigrid") == "sigrid"
    def test_replaces_spaces(self):          assert normalize_persona_id("Sigrid Stormborn") == "sigrid_stormborn"
    def test_collapses_spaces(self):         assert normalize_persona_id("a  b") == "a_b"
    def test_strips_leading(self):           assert normalize_persona_id("_Sigrid") == "sigrid"
    def test_strips_trailing(self):          assert normalize_persona_id("Sigrid_") == "sigrid"
    def test_truncates(self):                assert len(normalize_persona_id("a" * 100)) == 64
    def test_empty(self):                    assert normalize_persona_id("") == ""
    def test_preserves_numbers(self):        assert normalize_persona_id("npc_001") == "npc_001"
    def test_replaces_dots(self):            assert normalize_persona_id("First.Last") == "first_last"
    def test_already_valid(self):            assert normalize_persona_id("sigrid") == "sigrid"
    def test_ue_asset_name(self):            assert normalize_persona_id("BP_NPC_Sigrid") == "bp_npc_sigrid"
    def test_all_non_alpha(self):            assert normalize_persona_id("!!!") == ""
    def test_replaces_dash(self):            assert normalize_persona_id("Eirik-Red") == "eirik_red"
    def test_preserves_underscores(self):    assert normalize_persona_id("npc_01_sigrid") == "npc_01_sigrid"
    def test_number_only(self):              assert normalize_persona_id("12345") == "12345"


# ===========================================================================
# Tests — BuildQueryBody
# ===========================================================================

class TestBuildQueryBody:
    def test_basic(self):
        p = json.loads(build_query_body("sigrid", "Hello"))
        assert p["persona_id"] == "sigrid" and p["user_input"] == "Hello"
        assert p["use_turn_loop"] is False

    def test_empty_defaults(self):
        p = json.loads(build_query_body("sigrid", ""))
        assert "world state" in p["user_input"]

    def test_whitespace_defaults(self):
        p = json.loads(build_query_body("sigrid", "  "))
        assert "world state" in p["user_input"]

    def test_special_chars(self):
        p = json.loads(build_query_body("sigrid", 'Say "hello"'))
        assert p["user_input"] == 'Say "hello"'

    def test_valid_json(self):
        json.loads(build_query_body("gunnar", "What happened?"))

    def test_multiword(self):
        p = json.loads(build_query_body("astrid", "What do the runes say?"))
        assert "runes" in p["user_input"]

    def test_persona_id(self):
        p = json.loads(build_query_body("bp_npc_leif", ""))
        assert p["persona_id"] == "bp_npc_leif"


# ===========================================================================
# Tests — BuildObservationBody
# ===========================================================================

class TestBuildObservationBody:
    def test_basic(self):
        p = json.loads(build_observation_body("NPC spawned", "Sigrid appeared in Midgard."))
        assert p["event_type"] == "observation"
        assert p["payload"]["title"] == "NPC spawned"

    def test_valid_json(self):
        json.loads(build_observation_body("T", "S"))

    def test_special_chars(self):
        json.loads(build_observation_body('She said "hi"', "Line\nTwo"))

    def test_event_type(self):
        assert '"event_type":"observation"' in build_observation_body("A", "B")

    def test_ue_level_event(self):
        p = json.loads(build_observation_body("Level loaded", "Player entered Valhalla."))
        assert "Valhalla" in p["payload"]["summary"]


# ===========================================================================
# Tests — BuildFactBody
# ===========================================================================

class TestBuildFactBody:
    def test_basic(self):
        p = json.loads(build_fact_body("sigrid", "level", "Valhalla"))
        assert p["event_type"] == "fact"
        assert p["payload"]["subject_id"] == "sigrid"
        assert p["payload"]["key"] == "level"
        assert p["payload"]["value"] == "Valhalla"

    def test_valid_json(self):
        json.loads(build_fact_body("npc_001", "role", "seer"))

    def test_special_chars(self):
        json.loads(build_fact_body("x", "note", 'She said "skål"'))

    def test_event_type(self):
        assert '"event_type":"fact"' in build_fact_body("a", "b", "c")

    def test_subject_id(self):
        p = json.loads(build_fact_body("eirik", "rank", "jarl"))
        assert p["payload"]["subject_id"] == "eirik"


# ===========================================================================
# Tests — ToFacts
# ===========================================================================

class TestToFacts:
    def test_name(self):
        facts = to_facts("Sigrid", "uuid-001", None, None)
        assert any(f["key"] == "name" and f["value"] == "Sigrid" for f in facts)

    def test_entity_id(self):
        facts = to_facts("X", "uuid-abc", None, None)
        assert any(f["key"] == "entity_id" for f in facts)

    def test_level_included(self):
        facts = to_facts("X", "id", "Valhalla", None)
        assert any(f["key"] == "level" and f["value"] == "Valhalla" for f in facts)

    def test_level_omitted(self):
        facts = to_facts("X", "id", None, None)
        assert not any(f["key"] == "level" for f in facts)

    def test_custom_included(self):
        facts = to_facts("X", "id", None, [("role", "seer")])
        assert any(f["key"] == "role" for f in facts)

    def test_empty_custom_omitted(self):
        facts = to_facts("X", "id", None, [("role", "")])
        assert not any(f["key"] == "role" for f in facts)

    def test_empty_name_omitted(self):
        facts = to_facts("", "id", None, None)
        assert not any(f["key"] == "name" for f in facts)

    def test_multiple_custom(self):
        facts = to_facts("Sigrid", "id", "Midgard", [("clan", "ravens"), ("rank", "jarl")])
        keys = [f["key"] for f in facts]
        assert "clan" in keys and "rank" in keys


# ===========================================================================
# Tests — ParseResponse
# ===========================================================================

class TestParseResponse:
    def test_extracts(self):
        assert parse_response('{"response":"The hall is quiet."}') == "The hall is quiet."

    def test_empty_fallback(self):
        assert parse_response("") == "The spirits whisper nothing of note."

    def test_none_fallback(self):
        assert parse_response(None) == "The spirits whisper nothing of note."

    def test_missing_key(self):
        assert parse_response('{"status":"ok"}') == "The spirits whisper nothing of note."

    def test_empty_value(self):
        assert parse_response('{"response":""}') == "The spirits whisper nothing of note."

    def test_unicode(self):
        assert parse_response('{"response":"Skål!"}') == "Skål!"

    def test_invalid_json(self):
        assert parse_response("not json") == "The spirits whisper nothing of note."

    def test_long_response(self):
        body = json.dumps({"response": "A" * 500})
        assert len(parse_response(body)) == 500
