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
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from wyrdforge.bridges.python_rpg import PythonRPGBridge


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

class _WyrdHandler(BaseHTTPRequestHandler):
    """Internal request handler.  Do not instantiate directly."""

    bridge: PythonRPGBridge  # injected by WyrdHTTPServer via class patching

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
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._send_error(400, f"Invalid JSON: {exc}")
            return None

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
        bridge: The PythonRPGBridge instance to serve.
        host:   Bind address (default ``"localhost"``).
        port:   Bind port (default ``8765``).
    """

    def __init__(
        self,
        bridge: PythonRPGBridge,
        *,
        host: str = "localhost",
        port: int = 8765,
    ) -> None:
        self._bridge = bridge
        self._host = host
        self._port = port
        self._server: HTTPServer | None = None

        # Inject bridge reference into handler class via subclass so that
        # multiple server instances each get their own handler class.
        handler_cls = type(
            "_BoundWyrdHandler",
            (_WyrdHandler,),
            {"bridge": bridge},
        )
        self._handler_cls = handler_cls

    def serve_forever(self) -> None:
        """Start the server and block until interrupted.

        Call :meth:`shutdown` from another thread to stop gracefully.
        """
        self._server = HTTPServer((self._host, self._port), self._handler_cls)
        self._server.serve_forever()

    def start_background(self) -> threading.Thread:
        """Start the server in a background daemon thread.

        Returns:
            The running Thread (daemon=True, joins on process exit).
        """
        self._server = HTTPServer((self._host, self._port), self._handler_cls)
        thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        thread.start()
        return thread

    def shutdown(self) -> None:
        """Stop the server if running."""
        if self._server is not None:
            self._server.shutdown()
            self._server = None

    @property
    def address(self) -> tuple[str, int]:
        """(host, port) this server is bound to."""
        return (self._host, self._port)
