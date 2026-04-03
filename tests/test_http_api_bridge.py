"""Tests for WyrdHTTPServer — Phase 6 Bifrost HTTP adapter."""
from __future__ import annotations

import json
import socket
import tempfile
import time
import urllib.request
from typing import Any

import pytest

from wyrdforge.bridges.http_api import WyrdHTTPServer
from wyrdforge.bridges.python_rpg import BridgeConfig, PythonRPGBridge
from wyrdforge.ecs.components.identity import NameComponent, StatusComponent
from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree
from wyrdforge.llm.ollama_connector import OllamaConnector
from wyrdforge.persistence.memory_store import PersistentMemoryStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


def _build_bridge() -> PythonRPGBridge:
    world = World("http_world", "HTTP World")
    tree = YggdrasilTree(world)
    tree.create_zone(zone_id="midgard", name="Midgard")
    tree.create_region(region_id="fjords", name="Fjords", parent_zone_id="midgard")
    tree.create_location(location_id="hall", name="Hall", parent_region_id="fjords")
    world.create_entity(entity_id="sigrid", tags={"character"})
    world.add_component("sigrid", NameComponent(entity_id="sigrid", name="Sigrid"))
    world.add_component("sigrid", StatusComponent(entity_id="sigrid", state="calm"))
    tree.place_entity("sigrid", location_id="hall")
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    bridge = PythonRPGBridge(world, tree, store, None)
    bridge.writeback.write_canonical_fact(
        fact_subject_id="sigrid",
        fact_key="role",
        fact_value="völva",
        domain="identity",
        confidence=0.95,
    )
    return bridge


def _request(
    port: int,
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    url = f"http://localhost:{port}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Fixture: server running in background thread
# ---------------------------------------------------------------------------

@pytest.fixture()
def server():
    bridge = _build_bridge()
    port = _free_port()
    srv = WyrdHTTPServer(bridge, host="localhost", port=port)
    srv.start_background()
    # Give the server a moment to bind
    time.sleep(0.05)
    yield srv, port
    srv.shutdown()


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

def test_health_returns_200(server) -> None:
    srv, port = server
    status, body = _request(port, "/health")
    assert status == 200


def test_health_body_ok(server) -> None:
    srv, port = server
    status, body = _request(port, "/health")
    assert body["status"] == "ok"


# ---------------------------------------------------------------------------
# /world
# ---------------------------------------------------------------------------

def test_world_returns_200(server) -> None:
    srv, port = server
    status, body = _request(port, "/world")
    assert status == 200


def test_world_has_world_id(server) -> None:
    srv, port = server
    _, body = _request(port, "/world")
    assert "world_id" in body


def test_world_has_formatted_for_llm(server) -> None:
    srv, port = server
    _, body = _request(port, "/world")
    assert "formatted_for_llm" in body


# ---------------------------------------------------------------------------
# /facts
# ---------------------------------------------------------------------------

def test_facts_requires_entity_id(server) -> None:
    srv, port = server
    status, body = _request(port, "/facts")
    assert status == 400
    assert "error" in body


def test_facts_returns_list_for_known_entity(server) -> None:
    srv, port = server
    status, body = _request(port, "/facts?entity_id=sigrid")
    assert status == 200
    assert "facts" in body
    assert isinstance(body["facts"], list)


def test_facts_returns_seeded_fact(server) -> None:
    srv, port = server
    _, body = _request(port, "/facts?entity_id=sigrid")
    texts = [f["content"]["structured_payload"]["fact_value"] for f in body["facts"]]
    assert "völva" in texts


def test_facts_empty_for_unknown_entity(server) -> None:
    srv, port = server
    _, body = _request(port, "/facts?entity_id=nobody")
    assert body["facts"] == []


# ---------------------------------------------------------------------------
# /query
# ---------------------------------------------------------------------------

def test_query_requires_persona_id(server) -> None:
    srv, port = server
    status, body = _request(port, "/query", method="POST", body={"user_input": "hi"})
    assert status == 400


def test_query_requires_user_input(server) -> None:
    srv, port = server
    status, body = _request(port, "/query", method="POST", body={"persona_id": "sigrid"})
    assert status == 400


def test_query_no_llm_returns_200(server) -> None:
    srv, port = server
    status, body = _request(
        port, "/query", method="POST",
        body={"persona_id": "sigrid", "user_input": "Hello", "use_turn_loop": False},
    )
    assert status == 200


def test_query_no_llm_response_is_string(server) -> None:
    srv, port = server
    _, body = _request(
        port, "/query", method="POST",
        body={"persona_id": "sigrid", "user_input": "Hello", "use_turn_loop": False},
    )
    assert isinstance(body["response"], str)
    assert len(body["response"]) > 0


def test_query_no_llm_response_contains_world_state(server) -> None:
    srv, port = server
    _, body = _request(
        port, "/query", method="POST",
        body={"persona_id": "sigrid", "user_input": "World check", "use_turn_loop": False},
    )
    assert "WORLD STATE" in body["response"]


# ---------------------------------------------------------------------------
# /event
# ---------------------------------------------------------------------------

def test_event_requires_event_type(server) -> None:
    srv, port = server
    status, body = _request(port, "/event", method="POST", body={"payload": {}})
    assert status == 400


def test_event_observation_returns_ok(server) -> None:
    srv, port = server
    status, body = _request(
        port, "/event", method="POST",
        body={
            "event_type": "observation",
            "payload": {"title": "Raven arrives", "summary": "A raven landed on the roof."},
        },
    )
    assert status == 200
    assert body["ok"] is True


def test_event_fact_returns_ok(server) -> None:
    srv, port = server
    status, body = _request(
        port, "/event", method="POST",
        body={
            "event_type": "fact",
            "payload": {"subject_id": "gunnar", "key": "weapon", "value": "axe"},
        },
    )
    assert status == 200
    assert body["ok"] is True


# ---------------------------------------------------------------------------
# 404 / unknown routes
# ---------------------------------------------------------------------------

def test_unknown_get_returns_404(server) -> None:
    srv, port = server
    status, body = _request(port, "/nonexistent")
    assert status == 404


def test_unknown_post_returns_404(server) -> None:
    srv, port = server
    status, body = _request(port, "/nonexistent", method="POST", body={})
    assert status == 404


# ---------------------------------------------------------------------------
# address property
# ---------------------------------------------------------------------------

def test_address_property(server) -> None:
    srv, port = server
    assert srv.address == ("localhost", port)


# ---------------------------------------------------------------------------
# shutdown idempotent
# ---------------------------------------------------------------------------

def test_shutdown_idempotent() -> None:
    bridge = _build_bridge()
    port = _free_port()
    srv = WyrdHTTPServer(bridge, host="localhost", port=port)
    srv.start_background()
    time.sleep(0.05)
    srv.shutdown()
    srv.shutdown()  # second call must not raise
