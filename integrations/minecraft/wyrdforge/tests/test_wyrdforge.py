"""
test_wyrdforge.py — Python mirror tests for WyrdForge Minecraft Fabric mod.

Tests the pure-logic functions from EntityMapper.java and ChatCommandHandler.java
without requiring a JVM or Minecraft runtime.

Same strategy as integrations/defold/wyrdforge/tests/test_wyrdforge.py —
mirror the Java logic in Python and run it with pytest.
"""

import pytest
import json
import re


# ---------------------------------------------------------------------------
# Python mirrors of Java pure-logic functions
# ---------------------------------------------------------------------------

def escape_json(s: str) -> str:
    """Mirror of EntityMapper.escapeJson()"""
    if s is None:
        return ""
    out = []
    for c in s:
        if   c == '"':  out.append('\\"')
        elif c == '\\': out.append('\\\\')
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


def to_persona_id(name: str) -> str:
    """Mirror of EntityMapper.toPersonaId()"""
    if not name:
        return ""
    result = name.lower()
    result = re.sub(r'[^a-z0-9_]', '_', result)
    result = re.sub(r'_+', '_', result)
    result = result.strip('_')
    return result[:64]


def build_query_body(persona_id: str, user_input: str) -> str:
    """Mirror of EntityMapper.buildQueryBody()"""
    if not user_input or not user_input.strip():
        user_input = "What is the current world state?"
    return (f'{{"persona_id":"{escape_json(persona_id)}",'
            f'"user_input":"{escape_json(user_input)}",'
            f'"use_turn_loop":false}}')


def build_observation_body(title: str, summary: str) -> str:
    """Mirror of EntityMapper.buildObservationBody()"""
    return (f'{{"event_type":"observation",'
            f'"payload":{{"title":"{escape_json(title)}",'
            f'"summary":"{escape_json(summary)}"}}}}')


def build_fact_body(subject_id: str, key: str, value: str) -> str:
    """Mirror of EntityMapper.buildFactBody()"""
    return (f'{{"event_type":"fact",'
            f'"payload":{{"subject_id":"{escape_json(subject_id)}",'
            f'"key":"{escape_json(key)}",'
            f'"value":"{escape_json(value)}"}}}}')


def to_facts(entity_name: str, entity_id: str,
             world_name: str | None,
             custom_facts: dict | None) -> list[dict]:
    """Mirror of EntityMapper.toFacts()"""
    facts = []
    if entity_name:
        facts.append({"key": "name", "value": entity_name})
    if entity_id:
        facts.append({"key": "entity_id", "value": entity_id})
    if world_name:
        facts.append({"key": "world", "value": world_name})
    if custom_facts:
        for k, v in custom_facts.items():
            if k and v:
                facts.append({"key": k, "value": v})
    return facts


def parse_response(body: str) -> str:
    """Mirror of EntityMapper.parseResponse()"""
    fallback = "The spirits whisper nothing of note."
    if not body or not body.strip():
        return fallback
    try:
        data = json.loads(body)
        val = data.get("response", "")
        return val if val else fallback
    except json.JSONDecodeError:
        return fallback


# ---------------------------------------------------------------------------
# Chat command parser mirror
# ---------------------------------------------------------------------------

class CommandType:
    NONE   = "NONE"
    QUERY  = "QUERY"
    SYNC   = "SYNC"
    HEALTH = "HEALTH"


def parse_chat_command(message: str | None) -> dict:
    """Mirror of ChatCommandHandler.parse()"""
    if not message:
        return {"type": CommandType.NONE, "persona_id": "", "query": ""}
    trimmed = message.strip()
    if not trimmed:
        return {"type": CommandType.NONE, "persona_id": "", "query": ""}
    lower = trimmed.lower()

    if lower == "/wyrd-health":
        return {"type": CommandType.HEALTH, "persona_id": "", "query": ""}

    if lower.startswith("/wyrd-sync"):
        rest = trimmed[len("/wyrd-sync"):].strip()
        return {"type": CommandType.SYNC, "persona_id": rest, "query": ""}

    if lower == "/wyrd" or lower.startswith("/wyrd "):
        rest = trimmed[len("/wyrd"):].strip()
        if not rest:
            return {"type": CommandType.QUERY, "persona_id": "", "query": ""}
        parts = rest.split(" ", 1)
        persona_id = parts[0]
        query      = parts[1].strip() if len(parts) > 1 else ""
        return {"type": CommandType.QUERY, "persona_id": persona_id, "query": query}

    return {"type": CommandType.NONE, "persona_id": "", "query": ""}


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


# ===========================================================================
# Tests — ToPersonaId
# ===========================================================================

