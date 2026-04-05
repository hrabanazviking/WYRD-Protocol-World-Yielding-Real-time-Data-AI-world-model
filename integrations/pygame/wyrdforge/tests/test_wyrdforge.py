"""test_wyrdforge.py — pytest suite for the WYRD pygame bridge.

Tests run directly against the Python bridge modules — no pygame runtime,
no WyrdHTTPServer, no network. HTTP calls are mocked via unittest.mock.
"""
import sys
import os
import json
import re
import threading
import time
from unittest.mock import MagicMock, patch, call

import pytest

# Make parent package importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wyrd_pygame_helpers import (
    normalize_persona_id,
    escape_json,
    build_query_body,
    build_observation_body,
    build_fact_body,
    parse_response,
    to_facts,
    WyrdFact,
)
from wyrd_pygame_client import WyrdPygameClient
from wyrd_pygame_loop import WyrdPygameLoop


# ===========================================================================
# normalize_persona_id
# ===========================================================================

class TestNormalizePersonaId:
    def test_simple_name(self):
        assert normalize_persona_id("Sigrid") == "sigrid"

    def test_two_words(self):
        assert normalize_persona_id("Sigrid Stormborn") == "sigrid_stormborn"

    def test_already_snake_case(self):
        assert normalize_persona_id("sigrid_stormborn") == "sigrid_stormborn"

    def test_special_chars_replaced(self):
        assert normalize_persona_id("NPC #42!") == "npc_42"

    def test_consecutive_underscores_collapsed(self):
        assert normalize_persona_id("goblin  king") == "goblin_king"

    def test_leading_trailing_stripped(self):
        assert normalize_persona_id("  sigrid  ") == "sigrid"

    def test_uppercase(self):
        assert normalize_persona_id("GOBLIN KING") == "goblin_king"

    def test_numbers_preserved(self):
        assert normalize_persona_id("guard_01") == "guard_01"

    def test_hyphens_replaced(self):
        assert normalize_persona_id("dark-elf") == "dark_elf"

    def test_empty_string(self):
        assert normalize_persona_id("") == ""

    def test_max_64_chars(self):
        long_name = "a" * 100
        assert len(normalize_persona_id(long_name)) == 64

    def test_unicode_replaced(self):
        result = normalize_persona_id("Björn")
        assert re.match(r"^[a-z0-9_]*$", result)


# ===========================================================================
# escape_json
# ===========================================================================

class TestEscapeJson:
    def test_plain_string(self):
        assert escape_json("hello world") == "hello world"

    def test_double_quote(self):
        assert escape_json('say "hello"') == 'say \\"hello\\"'

    def test_backslash(self):
        assert escape_json("path\\to\\file") == "path\\\\to\\\\file"

    def test_newline(self):
        assert escape_json("line1\nline2") == "line1\\nline2"

    def test_tab(self):
        assert escape_json("col1\tcol2") == "col1\\tcol2"

    def test_carriage_return(self):
        assert escape_json("text\rmore") == "text\\rmore"

    def test_control_char(self):
        result = escape_json("\x01")
        assert result == "\\u0001"

    def test_none_returns_empty(self):
        assert escape_json(None) == ""


# ===========================================================================
# build_query_body
# ===========================================================================

class TestBuildQueryBody:
    def test_basic(self):
        body = build_query_body("sigrid", "What is happening?")
        data = json.loads(body)
        assert data["persona_id"] == "sigrid"
        assert data["user_input"] == "What is happening?"
        assert data["use_turn_loop"] is False

    def test_empty_input_gets_default(self):
        body = build_query_body("sigrid", "")
        data = json.loads(body)
        assert data["user_input"] == "What is the current world state?"

    def test_whitespace_input_gets_default(self):
        body = build_query_body("sigrid", "   ")
        data = json.loads(body)
        assert "current world state" in data["user_input"]

    def test_special_chars_in_input_escaped(self):
        body = build_query_body("npc", 'He said "run!"')
        data = json.loads(body)
        assert data["user_input"] == 'He said "run!"'

    def test_newline_in_input_escaped(self):
        body = build_query_body("npc", "line1\nline2")
        data = json.loads(body)
        assert "line1" in data["user_input"]

    def test_valid_json(self):
        body = build_query_body("test_npc", "hello")
        json.loads(body)  # must not raise


