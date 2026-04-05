"""WyrdHTTPServer — minimal stdlib HTTP adapter for WYRD.

Exposes the WYRD stack over a plain JSON HTTP API.  No framework
dependencies; uses only ``http.server`` and ``json`` from the stdlib.

Endpoints:
    POST /query      — query a character (returns response text)
    GET  /world      — get the current WorldContextPacket as JSON
    GET  /facts      — get canonical facts for an entity
    POST /event      — push a world event (observation or fact)
    GET  /health     — liveness check

Request/response bodies are UTF-8 JSON.  All errors return
``{"error": "<message>"}`` with an appropriate HTTP status code.

Typical usage::

    from wyrdforge.bridges.http_api import WyrdHTTPServer
    from wyrdforge.bridges.python_rpg import PythonRPGBridge, BridgeConfig

    bridge = PythonRPGBridge.from_config(BridgeConfig(world_id="my_world"))
    server = WyrdHTTPServer(bridge, host="localhost", port=8765)
    server.serve_forever()   # blocks; Ctrl-C to stop
"""
from __future__ import annotations

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Optional

from wyrdforge.bridges.python_rpg import PythonRPGBridge

logger = logging.getLogger(__name__)

# Default maximum request body size (1 MiB). Requests larger than this receive
# 413 Content Too Large without reading the full body — prevents memory exhaustion.
DEFAULT_MAX_REQUEST_BYTES: int = 1 * 1024 * 1024  # 1 MiB


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

class _WyrdHandler(BaseHTTPRequestHandler):
    """Internal request handler.  Do not instantiate directly."""

    bridge: PythonRPGBridge  # injected by WyrdHTTPServer via class patching
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES  # injected at class creation

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path == "/health":
            self._send_json({"status": "ok"})
        elif path == "/world":
            self._handle_world()
        elif path == "/facts":
            self._handle_facts()
        else:
            self._send_error(404, "Not found")

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        if path == "/query":
            self._handle_query()
        elif path == "/event":
            self._handle_event()
        else:
            self._send_error(404, "Not found")

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_query(self) -> None:
        body = self._read_json()
        if body is None:
            return
        persona_id = body.get("persona_id", "")
        user_input = body.get("user_input", "")
        if not persona_id or not user_input:
            self._send_error(400, "persona_id and user_input are required")
            return
        try:
            response = self.bridge.query(
                persona_id,
                user_input,
                location_id=body.get("location_id"),
                bond_id=body.get("bond_id"),
                use_turn_loop=bool(body.get("use_turn_loop", True)),
            )
            self._send_json({"response": response})
        except Exception as exc:
            self._send_error(500, str(exc))

    def _handle_world(self) -> None:
        try:
            packet = self.bridge.oracle.build_context_packet(focus_entity_ids=[])
            self._send_json(json.loads(packet.model_dump_json()))
        except Exception as exc:
            self._send_error(500, str(exc))

    def _handle_facts(self) -> None:
        # Extract entity_id from query string: /facts?entity_id=sigrid
        qs = self.path.partition("?")[2]
        params: dict[str, str] = {}
        for part in qs.split("&"):
            if "=" in part:
                k, _, v = part.partition("=")
                params[k] = v
        entity_id = params.get("entity_id", "")
        if not entity_id:
            self._send_error(400, "entity_id query param required")
            return
        try:
            facts = self.bridge.oracle.get_facts(entity_id)
            out = [json.loads(f.model_dump_json()) for f in facts]
            self._send_json({"facts": out})
        except Exception as exc:
            self._send_error(500, str(exc))

    def _handle_event(self) -> None:
        body = self._read_json()
        if body is None:
            return
        event_type = body.get("event_type", "")
        payload = body.get("payload", {})
        if not event_type:
            self._send_error(400, "event_type is required")
            return
        try:
            self.bridge.push_event(event_type, payload)
            self._send_json({"ok": True})
        except Exception as exc:
            self._send_error(500, str(exc))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _read_json(self) -> dict[str, Any] | None:
        length_str = self.headers.get("Content-Length", "0")
        try:
            length = int(length_str)
        except ValueError:
            self._send_error(400, "Invalid Content-Length header")
            return None
        if length > self.max_request_bytes:
            self._send_error(413, f"Request body too large (max {self.max_request_bytes} bytes)")
            return None
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._send_error(400, f"Invalid JSON: {exc}")
            return None
        if not isinstance(data, dict):
            self._send_error(400, "Request body must be a JSON object")
            return None
        return data

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, message: str) -> None:
        self._send_json({"error": message}, status=status)

    def log_message(self, fmt: str, *args: Any) -> None:  # silence default logging
        pass


