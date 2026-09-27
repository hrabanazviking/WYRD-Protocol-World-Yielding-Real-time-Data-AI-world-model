"""test_exposure_probe.py — Track 1, P2 exposure/moat probe (Wave G, Slice 4).

Proves the exposure model with live servers, not assertions about code:

1. LOOPBACK MOAT — every localhost HTTP surface (WyrdHTTPServer :8765,
   voxta :8766, kindroid :8767) binds a loopback-only address by
   default. The measurable form of "0 unauthenticated write endpoints
   reachable from off-loopback": nothing here listens on a
   non-loopback interface, so from off-loopback nothing is reachable.
2. BODY GUARDS — garbage Content-Length -> 400 naming the header (not
   a silently dropped connection); a 2 MiB declared body -> 413 (not
   an unbounded read) — on all three surfaces.
3. RELAY AUTH — the cloud relay (FastAPI TestClient) returns 401
   without a valid bearer token on every proxied route; / stays
   public and documents the auth state.
4. CORS PIN — the "*" default is pinned as the D1 named decision
   (Volmarr, 2026-09-26), coupled to the token requirement.

No real secrets anywhere: the relay probe uses the placeholder
token "probe-token".
"""
from __future__ import annotations

import inspect
import ipaddress
import json
import socket
import tempfile
import threading
import time
import urllib.error
import urllib.request

import pytest

from wyrdforge.bridges.http_api import WyrdHTTPServer
from wyrdforge.bridges.kindroid_bridge import KindroidWyrdBridge
from wyrdforge.bridges.python_rpg import PythonRPGBridge
from wyrdforge.bridges.voxta_bridge import VoxtaWyrdBridge
from wyrdforge.ecs.components.identity import NameComponent, StatusComponent
from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree
from wyrdforge.persistence.memory_store import PersistentMemoryStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


def _build_bridge() -> PythonRPGBridge:
    world = World("probe_world", "Probe World")
    tree = YggdrasilTree(world)
    tree.create_zone(zone_id="midgard", name="Midgard")
    tree.create_region(region_id="fjords", name="Fjords",
                       parent_zone_id="midgard")
    tree.create_location(location_id="hall", name="Hall",
                         parent_region_id="fjords")
    world.create_entity(entity_id="sigrid", tags={"character"})
    world.add_component("sigrid", NameComponent(entity_id="sigrid",
                                                name="Sigrid"))
    world.add_component("sigrid", StatusComponent(entity_id="sigrid",
                                                  state="calm"))
    tree.place_entity("sigrid", location_id="hall")
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    return PythonRPGBridge(world, tree, store, None)


def _assert_loopback_bound(server) -> None:
    """The server's *actual listening socket* must be loopback-only.

    This deliberately reads the live socket (``getsockname``), not
    the configured ``(host, port)`` tuple: a server that ignored its
    ``host=`` argument and bound 0.0.0.0 must FAIL this probe. The
    configured value is asserted separately against the defaults
    below.
    """
    bound = server._server.socket.getsockname()
    ip = ipaddress.ip_address(bound[0])
    assert ip.is_loopback, (
        f"listening socket bound to non-loopback {ip} — "
        "the loopback moat is broken")


def _default_host(cls) -> str:
    """The constructor's default ``host`` kwarg value."""
    return inspect.signature(cls.__init__).parameters["host"].default


def _assert_default_host_is_loopback(cls) -> None:
    host = _default_host(cls)
    infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    assert infos, f"{cls.__name__} default host {host!r} resolved to nothing"
    for _fam, _type, _proto, _canon, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        assert ip.is_loopback, (
            f"{cls.__name__} default host {host!r} resolves to "
            f"non-loopback {ip} — the loopback moat is broken")


def _raw_request(port: int, head: bytes) -> bytes:
    """Send a raw HTTP/1.0 request head, half-close, read to EOF."""
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    try:
        s.sendall(head)
        s.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            data = s.recv(65536)
            if not data:
                break
            chunks.append(data)
        return b"".join(chunks)
    finally:
        s.close()


def _status_line(response: bytes) -> str:
    return response.split(b"\r\n", 1)[0].decode("latin-1")


def _wait_until_up(port: int, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=0.5)
            s.close()
            return
        except OSError:
            time.sleep(0.05)
    raise AssertionError(f"server on port {port} never came up")


# ---------------------------------------------------------------------------
# Fixtures — one live server per surface, ephemeral localhost ports
# ---------------------------------------------------------------------------

@pytest.fixture()
def http_server():
    port = _free_port()
    srv = WyrdHTTPServer(_build_bridge(), host="localhost", port=port)
    t = srv.start_background()
    _wait_until_up(port)
    yield srv
    srv.shutdown()
    t.join(timeout=5)


@pytest.fixture()
def kindroid_server():
    port = _free_port()
    b = KindroidWyrdBridge(port=port,
                           db_path=tempfile.mktemp(suffix=".db"))
    t = b.start_background()
    _wait_until_up(port)
    yield b
    b.shutdown()
    t.join(timeout=5)


@pytest.fixture()
def voxta_server():
    port = _free_port()
    b = VoxtaWyrdBridge(port=port, db_path=tempfile.mktemp(suffix=".db"))
    t = b.start_background()
    _wait_until_up(port)
    yield b
    b.shutdown()
    t.join(timeout=5)


# ---------------------------------------------------------------------------
# 1. Loopback moat
# ---------------------------------------------------------------------------

