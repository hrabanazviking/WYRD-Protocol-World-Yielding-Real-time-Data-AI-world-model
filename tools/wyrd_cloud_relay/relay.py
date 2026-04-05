#!/usr/bin/env python
"""
wyrd_cloud_relay/relay.py — WYRD Cloud Relay Server (Phase 14C)

A thin FastAPI relay that proxies requests to a local WyrdHTTPServer.
Enables plugins running on external/cloud hosts (Roblox, hosted Foundry,
public Minecraft servers) to reach a WyrdHTTPServer behind a NAT.

Features:
  - Proxies /query, /event, /world, /facts, /health
  - Optional bearer token authentication
  - CORS support for browser-based clients (D&D Beyond, Owlbear, etc.)
  - Rate limiting (requests per minute per token)
  - Request logging

Usage:
    pip install fastapi uvicorn httpx
    python tools/wyrd_cloud_relay/relay.py
    python tools/wyrd_cloud_relay/relay.py --upstream http://localhost:8765 --port 9000
    python tools/wyrd_cloud_relay/relay.py --token my-secret-token

Environment variables (alternative to CLI flags):
    WYRD_UPSTREAM_URL   — upstream WyrdHTTPServer URL
    WYRD_RELAY_PORT     — port to listen on
    WYRD_RELAY_TOKEN    — bearer token (empty = no auth)
    WYRD_RATE_LIMIT     — requests per minute per token (0 = unlimited)
"""
from __future__ import annotations

import argparse
import os
import time
from collections import defaultdict
from typing import Optional

# ---------------------------------------------------------------------------
# Pure relay logic (no FastAPI dependency — testable in isolation)
# ---------------------------------------------------------------------------

class RateLimiter:
    """
    Token-bucket rate limiter.
    Tracks request counts per client key within a rolling 60-second window.
    """

    def __init__(self, requests_per_minute: int = 60):
        self.rpm   = requests_per_minute
        self._log: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, client_key: str, now: float | None = None) -> bool:
        if self.rpm <= 0:
            return True
        now = now if now is not None else time.monotonic()
        window_start = now - 60.0
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
        return sum(1 for t in self._log.get(client_key, []) if t > window_start)


class TokenValidator:
    """Validates bearer tokens. Empty token list = auth disabled."""

    def __init__(self, tokens: list[str]):
        self._tokens = set(t.strip() for t in tokens if t.strip())

    @property
    def auth_required(self) -> bool:
        return bool(self._tokens)

    def validate(self, authorization_header: str | None) -> tuple[bool, str]:
        """
        Returns (is_valid, client_key).
        client_key is the token itself (for rate limiting) or "anon".
        """
        if not self.auth_required:
            return True, "anon"
        if not authorization_header:
            return False, ""
        parts = authorization_header.split(maxsplit=1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return False, ""
        token = parts[1].strip()
        if token in self._tokens:
            return True, token
        return False, ""


class RelayConfig:
    """Runtime configuration for the relay."""

    def __init__(
        self,
        upstream_url: str = "http://localhost:8765",
        port: int = 9000,
        tokens: list[str] | None = None,
        rate_limit: int = 60,
        cors_origins: list[str] | None = None,
        timeout: float = 15.0,
    ):
        self.upstream_url = upstream_url.rstrip("/")
        self.port         = port
        self.tokens       = tokens or []
        self.rate_limit   = rate_limit
        self.cors_origins = cors_origins or ["*"]
        self.timeout      = timeout

    @classmethod
    def from_env(cls) -> "RelayConfig":
        return cls(
            upstream_url=os.environ.get("WYRD_UPSTREAM_URL", "http://localhost:8765"),
            port=int(os.environ.get("WYRD_RELAY_PORT", "9000")),
            tokens=[t for t in os.environ.get("WYRD_RELAY_TOKEN", "").split(",") if t],
            rate_limit=int(os.environ.get("WYRD_RATE_LIMIT", "60")),
        )

    def upstream(self, path: str) -> str:
        return self.upstream_url + path

    def __repr__(self) -> str:
        return (f"RelayConfig(upstream={self.upstream_url!r}, "
                f"port={self.port}, "
                f"auth={'enabled' if self.tokens else 'disabled'}, "
                f"rate_limit={self.rate_limit}/min)")


def build_cors_headers(origins: list[str]) -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin":  ", ".join(origins) if origins != ["*"] else "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    }