class TestToPersonaId:
    def test_lowercases(self):
        assert to_persona_id("Sigrid") == "sigrid"

    def test_replaces_spaces(self):
        assert to_persona_id("Sigrid Stormborn") == "sigrid_stormborn"

    def test_collapses_spaces(self):
        assert to_persona_id("a  b") == "a_b"

    def test_strips_leading_underscore(self):
        assert to_persona_id("_Sigrid") == "sigrid"

    def test_strips_trailing_underscore(self):
        assert to_persona_id("Sigrid_") == "sigrid"

    def test_truncates_at_64(self):
        assert len(to_persona_id("a" * 100)) == 64

    def test_empty(self):
        assert to_persona_id("") == ""

    def test_preserves_numbers(self):
        assert to_persona_id("npc_001") == "npc_001"

    def test_replaces_dots(self):
        assert to_persona_id("First.Last") == "first_last"

    def test_already_valid(self):
        assert to_persona_id("sigrid") == "sigrid"

    def test_replaces_dash(self):
        assert to_persona_id("Eirik-the-Red") == "eirik_the_red"

    def test_minecraft_uuid_style(self):
        # UUIDs have hyphens — should normalize to underscores
        result = to_persona_id("550e8400-e29b-41d4-a716-446655440000")
        assert "_" in result
        assert "-" not in result

    def test_all_non_alpha(self):
        assert to_persona_id("!!!") == ""

    def test_none_like_empty(self):
        assert to_persona_id("") == ""

    def test_preserves_underscores(self):
        assert to_persona_id("npc_sigrid_01") == "npc_sigrid_01"


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
        parsed = json.loads(body)  # must parse cleanly
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
        body = build_observation_body("Player joined", "Sigrid joined Midgard.")
        parsed = json.loads(body)
        assert parsed["event_type"] == "observation"
        assert parsed["payload"]["title"] == "Player joined"
        assert parsed["payload"]["summary"] == "Sigrid joined Midgard."

    def test_valid_json(self):
        body = build_observation_body("Test", "Summary here.")
        json.loads(body)

    def test_special_chars(self):
        body = build_observation_body('He said "hi"', "Line1\nLine2")
        json.loads(body)  # must parse cleanly

    def test_event_type_is_observation(self):
        body = build_observation_body("A", "B")
        assert '"event_type":"observation"' in body


# ===========================================================================
# Tests — BuildFactBody
# ===========================================================================

class TestBuildFactBody:
    def test_basic(self):
        body = build_fact_body("sigrid", "world", "minecraft:overworld")
        parsed = json.loads(body)
        assert parsed["event_type"] == "fact"
        assert parsed["payload"]["subject_id"] == "sigrid"
        assert parsed["payload"]["key"] == "world"
        assert parsed["payload"]["value"] == "minecraft:overworld"

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
        facts = to_facts("Sigrid", "uuid-001", None, None)
        assert any(f["key"] == "name" and f["value"] == "Sigrid" for f in facts)

    def test_entity_id_included(self):
        facts = to_facts("X", "uuid-abc", None, None)
        assert any(f["key"] == "entity_id" and f["value"] == "uuid-abc" for f in facts)

    def test_world_included_when_set(self):
        facts = to_facts("X", "id", "minecraft:overworld", None)
        assert any(f["key"] == "world" and f["value"] == "minecraft:overworld" for f in facts)

    def test_world_omitted_when_none(self):
        facts = to_facts("X", "id", None, None)
        assert not any(f["key"] == "world" for f in facts)

    def test_custom_facts_included(self):
        facts = to_facts("X", "id", None, {"role": "seer"})
        assert any(f["key"] == "role" and f["value"] == "seer" for f in facts)

    def test_null_custom_value_omitted(self):
        facts = to_facts("X", "id", None, {"role": None})
        assert not any(f["key"] == "role" for f in facts)

    def test_empty_name_omitted(self):
        facts = to_facts("", "id", None, None)
        assert not any(f["key"] == "name" for f in facts)

    def test_multiple_custom_facts(self):
        facts = to_facts("Sigrid", "id", "minecraft:the_nether",
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


# ===========================================================================
# Tests — ChatCommandParser
# ===========================================================================

class TestChatCommandParser:
    def test_none_input(self):
        r = parse_chat_command(None)
        assert r["type"] == CommandType.NONE

    def test_empty_input(self):
        r = parse_chat_command("")
        assert r["type"] == CommandType.NONE

    def test_non_command(self):
        r = parse_chat_command("Hello everyone")
        assert r["type"] == CommandType.NONE

    def test_health_command(self):
        r = parse_chat_command("/wyrd-health")
        assert r["type"] == CommandType.HEALTH

    def test_health_case_insensitive(self):
        r = parse_chat_command("/WYRD-HEALTH")
        assert r["type"] == CommandType.HEALTH

    def test_sync_extracts_name(self):
        r = parse_chat_command("/wyrd-sync Sigrid Stormborn")
        assert r["type"] == CommandType.SYNC
        assert r["persona_id"] == "Sigrid Stormborn"

    def test_sync_no_name(self):
        r = parse_chat_command("/wyrd-sync")
        assert r["type"] == CommandType.SYNC
        assert r["persona_id"] == ""

    def test_query_persona_only(self):
        r = parse_chat_command("/wyrd sigrid")
        assert r["type"] == CommandType.QUERY
        assert r["persona_id"] == "sigrid"
        assert r["query"] == ""

    def test_query_persona_and_query(self):
        r = parse_chat_command("/wyrd sigrid What do the runes say?")
        assert r["persona_id"] == "sigrid"
        assert r["query"] == "What do the runes say?"

    def test_query_multiword_query(self):
        r = parse_chat_command("/wyrd gunnar Tell me about the hall of Valhalla")
        assert r["persona_id"] == "gunnar"
        assert r["query"] == "Tell me about the hall of Valhalla"

    def test_query_no_persona(self):
        r = parse_chat_command("/wyrd")
        assert r["type"] == CommandType.QUERY
        assert r["persona_id"] == ""

    def test_trims_whitespace(self):
        r = parse_chat_command("  /wyrd astrid  Storm?  ")
        assert r["persona_id"] == "astrid"
        assert r["query"] == "Storm?"

    def test_sync_case_insensitive(self):
        r = parse_chat_command("/WYRD-SYNC Leif")
        assert r["type"] == CommandType.SYNC
        assert r["persona_id"] == "Leif"

    def test_query_case_insensitive(self):
        r = parse_chat_command("/WYRD leif")
        assert r["type"] == CommandType.QUERY
        assert r["persona_id"] == "leif"

    def test_unrelated_slash_command(self):
        r = parse_chat_command("/give @a diamond 1")
        assert r["type"] == CommandType.NONE
