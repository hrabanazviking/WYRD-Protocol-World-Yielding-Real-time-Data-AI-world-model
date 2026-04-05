"""
test_relay.py — Tests for WYRD Cloud Relay pure-logic modules.

Tests RateLimiter, TokenValidator, RelayConfig, and TUI helpers
without requiring FastAPI, uvicorn, or httpx to be installed.
"""

import pytest
import time
import sys
import os

# Make relay importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from tools.wyrd_cloud_relay.relay import (
    RateLimiter, TokenValidator, RelayConfig, build_cors_headers
)
from tools.wyrd_tui import (
    normalize_persona_id,
    parse_world_response,
    parse_facts_response,
    format_uptime,
    build_command_help,
    handle_tui_command,
    EntityInfo,
    MemoryEntry,
    WorldSummary,
    TuiState,
    WyrdRelayClient,
)


# ===========================================================================
# RateLimiter
# ===========================================================================

class TestRateLimiter:
    def test_allows_within_limit(self):
        rl = RateLimiter(10)
        for _ in range(10):
            assert rl.is_allowed("client1")

    def test_blocks_over_limit(self):
        rl = RateLimiter(3)
        assert rl.is_allowed("c")
        assert rl.is_allowed("c")
        assert rl.is_allowed("c")
        assert not rl.is_allowed("c")

    def test_zero_limit_always_allows(self):
        rl = RateLimiter(0)
        for _ in range(100):
            assert rl.is_allowed("c")

    def test_different_clients_independent(self):
        rl = RateLimiter(2)
        rl.is_allowed("a"); rl.is_allowed("a")
        assert not rl.is_allowed("a")
        assert rl.is_allowed("b")

    def test_old_requests_evicted(self):
        rl = RateLimiter(2)
        past = time.monotonic() - 61.0
        rl._log["c"] = [past, past]
        # Old entries should be evicted, allowing new requests
        assert rl.is_allowed("c")

    def test_request_count_empty(self):
        rl = RateLimiter(10)
        assert rl.request_count("nobody") == 0

    def test_request_count_increments(self):
        rl = RateLimiter(10)
        rl.is_allowed("x")
        rl.is_allowed("x")
        assert rl.request_count("x") == 2

    def test_request_count_excludes_old(self):
        rl = RateLimiter(10)
        past = time.monotonic() - 61.0
        rl._log["y"] = [past, past, time.monotonic()]
        assert rl.request_count("y") == 1


# ===========================================================================
# TokenValidator
# ===========================================================================

class TestTokenValidator:
    def test_no_tokens_auth_disabled(self):
        v = TokenValidator([])
        assert not v.auth_required

    def test_no_tokens_always_valid(self):
        v = TokenValidator([])
        ok, key = v.validate(None)
        assert ok and key == "anon"

    def test_no_tokens_any_header(self):
        v = TokenValidator([])
        ok, key = v.validate("Bearer anything")
        assert ok and key == "anon"

    def test_auth_required_when_tokens_set(self):
        v = TokenValidator(["secret"])
        assert v.auth_required

    def test_valid_token_accepted(self):
        v = TokenValidator(["secret-token"])
        ok, key = v.validate("Bearer secret-token")
        assert ok and key == "secret-token"

    def test_invalid_token_rejected(self):
        v = TokenValidator(["secret"])
        ok, _ = v.validate("Bearer wrong")
        assert not ok

    def test_missing_header_rejected(self):
        v = TokenValidator(["secret"])
        ok, _ = v.validate(None)
        assert not ok

    def test_malformed_header_rejected(self):
        v = TokenValidator(["secret"])
        ok, _ = v.validate("secret")  # no "Bearer " prefix
        assert not ok

    def test_multiple_tokens(self):
        v = TokenValidator(["token-a", "token-b"])
        ok1, _ = v.validate("Bearer token-a")
        ok2, _ = v.validate("Bearer token-b")
        ok3, _ = v.validate("Bearer token-c")
        assert ok1 and ok2 and not ok3

    def test_whitespace_stripped_from_tokens(self):
        v = TokenValidator(["  secret  ", ""])
        ok, key = v.validate("Bearer secret")
        assert ok and key == "secret"

    def test_empty_string_token_ignored(self):
        v = TokenValidator([""])
        assert not v.auth_required


