"""KindroidWyrdBridge — WYRD integration for Kindroid AI companion platform.

Kindroid can send outgoing webhooks to external services.  This bridge
exposes a `/kindroid` POST endpoint that accepts Kindroid's webhook payload
and returns WYRD world context injected into the response body.

Kindroid integration pattern:
    1. Start KindroidWyrdBridge — exposes WyrdHTTPServer on a local port.
    2. In Kindroid, configure a webhook pointing to your bridge URL.
    3. Kindroid POSTs {"ai_id": "...", "message": "..."} to /kindroid.
    4. WYRD returns {"context": "<enriched context block>", "ok": true}.
    5. Kindroid's system prompt picks up the context block on the next turn.

Usage::

    from wyrdforge.bridges.kindroid_bridge import KindroidWyrdBridge

    bridge = KindroidWyrdBridge(
        default_persona_id="sigrid",
        db_path="wyrd_kindroid.db",
    )
    bridge.start_background()
    # Kindroid webhook: http://localhost:8767/kindroid
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from wyrdforge.bridges.python_rpg import BridgeConfig, PythonRPGBridge


class KindroidWyrdBridge:
    """WYRD bridge for Kindroid AI companion platform.

    Args:
        default_persona_id: Fallback persona ID when Kindroid doesn't send one.
        db_path:            SQLite path for PersistentMemoryStore.
        host:               Bind address. Default: ``"localhost"``.
        port:               Bind port. Default: ``8767``.
        ollama_model:       Ollama model name.
        context_only:       When True (default), return WYRD context block only
                            rather than calling Ollama. Kindroid handles the LLM.
    """

    def __init__(
        self,
        *,
        default_persona_id: str = "character",
        db_path: str = "wyrd_kindroid.db",
        host: str = "localhost",
        port: int = 8767,
        ollama_model: str = "llama3",
        context_only: bool = True,
    ) -> None:
        self._default_persona = default_persona_id
        self._host = host
        self._port = port
        self._context_only = context_only

        cfg = BridgeConfig(
            world_id="kindroid_world",
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

        handler_cls = type("_KindroidHandler", (_KindroidHandler,), {"_wyrd_bridge": self})
        self._server: HTTPServer | None = None
        self._handler_cls = handler_cls

    def start_background(self) -> threading.Thread:
        """Start the Kindroid webhook server in a background daemon thread."""
        self._server = HTTPServer((self._host, self._port), self._handler_cls)
        t = threading.Thread(target=self._server.serve_forever, daemon=True)
        t.start()
        return t

    def shutdown(self) -> None:
        """Stop the server if running."""
        if self._server:
            self._server.shutdown()
            self._server = None

    def handle_kindroid_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Process a Kindroid webhook payload and return context/response.

        Expected payload keys:
            - ``ai_id``   — Kindroid AI ID, maps to WYRD persona_id.
            - ``message`` — current user message text.
            - ``location`` — optional location override.

        Returns:
            ``{"context": "<wyrd context block>", "ok": True}``
        """
        persona_id = payload.get("ai_id") or self._default_persona
        user_message = payload.get("message", "")
        location_id = payload.get("location")

        world = self._bridge.world
        if not world.get_entity(persona_id):
            world.create_entity(entity_id=persona_id, tags={"character"})
            try:
                self._bridge.yggdrasil.place_entity(persona_id, location_id="shared_space")
            except Exception:
                pass

        context = self._bridge.query(
            persona_id,
            user_message,
            location_id=location_id,
            use_turn_loop=not self._context_only,
        )
        return {"context": context, "ok": True}

    @property
    def bridge(self) -> PythonRPGBridge:
        """The underlying PythonRPGBridge."""
        return self._bridge

    @property
    def address(self) -> tuple[str, int]:
        """(host, port) this server is bound to."""
        return (self._host, self._port)


class _KindroidHandler(BaseHTTPRequestHandler):
    _wyrd_bridge: KindroidWyrdBridge

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        if path in ("/kindroid", "/"):
            self._handle_kindroid()
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_GET(self) -> None:
        if self.path.split("?")[0] == "/health":
            self._send_json({"status": "ok"})
        else:
            self._send_json({"error": "Not found"}, 404)

    def _handle_kindroid(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._send_json({"error": f"Invalid JSON: {exc}"}, 400)
            return
        try:
            result = self._wyrd_bridge.handle_kindroid_payload(payload)
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
