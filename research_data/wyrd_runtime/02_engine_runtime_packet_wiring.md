# `core/engine.py` runtime packet wiring

This patch wires the new runtime packet lane into the actual engine flow.

The goal is not to replace your current memory systems. The goal is to add a **stable prompt-assembly snapshot** that sits between:

- continuity building
- memory selection
- prompt construction
- final LLM call
- session persistence

---

## 1. Add this import near the top

```python
import uuid
```

---

## 2. Add these methods inside `YggdrasilEngine`

Put them near the other prompt/memory helper methods, ideally close to:

- `_build_continuity_context_packet`
- `get_memory_summary`
- `_build_prompt_context`

### `_render_runtime_packet_summary`

```python
def _render_runtime_packet_summary(self, packet: Dict[str, Any]) -> str:
    """Render a compact, prompt-safe summary of the current runtime packet."""
    if not isinstance(packet, dict):
        return ""

    lines: List[str] = ["=== LIVE TURN RUNTIME PACKET ==="]

    turn_count = packet.get("turn_count", 0)
    location_id = packet.get("current_sub_location_id", "") or packet.get("current_location_id", "")
    time_of_day = packet.get("time_of_day", "")
    season = packet.get("season", "")
    chaos_factor = packet.get("chaos_factor", DEFAULT_CHAOS_FACTOR)

    lines.append(
        f"Turn={turn_count} | Location={location_id} | Time={time_of_day} | Season={season} | Chaos={chaos_factor}/100"
    )

    emotion = packet.get("emotion_snapshot", {}) or {}
    dominant = emotion.get("dominant_emotion", "neutral")
    intensity = float(emotion.get("dominant_value", 0.0) or 0.0)
    rune = emotion.get("rune", "") or "none"
    lines.append(f"Emotion={dominant} ({intensity:.2f}) | Rune={rune}")

    fate_threads = packet.get("active_fate_threads", []) or []
    if fate_threads:
        lines.append("FateThreads=" + "; ".join([str(item)[:120] for item in fate_threads[:4]]))

    event_signals = packet.get("turn_event_signals", []) or []
    if event_signals:
        lines.append("Signals=" + " | ".join([str(item)[:140] for item in event_signals[:4]]))

    npc_snapshot = packet.get("npc_scene_snapshot", {}) or {}
    npc_briefs = npc_snapshot.get("npc_briefs", []) if isinstance(npc_snapshot, dict) else []
    if npc_briefs:
        npc_lines = []
        for brief in npc_briefs[:5]:
            if not isinstance(brief, dict):
                continue
            npc_lines.append(
                f"{brief.get('name', 'Unknown')}:{brief.get('emotional_state', 'neutral')}:{brief.get('role', 'person')}"
            )
        if npc_lines:
            lines.append("NPCs=" + " | ".join(npc_lines))

    subjective = packet.get("subjective_memories", []) or []
    if subjective:
        memory_lines = []
        for item in subjective[:3]:
            if not isinstance(item, dict):
                continue
            payload = item.get("data", {}) if isinstance(item.get("data", {}), dict) else {}
            event = payload.get("event", {}) if isinstance(payload, dict) else {}
            emo_ctx = payload.get("emotional_context", {}) if isinstance(payload, dict) else {}
            memory_lines.append(
                f"{event.get('event_type', 'memory')}:{emo_ctx.get('dominant_emotion', 'neutral')}"
            )
        if memory_lines:
            lines.append("Subjective=" + " | ".join(memory_lines))

    return "\n".join(lines)
```

### `_build_runtime_packet_payload`

```python
def _build_runtime_packet_payload(
    self,
    *,
    action: str,
    system_prompt: str = "",
    user_prompt: str = "",
    response: str = "",
    npc_scene_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Assemble the structured runtime packet used for persistence + prompt reuse."""
    continuity_packet = self._turn_continuity_cache or self._build_continuity_context_packet(max_items=200)
    emotion_snapshot = self._get_emotional_snapshot()
    subjective_memories = self._get_subjective_memories_for_current_state(action=action, limit=6)
    chaos_story_pressure = self._get_chaos_story_pressure()
    fate_pressure = self._build_fate_prompt_payload(action=action, response=response)
    turn_event_signals = self._collect_turn_event_signals(action=action, response=response)

    short_term_memory = ""
    medium_term_memory = ""
    if self.enhanced_memory:
        try:
            short_term_memory = self.enhanced_memory.get_short_term_context_for_ai(max_items=10)
            medium_term_memory = self.enhanced_memory.get_medium_term_context_for_ai(max_items=14)
        except Exception as exc:
            logger.warning("Runtime packet memory pull skipped: %s", exc)

    packet: Dict[str, Any] = {
        "session_id": getattr(self.state, "session_id", ""),
        "turn_count": getattr(self.state, "turn_count", 0),
        "current_location_id": getattr(self.state, "current_location_id", ""),
        "current_sub_location_id": getattr(self.state, "current_sub_location_id", ""),
        "time_of_day": getattr(self.state, "time_of_day", ""),
        "season": getattr(self.state, "season", ""),
        "year": getattr(self.state, "year", 850),
        "chaos_factor": getattr(self.state, "chaos_factor", DEFAULT_CHAOS_FACTOR),
        "player_input": str(action or ""),
        "system_prompt": str(system_prompt or ""),
        "user_prompt": str(user_prompt or ""),
        "continuity_packet": continuity_packet,
        "memory_summary": self.get_memory_summary(),
        "short_term_memory": short_term_memory,
        "medium_term_memory": medium_term_memory,
        "emotion_snapshot": emotion_snapshot,
        "subjective_memories": subjective_memories,
        "active_scene_rune": self.get_active_scene_rune() or {},
        "active_fate_threads": list(getattr(self.state, "fate_threads", []) or []),
        "fate_pressure": fate_pressure,
        "chaos_story_pressure": chaos_story_pressure,
        "turn_event_signals": turn_event_signals,
        "npc_scene_snapshot": npc_scene_snapshot or {},
        "active_interaction_attire": dict(getattr(self, "_active_interaction_attire", {}) or {}),
        "response": str(response or ""),
    }

    packet["summary"] = self._render_runtime_packet_summary(packet)
    return packet
```

