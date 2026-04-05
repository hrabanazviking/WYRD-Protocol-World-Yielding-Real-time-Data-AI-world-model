"""VoxtaWyrdBridge — WYRD integration for Voxta AI companion platform.

Voxta connects to WYRD by calling WyrdHTTPServer's /query endpoint as an
external action/service.  This bridge configures a WyrdHTTPServer tuned
for Voxta's expected request shape and adds a `/voxta` webhook endpoint
that accepts Voxta's native action payload format.

Voxta integration pattern:
    1. Start VoxtaWyrdBridge — it exposes a WyrdHTTPServer on a local port.
    2. In Voxta, add an "External Action" pointing to http://localhost:<port>/voxta.
    3. Voxta POSTs {"characterId": "...", "userMessage": "..."} to the endpoint.
    4. WYRD returns {"reply": "<enriched context or LLM response>"}.

Usage::

    from wyrdforge.bridges.voxta_bridge import VoxtaWyrdBridge

    bridge = VoxtaWyrdBridge(
        default_persona_id="sigrid",
        db_path="wyrd_voxta.db",
    )
    bridge.start_background()
    # Voxta can now reach http://localhost:8766/voxta
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from wyrdforge.bridges.python_rpg import BridgeConfig, PythonRPGBridge


class VoxtaWyrdBridge:
    """WYRD bridge for Voxta AI companion platform.

    Starts a lightweight HTTP server that accepts Voxta's action payload
    and returns WYRD world context as the reply.

    Args:
        default_persona_id: Fallback persona ID when Voxta doesn't send one.
        db_path:            SQLite path for PersistentMemoryStore.
        host:               Bind address. Default: ``"localhost"``.
        port:               Bind port. Default: ``8766``.
        ollama_model:       Ollama model for LLM calls.
        use_turn_loop:      Whether to call Ollama or return context only.
    """

    def __init__(
        self,
        *,
        default_persona_id: str = "character",
        db_path: str = "wyrd_voxta.db",
        host: str = "localhost",
        port: int = 8766,
        ollama_model: str = "llama3",
        use_turn_loop: bool = False,
    ) -> None:
        self._default_persona = default_persona_id
        self._host = host
        self._port = port
        self._use_turn_loop = use_turn_loop

        cfg = BridgeConfig(
            world_id="voxta_world",
            db_path=db_path,
            ollama_model=ollama_model,
        )
        self._bridge = PythonRPGBridge.from_config(cfg)

        # Minimal spatial scaffold
        self._bridge.yggdrasil.create_zone(zone_id="midgard", name="Midgard")
        self._bridge.yggdrasil.create_region(
            region_id="home", name="Home", parent_zone_id="midgard"
        )
        self._bridge.yggdrasil.create_location(
            location_id="shared_space", name="Shared Space", parent_region_id="home"
        )

        handler_cls = type("_VoxtaHandler", (_VoxtaHandler,), {"_wyrd_bridge": self})
        self._server: HTTPServer | None = None
        self._handler_cls = handler_cls

    def start_background(self) -> threading.Thread:
        """Start the Voxta webhook server in a background daemon thread."""
        self._server = HTTPServer((self._host, self._port), self._handler_cls)
        t = threading.Thread(target=self._server.serve_forever, daemon=True)
        t.start()
        return t

    def shutdown(self) -> None:
        """Stop the server if running."""
        if self._server:
            self._server.shutdown()
            self._server = None

    def handle_voxta_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Process a Voxta action payload and return a reply dict.

        Expected payload keys:
            - ``characterId`` — maps to WYRD persona_id (fallback to default).
            - ``userMessage`` — current user message text.
            - ``locationId``  — optional location override.

        Returns:
            ``{"reply": "<context or LLM response>"}``
        """
        persona_id = payload.get("characterId") or self._default_persona
        user_message = payload.get("userMessage", "")
        location_id = payload.get("locationId")

        # Ensure entity exists
        world = self._bridge.world
        if not world.get_entity(persona_id):
            world.create_entity(entity_id=persona_id, tags={"character"})
            try:
                self._bridge.yggdrasil.place_entity(persona_id, location_id="shared_space")
            except Exception:
                pass

        reply = self._bridge.query(
            persona_id,
            user_message,
            location_id=location_id,
            use_turn_loop=self._use_turn_loop,
        )
        return {"reply": reply}

    @property
    def bridge(self) -> PythonRPGBridge:
        """The underlying PythonRPGBridge."""
        return self._bridge

    @property
    def address(self) -> tuple[str, int]:
        """(host, port) this server is bound to."""
        return (self._host, self._port)


class _VoxtaHandler(BaseHTTPRequestHandler):
    _wyrd_bridge: VoxtaWyrdBridge

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        if path in ("/voxta", "/"):
            self._handle_voxta()
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_GET(self) -> None:
        if self.path.split("?")[0] == "/health":
            self._send_json({"status": "ok"})
        else:
            self._send_json({"error": "Not found"}, 404)

    def _handle_voxta(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._send_json({"error": f"Invalid JSON: {exc}"}, 400)
            return
        try:
            result = self._wyrd_bridge.handle_voxta_payload(payload)
            self._send_json(result)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 500)

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:
        pass
