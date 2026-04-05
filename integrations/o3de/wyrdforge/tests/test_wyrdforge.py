"""
test_wyrdforge.py — Python mirror tests for WyrdForge O3DE Gem.

Tests the pure-logic functions from WyrdHelpers (Code/Source/WyrdHelpers.h/.cpp)
without requiring an O3DE build environment or AZ:: runtime.
"""

import pytest
import json
import re


# ---------------------------------------------------------------------------
# Python mirrors — same logic as WyrdHelpers.cpp (O3DE uses AZStd strings
# but the algorithms are identical to the CryEngine/Unreal versions)
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
        if c.isalnum() or c == '_':
            out.append(c); last_under = (c == '_')
        elif not last_under:
            out.append('_'); last_under = True
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
# TestEscapeJson
# ===========================================================================

class TestEscapeJson:
    def test_plain(self):       assert escape_json("hello") == "hello"
    def test_quote(self):       assert escape_json('"') == '\\"'
    def test_backslash(self):   assert escape_json('\\') == '\\\\'
    def test_newline(self):     assert escape_json('\n') == '\\n'
    def test_cr(self):          assert escape_json('\r') == '\\r'
    def test_tab(self):         assert escape_json('\t') == '\\t'
    def test_backspace(self):   assert escape_json('\b') == '\\b'
    def test_formfeed(self):    assert escape_json('\f') == '\\f'
    def test_control(self):     assert escape_json('\x02') == '\\u0002'
    def test_empty(self):       assert escape_json("") == ""
    def test_none(self):        assert escape_json(None) == ""
    def test_unicode(self):     assert escape_json("Sigríðr") == "Sigríðr"
    def test_mixed(self):       assert escape_json('a"b') == 'a\\"b'


# ===========================================================================
# TestNormalizePersonaId
# ===========================================================================

class TestNormalizePersonaId:
    def test_lowercases(self):          assert normalize_persona_id("SIGRID") == "sigrid"
    def test_spaces(self):              assert normalize_persona_id("Sigrid Stormborn") == "sigrid_stormborn"
    def test_collapses(self):           assert normalize_persona_id("a  b") == "a_b"
    def test_leading(self):             assert normalize_persona_id("_Sigrid") == "sigrid"
    def test_trailing(self):            assert normalize_persona_id("Sigrid_") == "sigrid"
    def test_truncates(self):           assert len(normalize_persona_id("a" * 100)) == 64
    def test_empty(self):               assert normalize_persona_id("") == ""
    def test_numbers(self):             assert normalize_persona_id("npc_001") == "npc_001"
    def test_dots(self):                assert normalize_persona_id("First.Last") == "first_last"
    def test_already_valid(self):       assert normalize_persona_id("sigrid") == "sigrid"
    def test_o3de_component_name(self): assert normalize_persona_id("WyrdNPC_Sigrid") == "wyrdnpc_sigrid"
    def test_all_special(self):         assert normalize_persona_id("@@@") == ""
    def test_dash(self):                assert normalize_persona_id("Eirik-Red") == "eirik_red"
    def test_preserve_underscores(self): assert normalize_persona_id("npc_seer") == "npc_seer"


# ===========================================================================
# TestBuildQueryBody
# ===========================================================================

class TestBuildQueryBody:
    def test_basic(self):
        p = json.loads(build_query_body("sigrid", "Hello"))
        assert p["persona_id"] == "sigrid" and p["use_turn_loop"] is False

    def test_empty_defaults(self):
        p = json.loads(build_query_body("sigrid", ""))
        assert "world state" in p["user_input"]

    def test_whitespace_defaults(self):
        p = json.loads(build_query_body("sigrid", " "))
        assert "world state" in p["user_input"]

    def test_special_chars(self):
        p = json.loads(build_query_body("sigrid", 'Say "hello"'))
        assert '"hello"' in p["user_input"]

    def test_valid_json(self):
        json.loads(build_query_body("gunnar", "What?"))

    def test_multiword(self):
        p = json.loads(build_query_body("astrid", "What do the runes say?"))
        assert "runes" in p["user_input"]

    def test_persona_id(self):
        p = json.loads(build_query_body("wyrdnpc_sigrid", ""))
        assert p["persona_id"] == "wyrdnpc_sigrid"


# ===========================================================================
# TestBuildObservationBody
# ===========================================================================

class TestBuildObservationBody:
    def test_basic(self):
        p = json.loads(build_observation_body("Entity activate", "Sigrid activated."))
        assert p["event_type"] == "observation"

    def test_valid_json(self):
        json.loads(build_observation_body("T", "S"))

    def test_special(self):
        json.loads(build_observation_body('He said "hi"', "Line\nTwo"))

    def test_event_type(self):
        assert '"event_type":"observation"' in build_observation_body("A", "B")

    def test_o3de_level_event(self):
        p = json.loads(build_observation_body("Level loaded", "O3DE level Valhalla activated."))
        assert "Valhalla" in p["payload"]["summary"]


# ===========================================================================
# TestBuildFactBody
# ===========================================================================

class TestBuildFactBody:
    def test_basic(self):
        p = json.loads(build_fact_body("sigrid", "level", "Valhalla"))
        assert p["payload"]["value"] == "Valhalla"

    def test_valid_json(self):
        json.loads(build_fact_body("npc", "role", "seer"))

    def test_special_chars(self):
        json.loads(build_fact_body("x", "note", 'She said "skål"'))

    def test_event_type(self):
        assert '"event_type":"fact"' in build_fact_body("a", "b", "c")

    def test_subject_id(self):
        p = json.loads(build_fact_body("eirik", "rank", "jarl"))
        assert p["payload"]["subject_id"] == "eirik"


# ===========================================================================
# TestToFacts
# ===========================================================================

class TestToFacts:
    def test_name(self):
        assert any(f["key"] == "name" for f in to_facts("Sigrid", "id", None, None))

    def test_entity_id(self):
        assert any(f["key"] == "entity_id" for f in to_facts("X", "uuid", None, None))

    def test_level_included(self):
        assert any(f["key"] == "level" for f in to_facts("X", "id", "Valhalla", None))

    def test_level_omitted(self):
        assert not any(f["key"] == "level" for f in to_facts("X", "id", None, None))

    def test_custom(self):
        assert any(f["key"] == "role" for f in to_facts("X", "id", None, [("role", "seer")]))

    def test_empty_custom_omitted(self):
        assert not any(f["key"] == "role" for f in to_facts("X", "id", None, [("role", "")]))

    def test_empty_name_omitted(self):
        assert not any(f["key"] == "name" for f in to_facts("", "id", None, None))

    def test_multi_custom(self):
        facts = to_facts("S", "id", None, [("a", "1"), ("b", "2")])
        keys = [f["key"] for f in facts]
        assert "a" in keys and "b" in keys


# ===========================================================================
# TestParseResponse
# ===========================================================================

class TestParseResponse:
    def test_extracts(self):
        assert parse_response('{"response":"Hall is quiet."}') == "Hall is quiet."

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

    def test_long(self):
        body = json.dumps({"response": "Z" * 300})
        assert len(parse_response(body)) == 300