# ===========================================================================
# build_observation_body
# ===========================================================================

class TestBuildObservationBody:
    def test_basic(self):
        body = build_observation_body("Army sighted", "300 warriors at the gate.")
        data = json.loads(body)
        assert data["event_type"] == "observation"
        assert data["payload"]["title"] == "Army sighted"
        assert data["payload"]["summary"] == "300 warriors at the gate."

    def test_special_chars(self):
        body = build_observation_body('Event "A"', "Summary\nwith newline")
        data = json.loads(body)
        assert data["payload"]["title"] == 'Event "A"'

    def test_valid_json(self):
        json.loads(build_observation_body("t", "s"))

    def test_empty_fields(self):
        body = build_observation_body("", "")
        data = json.loads(body)
        assert data["payload"]["title"] == ""


# ===========================================================================
# build_fact_body
# ===========================================================================

class TestBuildFactBody:
    def test_basic(self):
        body = build_fact_body("sigrid", "location", "great_hall")
        data = json.loads(body)
        assert data["event_type"] == "fact"
        assert data["payload"]["subject_id"] == "sigrid"
        assert data["payload"]["key"] == "location"
        assert data["payload"]["value"] == "great_hall"

    def test_special_chars_escaped(self):
        body = build_fact_body("npc", "name", 'He said "hi"')
        data = json.loads(body)
        assert data["payload"]["value"] == 'He said "hi"'

    def test_valid_json(self):
        json.loads(build_fact_body("s", "k", "v"))

    def test_empty_value(self):
        body = build_fact_body("npc", "status", "")
        data = json.loads(body)
        assert data["payload"]["value"] == ""


# ===========================================================================
# parse_response
# ===========================================================================

class TestParseResponse:
    def test_basic(self):
        raw = '{"response":"The scouts saw 300 warriors.","persona_id":"sigrid"}'
        assert parse_response(raw) == "The scouts saw 300 warriors."

    def test_empty_string(self):
        assert parse_response("") == ""

    def test_none_like_empty(self):
        assert parse_response(None) == ""

    def test_missing_response_field(self):
        assert parse_response('{"status":"ok"}') == ""

    def test_escaped_quote_in_response(self):
        raw = r'{"response":"She said \"hello\"."}'
        result = parse_response(raw)
        assert 'hello' in result

    def test_response_with_newline_escape(self):
        raw = '{"response":"line1\\nline2"}'
        result = parse_response(raw)
        assert "line1" in result


# ===========================================================================
# to_facts
# ===========================================================================

class TestToFacts:
    def test_single_fact(self):
        raw = '[{"subject_id":"sigrid","key":"location","value":"great_hall"}]'
        facts = to_facts(raw)
        assert len(facts) == 1
        assert facts[0].subject_id == "sigrid"
        assert facts[0].key == "location"
        assert facts[0].value == "great_hall"

    def test_multiple_facts(self):
        raw = (
            '[{"subject_id":"sigrid","key":"name","value":"Sigrid Stormborn"},'
            '{"subject_id":"sigrid","key":"role","value":"völva"}]'
        )
        facts = to_facts(raw)
        assert len(facts) == 2

    def test_empty_string(self):
        assert to_facts("") == []

    def test_invalid_json(self):
        assert to_facts("not json") == []


# ===========================================================================
# WyrdPygameClient — init
# ===========================================================================

class TestWyrdPygameClientInit:
    def test_defaults(self):
        c = WyrdPygameClient()
        assert c.host == "localhost"
        assert c.port == 8765
        assert c.timeout == 10
        assert c.silent_on_error is True

    def test_custom_host_port(self):
        c = WyrdPygameClient(host="192.168.1.50", port=9000)
        assert c.host == "192.168.1.50"
        assert c.port == 9000

    def test_base_url(self):
        c = WyrdPygameClient(host="myserver", port=8765)
        assert c.base_url == "http://myserver:8765"

    def test_custom_fallback(self):
        c = WyrdPygameClient(fallback_response="Silence.")
        assert c.fallback_response == "Silence."