# ---------------------------------------------------------------------------
# Public server class
# ---------------------------------------------------------------------------

class WyrdHTTPServer:
    """Minimal HTTP server wrapping a PythonRPGBridge.

    Args:
        bridge:            The PythonRPGBridge instance to serve.
        host:              Bind address (default ``"localhost"``).
        port:              Bind port (default ``8765``).
        max_request_bytes: Maximum accepted request body size in bytes.
                           Requests larger than this receive ``413``.
                           Default: 1 MiB.
        watchdog:          If True, a watchdog thread monitors the server and
                           restarts it after an unhandled crash (default False).
        watchdog_interval: Seconds between watchdog health checks (default 5).
    """

    def __init__(
        self,
        bridge: PythonRPGBridge,
        *,
        host: str = "localhost",
        port: int = 8765,
        max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
        watchdog: bool = False,
        watchdog_interval: float = 5.0,
    ) -> None:
        self._bridge = bridge
        self._host = host
        self._port = port
        self._max_request_bytes = max_request_bytes
        self._watchdog = watchdog
        self._watchdog_interval = watchdog_interval
        self._server: Optional[HTTPServer] = None
        self._stopped = threading.Event()

        # Inject bridge + config into handler class via subclass so that
        # multiple server instances each get their own handler class.
        handler_cls = type(
            "_BoundWyrdHandler",
            (_WyrdHandler,),
            {"bridge": bridge, "max_request_bytes": max_request_bytes},
        )
        self._handler_cls = handler_cls

    def serve_forever(self) -> None:
        """Start the server and block until interrupted.

        Call :meth:`shutdown` from another thread to stop gracefully.
        """
        self._stopped.clear()
        self._server = HTTPServer((self._host, self._port), self._handler_cls)
        self._server.serve_forever()

    def start_background(self) -> threading.Thread:
        """Start the server in a background daemon thread.

        When *watchdog=True* was passed to the constructor, an additional
        watchdog daemon thread monitors the server and restarts it if the
        serve loop exits unexpectedly.

        Returns:
            The running server Thread (daemon=True, joins on process exit).
        """
        self._stopped.clear()
        self._server = HTTPServer((self._host, self._port), self._handler_cls)
        thread = threading.Thread(target=self._serve_loop, name="wyrd-server", daemon=True)
        thread.start()
        if self._watchdog:
            wd = threading.Thread(target=self._watchdog_loop, name="wyrd-watchdog", daemon=True)
            wd.start()
        return thread

    def shutdown(self) -> None:
        """Stop the server if running."""
        self._stopped.set()
        if self._server is not None:
            self._server.shutdown()
            self._server = None

    @property
    def address(self) -> tuple[str, int]:
        """(host, port) this server is bound to."""
        return (self._host, self._port)

    @property
    def max_request_bytes(self) -> int:
        """Maximum accepted request body size in bytes."""
        return self._max_request_bytes

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _serve_loop(self) -> None:
        """Target for the server background thread."""
        try:
            self._server.serve_forever()
        except Exception:
            logger.exception("WyrdHTTPServer: serve_forever exited with exception")

    def _watchdog_loop(self) -> None:
        """Daemon thread that restarts the server if it crashes."""
        while not self._stopped.wait(timeout=self._watchdog_interval):
            if self._server is None:
                continue
            # Check if the serve_forever select loop is still running by
            # inspecting the internal _BaseServer__shutdown_request flag.
            try:
                if getattr(self._server, "_BaseServer__shutdown_request", False):
                    if not self._stopped.is_set():
                        logger.warning("WyrdHTTPServer watchdog: server stopped unexpectedly — restarting")
                        self._server = HTTPServer((self._host, self._port), self._handler_cls)
                        t = threading.Thread(target=self._serve_loop, name="wyrd-server-restart", daemon=True)
                        t.start()
            except Exception:
                logger.exception("WyrdHTTPServer watchdog: error during health check")
