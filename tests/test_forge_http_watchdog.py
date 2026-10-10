"""Forge tests: WyrdHTTPServer watchdog crash detection via serve-thread aliveness.

Proves the watchdog restarts a crashed server using only the public
``Thread.is_alive`` API — no private CPython internals. The crash is real:
the listening socket is closed from underneath ``serve_forever``, the serve
thread dies, and the watchdog must detect the dead thread and bring the
server back on /health.
"""
from __future__ import annotations

import json
import socket
import tempfile
import time
import urllib.error
import urllib.request
from typing import Any

from wyrdforge.bridges import http_api as _http_api_module
from wyrdforge.bridges.http_api import WyrdHTTPServer
from wyrdforge.bridges.python_rpg import PythonRPGBridge
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
    world = World("watchdog_world", "Watchdog World")
    tree = YggdrasilTree(world)
    tree.create_zone(zone_id="midgard", name="Midgard")
    tree.create_region(region_id="fjords", name="Fjords", parent_zone_id="midgard")
    tree.create_location(location_id="hall", name="Hall", parent_region_id="fjords")
    world.create_entity(entity_id="sigrid", tags={"character"})
    world.add_component("sigrid", NameComponent(entity_id="sigrid", name="Sigrid"))
    world.add_component("sigrid", StatusComponent(entity_id="sigrid", state="calm"))
    tree.place_entity("sigrid", location_id="hall")
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    return PythonRPGBridge(world, tree, store, None)


def _health(port: int) -> tuple[int, dict[str, Any]] | None:
    try:
        with urllib.request.urlopen(
            f"http://localhost:{port}/health", timeout=2
        ) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except (OSError, urllib.error.URLError):
        return None


def _wait_for_health(port: int, timeout: float = 10.0) -> tuple[int, dict[str, Any]]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = _health(port)
        if result is not None:
            return result
        time.sleep(0.05)
    raise AssertionError(f"/health never came back on port {port}")


# ---------------------------------------------------------------------------
# Crash → watchdog restart
# ---------------------------------------------------------------------------

def test_watchdog_restarts_crashed_server() -> None:
    """Kill the serve thread (close its socket) — the watchdog must restart."""
    port = _free_port()
    srv = WyrdHTTPServer(
        _build_bridge(), host="localhost", port=port,
        watchdog=True, watchdog_interval=0.1,
    )
    try:
        srv.start_background()
        status, body = _wait_for_health(port)
        assert status == 200 and body["status"] == "ok"

        old_server = srv._server
        old_thread = srv._serve_thread
        assert old_thread is not None and old_thread.is_alive()

        # The crash: stop the serve loop out from under the server *without*
        # going through the graceful shutdown path (which would set
        # _stopped and park the watchdog). socketserver.shutdown() makes
        # serve_forever return so the serve thread dies; server_close()
        # releases the port so the watchdog's restart can rebind it.
        srv._server.shutdown()
        srv._server.server_close()
        old_thread.join(timeout=10.0)
        assert not old_thread.is_alive(), "serve thread survived the crash"

        # The watchdog must detect the dead thread and restart the server.
        status, body = _wait_for_health(port, timeout=10.0)
        assert status == 200
        assert body["status"] == "ok"
        assert srv._serve_thread is not old_thread, "watchdog did not launch a new serve thread"
        assert srv._server is not old_server, "watchdog did not rebuild the server socket"
    finally:
        srv.shutdown()


def test_healthy_server_is_not_restarted() -> None:
    """A live serve thread must not trigger restarts (no false positives)."""
    port = _free_port()
    srv = WyrdHTTPServer(
        _build_bridge(), host="localhost", port=port,
        watchdog=True, watchdog_interval=0.1,
    )
    try:
        srv.start_background()
        _wait_for_health(port)
        server_before = srv._server
        thread_before = srv._serve_thread
        time.sleep(0.35)  # several watchdog intervals
        assert srv._server is server_before, "watchdog restarted a healthy server"
        assert srv._serve_thread is thread_before
        assert srv._watchdog_failures == 0
        status, _ = _wait_for_health(port)
        assert status == 200
    finally:
        srv.shutdown()


def test_no_private_cpython_internals_in_watchdog() -> None:
    """The watchdog must not read name-mangled private server attributes."""
    import inspect

    source = inspect.getsource(_http_api_module)
    assert "_BaseServer__" not in source, (
        "http_api.py still references the private _BaseServer__ attribute"
    )


def test_start_background_tracks_serve_thread() -> None:
    """start_background records the thread the watchdog is meant to watch."""
    port = _free_port()
    srv = WyrdHTTPServer(_build_bridge(), host="localhost", port=port, watchdog=True)
    try:
        thread = srv.start_background()
        assert srv._serve_thread is thread
        assert thread.is_alive()
    finally:
        srv.shutdown()
