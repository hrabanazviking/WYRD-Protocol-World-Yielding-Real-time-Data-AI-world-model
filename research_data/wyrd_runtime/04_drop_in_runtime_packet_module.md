# Optional drop-in module: `systems/runtime_packet_contract.py`

If you want the runtime packet structure centralized instead of leaving it as a raw dict in `engine.py`, use this module.

This is optional, but it gives you a typed schema for later validation, replay tooling, and pruning.

---

## File contents

```python
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class RuntimePacketContract:
    session_id: str = ""
    turn_count: int = 0
    current_location_id: str = ""
    current_sub_location_id: str = ""
    time_of_day: str = ""
    season: str = ""
    year: int = 850
    chaos_factor: int = 30

    player_input: str = ""
    system_prompt: str = ""
    user_prompt: str = ""
    response: str = ""

    continuity_packet: str = ""
    memory_summary: str = ""
    short_term_memory: str = ""
    medium_term_memory: str = ""

    emotion_snapshot: Dict[str, Any] = field(default_factory=dict)
    subjective_memories: List[Dict[str, Any]] = field(default_factory=list)
    active_scene_rune: Dict[str, Any] = field(default_factory=dict)
    active_fate_threads: List[str] = field(default_factory=list)
    fate_pressure: str = ""
    chaos_story_pressure: Dict[str, Any] = field(default_factory=dict)
    turn_event_signals: List[str] = field(default_factory=list)
    npc_scene_snapshot: Dict[str, Any] = field(default_factory=dict)
    active_interaction_attire: Dict[str, Dict[str, str]] = field(default_factory=dict)

    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "RuntimePacketContract":
        if not isinstance(data, dict):
            return cls()
        allowed = {field_name for field_name in cls.__dataclass_fields__.keys()}
        filtered = {k: v for k, v in data.items() if k in allowed}
        return cls(**filtered)
```

---

## Optional engine use

If you adopt this module, change `_build_runtime_packet_payload(...)` in `engine.py` from building a raw dict to:

```python
from systems.runtime_packet_contract import RuntimePacketContract
```

Then:

```python
packet = RuntimePacketContract(
    session_id=getattr(self.state, "session_id", ""),
    turn_count=getattr(self.state, "turn_count", 0),
    current_location_id=getattr(self.state, "current_location_id", ""),
    current_sub_location_id=getattr(self.state, "current_sub_location_id", ""),
    time_of_day=getattr(self.state, "time_of_day", ""),
    season=getattr(self.state, "season", ""),
    year=getattr(self.state, "year", 850),
    chaos_factor=getattr(self.state, "chaos_factor", DEFAULT_CHAOS_FACTOR),
    player_input=str(action or ""),
    system_prompt=str(system_prompt or ""),
    user_prompt=str(user_prompt or ""),
    continuity_packet=continuity_packet,
    memory_summary=self.get_memory_summary(),
    short_term_memory=short_term_memory,
    medium_term_memory=medium_term_memory,
    emotion_snapshot=emotion_snapshot,
    subjective_memories=subjective_memories,
    active_scene_rune=self.get_active_scene_rune() or {},
    active_fate_threads=list(getattr(self.state, "fate_threads", []) or []),
    fate_pressure=fate_pressure,
    chaos_story_pressure=chaos_story_pressure,
    turn_event_signals=turn_event_signals,
    npc_scene_snapshot=npc_scene_snapshot or {},
    active_interaction_attire=dict(getattr(self, "_active_interaction_attire", {}) or {}),
    response=str(response or ""),
)
packet.summary = self._render_runtime_packet_summary(packet.to_dict())
return packet.to_dict()
```

---

## Why this optional module helps

Use it if you want:

- typed packet structure
- future validation rules
- clean replay/export tooling
- easier downstream unit tests

Skip it if you want the lightest possible integration right now.
