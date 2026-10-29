"""Tests for WyrdHTTPServer Phase C2 — HTTP API auth + versioning.

Pins:
- /v1/ routes work for all five endpoints, response shapes identical
  to the unversioned surface;
- unversioned routes remain as working aliases (compat for in-repo
  bridges / integrations / harnesses that hard-code them);
- when a token is configured (constructor arg or WYRD_API_TOKEN),
  every endpoint refuses missing/wrong tokens with 401 and no data,
  and passes the correct token (constant-time compare path);
- when no token is configured, behaviour is exactly pre-C2 (the
  existing http test files pin that unmodified; here: a fresh server
  reports auth disabled and serves without a header);
- rate limiting (relay pattern, rolling 60 s window) trips with the
  429 {"error": ...} shape, is per-client-key, and recovers as the
  window rolls.
"""
from __future__ import annotations

import json
import socket
import tempfile
import time
import urllib.error
import urllib.request
from typing import Any

import pytest

from wyrdforge.bridges.http_api import (
    API_TOKEN_ENV_VAR,
    RateLimiter,
    WyrdHTTPServer,
)
from wyrdforge.bridges.python_rpg import PythonRPGBridge
from wyrdforge.ecs.components.identity import NameComponent, StatusComponent
from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree
from wyrdforge.persistence.memory_store import PersistentMemoryStore

TOKEN = "c2-test-token-not-a-real-secret"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


def _build_bridge() -> PythonRPGBridge:
    world = World("http_c2_world", "HTTP C2 World")
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
    token: str | None = None,
    raw_auth: str | None = None,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    url = f"http://localhost:{port}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers: dict[str, str] = {}
    if data:
        headers["Content-Type"] = "application/json"
    if raw_auth is not None:
        headers["Authorization"] = raw_auth
    elif token is not None:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8")), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8")), dict(exc.headers)


@pytest.fixture()
def make_server():
    servers: list[WyrdHTTPServer] = []

    def _make(**kwargs) -> tuple[WyrdHTTPServer, int]:
        port = _free_port()
        srv = WyrdHTTPServer(_build_bridge(), host="localhost", port=port, **kwargs)
        srv.start_background()
        time.sleep(0.05)
        servers.append(srv)
        return srv, port

    yield _make
    for srv in servers:
        srv.shutdown()


# ---------------------------------------------------------------------------
# Versioning: /v1/ works for all five endpoints; aliases identical
# ---------------------------------------------------------------------------

ALL_ROUTES = [
    ("GET", "/health", None),
    ("GET", "/world", None),
    ("GET", "/facts?entity_id=sigrid", None),
    ("POST", "/query", {"persona_id": "sigrid", "user_input": "Hello",
                        "use_turn_loop": False}),
    ("POST", "/event", {"event_type": "observation",
                        "payload": {"title": "Raven", "summary": "A raven landed."}}),
]


@pytest.mark.parametrize("method,path,body", ALL_ROUTES)
def test_v1_routes_work(make_server, method, path, body) -> None:
    _, port = make_server()
    status, resp, headers = _request(port, "/v1" + path, method=method, body=body)
    assert status == 200
    assert headers.get("X-Wyrd-API-Version") == "1"


@pytest.mark.parametrize("method,path,body", ALL_ROUTES)
def test_unversioned_alias_still_works(make_server, method, path, body) -> None:
    _, port = make_server()
    status, _, _ = _request(port, path, method=method, body=body)
    assert status == 200


def test_v1_and_alias_response_shapes_identical(make_server) -> None:
    _, port = make_server()
    for method, path, body in ALL_ROUTES:
        if method == "POST" and path == "/event":
            continue  # state-changing; shape pinned separately below
        s1, b1, _ = _request(port, "/v1" + path, method=method, body=body)
        s2, b2, _ = _request(port, path, method=method, body=body)
        assert s1 == s2 == 200
        if path == "/world":
            b1.pop("query_timestamp", None)
            b2.pop("query_timestamp", None)
        assert b1 == b2
    s1, b1, _ = _request(port, "/v1/event", method="POST",
                         body={"event_type": "observation",
                               "payload": {"title": "T", "summary": "S"}})
    assert (s1, b1) == (200, {"ok": True})


def test_unknown_version_prefix_is_404(make_server) -> None:
    _, port = make_server()
    status, body, _ = _request(port, "/v2/health")
    assert status == 404
    assert "error" in body
    status, _, _ = _request(port, "/v1/nonexistent")
    assert status == 404


# ---------------------------------------------------------------------------
# Auth: configured token required everywhere; correct token passes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method,path,body", ALL_ROUTES)
def test_no_token_refused_401_no_data(make_server, method, path, body) -> None:
    _, port = make_server(auth_token=TOKEN)
    status, resp, headers = _request(port, "/v1" + path, method=method, body=body)
    assert status == 401
    assert resp == {"error": "Invalid or missing bearer token"}
    lowered = {k.lower(): v for k, v in headers.items()}
    assert lowered.get("www-authenticate") == "Bearer"


