# HTTP API Reference

WyrdHTTPServer exposes a JSON REST API on `http://localhost:8765` by default.

## POST /query

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

## POST /event

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

## GET /world

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

## GET /facts

Returns canonical facts for a subject.

```
GET /facts?subject_id=sigrid
```

```json
[
  {"subject_id": "sigrid", "key": "name",     "value": "Sigrid Stormborn"},
  {"subject_id": "sigrid", "key": "role",     "value": "völva"},
  {"subject_id": "sigrid", "key": "location", "value": "great_hall"}
]
```

---

## GET /health

Health check endpoint.

```json
{"status": "ok", "version": "1.0.0"}
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