# ===========================================================================
# WyrdPygameClient — query (mocked HTTP)
# ===========================================================================

class TestWyrdPygameClientQuery:
    def _mock_response(self, text: str):
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = text.encode("utf-8")
        return mock_resp

    def test_query_returns_response(self):
        client = WyrdPygameClient()
        payload = '{"response":"The army approaches.","persona_id":"sigrid"}'
        with patch("urllib.request.urlopen", return_value=self._mock_response(payload)):
            result = client.query("sigrid", "What do you see?")
        assert result == "The army approaches."

    def test_query_normalizes_persona_id(self):
        client = WyrdPygameClient()
        payload = '{"response":"ok","persona_id":"goblin_king"}'
        captured = {}
        original_post = client._post

        def capture_post(path, body):
            captured["body"] = body
            return payload

        client._post = capture_post
        client.query("Goblin King", "hello")
        assert '"goblin_king"' in captured["body"]

    def test_query_silent_on_error(self):
        client = WyrdPygameClient(silent_on_error=True, fallback_response="Fallback.")
        with patch("urllib.request.urlopen", side_effect=OSError("refused")):
            result = client.query("sigrid", "hello")
        assert result == "Fallback."

    def test_query_raises_when_not_silent(self):
        client = WyrdPygameClient(silent_on_error=False)
        with patch("urllib.request.urlopen", side_effect=OSError("refused")):
            with pytest.raises(OSError):
                client.query("sigrid", "hello")

    def test_query_fallback_on_empty_response(self):
        client = WyrdPygameClient(fallback_response="Nothing.")
        with patch("urllib.request.urlopen", return_value=self._mock_response('{"status":"ok"}')):
            result = client.query("sigrid", "hello")
        assert result == "Nothing."

    def test_query_default_prompt_on_empty_input(self):
        client = WyrdPygameClient()
        payload = '{"response":"ok"}'
        captured = {}
        def capture_post(path, body):
            captured["body"] = body
            return payload
        client._post = capture_post
        client.query("sigrid", "")
        assert "current world state" in captured["body"]


# ===========================================================================
# WyrdPygameClient — push fire-and-forget
# ===========================================================================

class TestWyrdPygameClientPush:
    def test_push_observation_non_blocking(self):
        client = WyrdPygameClient()
        called = threading.Event()

        def fake_post(path, body):
            called.set()
            return '{"status":"ok"}'

        client._post = fake_post
        client.push_observation("Army spotted", "300 warriors.")
        assert called.wait(timeout=2.0), "fire-and-forget thread never fired"

    def test_push_fact_non_blocking(self):
        client = WyrdPygameClient()
        called = threading.Event()

        def fake_post(path, body):
            called.set()
            return '{"status":"ok"}'

        client._post = fake_post
        client.push_fact("sigrid", "location", "great_hall")
        assert called.wait(timeout=2.0)

    def test_push_observation_silent_on_network_error(self):
        client = WyrdPygameClient(silent_on_error=True)
        # Should not raise even when server is down
        with patch("urllib.request.urlopen", side_effect=OSError("refused")):
            client.push_observation("event", "summary")
        time.sleep(0.05)  # let daemon thread finish


# ===========================================================================
# WyrdPygameClient — health check
# ===========================================================================

class TestWyrdPygameClientHealthCheck:
    def test_returns_true_on_200(self):
        client = WyrdPygameClient()
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.status = 200
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert client.health_check() is True

    def test_returns_false_on_connection_error(self):
        client = WyrdPygameClient()
        with patch("urllib.request.urlopen", side_effect=OSError("refused")):
            assert client.health_check() is False

    def test_returns_false_on_timeout(self):
        import urllib.error
        client = WyrdPygameClient()
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            assert client.health_check() is False


# ===========================================================================
# WyrdPygameLoop — on_npc_interact
# ===========================================================================

