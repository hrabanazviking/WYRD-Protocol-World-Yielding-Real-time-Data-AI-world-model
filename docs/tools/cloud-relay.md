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
# Basic — relay localhost:8765 on port 9000
python tools/wyrd_cloud_relay/relay.py

# Custom upstream and port
python tools/wyrd_cloud_relay/relay.py --upstream http://myserver:8765 --port 9000

# With authentication token
python tools/wyrd_cloud_relay/relay.py --token my-secret-token

# Multiple tokens (comma-separated)
python tools/wyrd_cloud_relay/relay.py --token "token-a,token-b"

# Rate limiting (requests per minute per token)
python tools/wyrd_cloud_relay/relay.py --rate-limit 30
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `WYRD_UPSTREAM_URL` | `http://localhost:8765` | Upstream WyrdHTTPServer |
| `WYRD_RELAY_PORT` | `9000` | Port to listen on |
| `WYRD_RELAY_TOKEN` | (empty) | Bearer token(s), comma-separated |
| `WYRD_RATE_LIMIT` | `60` | Requests per minute (0 = unlimited) |

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