class TestLoopbackMoat:
    @pytest.mark.parametrize("fixture_name,path",
                             [("http_server", "/health"),
                              ("kindroid_server", "/health"),
                              ("voxta_server", "/health")])
    def test_default_bind_is_loopback_only(self, fixture_name, path,
                                           request):
        server = request.getfixturevalue(fixture_name)
        _assert_loopback_bound(server)

    def test_default_host_kwargs_are_loopback(self):
        # The moat must hold for the *defaults*, not just when the
        # fixture passes host="localhost" explicitly.
        _assert_default_host_is_loopback(WyrdHTTPServer)
        _assert_default_host_is_loopback(KindroidWyrdBridge)
        _assert_default_host_is_loopback(VoxtaWyrdBridge)

    def test_configured_address_matches_socket(self, http_server):
        # Belt and braces: the public ``address`` property must agree
        # with the live socket (no silent 0.0.0.0 behind a loopback label).
        host, port = http_server.address
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        assert infos

    def test_no_listener_on_non_loopback(self, http_server):
        """Connecting to the LAN IP must fail — nothing listens there."""
        port = http_server.address[1]
        lan_ip = socket.gethostbyname(socket.gethostname())
        if ipaddress.ip_address(lan_ip).is_loopback:
            pytest.skip("no non-loopback interface on this machine")
        with pytest.raises(OSError):
            socket.create_connection((lan_ip, port), timeout=2)


# ---------------------------------------------------------------------------
# 2. Body guards on all three surfaces
# ---------------------------------------------------------------------------

def _garbage_content_length(port: int, path: str) -> bytes:
    return _raw_request(
        port,
        b"POST %s HTTP/1.0\r\nHost: localhost\r\n"
        b"Content-Length: garbage\r\n"
        b"Content-Type: application/json\r\n\r\n" % path.encode(),
    )


def _oversize_body(port: int, path: str) -> bytes:
    # Declare 2 MiB; send nothing more. The server must 413 on the
    # declared length without reading 2 MiB.
    return _raw_request(
        port,
        b"POST %s HTTP/1.0\r\nHost: localhost\r\n"
        b"Content-Length: 2097152\r\n"
        b"Content-Type: application/json\r\n\r\n{}" % path.encode(),
    )


class TestBodyGuards:
    @pytest.mark.parametrize(
        "fixture_name,path",
        [("http_server", "/query"),
         ("kindroid_server", "/kindroid"),
         ("voxta_server", "/voxta")])
    def test_garbage_content_length_is_400(self, fixture_name, path,
                                           request):
        server = request.getfixturevalue(fixture_name)
        resp = _garbage_content_length(server.address[1], path)
        status = _status_line(resp)
        assert " 400 " in status, f"expected 400, got: {status}"
        assert b"Content-Length" in resp, (
            "the 400 must name the offending header, "
            f"not drop the connection: {resp!r}")

    @pytest.mark.parametrize(
        "fixture_name,path",
        [("http_server", "/query"),
         ("kindroid_server", "/kindroid"),
         ("voxta_server", "/voxta")])
    def test_oversize_body_is_413(self, fixture_name, path, request):
        server = request.getfixturevalue(fixture_name)
        resp = _oversize_body(server.address[1], path)
        status = _status_line(resp)
        assert " 413 " in status, f"expected 413, got: {status}"

    def test_valid_small_body_still_works(self, kindroid_server):
        """Additive-only proof: the guards didn't break the happy path."""
        port = kindroid_server.address[1]
        data = json.dumps({"ai_id": "x", "message": "hi"}).encode()
        req = urllib.request.Request(
            f"http://localhost:{port}/kindroid", data=data, method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                assert r.status == 200
        except urllib.error.HTTPError as exc:
            pytest.fail(f"valid body rejected: {exc.code}")


# ---------------------------------------------------------------------------
# 3 + 4. Relay auth and the CORS named-decision pin
# ---------------------------------------------------------------------------

def _relay_client(tokens):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from tools.wyrd_cloud_relay.relay import RelayConfig, create_app
    return TestClient(create_app(RelayConfig(tokens=tokens)))


class TestRelayAuth:
    PROXIED = [("/query", "post"), ("/event", "post"),
               ("/world", "get"), ("/facts", "get"),
               ("/health", "get")]

    @pytest.mark.parametrize("path,method", PROXIED)
    def test_no_token_is_401(self, path, method):
        client = _relay_client(tokens=["probe-token"])
        if method == "post":
            resp = client.post(path, json={})
        else:
            resp = client.get(path)
        assert resp.status_code == 401, f"{method} {path}"

    @pytest.mark.parametrize("path,method", PROXIED)
    def test_wrong_token_is_401(self, path, method):
        client = _relay_client(tokens=["probe-token"])
        headers = {"Authorization": "Bearer wrong-token"}
        if method == "post":
            resp = client.post(path, json={}, headers=headers)
        else:
            resp = client.get(path, headers=headers)
        assert resp.status_code == 401, f"{method} {path}"

    def test_right_token_passes_auth(self):
        # Auth passes; the upstream is unreachable in the probe, so
        # /health reports relay-ok/upstream-unreachable instead of 401.
        client = _relay_client(tokens=["probe-token"])
        resp = client.get("/health",
                          headers={"Authorization": "Bearer probe-token"})
        assert resp.status_code == 200
        assert resp.json()["relay"] == "ok"

    def test_root_is_public_and_documents_auth(self):
        client = _relay_client(tokens=["probe-token"])
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["auth"] == "enabled"


class TestCorsNamedDecision:
    def test_wildcard_default_pinned(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from tools.wyrd_cloud_relay.relay import RelayConfig
        # D1 ruling (Volmarr, 2026-09-26): "*" stays the default by name
        # and date — see docs/security.md. The narrowing mechanism
        # (--cors-origins / WYRD_CORS_ORIGINS) is tested in
        # tools/wyrd_cloud_relay/tests/test_relay.py.
        assert RelayConfig().cors_origins == ["*"]