# ===========================================================================
# RelayConfig
# ===========================================================================

class TestRelayConfig:
    def test_defaults(self):
        c = RelayConfig()
        assert c.port == 9000
        assert "localhost:8765" in c.upstream_url
        assert c.rate_limit == 60

    def test_upstream_trailing_slash_stripped(self):
        c = RelayConfig(upstream_url="http://example.com:8765/")
        assert not c.upstream_url.endswith("/")

    def test_upstream_path_composition(self):
        c = RelayConfig(upstream_url="http://example.com:8765")
        assert c.upstream("/query") == "http://example.com:8765/query"

    def test_cors_default_wildcard(self):
        c = RelayConfig()
        assert "*" in c.cors_origins

    def test_repr_contains_key_info(self):
        c = RelayConfig(upstream_url="http://example.com", port=9001,
                        tokens=["tok"], rate_limit=30)
        r = repr(c)
        assert "9001" in r and "enabled" in r

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("WYRD_UPSTREAM_URL", "http://myserver:1234")
        monkeypatch.setenv("WYRD_RELAY_PORT",   "8888")
        monkeypatch.setenv("WYRD_RATE_LIMIT",   "30")
        c = RelayConfig.from_env()
        assert c.upstream_url == "http://myserver:1234"
        assert c.port == 8888
        assert c.rate_limit == 30


# ===========================================================================
# build_cors_headers
# ===========================================================================

class TestBuildCorsHeaders:
    def test_wildcard(self):
        h = build_cors_headers(["*"])
        assert h["Access-Control-Allow-Origin"] == "*"

    def test_specific_origins(self):
        h = build_cors_headers(["https://example.com"])
        assert "example.com" in h["Access-Control-Allow-Origin"]

    def test_methods_present(self):
        h = build_cors_headers(["*"])
        assert "POST" in h["Access-Control-Allow-Methods"]


# ===========================================================================
# TUI helpers — normalize_persona_id
# ===========================================================================

class TestNormalizePersonaId:
    def test_lowercases(self):   assert normalize_persona_id("Sigrid") == "sigrid"
    def test_spaces(self):       assert normalize_persona_id("Sigrid Stormborn") == "sigrid_stormborn"
    def test_collapses(self):    assert normalize_persona_id("a  b") == "a_b"
    def test_leading(self):      assert normalize_persona_id("_Sigrid") == "sigrid"
    def test_trailing(self):     assert normalize_persona_id("Sigrid_") == "sigrid"
    def test_truncates(self):    assert len(normalize_persona_id("a" * 100)) == 64
    def test_empty(self):        assert normalize_persona_id("") == ""
    def test_numbers(self):      assert normalize_persona_id("npc_001") == "npc_001"
    def test_dots(self):         assert normalize_persona_id("First.Last") == "first_last"
    def test_already_valid(self): assert normalize_persona_id("sigrid") == "sigrid"


# ===========================================================================
# TUI helpers — parse_world_response
# ===========================================================================

class TestParseWorldResponse:
    def test_empty_dict_returns_offline(self):
        summary, entities = parse_world_response({})
        assert summary.server_status == "offline"

    def test_none_returns_offline(self):
        summary, entities = parse_world_response(None)
        assert summary.server_status == "offline"

    def test_extracts_entity_count(self):
        data = {"world_name": "Thornholt", "entities": [
            {"entity_id": "sigrid", "name": "Sigrid"},
            {"entity_id": "gunnar", "name": "Gunnar"},
        ]}
        summary, entities = parse_world_response(data)
        assert summary.entity_count == 2
        assert len(entities) == 2

    def test_extracts_world_name(self):
        data = {"world_name": "Midgard", "entities": []}
        summary, _ = parse_world_response(data)
        assert summary.world_name == "Midgard"

    def test_status_online(self):
        data = {"entities": []}
        summary, _ = parse_world_response(data)
        assert summary.server_status == "online"

    def test_entity_fields_mapped(self):
        data = {"entities": [
            {"entity_id": "sigrid", "name": "Sigrid",
             "location": "mead_hall", "status": "active"}
        ]}
        _, entities = parse_world_response(data)
        e = entities[0]
        assert e.entity_id == "sigrid" and e.name == "Sigrid"
        assert e.location == "mead_hall"