# ---------------------------------------------------------------------------
# FastAPI application factory
# ---------------------------------------------------------------------------

def create_app(config: RelayConfig):
    """
    Create and return the FastAPI application.
    Imported separately so the module is importable without FastAPI installed.
    """
    try:
        import fastapi
        import httpx
        from fastapi import FastAPI, Request, Response, HTTPException
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError:
        raise ImportError(
            "FastAPI and httpx are required for the cloud relay.\n"
            "Install with: pip install fastapi uvicorn httpx"
        )

    app        = FastAPI(title="WYRD Cloud Relay", version="1.0.0")
    limiter    = RateLimiter(config.rate_limit)
    validator  = TokenValidator(config.tokens)
    http       = httpx.AsyncClient(timeout=config.timeout)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    async def _auth_and_limit(request: Request) -> str:
        """Validate token and rate-limit. Returns client_key."""
        ok, client_key = validator.validate(
            request.headers.get("Authorization"))
        if not ok:
            raise HTTPException(status_code=401, detail="Invalid or missing bearer token")
        if not limiter.is_allowed(client_key):
            raise HTTPException(status_code=429,
                                detail=f"Rate limit exceeded ({config.rate_limit}/min)")
        return client_key

    async def _proxy_get(path: str, params: dict = None) -> dict:
        resp = await http.get(config.upstream(path), params=params)
        resp.raise_for_status()
        return resp.json()

    async def _proxy_post(path: str, body: dict) -> dict:
        resp = await http.post(config.upstream(path), json=body)
        resp.raise_for_status()
        return resp.json()

    # -------------------------------------------------------------------------
    # Routes
    # -------------------------------------------------------------------------

    @app.get("/health")
    async def health(request: Request):
        await _auth_and_limit(request)
        try:
            data = await _proxy_get("/health")
            return {"relay": "ok", "upstream": data}
        except Exception as e:
            return {"relay": "ok", "upstream": "unreachable", "error": str(e)}

    @app.post("/query")
    async def query(request: Request):
        await _auth_and_limit(request)
        body = await request.json()
        return await _proxy_post("/query", body)

    @app.post("/event")
    async def event(request: Request):
        await _auth_and_limit(request)
        body = await request.json()
        return await _proxy_post("/event", body)

    @app.get("/world")
    async def world(request: Request):
        await _auth_and_limit(request)
        return await _proxy_get("/world")

    @app.get("/facts")
    async def facts(request: Request, subject_id: str = ""):
        await _auth_and_limit(request)
        return await _proxy_get("/facts", {"subject_id": subject_id} if subject_id else {})

    @app.get("/")
    async def root():
        return {
            "service": "WYRD Cloud Relay",
            "version": "1.0.0",
            "upstream": config.upstream_url,
            "auth":     "enabled" if validator.auth_required else "disabled",
            "endpoints": ["/health", "/query", "/event", "/world", "/facts"],
        }

    return app


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="WYRD Cloud Relay")
    p.add_argument("--upstream", default=os.environ.get("WYRD_UPSTREAM_URL",
                   "http://localhost:8765"),
                   help="Upstream WyrdHTTPServer URL")
    p.add_argument("--port",    type=int,
                   default=int(os.environ.get("WYRD_RELAY_PORT", "9000")),
                   help="Port to listen on")
    p.add_argument("--token",   default=os.environ.get("WYRD_RELAY_TOKEN", ""),
                   help="Bearer token(s), comma-separated (empty = no auth)")
    p.add_argument("--rate-limit", type=int,
                   default=int(os.environ.get("WYRD_RATE_LIMIT", "60")),
                   help="Requests per minute per token (0 = unlimited)")
    p.add_argument("--host",   default="0.0.0.0", help="Bind host")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    try:
        import uvicorn
    except ImportError:
        print("uvicorn is required: pip install uvicorn")
        raise SystemExit(1)

    config = RelayConfig(
        upstream_url=args.upstream,
        port=args.port,
        tokens=[t for t in args.token.split(",") if t],
        rate_limit=args.rate_limit,
    )
    print(f"[WyrdRelay] {config}")
    app = create_app(config)
    uvicorn.run(app, host=args.host, port=args.port)
