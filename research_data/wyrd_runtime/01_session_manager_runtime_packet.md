# `session/session_manager.py` runtime packet patch

This patch adds a durable runtime packet lane to the existing session persistence system.

## Why this belongs here

`SessionManager` already persists:

- character changes
- quest progress
- world state
- conversation history

A runtime packet is the missing bridge for **prompt assembly state** that you want to survive save/load and be available for replay, audit, and future summarization.

---

## 1. Add this dataclass block near the other session dataclasses

```python
@dataclass
class RuntimePacketRecord:
    """Durable snapshot of one turn's runtime packet."""

    packet_id: str
    turn_count: int
    stage: str = "pre_llm"  # pre_llm | post_llm | rewritten
    player_input: str = ""
    system_prompt: str = ""
    user_prompt: str = ""
    continuity_packet: str = ""
    memory_summary: str = ""
    runtime_packet_summary: str = ""
    packet: Dict = field(default_factory=dict)
    ai_response: str = ""
    created_at: str = ""
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "RuntimePacketRecord":
        return cls(**data)
```

---

## 2. Add these fields in `SessionManager.__init__`

```python
# Runtime packet persistence
self.runtime_packets: List[RuntimePacketRecord] = []
self.max_runtime_packets: int = 64
```

---

## 3. Save runtime packets in `save()`

Add this block after the existing `conversation_history.json` write:

```python
# Save runtime packet records
runtime_packet_data = [packet.to_dict() for packet in self.runtime_packets[-self.max_runtime_packets:]]
async with aiofiles.open(self.session_path / "runtime_packets.yaml", 'w', encoding='utf-8') as f:
    await f.write(yaml.safe_dump(runtime_packet_data, default_flow_style=False, sort_keys=False))
```

---

## 4. Load runtime packets in `load()`

Add this block after conversation history is loaded:

```python
runtime_packets_path = self.session_path / "runtime_packets.yaml"
self.runtime_packets = []
if runtime_packets_path.exists():
    async with aiofiles.open(runtime_packets_path, 'r', encoding='utf-8') as f:
        content = await f.read()
        packet_data = yaml.safe_load(content) or []

    if isinstance(packet_data, list):
        self.runtime_packets = [
            RuntimePacketRecord.from_dict(item)
            for item in packet_data
            if isinstance(item, dict)
        ]
```

---

## 5. Add these helper methods to `SessionManager`

```python
def record_runtime_packet(
    self,
    *,
    packet_id: str,
    turn_count: int,
    stage: str,
    player_input: str,
    system_prompt: str,
    user_prompt: str,
    continuity_packet: str,
    memory_summary: str,
    runtime_packet_summary: str,
    packet: Dict,
    ai_response: str = "",
) -> RuntimePacketRecord:
    """Persist a runtime packet for later replay, audit, and prompt reuse."""
    record = RuntimePacketRecord(
        packet_id=packet_id,
        turn_count=int(turn_count or 0),
        stage=str(stage or "pre_llm"),
        player_input=str(player_input or ""),
        system_prompt=str(system_prompt or ""),
        user_prompt=str(user_prompt or ""),
        continuity_packet=str(continuity_packet or ""),
        memory_summary=str(memory_summary or ""),
        runtime_packet_summary=str(runtime_packet_summary or ""),
        packet=packet if isinstance(packet, dict) else {},
        ai_response=str(ai_response or ""),
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
    )
    self.runtime_packets.append(record)
    self.runtime_packets = self.runtime_packets[-self.max_runtime_packets:]
    self.save_sync()
    return record


def update_runtime_packet_response(
    self,
    packet_id: str,
    ai_response: str,
    stage: Optional[str] = None,
) -> bool:
    """Update the final response for an already-recorded packet."""
    for packet in reversed(self.runtime_packets):
        if packet.packet_id == packet_id:
            packet.ai_response = str(ai_response or "")
            if stage:
                packet.stage = str(stage)
            packet.updated_at = datetime.now().isoformat()
            self.save_sync()
            return True
    return False


def get_latest_runtime_packet(
    self,
    stage: Optional[str] = None,
) -> Optional[RuntimePacketRecord]:
    """Return the most recent runtime packet, optionally filtered by stage."""
    for packet in reversed(self.runtime_packets):
        if stage is None or packet.stage == stage:
            return packet
    return None


def get_recent_runtime_packet_summaries(self, limit: int = 3) -> List[str]:
    """Return compact summaries for prompt assembly."""
    results: List[str] = []
    for packet in reversed(self.runtime_packets[-max(1, limit):]):
        summary = str(packet.runtime_packet_summary or "").strip()
        if summary:
            results.append(summary)
    return list(reversed(results))


def get_latest_runtime_packet_dict(self) -> Dict:
    """Convenience accessor for prompt assembly."""
    latest = self.get_latest_runtime_packet()
    return latest.packet if latest else {}
```

---

## 6. Result

After this patch, every turn can persist a compact runtime packet with:

- pre-LLM context
- post-LLM response
- continuity packet
- memory summary
- prompt-facing summary
- arbitrary structured packet data

That gives you a clean persistence seam for later evolution into:

- turn replay
- regression testing
- verification layers
- smart pruning
- packet scoring