class TestWyrdPygameLoopOnNpcInteract:
    def _loop(self, response: str = "ok") -> WyrdPygameLoop:
        client = WyrdPygameClient()
        client.query = MagicMock(return_value=response)
        return WyrdPygameLoop(client)

    def test_calls_query(self):
        loop = self._loop("The dragon stirs.")
        result = loop.on_npc_interact("dragon", "Are you awake?")
        assert result == "The dragon stirs."
        loop.client.query.assert_called_once()

    def test_normalizes_entity_id(self):
        loop = self._loop()
        loop.on_npc_interact("Dark Elf Guard", "hello")
        args = loop.client.query.call_args[0]
        assert args[0] == "dark_elf_guard"

    def test_passes_player_input(self):
        loop = self._loop()
        loop.on_npc_interact("guard", "What's the password?")
        args = loop.client.query.call_args[0]
        assert args[1] == "What's the password?"

    def test_returns_fallback_on_error(self):
        client = WyrdPygameClient(fallback_response="Silence.")
        client.query = MagicMock(return_value="Silence.")
        loop = WyrdPygameLoop(client)
        result = loop.on_npc_interact("npc", "hi")
        assert result == "Silence."


# ===========================================================================
# WyrdPygameLoop — on_scene_change
# ===========================================================================

class TestWyrdPygameLoopOnSceneChange:
    def _loop(self) -> WyrdPygameLoop:
        client = WyrdPygameClient()
        client.push_observation = MagicMock()
        return WyrdPygameLoop(client)

    def test_pushes_observation(self):
        loop = self._loop()
        loop.on_scene_change("dark_forest")
        loop.client.push_observation.assert_called_once()

    def test_title_contains_location(self):
        loop = self._loop()
        loop.on_scene_change("dark_forest")
        title = loop.client.push_observation.call_args[0][0]
        assert "dark_forest" in title

    def test_custom_description_used(self):
        loop = self._loop()
        loop.on_scene_change("cave", "A damp, dark cavern.")
        summary = loop.client.push_observation.call_args[0][1]
        assert "damp" in summary


# ===========================================================================
# WyrdPygameLoop — on_npc_move
# ===========================================================================

class TestWyrdPygameLoopOnNpcMove:
    def _loop(self) -> WyrdPygameLoop:
        client = WyrdPygameClient()
        client.push_fact = MagicMock()
        return WyrdPygameLoop(client)

    def test_pushes_location_fact(self):
        loop = self._loop()
        loop.on_npc_move("goblin_scout", "cave_entrance")
        loop.client.push_fact.assert_called_once_with(
            "goblin_scout", "location", "cave_entrance"
        )

    def test_normalizes_entity_id(self):
        loop = self._loop()
        loop.on_npc_move("Goblin Scout", "cave")
        pid = loop.client.push_fact.call_args[0][0]
        assert pid == "goblin_scout"

    def test_passes_new_location(self):
        loop = self._loop()
        loop.on_npc_move("npc", "great_hall")
        loc = loop.client.push_fact.call_args[0][2]
        assert loc == "great_hall"


# ===========================================================================
# WyrdPygameLoop — sync_entity integration
# ===========================================================================

class TestWyrdPygameClientSyncEntity:
    def test_sync_pushes_name_and_location(self):
        client = WyrdPygameClient()
        pushed: list[tuple] = []

        def fake_push(subject_id, key, value):
            pushed.append((subject_id, key, value))

        client.push_fact = fake_push
        client.sync_entity("Goblin King", name="Goblin King", location="throne_room")
        keys = {p[1] for p in pushed}
        assert "name" in keys
        assert "location" in keys

    def test_sync_skips_empty_fields(self):
        client = WyrdPygameClient()
        pushed: list[tuple] = []

        def fake_push(subject_id, key, value):
            pushed.append((subject_id, key, value))

        client.push_fact = fake_push
        client.sync_entity("npc", name="NPC", location="", status="")
        assert len(pushed) == 1
        assert pushed[0][1] == "name"

    def test_sync_normalizes_entity_id(self):
        client = WyrdPygameClient()
        pushed: list[tuple] = []

        def fake_push(subject_id, key, value):
            pushed.append((subject_id, key, value))

        client.push_fact = fake_push
        client.sync_entity("Dark Elf Guard", name="Dark Elf Guard")
        assert pushed[0][0] == "dark_elf_guard"
