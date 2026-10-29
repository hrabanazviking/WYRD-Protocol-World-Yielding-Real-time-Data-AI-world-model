# HTTP API Reference

WyrdHTTPServer exposes a JSON REST API on `http://localhost:8765` by default.

Since Phase C2 the canonical paths are versioned under `/v1/`
(`/v1/query`, `/v1/event`, `/v1/world`, `/v1/facts`, `/v1/health`);
the original unversioned paths below remain as backwards-compatible
aliases with identical behaviour, and every response carries an
`X-Wyrd-API-Version: 1` header.  When a bearer token is configured
(the `auth_token` argument or the `WYRD_API_TOKEN` environment
variable), every endpoint — health included — requires
`Authorization: Bearer <token>`; see `docs/security.md`.

## POST /v1/query

Query world context for a character persona.

**Request body:**
```json
{
  "persona_id": "sigrid_stormborn",
  "user_input": "What do I know about the approaching army?",
  "use_turn_loop": false
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `persona_id` | string | yes | Normalised character ID (lowercase, underscores) |
| `user_input` | string | yes | The question or player input |
| `use_turn_loop` | bool | no | If true, uses full LLM turn loop (default: false) |

**Response:**
```json
{
  "response": "The scouts reported 300 warriors...",
  "persona_id": "sigrid_stormborn",
  "context_used": true
}
```

---

## POST /v1/event

Push a world event into WYRD memory.

### Observation event

```json
{
  "event_type": "observation",
  "payload": {
    "title": "Army sighted",
    "summary": "300 warriors crossing the northern river at dawn."
  }
}
```

### Fact event

```json
{
  "event_type": "fact",
  "payload": {
    "subject_id": "sigrid",
    "key": "location",
    "value": "great_hall"
  }
}
```

**Response:** `{"status": "ok"}`

---

## GET /v1/world

Returns the full world state snapshot.

```json
{
  "world_name": "thornholt",
  "entities": [
    {
      "entity_id": "sigrid",
      "name": "Sigrid Stormborn",
      "location": "great_hall",
      "status": "active",
      "faction": "Raven Clan"
    }
  ],
  "location_count": 24,
  "zones": ["midgard", "jotunheim_border"]
}
```

---

## GET /v1/facts

Returns canonical facts for a subject.

```
GET /v1/facts?subject_id=sigrid
```

```json
[
  {"subject_id": "sigrid", "key": "name",     "value": "Sigrid Stormborn"},
  {"subject_id": "sigrid", "key": "role",     "value": "völva"},
  {"subject_id": "sigrid", "key": "location", "value": "great_hall"}
]
```

---

## GET /v1/health

Health check endpoint.

```json
{"status": "ok"}
```

---

## Persona ID convention

All `persona_id` values follow a normalisation convention:

- Lowercase
- Non-alphanumeric characters replaced with `_`
- Consecutive underscores collapsed
- Leading/trailing underscores stripped
- Max 64 characters

Examples: `sigrid_stormborn`, `gunnar_ironside`, `npc_merchant_01`