# ===========================================================================
# TUI helpers — parse_facts_response
# ===========================================================================

class TestParseFactsResponse:
    def test_empty_list(self):
        assert parse_facts_response([]) == []

    def test_maps_fields(self):
        raw = [{"subject_id": "sigrid", "key": "role", "value": "seer", "source": "obs"}]
        entries = parse_facts_response(raw)
        assert len(entries) == 1
        assert entries[0].subject == "sigrid"
        assert entries[0].key == "role"
        assert entries[0].value == "seer"

    def test_missing_fields_default(self):
        raw = [{}]
        entries = parse_facts_response(raw)
        assert entries[0].subject == "?" and entries[0].key == "?"


# ===========================================================================
# TUI helpers — format_uptime
# ===========================================================================

class TestFormatUptime:
    def test_seconds(self):
        assert "s ago" in format_uptime(30)

    def test_minutes(self):
        assert "m ago" in format_uptime(90)

    def test_zero(self):
        assert "0s" in format_uptime(0)


# ===========================================================================
# TUI helpers — handle_tui_command
# ===========================================================================

class TestHandleTuiCommand:
    def _state(self) -> TuiState:
        return TuiState(
            entities=[
                EntityInfo("sigrid", "Sigrid", "mead_hall", "active"),
                EntityInfo("gunnar", "Gunnar", "courtyard", "patrol"),
            ]
        )

    def test_quit_returns_sentinel(self):
        assert handle_tui_command("/quit", self._state(), None) == "__QUIT__"

    def test_exit_returns_sentinel(self):
        assert handle_tui_command("/exit", self._state(), None) == "__QUIT__"

    def test_q_returns_sentinel(self):
        assert handle_tui_command("/q", self._state(), None) == "__QUIT__"

    def test_help_returns_commands(self):
        result = handle_tui_command("/help", self._state(), None)
        assert "refresh" in result.lower()

    def test_clear_empties_log(self):
        state = self._state()
        state.command_log = ["old entry"]
        handle_tui_command("/clear", state, None)
        assert state.command_log == []

    def test_world_returns_summary(self):
        state = self._state()
        state.world.world_name = "Thornholt"
        result = handle_tui_command("/world", state, None)
        assert "Thornholt" in result

    def test_who_all(self):
        state = self._state()
        result = handle_tui_command("/who", state, None)
        assert "sigrid" in result.lower() or "mead" in result.lower()

    def test_who_filtered(self):
        state = self._state()
        result = handle_tui_command("/who mead_hall", state, None)
        assert "sigrid" in result.lower()

    def test_who_no_match(self):
        state = self._state()
        result = handle_tui_command("/who valhalla", state, None)
        assert "nobody" in result.lower()

    def test_where_found(self):
        state = self._state()
        result = handle_tui_command("/where sigrid", state, None)
        assert "mead_hall" in result

    def test_where_not_found(self):
        state = self._state()
        result = handle_tui_command("/where eirik", state, None)
        assert "not found" in result.lower()

    def test_where_no_arg(self):
        result = handle_tui_command("/where", self._state(), None)
        assert "usage" in result.lower()

    def test_unknown_command(self):
        result = handle_tui_command("/xyzzy", self._state(), None)
        assert "unknown" in result.lower()

    def test_refresh_offline(self):
        result = handle_tui_command("/refresh", self._state(), None)
        assert "offline" in result.lower()

    def test_facts_offline(self):
        result = handle_tui_command("/facts sigrid", self._state(), None)
        assert "offline" in result.lower()

    def test_query_offline(self):
        result = handle_tui_command("/query sigrid Hello?", self._state(), None)
        assert "offline" in result.lower()

    def test_push_obs_offline(self):
        result = handle_tui_command("/push obs Title Summary text", self._state(), None)
        assert "offline" in result.lower()

    def test_push_bad_usage(self):
        result = handle_tui_command("/push fact", self._state(), None)
        assert "usage" in result.lower()