@pytest.mark.parametrize("method,path,body", ALL_ROUTES)
def test_wrong_token_refused_401(make_server, method, path, body) -> None:
    _, port = make_server(auth_token=TOKEN)
    status, resp, _ = _request(
        port, path, method=method, body=body, token="wrong-token")
    assert status == 401
    assert "error" in resp


def test_malformed_auth_headers_refused(make_server) -> None:
    _, port = make_server(auth_token=TOKEN)
    for raw in ("Bearer", f"Basic {TOKEN}", TOKEN, "Bearer "):
        status, _, _ = _request(port, "/v1/health", raw_auth=raw)
        assert status == 401, raw


@pytest.mark.parametrize("method,path,body", ALL_ROUTES)
def test_correct_token_passes(make_server, method, path, body) -> None:
    _, port = make_server(auth_token=TOKEN)
    status, _, _ = _request(port, "/v1" + path, method=method, body=body, token=TOKEN)
    assert status == 200
    # The alias surface enforces the same auth.
    status, _, _ = _request(port, path, method=method, body=body, token=TOKEN)
    assert status == 200


def test_auth_from_env_var(make_server, monkeypatch) -> None:
    monkeypatch.setenv(API_TOKEN_ENV_VAR, TOKEN)
    srv, port = make_server()
    assert srv.auth_enabled is True
    status, _, _ = _request(port, "/v1/health")
    assert status == 401
    status, _, _ = _request(port, "/v1/health", token=TOKEN)
    assert status == 200


def test_explicit_empty_token_disables_auth(make_server, monkeypatch) -> None:
    monkeypatch.setenv(API_TOKEN_ENV_VAR, TOKEN)
    srv, port = make_server(auth_token="")
    assert srv.auth_enabled is False
    status, _, _ = _request(port, "/v1/health")
    assert status == 200


def test_no_token_configured_is_pre_c2_behaviour(make_server, monkeypatch) -> None:
    monkeypatch.delenv(API_TOKEN_ENV_VAR, raising=False)
    srv, port = make_server()
    assert srv.auth_enabled is False
    status, body, _ = _request(port, "/health")
    assert (status, body) == (200, {"status": "ok"})


def test_no_auth_warning_logged(make_server, monkeypatch, caplog) -> None:
    monkeypatch.delenv(API_TOKEN_ENV_VAR, raising=False)
    with caplog.at_level("WARNING", logger="wyrdforge.bridges.http_api"):
        make_server()
    assert any("WITHOUT authentication" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Rate limiting: trips with 429 shape, per-key, recovers with window
# ---------------------------------------------------------------------------

def test_rate_limit_trips_and_returns_429_shape(make_server) -> None:
    _, port = make_server(rate_limit_per_minute=3)
    for _ in range(3):
        status, _, _ = _request(port, "/v1/health")
        assert status == 200
    status, body, _ = _request(port, "/v1/health")
    assert status == 429
    assert body == {"error": "Rate limit exceeded (3/min)"}
    # Still tripped on other endpoints too (uniform application).
    status, _, _ = _request(port, "/v1/world")
    assert status == 429


def test_rate_limit_applies_with_auth_and_401_does_not_consume(make_server) -> None:
    _, port = make_server(auth_token=TOKEN, rate_limit_per_minute=2)
    # Unauthenticated attempts are refused before the limiter.
    for _ in range(5):
        status, _, _ = _request(port, "/v1/health")
        assert status == 401
    for _ in range(2):
        status, _, _ = _request(port, "/v1/health", token=TOKEN)
        assert status == 200
    status, _, _ = _request(port, "/v1/health", token=TOKEN)
    assert status == 429


def test_rate_limiter_window_recovers_unit() -> None:
    limiter = RateLimiter(2)
    assert limiter.is_allowed("k", now=1000.0)
    assert limiter.is_allowed("k", now=1001.0)
    assert not limiter.is_allowed("k", now=1002.0)
    # A different key has its own bucket.
    assert limiter.is_allowed("other", now=1002.0)
    # After the rolling 60 s window passes, the key recovers.
    assert limiter.is_allowed("k", now=1061.5)
    # 0 = unlimited (relay rule).
    unlimited = RateLimiter(0)
    for i in range(50):
        assert unlimited.is_allowed("k", now=2000.0 + i * 0.01)


def test_rate_limit_zero_disables(make_server) -> None:
    _, port = make_server(rate_limit_per_minute=0)
    for _ in range(20):
        status, _, _ = _request(port, "/v1/health")
        assert status == 200
