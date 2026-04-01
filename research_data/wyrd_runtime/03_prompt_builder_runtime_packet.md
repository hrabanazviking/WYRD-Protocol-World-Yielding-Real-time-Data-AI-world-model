# `ai/prompt_builder.py` runtime packet injection

This patch teaches the prompt builder how to consume the persisted runtime packet without dumping huge raw blobs into the LLM.

The key principle is:

- persist the full packet
- inject only a compact summary into prompt assembly
- optionally surface a few structured fields for extra steering

---

## 1. Extend `GameContext`

Add these fields to the `GameContext` dataclass:

```python
# Runtime packet from SessionManager / engine turn assembly
runtime_packet: Optional[Dict[str, Any]] = None
runtime_packet_summary: str = ""
```

---

## 2. Add a new builder method inside `PromptBuilder`

Put this near the other `build_*` helper methods.

```python
def build_runtime_packet_context(self, context: GameContext) -> str:
    """Inject the latest persisted runtime packet into the live narrator prompt."""
    summary = str(getattr(context, "runtime_packet_summary", "") or "").strip()
    packet = getattr(context, "runtime_packet", None) or {}

    if not summary and not packet:
        return ""

    lines = ["=== LIVE RUNTIME PACKET ==="]

    if summary:
        lines.append(summary)

    if isinstance(packet, dict):
        chaos_story_pressure = packet.get("chaos_story_pressure", {}) or {}
        if isinstance(chaos_story_pressure, dict) and chaos_story_pressure:
            lines.append(
                f"HeatBand={chaos_story_pressure.get('heat_band', 'warm')} | "
                f"Pressure={chaos_story_pressure.get('persistent_pressure', 0)}"
            )

        active_rune = packet.get("active_scene_rune", {}) or {}
        if isinstance(active_rune, dict) and active_rune:
            lines.append(
                f"ActiveSceneRune={active_rune.get('name', 'Unknown')} "
                f"({active_rune.get('symbol', '?')})"
            )

        npc_snapshot = packet.get("npc_scene_snapshot", {}) or {}
        npc_briefs = npc_snapshot.get("npc_briefs", []) if isinstance(npc_snapshot, dict) else []
        if npc_briefs:
            lines.append("NPC Scene Lock:")
            for brief in npc_briefs[:5]:
                if not isinstance(brief, dict):
                    continue
                lines.append(
                    f"- {brief.get('name', 'Unknown')} | "
                    f"role={brief.get('role', 'person')} | "
                    f"emotion={brief.get('emotional_state', 'neutral')} | "
                    f"wearing={brief.get('wearing', 'unspecified garments')}"
                )

    lines.append(
        "Use this packet as the compact truth layer for current continuity, "
        "but do not expose it as meta text in narration."
    )
    return "\n".join(lines)
```

---

## 3. Inject it into `build_narrator_prompt`

Inside `build_narrator_prompt(...)`, after story memory is inserted and before the main scene/person/NPC sections, add:

```python
runtime_packet_block = self.build_runtime_packet_context(context)
if runtime_packet_block:
    sections.extend(
        [
            runtime_packet_block,
            "",
        ]
    )
```

That gives the LLM a compact, structured current-truth layer before the larger narrative context.

---

## 4. Optional: also expose it to character voice prompts

Inside `build_character_voice_prompt(...)`, add this before the final situation block:

```python
if game_context:
    runtime_packet_block = self.build_runtime_packet_context(game_context)
    if runtime_packet_block:
        lines.extend(
            [
                "",
                runtime_packet_block,
            ]
        )
```

That lets individual NPC voice generation inherit the same current-truth packet.

---

## 5. Why this is better than dumping raw history

Your engine already has several memory/context channels:

- `_history`
- enhanced memory
- Muninn subjective recall
- Yggdrasil context
- NPC scene lock
- fate pressure
- chaos pressure

The runtime packet is useful because it gives the LLM a **single current-turn truth digest** instead of forcing it to reconstruct that truth from several scattered inputs each time.

That means:

- less drift
- cleaner continuity
- better replayability
- easier future pruning and scoring

---

## 6. Minimal result

Once this file is patched, `PromptBuilder` can consume:

- latest runtime packet summary
- current heat band
- active scene rune
- NPC scene lock data

without inflating the prompt with the full raw packet body.
