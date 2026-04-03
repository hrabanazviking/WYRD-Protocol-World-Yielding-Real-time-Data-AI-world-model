"""Tests for Voxta, Kindroid, Hermes Agent, and AgentZero bridges — Phases 9D–9G."""
from __future__ import annotations

import json
import socket
import tempfile
import time
import urllib.request
from typing import Any

import pytest

from wyrdforge.bridges.agentzero_bridge import (
    AgentZeroWyrdBridge,
    WyrdReadTool,
    WyrdWriteTool,
    WyrdReadResult,
    WyrdWriteResult,
)
from wyrdforge.bridges.hermes_bridge import HermesWyrdBridge, WyrdTool, WyrdToolResult
from wyrdforge.bridges.kindroid_bridge import KindroidWyrdBridge
from wyrdforge.bridges.voxta_bridge import VoxtaWyrdBridge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


def _post(port: int, path: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    url = f"http://localhost:{port}{path}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _get(port: int, path: str) -> tuple[int, dict[str, Any]]:
    url = f"http://localhost:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


# ===========================================================================
# Voxta Bridge (Phase 9D)
# ===========================================================================

class TestVoxtaBridge:

    def test_construction_succeeds(self) -> None:
        b = VoxtaWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        assert b is not None

    def test_address_property(self) -> None:
        b = VoxtaWyrdBridge(db_path=tempfile.mktemp(suffix=".db"), port=_free_port())
        assert isinstance(b.address, tuple)

    def test_handle_voxta_payload_returns_reply(self) -> None:
        b = VoxtaWyrdBridge(db_path=tempfile.mktemp(suffix=".db"), default_persona_id="sigrid")
        result = b.handle_voxta_payload({"characterId": "sigrid", "userMessage": "Hello"})
        assert "reply" in result
        assert isinstance(result["reply"], str)

    def test_handle_payload_uses_default_persona(self) -> None:
        b = VoxtaWyrdBridge(db_path=tempfile.mktemp(suffix=".db"), default_persona_id="sigrid")
        result = b.handle_voxta_payload({"userMessage": "Hello"})
        assert "reply" in result

    def test_handle_payload_registers_entity(self) -> None:
        b = VoxtaWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        b.handle_voxta_payload({"characterId": "gunnar", "userMessage": "Hello"})
        assert b.bridge.world.get_entity("gunnar") is not None

    def test_health_endpoint(self) -> None:
        b = VoxtaWyrdBridge(
            db_path=tempfile.mktemp(suffix=".db"),
            port=_free_port(), host="localhost",
        )
        b.start_background()
        time.sleep(0.05)
        status, body = _get(b.address[1], "/health")
        b.shutdown()
        assert status == 200
        assert body["status"] == "ok"

    def test_voxta_endpoint_returns_reply(self) -> None:
        b = VoxtaWyrdBridge(
            db_path=tempfile.mktemp(suffix=".db"),
            port=_free_port(), default_persona_id="sigrid",
        )
        b.start_background()
        time.sleep(0.05)
        status, body = _post(b.address[1], "/voxta", {"characterId": "sigrid", "userMessage": "Hi"})
        b.shutdown()
        assert status == 200
        assert "reply" in body

    def test_voxta_endpoint_invalid_json_returns_400(self) -> None:
        b = VoxtaWyrdBridge(db_path=tempfile.mktemp(suffix=".db"), port=_free_port())
        b.start_background()
        time.sleep(0.05)
        url = f"http://localhost:{b.address[1]}/voxta"
        req = urllib.request.Request(
            url, data=b"not-json", method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=3)
        except urllib.error.HTTPError as exc:
            b.shutdown()
            assert exc.code == 400
            return
        b.shutdown()
        pytest.fail("Expected 400")

    def test_shutdown_idempotent(self) -> None:
        b = VoxtaWyrdBridge(db_path=tempfile.mktemp(suffix=".db"), port=_free_port())
        b.start_background()
        time.sleep(0.05)
        b.shutdown()
        b.shutdown()

    def test_bridge_property(self) -> None:
        from wyrdforge.bridges.python_rpg import PythonRPGBridge
        b = VoxtaWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        assert isinstance(b.bridge, PythonRPGBridge)


# ===========================================================================
# Kindroid Bridge (Phase 9E)
# ===========================================================================

class TestKindroidBridge:

    def test_construction_succeeds(self) -> None:
        b = KindroidWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        assert b is not None

    def test_handle_kindroid_payload_returns_context(self) -> None:
        b = KindroidWyrdBridge(db_path=tempfile.mktemp(suffix=".db"), default_persona_id="sigrid")
        result = b.handle_kindroid_payload({"ai_id": "sigrid", "message": "Hello"})
        assert "context" in result
        assert result["ok"] is True

    def test_handle_payload_uses_default_persona(self) -> None:
        b = KindroidWyrdBridge(db_path=tempfile.mktemp(suffix=".db"), default_persona_id="sigrid")
        result = b.handle_kindroid_payload({"message": "Hello"})
        assert "context" in result

    def test_handle_payload_registers_entity(self) -> None:
        b = KindroidWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        b.handle_kindroid_payload({"ai_id": "astrid", "message": "Hi"})
        assert b.bridge.world.get_entity("astrid") is not None

    def test_health_endpoint(self) -> None:
        b = KindroidWyrdBridge(
            db_path=tempfile.mktemp(suffix=".db"), port=_free_port()
        )
        b.start_background()
        time.sleep(0.05)
        status, body = _get(b.address[1], "/health")
        b.shutdown()
        assert status == 200

    def test_kindroid_endpoint_returns_200(self) -> None:
        b = KindroidWyrdBridge(
            db_path=tempfile.mktemp(suffix=".db"),
            port=_free_port(), default_persona_id="sigrid",
        )
        b.start_background()
        time.sleep(0.05)
        status, body = _post(b.address[1], "/kindroid", {"ai_id": "sigrid", "message": "Hi"})
        b.shutdown()
        assert status == 200
        assert body["ok"] is True

    def test_shutdown_idempotent(self) -> None:
        b = KindroidWyrdBridge(db_path=tempfile.mktemp(suffix=".db"), port=_free_port())
        b.start_background()
        time.sleep(0.05)
        b.shutdown()
        b.shutdown()


# ===========================================================================
# Hermes Agent Bridge (Phase 9F)
# ===========================================================================

class TestHermesBridge:

    def test_construction_succeeds(self) -> None:
        b = HermesWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        assert b is not None

    def test_get_tool_returns_wyrd_tool(self) -> None:
        b = HermesWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        tool = b.get_tool()
        assert isinstance(tool, WyrdTool)

    def test_tool_has_name(self) -> None:
        b = HermesWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        tool = b.get_tool()
        assert tool.name == "wyrd_world"

    def test_tool_name_override(self) -> None:
        b = HermesWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        tool = b.get_tool(name="custom_wyrd")
        assert tool.name == "custom_wyrd"

    def test_tool_run_returns_wyrd_tool_result(self) -> None:
        b = HermesWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        tool = b.get_tool()
        result = tool.run("sigrid", "What is happening?")
        assert isinstance(result, WyrdToolResult)

    def test_tool_run_result_has_context(self) -> None:
        b = HermesWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        tool = b.get_tool()
        result = tool.run("sigrid")
        assert isinstance(result.context, str)
        assert len(result.context) > 0

    def test_tool_run_result_has_persona_id(self) -> None:
        b = HermesWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        tool = b.get_tool()
        result = tool.run("gunnar", "Hello")
        assert result.persona_id == "gunnar"

    def test_tool_to_dict_has_name(self) -> None:
        b = HermesWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        tool = b.get_tool()
        d = tool.to_dict()
        assert d["name"] == "wyrd_world"
        assert "description" in d
        assert "parameters" in d

    def test_tool_to_dict_has_persona_id_param(self) -> None:
        b = HermesWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        d = b.get_tool().to_dict()
        assert "persona_id" in d["parameters"]["properties"]

    def test_bridge_property(self) -> None:
        from wyrdforge.bridges.python_rpg import PythonRPGBridge
        b = HermesWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        assert isinstance(b.bridge, PythonRPGBridge)


# ===========================================================================
# AgentZero Bridge (Phase 9G)
# ===========================================================================

class TestAgentZeroBridge:

    def test_construction_succeeds(self) -> None:
        b = AgentZeroWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        assert b is not None

    def test_get_tools_returns_both(self) -> None:
        b = AgentZeroWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        tools = b.get_tools()
        assert len(tools) == 2
        names = {t.name for t in tools}
        assert "wyrd_read" in names
        assert "wyrd_write" in names

    def test_get_read_tool_returns_wyrd_read_tool(self) -> None:
        b = AgentZeroWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        assert isinstance(b.get_read_tool(), WyrdReadTool)

    def test_get_write_tool_returns_wyrd_write_tool(self) -> None:
        b = AgentZeroWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        assert isinstance(b.get_write_tool(), WyrdWriteTool)

    def test_read_tool_run_returns_result(self) -> None:
        b = AgentZeroWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        result = b.get_read_tool().run("sigrid")
        assert isinstance(result, WyrdReadResult)

    def test_read_tool_result_has_context(self) -> None:
        b = AgentZeroWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        result = b.get_read_tool().run("sigrid", "What is happening?")
        assert isinstance(result.context, str)
        assert len(result.context) > 0

    def test_read_tool_result_has_persona_id(self) -> None:
        b = AgentZeroWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        result = b.get_read_tool().run("gunnar")
        assert result.persona_id == "gunnar"

    def test_write_tool_run_observation_returns_written(self) -> None:
        b = AgentZeroWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        result = b.get_write_tool().run(
            "observation",
            {"title": "Storm", "summary": "A storm began."},
        )
        assert isinstance(result, WyrdWriteResult)
        assert result.written is True

    def test_write_tool_run_fact_succeeds(self) -> None:
        b = AgentZeroWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        result = b.get_write_tool().run(
            "fact",
            {"subject_id": "sigrid", "key": "role", "value": "seer"},
        )
        assert result.written is True
        assert result.record_type == "fact"

    def test_read_tool_to_dict(self) -> None:
        b = AgentZeroWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        d = b.get_read_tool().to_dict()
        assert d["name"] == "wyrd_read"
        assert "persona_id" in d["parameters"]["properties"]

    def test_write_tool_to_dict(self) -> None:
        b = AgentZeroWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        d = b.get_write_tool().to_dict()
        assert d["name"] == "wyrd_write"
        assert "event_type" in d["parameters"]["properties"]
        assert "payload" in d["parameters"]["properties"]

    def test_tool_name_override(self) -> None:
        b = AgentZeroWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        tool = b.get_read_tool(name="custom_read")
        assert tool.name == "custom_read"

    def test_bridge_property(self) -> None:
        from wyrdforge.bridges.python_rpg import PythonRPGBridge
        b = AgentZeroWyrdBridge(db_path=tempfile.mktemp(suffix=".db"))
        assert isinstance(b.bridge, PythonRPGBridge)
