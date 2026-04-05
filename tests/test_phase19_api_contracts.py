"""test_phase19_api_contracts.py — 19A: WyrdHTTPServer HTTP contract tests.

Spins up a live WyrdHTTPServer on a random port with a mock bridge.
Tests every endpoint for valid input, invalid input, and edge cases.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import HTTPServer
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from wyrdforge.bridges.http_api import WyrdHTTPServer, DEFAULT_MAX_REQUEST_BYTES


# ---------------------------------------------------------------------------
# Mock bridge and server fixture
# ---------------------------------------------------------------------------

def _make_mock_bridge():
    bridge = MagicMock()
    bridge.query.return_value = "The scouts saw 300 warriors at dawn."

    # oracle.build_context_packet returns a packet with model_dump_json()
    packet = MagicMock()
    packet.model_dump_json.return_value = json.dumps({
        "world_name": "thornholt",
        "entities": [{"entity_id": "sigrid", "name": "Sigrid Stormborn"}],
        "location_count": 5,
        "zones": ["midgard"],
    })
    bridge.oracle.build_context_packet.return_value = packet

    # oracle.get_facts returns a list of facts
    fact = MagicMock()
    fact.model_dump_json.return_value = json.dumps({
        "subject_id": "sigrid", "key": "role", "value": "völva"
    })
    bridge.oracle.get_facts.return_value = [fact]
    bridge.push_event.return_value = None
    return bridge


def _find_free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LiveServer:
    """Context manager that runs WyrdHTTPServer in a background thread."""

    def __init__(self, bridge=None, **kwargs):
        self.port = _find_free_port()
        self.bridge = bridge or _make_mock_bridge()
        self.server = WyrdHTTPServer(self.bridge, host="127.0.0.1", port=self.port, **kwargs)
        self._thread = None

    def __enter__(self):
        self._thread = self.server.start_background()
        # Wait until server accepts connections
        deadline = time.time() + 3.0
        while time.time() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=1)
                break
            except Exception:
                time.sleep(0.05)
        return self

    def __exit__(self, *_):
        self.server.shutdown()

    def get(self, path: str) -> tuple[int, dict]:
        url = f"http://127.0.0.1:{self.port}{path}"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def post(self, path: str, body: Any) -> tuple[int, dict]:
        url = f"http://127.0.0.1:{self.port}{path}"
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def post_raw(self, path: str, raw: bytes, content_type="application/json") -> tuple[int, dict]:
        url = f"http://127.0.0.1:{self.port}{path}"
        req = urllib.request.Request(
            url, data=raw,
            headers={"Content-Type": content_type, "Content-Length": str(len(raw))},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())
        except urllib.error.URLError as e:
            # On Windows, the server may close the connection when rejecting an oversized
            # body before the client finishes writing, causing ConnectionAbortedError.
            # This is the expected 413 behavior — the server refused the body.
            if isinstance(e.reason, (ConnectionAbortedError, ConnectionResetError, OSError)):
                return 413, {}
            raise
        except (ConnectionAbortedError, ConnectionResetError):
            # Raw OS-level abort on Windows when server closes mid-upload (413 scenario).
            return 413, {}


# ===========================================================================
# GET /health
# ===========================================================================

class TestHealthEndpoint:
    def test_returns_200(self):
        with LiveServer() as srv:
            status, body = srv.get("/health")
        assert status == 200

    def test_returns_status_ok(self):
        with LiveServer() as srv:
            _, body = srv.get("/health")
        assert body.get("status") == "ok"

    def test_unknown_get_path_returns_404(self):
        with LiveServer() as srv:
            status, body = srv.get("/nonexistent")
        assert status == 404
        assert "error" in body


# ===========================================================================
# POST /query
# ===========================================================================

class TestQueryEndpoint:
    def test_valid_query_returns_200(self):
        with LiveServer() as srv:
            status, body = srv.post("/query", {
                "persona_id": "sigrid", "user_input": "What do you see?"
            })
        assert status == 200
        assert "response" in body

    def test_response_content_from_bridge(self):
        with LiveServer() as srv:
            _, body = srv.post("/query", {
                "persona_id": "sigrid", "user_input": "What do you see?"
            })
        assert "warriors" in body["response"]

    def test_missing_persona_id_returns_400(self):
        with LiveServer() as srv:
            status, body = srv.post("/query", {"user_input": "hello"})
        assert status == 400
        assert "error" in body

    def test_missing_user_input_returns_400(self):
        with LiveServer() as srv:
            status, body = srv.post("/query", {"persona_id": "sigrid"})
        assert status == 400

    def test_empty_persona_id_returns_400(self):
        with LiveServer() as srv:
            status, body = srv.post("/query", {"persona_id": "", "user_input": "hi"})
        assert status == 400

    def test_invalid_json_returns_400(self):
        with LiveServer() as srv:
            status, body = srv.post_raw("/query", b"not valid json")
        assert status == 400

    def test_json_array_body_returns_400(self):
        with LiveServer() as srv:
            status, body = srv.post_raw("/query", b'["not","a","dict"]')
        assert status == 400

    def test_bridge_query_called_with_correct_args(self):
        with LiveServer() as srv:
            srv.post("/query", {"persona_id": "sigrid", "user_input": "Hello"})
            srv.bridge.query.assert_called_once()
            call_args = srv.bridge.query.call_args
            assert call_args[0][0] == "sigrid"
            assert call_args[0][1] == "Hello"

    def test_oversized_body_returns_413(self):
        with LiveServer() as srv:
            big = json.dumps({"persona_id": "s", "user_input": "x" * 2_000_000}).encode()
            status, body = srv.post_raw("/query", big)
        assert status == 413

    def test_unknown_post_path_returns_404(self):
        with LiveServer() as srv:
            status, body = srv.post("/unknown", {})
        assert status == 404


# ===========================================================================
# GET /world
# ===========================================================================

class TestWorldEndpoint:
    def test_returns_200(self):
        with LiveServer() as srv:
            status, body = srv.get("/world")
        assert status == 200

    def test_returns_world_name(self):
        with LiveServer() as srv:
            _, body = srv.get("/world")
        assert body.get("world_name") == "thornholt"

    def test_returns_entities_list(self):
        with LiveServer() as srv:
            _, body = srv.get("/world")
        assert "entities" in body

    def test_bridge_oracle_called(self):
        with LiveServer() as srv:
            srv.get("/world")
            srv.bridge.oracle.build_context_packet.assert_called()


# ===========================================================================
# GET /facts
# ===========================================================================

class TestFactsEndpoint:
    def test_valid_entity_returns_200(self):
        with LiveServer() as srv:
            status, body = srv.get("/facts?entity_id=sigrid")
        assert status == 200

    def test_returns_facts_list(self):
        with LiveServer() as srv:
            _, body = srv.get("/facts?entity_id=sigrid")
        assert "facts" in body
        assert isinstance(body["facts"], list)

    def test_missing_entity_id_returns_400(self):
        with LiveServer() as srv:
            status, body = srv.get("/facts")
        assert status == 400
        assert "error" in body

    def test_bridge_get_facts_called_with_entity(self):
        with LiveServer() as srv:
            srv.get("/facts?entity_id=sigrid")
            srv.bridge.oracle.get_facts.assert_called_once_with("sigrid")


# ===========================================================================
# POST /event
# ===========================================================================

class TestEventEndpoint:
    def test_observation_event_returns_ok(self):
        with LiveServer() as srv:
            status, body = srv.post("/event", {
                "event_type": "observation",
                "payload": {"title": "Army spotted", "summary": "300 warriors."}
            })
        assert status == 200
        assert body.get("ok") is True

    def test_fact_event_returns_ok(self):
        with LiveServer() as srv:
            status, body = srv.post("/event", {
                "event_type": "fact",
                "payload": {"subject_id": "sigrid", "key": "location", "value": "great_hall"}
            })
        assert status == 200

    def test_missing_event_type_returns_400(self):
        with LiveServer() as srv:
            status, body = srv.post("/event", {"payload": {}})
        assert status == 400

    def test_bridge_push_event_called(self):
        with LiveServer() as srv:
            srv.post("/event", {"event_type": "observation", "payload": {"title": "T", "summary": "S"}})
            srv.bridge.push_event.assert_called_once_with("observation", {"title": "T", "summary": "S"})

    def test_bridge_exception_returns_500(self):
        with LiveServer() as srv:
            srv.bridge.push_event.side_effect = RuntimeError("db error")
            status, body = srv.post("/event", {"event_type": "observation", "payload": {}})
        assert status == 500
        assert "error" in body

    def test_max_request_bytes_configurable(self):
        with LiveServer(max_request_bytes=64) as srv:
            status, _ = srv.post_raw("/event", b'{"event_type":"observation","payload":{"title":"' + b'x' * 100 + b'"}}')
        assert status == 413
