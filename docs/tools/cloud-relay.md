# WYRD Cloud Relay

A thin FastAPI proxy that exposes WyrdHTTPServer to external/cloud clients.

Enables platforms where the game server and WyrdHTTPServer can't share a LAN
(hosted Foundry VTT, public Roblox servers, cloud-hosted Minecraft, etc.).

## Installation

```bash
pip install fastapi uvicorn httpx
```

## Usage

```bash
# Local dev — loopback bind, narrowed CORS, no token (starts with a warning)
python tools/wyrd_cloud_relay/relay.py --host 127.0.0.1 \
    --cors-origins https://www.owlbear.rodeo

# Custom upstream and port
python tools/wyrd_cloud_relay/relay.py --upstream http://myserver:8765 --port 9000

# With authentication token
python tools/wyrd_cloud_relay/relay.py --token my-secret-token

# Multiple tokens (comma-separated)
python tools/wyrd_cloud_relay/relay.py --token "token-a,token-b"

# Rate limiting (requests per minute per token)
python tools/wyrd_cloud_relay/relay.py --rate-limit 30

# Narrow CORS origins (comma-separated; default "*" — see docs/security.md D1)
python tools/wyrd_cloud_relay/relay.py --token my-secret-token \
    --cors-origins https://www.owlbear.rodeo,https://www.dndbeyond.com
```

> **Startup rule (D2, Volmarr 2026-09-26):** the relay refuses to
> start (exit 2) on a non-loopback bind — or with wildcard CORS —
> unless a bearer token is configured. Loopback without a token
> starts with a loud warning.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `WYRD_UPSTREAM_URL` | `http://localhost:8765` | Upstream WyrdHTTPServer |
| `WYRD_RELAY_PORT` | `9000` | Port to listen on |
| `WYRD_RELAY_TOKEN` | (empty) | Bearer token(s), comma-separated |
| `WYRD_RATE_LIMIT` | `60` | Requests per minute (0 = unlimited) |
| `WYRD_CORS_ORIGINS` | `*` | CORS origins, comma-separated (D1 named decision — see `docs/security.md`) |

## Endpoints

All endpoints proxy to the upstream WyrdHTTPServer:

| Relay endpoint | Upstream | Method |
|---|---|---|
| `GET /health` | `/health` | GET |
| `POST /query` | `/query` | POST |
| `POST /event` | `/event` | POST |
| `GET /world` | `/world` | GET |
| `GET /facts` | `/facts` | GET |

## Authentication

When `--token` is set, all requests must include:

```
Authorization: Bearer <token>
```

Requests without a valid token receive `401 Unauthorized`.

## Rate limiting

The relay tracks requests per token within a rolling 60-second window.
Exceeding the limit returns `429 Too Many Requests`.

## CORS

The relay sets permissive CORS headers by default (`*`), enabling browser-based
clients (D&D Beyond extension, Owlbear Rodeo, etc.) to call it directly.