### `_persist_runtime_packet`

```python
def _persist_runtime_packet(
    self,
    *,
    stage: str,
    packet: Dict[str, Any],
) -> str:
    """Persist one runtime packet to SessionManager."""
    if not self.session_manager:
        return ""

    packet_id = f"runtime_{self.state.turn_count}_{uuid.uuid4().hex[:10]}"
    try:
        self.session_manager.record_runtime_packet(
            packet_id=packet_id,
            turn_count=int(packet.get("turn_count", 0) or 0),
            stage=str(stage or "pre_llm"),
            player_input=str(packet.get("player_input", "") or ""),
            system_prompt=str(packet.get("system_prompt", "") or ""),
            user_prompt=str(packet.get("user_prompt", "") or ""),
            continuity_packet=str(packet.get("continuity_packet", "") or ""),
            memory_summary=str(packet.get("memory_summary", "") or ""),
            runtime_packet_summary=str(packet.get("summary", "") or ""),
            packet=packet,
            ai_response=str(packet.get("response", "") or ""),
        )
        return packet_id
    except Exception as exc:
        logger.warning("Runtime packet persistence skipped: %s", exc)
        return ""
```

### `_update_persisted_runtime_packet_response`

```python
def _update_persisted_runtime_packet_response(
    self,
    packet_id: str,
    response: str,
    stage: str = "post_llm",
) -> None:
    """Update a persisted packet with the final narrator response."""
    if not self.session_manager or not packet_id:
        return
    try:
        self.session_manager.update_runtime_packet_response(
            packet_id=packet_id,
            ai_response=response,
            stage=stage,
        )
    except Exception as exc:
        logger.warning("Runtime packet response update skipped: %s", exc)
```

### `_get_runtime_packet_prompt_summary`

```python
def _get_runtime_packet_prompt_summary(self, limit: int = 1) -> str:
    """Return compact prior runtime packet summaries for prompt injection."""
    if not self.session_manager:
        return ""

    try:
        summaries = self.session_manager.get_recent_runtime_packet_summaries(limit=limit)
        return "\n\n".join([item for item in summaries if str(item).strip()])
    except Exception as exc:
        logger.warning("Runtime packet prompt summary skipped: %s", exc)
        return ""
```

---

## 3. Persist the packet before the LLM call in `process_action`

In the `else:` branch where the engine builds `system_prompt` and `prompt`, add this block **just before**:

```python
response = self._ai_complete(
    prompt=prompt,
    system_prompt=system_prompt,
)
```

### Insert this

```python
runtime_packet_payload = self._build_runtime_packet_payload(
    action=action,
    system_prompt=system_prompt,
    user_prompt=prompt,
    response="",
    npc_scene_snapshot=npc_scene_snapshot,
)
runtime_packet_id = self._persist_runtime_packet(
    stage="pre_llm",
    packet=runtime_packet_payload,
)
```

Then immediately after the `_ai_complete(...)` returns, add:

```python
self._update_persisted_runtime_packet_response(
    runtime_packet_id,
    response,
    stage="post_llm",
)
```

---

## 4. Do the same in the deep-integration path

Inside the `if self._deep_integration:` branch, add a parallel packet build/persist call before `process_action(...)`, then update it after `response` is finalized.

### Example

```python
runtime_packet_payload = self._build_runtime_packet_payload(
    action=action,
    system_prompt="deep_integration",
    user_prompt=prompt_payload,
    response="",
    npc_scene_snapshot=npc_scene_snapshot,
)
runtime_packet_id = self._persist_runtime_packet(
    stage="pre_llm",
    packet=runtime_packet_payload,
)

response = self._deep_integration.process_action(
    action=action,
    game_state=context,
    characters_present=self.state.npcs_present,
)

self._update_persisted_runtime_packet_response(
    runtime_packet_id,
    response,
    stage="post_llm",
)
```

---

## 5. Inject runtime packet info into `_build_prompt_context`

Inside `_build_prompt_context`, before the `return GameContext(...)`, add:

```python
runtime_packet = {}
runtime_packet_summary = ""
if self.session_manager:
    try:
        runtime_packet = self.session_manager.get_latest_runtime_packet_dict()
        runtime_packet_summary = self._get_runtime_packet_prompt_summary(limit=1)
    except Exception as exc:
        logger.warning("Runtime packet context pull skipped: %s", exc)
```

Then add these fields to the `GameContext(...)` constructor:

```python
runtime_packet=runtime_packet,
runtime_packet_summary=runtime_packet_summary,
```

---

## 6. Why this works cleanly in your engine

This patch fits the current architecture because `engine.py` already has the pieces you need:

- continuity packet generation
- memory summary generation
- subjective memory recall
- NPC scene snapshots
- fate/chaos pressure builders
- `SessionManager` already attached and saved during play

So this is not a second memory system. It is a **durable turn-assembly seam**.

---

## 7. Result

After this patch, each turn gets:

- one structured runtime packet before generation
- one updated packet after final narration
- compact summary ready for prompt reuse
- replayable data for future test harnesses and audit systems
