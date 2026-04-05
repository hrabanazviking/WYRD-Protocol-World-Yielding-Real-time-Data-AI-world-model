# WYRD Protocol

**World-Yielding Real-time Data — AI World Model**

---

WYRD Protocol is an ECS-based external AI world model. It moves the World Model **out of the LLM context window** into a deterministic, queryable layer — so AI characters retrieve ground truth instead of hallucinating world state.

```
Without WYRD                      With WYRD
──────────────                    ──────────────
LLM context:                      LLM context:
  • Character backstory           • Character backstory
  • World state (remembered?)     • WyrdContextPacket (current)
  • Inventory (hallucinated?)     • Verified facts
  • Relationships (drifting?)     • Bond graph
  → Inconsistent, drifts          → Grounded, deterministic
```

---

## What It Does

| Layer | What it provides |
|---|---|
| **ECS core** | Entities with typed components (identity, spatial, faction, runic) |
| **Yggdrasil** | Zone → Region → Location → Sub-location spatial hierarchy |
| **Passive Oracle** | 9 ground-truth query types — read-only world reporter |
| **WyrdHTTPServer** | Language-agnostic REST API — any engine POSTs /query |
| **wyrdforge memory** | 6 Norse-named memory stores (Hugin/Munin/Mimir/Wyrd/Orlog/Seidr) |
| **Runic Metaphysics** | Hamingja, RunicCharge, AncestralResonance as ECS components |
| **Bifrost Bridges** | 20+ engine adapters — Unity, Unreal, Godot, Foundry, Roblox, etc. |

---

## Quick Example

```python
# Start the server
# python -m wyrdforge.server --port 8765

import requests

# Query world context for a character
response = requests.post("http://localhost:8765/query", json={
    "persona_id": "sigrid_stormborn",
    "user_input": "What do I know about the approaching army?",
    "use_turn_loop": False,
})
print(response.json()["response"])
# → "The scouts reported 300 warriors crossing the river at dawn. Gunnar saw
#    their banner — the Serpent of Jotunheim. They camp three leagues north."
```

The LLM didn't guess that. WYRD knew it from the ECS world state.

---

## Get Started

→ [Quickstart](guides/quickstart.md) — running WYRD in 5 minutes  
→ [Architecture](guides/architecture.md) — how the pieces fit together  
→ [Integrations](integrations/overview.md) — connect your game engine or AI platform  

---

## License

[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) — RuneForgeAI / Volmarr Wyrd
