"""WyrdHTTPServer — minimal stdlib HTTP adapter for WYRD.

Exposes the WYRD stack over a plain JSON HTTP API.  No framework
dependencies; uses only ``http.server`` and ``json`` from the stdlib.

Endpoints (Phase C2 — versioned, with unversioned aliases kept):
    POST /v1/query   — query a character (returns response text)
    GET  /v1/world   — get the current WorldContextPacket as JSON
    GET  /v1/facts   — get canonical facts for an entity
    POST /v1/event   — push a world event (observation or fact)
    GET  /v1/health  — liveness check

Every endpoint is also served at its original unversioned path
(``/query``, ``/world``, ``/facts``, ``/event``, ``/health``) as a
backwards-compatible alias with identical behaviour — existing
in-repo bridges, integrations and harnesses that hard-code the
unversioned surface keep working unchanged.  Responses carry an
``X-Wyrd-API-Version: 1`` header; response bodies are unchanged.

Authentication & rate limiting (Phase C2, ported from the cloud
relay's proven pattern in ``tools/wyrd_cloud_relay/relay.py``):

* When a bearer token is configured — the ``auth_token`` constructor
  argument, or the ``WYRD_API_TOKEN`` environment variable when no
  argument is given — EVERY endpoint (health included) requires
  ``Authorization: Bearer <token>``, compared in constant time.
  A missing or wrong token gets ``401 {"error": ...}`` and no data.
* When NO token is configured the server keeps its pre-C2 local-dev
  behaviour (no auth) and says so loudly: a WARNING is logged at
  construction.  Keep such a server on localhost, or set a token.
  A token is never hard-coded and never has a default value.
* Rate limiting applies uniformly to every endpoint, after auth:
  a rolling 60-second window per client key (the token's SHA-256
  fingerprint when authenticated, the client IP otherwise), in the
  relay's ``RateLimiter`` shape.  Over the limit:
  ``429 {"error": "Rate limit exceeded (<n>/min)"}``.
  ``rate_limit_per_minute=0`` disables limiting (the relay's rule).

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

import argparse
import hashlib
import hmac
import json
import logging
import os
import threading
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn


class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """HTTPServer with per-request daemon threads for concurrent request handling."""
    daemon_threads = True
from typing import Any, Optional

from wyrdforge.bridges.python_rpg import BridgeConfig, PythonRPGBridge
from wyrdforge.hardening.backoff import BackoffConfig
from wyrdforge.hardening.input_validation import (
    MAX_EVENT_DEPTH,
    MAX_ID_CHARS,
    MAX_QUERY_INPUT_CHARS,
    InputValidationError,
    check_depth,
    check_string,
    read_guarded_body,
    validate_event_envelope,
    validate_event_payload,
)

logger = logging.getLogger(__name__)

# Default maximum request body size (1 MiB). Requests larger than this receive
# 413 Content Too Large without reading the full body — prevents memory exhaustion.
DEFAULT_MAX_REQUEST_BYTES: int = 1 * 1024 * 1024  # 1 MiB

# ---------------------------------------------------------------------------
# Phase C2 — API versioning, token auth, rate limiting
# (pattern ported from tools/wyrd_cloud_relay/relay.py)
# ---------------------------------------------------------------------------

#: URL prefix for the current API version.  Unversioned paths remain
#: as aliases for the same routes (see the module docstring).
API_VERSION_PREFIX: str = "/v1"

#: Environment variable that configures the bearer token when the
#: ``auth_token`` constructor argument is not given.  Named after the
#: relay's ``WYRD_RELAY_TOKEN`` precedent.  Never a default value:
#: unset/empty means auth is disabled (local-dev mode, loudly logged).
API_TOKEN_ENV_VAR: str = "WYRD_API_TOKEN"

#: Default rate limit, requests per minute per client key.  The relay
#: defaults to 60/min for a public-facing proxy; the core server is
#: the live-rate engine behind it (B-phase: 1 Hz presence, concurrent
#: bridge + inspector + voice consumers), so its default is 600/min —
#: the same rolling-window mechanism, a core-appropriate bound.
#: ``0`` disables limiting (the relay's rule).
DEFAULT_RATE_LIMIT_PER_MINUTE: int = 600


class RateLimiter:
    """Rolling-window rate limiter — the relay's ``RateLimiter``,
    ported into core and made thread-safe (the threading HTTP server
    checks it from per-request threads; the relay's FastAPI version
    relied on its event loop).

    Tracks request counts per client key within a rolling 60-second
    window.  ``requests_per_minute <= 0`` means unlimited.  Expired
    buckets are pruned on access so the key map cannot grow with
    stale clients.
    """

    def __init__(self, requests_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE):
        self.rpm = requests_per_minute
        self._log: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, client_key: str, now: float | None = None) -> bool:
        if self.rpm <= 0:
            return True
        now = now if now is not None else time.monotonic()
        window_start = now - 60.0
        with self._lock:
            bucket = self._log[client_key]
            # Evict old entries
            bucket[:] = [t for t in bucket if t > window_start]
            if len(bucket) >= self.rpm:
                return False
            bucket.append(now)
            return True

    def request_count(self, client_key: str, now: float | None = None) -> int:
        now = now if now is not None else time.monotonic()
        window_start = now - 60.0
        with self._lock:
            return sum(1 for t in self._log.get(client_key, []) if t > window_start)


def _canonical_path(raw_path: str) -> str:
    """Map a request path to its canonical (unversioned) route.

    ``/v1/query`` → ``/query``; an already-unversioned path is its
    own canonical form (the alias).  Anything else is returned
    unchanged and will 404 in routing.
    """
    path = raw_path.split("?")[0]
    if path == API_VERSION_PREFIX:
        return "/"
    if path.startswith(API_VERSION_PREFIX + "/"):
        return path[len(API_VERSION_PREFIX):]
    return path

# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

class _WyrdHandler(BaseHTTPRequestHandler):
    """Internal request handler.  Do not instantiate directly."""

    bridge: PythonRPGBridge  # injected by WyrdHTTPServer via class patching
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES  # injected at class creation
    auth_token: str | None = None  # injected at class creation (None = auth disabled)
    rate_limiter: RateLimiter | None = None  # injected at class creation

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def do_GET(self) -> None:
        path = _canonical_path(self.path)
        if path not in ("/health", "/world", "/facts"):
            self._send_error(404, "Not found")
            return
        if not self._check_auth_and_limit():
            return
        if path == "/health":
            self._send_json({"status": "ok"})
        elif path == "/world":
            self._handle_world()
        else:
            self._handle_facts()

    def do_POST(self) -> None:
        path = _canonical_path(self.path)
        if path not in ("/query", "/event"):
            self._send_error(404, "Not found")
            return
        if not self._check_auth_and_limit():
            return
        if path == "/query":
            self._handle_query()
        else:
            self._handle_event()

    # ------------------------------------------------------------------
    # Auth + rate limiting (Phase C2 — relay pattern, applied uniformly
    # to every known route, versioned and alias alike, health included)
    # ------------------------------------------------------------------

    def _check_auth_and_limit(self) -> bool:
        """Validate the bearer token (when configured), then the rate
        limit — the relay's ``_auth_and_limit`` order.  On failure the
        error response is already sent and this returns False: a 401
        carries no endpoint data, and unauthenticated requests never
        consume rate-limit budget.
        """
        client_key = f"ip:{self.client_address[0]}"
        if self.auth_token:
            header = self.headers.get("Authorization")
            presented: str | None = None
            if header:
                parts = header.split(maxsplit=1)
                if len(parts) == 2 and parts[0].lower() == "bearer":
                    presented = parts[1]
            # Constant-time compare (the relay compared with ``in`` on
            # a token set; core hardens that to compare_digest).
            if presented is None or not hmac.compare_digest(
                presented.encode("utf-8"), self.auth_token.encode("utf-8")
            ):
                self._send_json(
                    {"error": "Invalid or missing bearer token"},
                    status=401,
                    extra_headers={"WWW-Authenticate": "Bearer"},
                )
                return False
            # Rate-limit per credential without keying on (or logging)
            # the raw token: its SHA-256 fingerprint is the key.
            client_key = "token:" + hashlib.sha256(
                presented.encode("utf-8")
            ).hexdigest()[:16]
        limiter = self.rate_limiter
        if limiter is not None and not limiter.is_allowed(client_key):
            self._send_error(
                429, f"Rate limit exceeded ({limiter.rpm}/min)"
            )
            return False
        return True

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_query(self) -> None:
        body = self._read_json()
        if body is None:
            return
        try:
            # The body envelope itself consumes one level, so the body
            # budget is the payload budget plus one.
            check_depth(body, max_depth=MAX_EVENT_DEPTH + 1, field="body")
            persona_id = check_string(
                body.get("persona_id"), field="persona_id",
                max_len=MAX_ID_CHARS, allow_empty=False,
            )
            user_input = check_string(
                body.get("user_input"), field="user_input",
                max_len=MAX_QUERY_INPUT_CHARS, allow_empty=False,
            )
            location_id = body.get("location_id")
            if location_id is not None:
                location_id = check_string(
                    location_id, field="location_id",
                    max_len=MAX_ID_CHARS, allow_empty=False,
                )
            bond_id = body.get("bond_id")
            if bond_id is not None:
                bond_id = check_string(
                    bond_id, field="bond_id",
                    max_len=MAX_ID_CHARS, allow_empty=False,
                )
        except InputValidationError as exc:
            self._send_error(400, str(exc))
            return
        try:
            response = self.bridge.query(
                persona_id,
                user_input,
                location_id=location_id,
                bond_id=bond_id,
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
        try:
            entity_id = check_string(
                entity_id, field="entity_id",
                max_len=MAX_ID_CHARS, allow_empty=False,
            )
        except InputValidationError as exc:
            self._send_error(400, str(exc))
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
        try:
            # The body envelope itself consumes one level, so the body
            # budget is the payload budget plus one.
            check_depth(body, max_depth=MAX_EVENT_DEPTH + 1, field="body")
            event_type = body.get("event_type")
            payload = body.get("payload", {})
            validate_event_envelope(event_type, payload)
            validate_event_payload(event_type, payload)
        except InputValidationError as exc:
            self._send_error(400, str(exc))
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
        raw, rejection = read_guarded_body(
            self.headers, self.rfile, max_bytes=self.max_request_bytes
        )
        if rejection is not None:
            status, message = rejection
            self._send_error(status, message)
            return None
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._send_error(400, f"Invalid JSON: {exc}")
            return None
        if not isinstance(data, dict):
            self._send_error(400, "Request body must be a JSON object")
            return None
        return data

    def _send_json(
        self,
        data: Any,
        status: int = 200,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Wyrd-API-Version", "1")
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
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
                           Restarts are bounded: at most
                           ``watchdog_backoff.max_attempts`` restarts; the
                           next consecutive crash after the budget is
                           exhausted logs CRITICAL and stops the watchdog
                           (manual intervention required).
        watchdog_interval: Seconds between watchdog health checks (default 5).
        watchdog_backoff:  BackoffConfig for restart delays (default: 4 attempts,
                           0.5s base, x2, 30s cap, +/-25% jitter).
        auth_token:        Bearer token required on every endpoint
                           (Phase C2).  ``None`` (default) reads the
                           ``WYRD_API_TOKEN`` environment variable; an
                           empty resolved value disables auth — the
                           pre-C2 local-dev behaviour, logged loudly
                           at construction.  Pass a token explicitly
                           or via the env var before binding beyond
                           localhost.  Never hard-code a token.
        rate_limit_per_minute: Rolling-window rate limit per client
                           key (Phase C2; default
                           ``DEFAULT_RATE_LIMIT_PER_MINUTE``).
                           ``0`` disables limiting.
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
        watchdog_backoff: BackoffConfig = BackoffConfig(),
        auth_token: str | None = None,
        rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE,
    ) -> None:
        self._bridge = bridge
        self._host = host
        self._port = port
        self._max_request_bytes = max_request_bytes
        self._watchdog = watchdog
        self._watchdog_interval = watchdog_interval
        self._watchdog_backoff = watchdog_backoff
        self._watchdog_failures = 0
        self._server: Optional[HTTPServer] = None
        self._serve_thread: Optional[threading.Thread] = None
        self._stopped = threading.Event()

        # Phase C2 auth resolution: explicit argument wins; otherwise
        # the WYRD_API_TOKEN env var; empty/unset = auth disabled.
        resolved_token = auth_token
        if resolved_token is None:
            resolved_token = os.environ.get(API_TOKEN_ENV_VAR, "")
        resolved_token = resolved_token.strip() or None
        self._auth_token = resolved_token
        if self._auth_token is None:
            logger.warning(
                "WyrdHTTPServer: starting WITHOUT authentication "
                "(no auth_token given and %s is not set) — anyone who "
                "can reach %s:%s can read and write the world API. "
                "Keep the bind on localhost, or set a token.",
                API_TOKEN_ENV_VAR, host, port,
            )
        self._rate_limiter = RateLimiter(rate_limit_per_minute)

        # Inject bridge + config into handler class via subclass so that
        # multiple server instances each get their own handler class.
        handler_cls = type(
            "_BoundWyrdHandler",
            (_WyrdHandler,),
            {
                "bridge": bridge,
                "max_request_bytes": max_request_bytes,
                "auth_token": self._auth_token,
                "rate_limiter": self._rate_limiter,
            },
        )
        self._handler_cls = handler_cls

    @property
    def auth_enabled(self) -> bool:
        """True when a bearer token is configured (Phase C2)."""
        return self._auth_token is not None

    @property
    def rate_limit_per_minute(self) -> int:
        """Configured rolling-window rate limit (0 = disabled)."""
        return self._rate_limiter.rpm

    def serve_forever(self) -> None:
        """Start the server and block until interrupted.

        Call :meth:`shutdown` from another thread to stop gracefully.
        """
        self._stopped.clear()
        self._server = _ThreadingHTTPServer((self._host, self._port), self._handler_cls)
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
        # A manual (re)start is the operator's intervention: restore the full
        # watchdog restart budget, so a stale counter from a previous terminal
        # stop can't kill the new run on its first crash.
        self._watchdog_failures = 0
        thread = self._restart_server()
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

    def _restart_server(self) -> threading.Thread:
        """Rebuild the listening socket and launch a fresh serve thread.

        Used by :meth:`start_background` and by the watchdog's restart
        path.  The new thread is recorded in ``_serve_thread`` so the
        watchdog can track its aliveness.  Factored out (rather than
        inlined) so tests can script restarts without real sockets.
        """
        self._server = _ThreadingHTTPServer((self._host, self._port), self._handler_cls)
        thread = threading.Thread(
            target=self._serve_loop, name="wyrd-server", daemon=True
        )
        thread.start()
        self._serve_thread = thread
        return thread

    def _watchdog_loop(self) -> None:
        """Daemon thread that restarts the server if it crashes.

        Crash detection is serve-thread aliveness: the background thread
        runs ``serve_forever`` for the life of the server, so a thread
        that is no longer alive means the server is gone.  This uses only
        the public ``Thread.is_alive`` API — deliberately no private
        interpreter internals (the old shutdown-request flag probe), which
        are not part of any stability contract and differ across
        implementations.

        Restarts are bounded: at most ``watchdog_backoff.max_attempts``
        restarts; the next consecutive crash after the budget is exhausted
        logs CRITICAL and stops the watchdog (terminal state — manual
        intervention required).
        A healthy check resets the consecutive-failure counter, so a
        transient blip restores the full restart budget.
        """
        while not self._stopped.wait(timeout=self._watchdog_interval):
            thread = self._serve_thread
            if thread is None:
                continue
            if thread.is_alive():
                # Healthy: a transient blip restores the full budget.
                self._watchdog_failures = 0
                continue
            # The serve thread died: the server crashed (or its socket was
            # killed from underneath it).  A graceful shutdown sets
            # _stopped first and exits the loop above; reaching here with
            # _stopped set means shutdown raced the health check — never
            # restart in that case.
            if self._stopped.is_set():
                continue
            try:
                self._watchdog_failures += 1
                if self._watchdog_failures > self._watchdog_backoff.max_attempts:
                    logger.critical(
                        "WyrdHTTPServer watchdog: server crashed %d times in a row — "
                        "automatic restarts STOPPED; manual intervention required",
                        self._watchdog_failures,
                    )
                    return
                delay = self._watchdog_backoff.delay_for(self._watchdog_failures - 1)
                logger.warning(
                    "WyrdHTTPServer watchdog: server stopped unexpectedly — "
                    "restarting (attempt %d/%d in %.1fs)",
                    self._watchdog_failures,
                    self._watchdog_backoff.max_attempts,
                    delay,
                )
                if self._stopped.wait(timeout=delay):
                    return
                self._restart_server()
            except Exception:
                logger.exception("WyrdHTTPServer watchdog: error during health check")


# ---------------------------------------------------------------------------
# CLI — python -m wyrdforge.bridges.http_api (Phase E5)
#
# The documented quickstart entry point, made real.  Before E5 this
# module had no __main__ entry at all: docs/guides/quickstart.md and
# docs/index.md named a nonexistent ``wyrdforge.server`` module, and
# CLAUDE.md's fallback line (``python -m wyrdforge.bridges.http_api``)
# exited silently doing nothing, because running a module without a
# ``__main__`` guard is a no-op.  This main() is the fix: the module
# path the docs name now starts the server it describes.
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Start a WyrdHTTPServer over a fresh PythonRPGBridge.

    The bridge is built from :class:`BridgeConfig` with a blank world
    (the ``from_config`` path the module docstring shows); world
    content arrives through the API itself, or use the chat/world
    CLIs (``wyrd-chat`` / ``wyrd-world``) for YAML-loaded worlds.
    Auth follows the Phase C2 rule: set ``WYRD_API_TOKEN`` to require
    a bearer token; without one the server runs unauthenticated on
    the bind address and logs a loud warning saying so.
    """
    parser = argparse.ArgumentParser(
        prog="wyrdforge.bridges.http_api",
        description="WYRD HTTP API server (WyrdHTTPServer over a PythonRPGBridge).",
    )
    parser.add_argument("--host", default="localhost", help="bind address (default: localhost)")
    parser.add_argument("--port", type=int, default=8765, help="bind port (default: 8765)")
    parser.add_argument("--world-id", default="wyrd_world", help="logical world id")
    parser.add_argument(
        "--db",
        default="wyrd.db",
        help="SQLite path for the persistent memory store (default: wyrd.db)",
    )
    args = parser.parse_args(argv)

    bridge = PythonRPGBridge.from_config(
        BridgeConfig(world_id=args.world_id, db_path=args.db)
    )
    server = WyrdHTTPServer(bridge, host=args.host, port=args.port)
    print(
        f"[WyrdForge] WyrdHTTPServer listening on http://{args.host}:{args.port}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
