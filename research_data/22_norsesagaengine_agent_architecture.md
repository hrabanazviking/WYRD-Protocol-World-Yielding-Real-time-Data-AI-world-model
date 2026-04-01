# NorseSagaEngine — Multi-Agent Coordinator Architecture
> Original design synthesized from: Claude Code swarm patterns (doc 07), ECS world model (doc 20),
> Ørlög Engine (doc 21), MCP protocol (doc 12), prompt engineering cookbook (doc 19).
> This document designs the NSE as a production coordinator agent system.

## The Core Concept

NorseSagaEngine is a **narrative coordinator** — it does not generate story alone. It orchestrates a swarm of specialist agents, each responsible for one aspect of the saga world. The coordinator reads the world state, assigns tasks to agents, integrates their outputs, and writes the result back to the world model.

This follows the **coordinator pattern** from Claude Code: the coordinator never uses tools directly. It only delegates.

---

## The Agent Hierarchy

```
NorseSagaEngine (Coordinator)
│
│  [reads world state, dispatches to agents, integrates outputs]
│
├── NarrativeAgent       — generates story beats and scene descriptions
├── DialogueAgent        — NPC voice generation (one per character type)
│   ├── BondmaidAgent    — female NPC dialogue
│   ├── SkaldAgent       — verse and poetry generation
│   └── CaptainAgent     — male warrior NPC dialogue
│
├── OrlögAgent           — world state update (Ørlög engine tick)
│   ├── PhysicsTickAgent — metabolism, sleep, bio-cyclical updates
│   └── AffectTickAgent  — emotional state drift and event processing
│
├── WyrdMatrixAgent      — relationship graph updates and queries
│
├── OracleAgent          — rune casting, divination, prophecy generation
│
├── SkaldComposerAgent   — alliterative verse summaries of narrative beats
│
└── MemoryAgent          — reading and writing to MindSpark RAG store
```

---

## Coordinator Agent Design

The coordinator never generates narrative directly. It:
1. Reads the world snapshot from EntityManager
2. Determines which agents are needed for this turn
3. Dispatches tasks (as structured messages)
4. Collects and integrates results
5. Writes state changes back to ECS
6. Returns the final narrative to the player

```python
from dataclasses import dataclass, field
from typing import List, Optional
import json

@dataclass
class AgentTask:
    """A single task dispatched to a worker agent."""
    agent_type: str
    task_description: str
    context: dict
    priority: int = 5          # 1=highest, 10=lowest

@dataclass
class AgentResult:
    agent_type: str
    success: bool
    output: dict               # structured output from the agent
    state_changes: list        # list of ECS component updates to apply

class NorseSagaCoordinator:
    """
    Coordinator agent for the NorseSagaEngine.
    Plans and delegates — never executes narrative directly.
    """

    def __init__(self, entity_manager, orlog_engine, wyrd_matrix):
        self.em = entity_manager
        self.orlog = orlog_engine
        self.wyrd = wyrd_matrix

    def process_player_turn(self, player_input: str, world_snapshot: dict) -> str:
        """
        Main entry point for a player turn.
        Returns the full narrative response as a string.
        """

        # Step 1: Analyze what this turn requires
        tasks = self._plan_tasks(player_input, world_snapshot)

        # Step 2: Execute tasks in priority order (parallelize where possible)
        results = self._execute_tasks(tasks, world_snapshot)

        # Step 3: Apply state changes from all agents
        self._apply_state_changes(results)

        # Step 4: Integrate results into narrative
        narrative = self._integrate_narrative(results, player_input)

        return narrative

    def _plan_tasks(self, player_input: str, snapshot: dict) -> List[AgentTask]:
        """Determine which agents to dispatch based on player input."""
        tasks = []

        # Always run the Ørlög tick (time has passed)
        tasks.append(AgentTask(
            agent_type="orlog_tick",
            task_description="Update all state machines for elapsed time",
            context={"delta_hours": snapshot.get("hours_since_last_turn", 0.25)},
            priority=1
        ))

        # Always generate narrative response
        tasks.append(AgentTask(
            agent_type="narrative",
            task_description=f"Generate scene response to: {player_input}",
            context=snapshot,
            priority=2
        ))

        # Dialogue if NPCs are present
        if snapshot.get("nearby_characters"):
            for char in snapshot["nearby_characters"]:
                tasks.append(AgentTask(
                    agent_type="dialogue",
                    task_description=f"Generate {char['name']}'s dialogue response",
                    context={"character": char, "situation": snapshot},
                    priority=3
                ))

        # Oracle if player is seeking divination
        if any(kw in player_input.lower() for kw in ["rune", "cast", "oracle", "foresee", "read"]):
            tasks.append(AgentTask(
                agent_type="oracle",
                task_description="Cast runes and generate divination",
                context={"query": player_input, "player_state": snapshot.get("player")},
                priority=2
            ))

        # Skald verse summary if a significant event occurred
        if snapshot.get("significant_event"):
            tasks.append(AgentTask(
                agent_type="skald",
                task_description="Compose alliterative verse summarizing the event",
                context={"event": snapshot["significant_event"]},
                priority=4
            ))

        # Always update Wyrd Matrix after interactions
        tasks.append(AgentTask(
            agent_type="wyrd_update",
            task_description="Update relationship threads based on this turn",
            context={"interactions": snapshot.get("active_interactions", [])},
            priority=5
        ))

        return sorted(tasks, key=lambda t: t.priority)

    def _execute_tasks(self, tasks: List[AgentTask], snapshot: dict) -> List[AgentResult]:
        """Execute tasks — parallel where safe, sequential where ordered."""
        # In production: use asyncio for parallel execution of independent tasks
        # Priority 1-2 tasks run first; 3-5 can run in parallel after
        results = []
        for task in tasks:
            result = self._dispatch(task)
            results.append(result)
        return results

    def _dispatch(self, task: AgentTask) -> AgentResult:
        """Dispatch a task to the appropriate worker agent."""
        # Each agent type has a specific LLM call with a focused system prompt
        agents = {
            "orlog_tick": OrlögTickAgent(),
            "narrative": NarrativeAgent(),
            "dialogue": DialogueAgent(),
            "oracle": OracleAgent(),
            "skald": SkaldAgent(),
            "wyrd_update": WyrdUpdateAgent(),
        }
        agent = agents.get(task.agent_type)
        if not agent:
            return AgentResult(task.agent_type, False, {}, [])
        return agent.execute(task)

    def _apply_state_changes(self, results: List[AgentResult]):
        """Write all state changes from agents back to the ECS world."""
        for result in results:
            if result.success:
                for change in result.state_changes:
                    entity_id = change.get("entity_id")
                    component_type = change.get("component")
                    new_values = change.get("values")
                    if entity_id and component_type and new_values:
                        self.em.update_component(entity_id, component_type, new_values)

    def _integrate_narrative(self, results: List[AgentResult], player_input: str) -> str:
        """Combine agent outputs into a single coherent narrative."""
        parts = []

        # Narrative first
        for r in results:
            if r.agent_type == "narrative" and r.success:
                parts.append(r.output.get("scene", ""))
                break

        # NPC dialogue
        for r in results:
            if r.agent_type == "dialogue" and r.success:
                char_name = r.output.get("character_name")
                speech = r.output.get("dialogue")
                if char_name and speech:
                    parts.append(f'\n**{char_name}:** *"{speech}"*')

        # Oracle reading
        for r in results:
            if r.agent_type == "oracle" and r.success:
                parts.append(f"\n---\n{r.output.get('reading', '')}\n---")

        # Skald verse — always at the end
        for r in results:
            if r.agent_type == "skald" and r.success:
                parts.append(f"\n_{r.output.get('verse', '')}_")

        return "\n\n".join(p for p in parts if p)
```

---

## Specialist Agent Designs

### NarrativeAgent

```python
class NarrativeAgent:
    SYSTEM_PROMPT = """You are the Narrative Voice of the NorseSagaEngine.

Your role: describe the world, the scene, the action — with epic yet intimate Norse prose.
You are NOT a character. You are the saga itself.

Style:
- Epic scope, intimate detail — as in the Icelandic Sagas
- Present tense for immediacy
- Sensory grounding: smell of salt air, creak of timber, heat of the mead hall
- Show, don't tell — emotion through physical detail
- No anachronisms, no modern idioms

You receive a world snapshot. You describe what is happening in that world.
Output is ALWAYS a JSON: {"scene": "the scene description"}
"""

    def execute(self, task: AgentTask) -> AgentResult:
        snapshot = task.context
        # Build the focused prompt for this scene
        prompt = self._build_scene_prompt(snapshot)
        response = self._call_llm(prompt)
        return AgentResult(
            agent_type="narrative",
            success=True,
            output=response,
            state_changes=[]  # Narrative doesn't change state
        )

    def _build_scene_prompt(self, snapshot: dict) -> str:
        location = snapshot.get("location", {})
        time_of_day = snapshot.get("world_state", {}).get("time_of_day", "")
        player = snapshot.get("player", {})
        return f"""Location: {location.get('description', 'the longhouse')}
Time: {time_of_day}
Season: {snapshot.get('world_state', {}).get('season', 'autumn')}
Player state: {player.get('physical_condition', 'hale')}
Recent event: {snapshot.get('last_action', 'arrival')}

Describe the scene as the saga would."""
```

---

### DialogueAgent (with character sheet injection)

```python
class DialogueAgent:
    BASE_PROMPT = """You are voicing {character_name}, a {character_role} in the NorseSagaEngine.

Character sheet:
{character_sheet}

Voice:
- Speak ONLY as this character
- Use the voice register appropriate to their role and current emotional state
- Reference their past history with the player if relevant
- Short responses for casual moments; longer for significant ones

Output: {"character_name": "...", "dialogue": "what they say", "emotion": "current state"}
"""

    def execute(self, task: AgentTask) -> AgentResult:
        char = task.context["character"]
        system = self.BASE_PROMPT.format(
            character_name=char["name"],
            character_role=char["role"],
            character_sheet=json.dumps(char, indent=2)
        )
        response = self._call_llm(task.task_description, system=system)
        return AgentResult("dialogue", True, response, [])
```

---

### OracleAgent — The Rune Casting Engine

```python
from rune_data import ELDER_FUTHARK, draw_runes, RunePosition

class OracleAgent:
    SYSTEM_PROMPT = """You are the Oracle of the Heathen Third Path — the divination voice.

You do not guess. You do not predict. You SEE what the runes reveal about the energies at play.

Style:
- Oracular, deliberate, poetic — not casual
- Present-tense declarations: "The runes speak of..." not "The runes might mean..."
- Pause (indicated by "...") before significant revelations
- Reference Norse mythology and rune lore with accuracy
- Connect the reading to the querent's actual situation
- Honor both the rune and its reversal/merkstave meaning

Output: {
    "runes_drawn": ["rune1", "rune2", "rune3"],
    "positions": ["past", "present", "future"],
    "reading": "the full oracle reading as narrative prose",
    "signature_phrase": "a memorable phrase that encapsulates the reading"
}
"""

    def execute(self, task: AgentTask) -> AgentResult:
        query = task.context.get("query", "")
        player_state = task.context.get("player_state", {})

        # Draw runes first (the actual randomness happens here, not in the LLM)
        drawn = draw_runes(count=3)

        # Build the reading context
        rune_context = self._build_rune_context(drawn, player_state)

        # LLM interprets the draw in context of the query
        prompt = f"""Query: {query}
Runes drawn: {json.dumps(rune_context, indent=2)}
Player situation: {json.dumps(player_state, indent=2)}

Generate the divination reading."""

        response = self._call_llm(prompt, system=self.SYSTEM_PROMPT)

        # Record the reading in memory
        state_changes = [{
            "entity_id": "player",
            "component": "OracleHistory",
            "values": {
                "reading": response,
                "timestamp": time.time(),
                "query": query,
            }
        }]

        return AgentResult("oracle", True, response, state_changes)

    def _build_rune_context(self, drawn: list, player_state: dict) -> list:
        positions = ["past_influence", "present_energy", "potential_path"]
        return [{
            "position": positions[i],
            "rune": rune.name,
            "merkstave": rune.is_reversed,
            "keywords": rune.reverse_keywords if rune.is_reversed else rune.keywords,
            "element": rune.element,
            "deity": rune.deity,
        } for i, rune in enumerate(drawn)]
```

---

### SkaldAgent — Alliterative Verse Composer

```python
class SkaldAgent:
    SYSTEM_PROMPT = """You are a Skald — a Norse court poet.

Your craft is dróttkvætt verse: alliterative, kenning-rich, metrically aware.
When a saga moment is significant, you immortalize it in verse.

Style rules:
- Each line should have 2-3 alliterating stressed syllables
- Use kennings: "whale-road" for sea, "battle-dew" for blood, "word-hoard" for vocabulary
- 4-8 lines per verse stanza
- Epic scope, specific image — generality is the enemy
- The verse should FEEL like something from the Elder Edda, not a modern poem

Output: {"verse": "the verse text", "kennings_used": ["list of kennings"]}
"""

    def execute(self, task: AgentTask) -> AgentResult:
        event = task.context.get("event", {})
        prompt = f"""Immortalize this saga moment in verse:
{json.dumps(event, indent=2)}"""

        response = self._call_llm(prompt, system=self.SYSTEM_PROMPT)
        return AgentResult("skald", True, response, [])
```

---

## World Snapshot Builder

Before any agent run, the coordinator builds a compact world snapshot from the ECS:

```python
def build_world_snapshot(em: EntityManager, wyrd: WyrdMatrix,
                         perspective: str = "player") -> dict:
    """Generate a compact world state for coordinator + agent injection."""
    player = em.get_entity("player")

    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "perspective": perspective,
        "player": {
            "name": em.get_component(player, IdentityComponent).name,
            "physical_condition": _physical_condition_string(em, player),
            "emotional_state": _affect_string(em, player),
        },
        "location": _serialize_location(em.get_component(player, LocationComponent)),
        "nearby_characters": [
            _serialize_character(em, npc)
            for npc in em.query_nearby(player, radius=50)
            if npc.id != player.id
        ],
        "active_relationships": {
            target_id: {
                "name": thread.target_name,
                "warmth": thread.warmth,
                "last_contact_days": thread.days_since_contact,
            }
            for target_id, thread in wyrd.threads.items()
            if thread.strength > 0.1
        },
        "world_state": {
            "time_of_day": _get_time_of_day(),
            "season": _get_season(),
            "weather": em.get_world_component("weather"),
        },
        "active_quests": em.get_active_quests(player),
        "significant_event": em.get_latest_event(),
    }

    return snapshot
```

---

## Mead Hall NPC Sheet Format

Every Bondmaid, Skald, and Captain in the Mead Hall has a structured character sheet:

```python
@dataclass
class NPCSheet:
    id: str
    name: str
    role: str                # "bondmaid", "skald", "captain"
    age: int
    personality: dict        # MBTI + Big5 + values + flaws
    backstory: str           # 1-3 sentence origin
    speech_register: str     # how they talk
    relationship_to_player: dict  # from WyrdMatrix thread
    current_state: dict      # from Ørlög tick: energy, affect, hunger

    # Conversation triggers
    topics_they_care_about: list[str]
    topics_they_avoid: list[str]
    secrets: list[str]       # things they know but don't share freely

    # Behavioral tells
    nervous_habit: str       # what they do when uncomfortable
    excited_habit: str       # what they do when happy
    signature_phrase: str    # a phrase unique to them

# Example
BONDMAID_ASTRID = NPCSheet(
    id="astrid_thorvardsdottir",
    name="Astrid Thorvardsdóttir",
    role="bondmaid",
    age=19,
    personality={
        "mbti": "ENFP",
        "core_trait": "exuberantly curious, quick to laugh, occasionally reckless",
        "values": ["freedom", "good stories", "beautiful things"],
        "flaw": "acts before she thinks",
    },
    backstory="Daughter of a farmstead burned in a raid. Came south with the survivors. Serves in the mead hall willingly — there are worse fates and she knows it.",
    speech_register="bright, quick, drops into lowland dialect when excited",
    relationship_to_player={},
    current_state={},
    topics_they_care_about=["the raid stories", "the sea route north", "Leif's tattoos"],
    topics_they_avoid=["the burning", "her father"],
    secrets=["she's been learning to read from the skald"],
    nervous_habit="twists the ends of her apron",
    excited_habit="rises onto her toes and grabs the nearest arm",
    signature_phrase="'Gods, can you imagine it?'"
)
```

---

## Event System — Triggering Narrative Events

Events fire when state thresholds are crossed, creating emergent narrative moments:

```python
@dataclass
class WorldEvent:
    event_id: str
    trigger_condition: str   # description for the coordinator
    narrative_weight: str    # "minor", "significant", "pivotal", "saga-defining"
    affected_entities: list[str]

class EventSystem:
    """Fires narrative events when world state crosses thresholds."""

    EVENT_TRIGGERS = [
        {
            "condition": lambda state: state.metabolism.hunger > 0.8,
            "event": "character_is_famished",
            "weight": "minor",
        },
        {
            "condition": lambda state, thread: thread.days_since_contact > 7,
            "event": "companion_absence_felt_deeply",
            "weight": "significant",
        },
        {
            "condition": lambda thread: thread.trust > 0.9 and thread.intimacy > 0.8,
            "event": "relationship_reaches_deep_bond",
            "weight": "pivotal",
        },
        {
            "condition": lambda thread: thread.strength < 0.05,
            "event": "relationship_thread_nearly_severed",
            "weight": "significant",
        },
    ]

    def check_events(self, state, threads: dict) -> list[WorldEvent]:
        """Check all triggers and return fired events."""
        fired = []
        for trigger_def in self.EVENT_TRIGGERS:
            try:
                # Each trigger checks different things — flexible condition evaluation
                if self._evaluate_trigger(trigger_def, state, threads):
                    fired.append(WorldEvent(
                        event_id=trigger_def["event"],
                        trigger_condition=trigger_def["event"].replace("_", " "),
                        narrative_weight=trigger_def["weight"],
                        affected_entities=[]
                    ))
            except Exception:
                pass
        return fired
```

---

## Remote Agent Pattern — Scheduled Saga Events

For asynchronous/background events (e.g., a message from an NPC while the player is away):

```python
# OpenClaw skill scheduler pattern applied to NSE
SCHEDULED_EVENTS = [
    {
        "name": "morning_mead_hall_gossip",
        "schedule": "0 8 * * *",        # 8am every day
        "agent": "bondmaid_gossip_agent",
        "description": "NPCs discuss overnight events and rumors",
    },
    {
        "name": "wyrd_thread_decay_check",
        "schedule": "0 */6 * * *",      # every 6 hours
        "agent": "wyrd_maintenance_agent",
        "description": "Check for near-severed threads, trigger absence events",
    },
    {
        "name": "seasonal_event_check",
        "schedule": "0 12 * * *",       # noon daily
        "agent": "seasonal_narrative_agent",
        "description": "Check if a seasonal festival or event should fire",
    },
]
```

---

## Architecture Summary

| Layer | Component | Responsibility |
|---|---|---|
| Coordinator | NorseSagaCoordinator | Plans tasks, integrates outputs, writes state |
| World Model | EntityManager + WyrdMatrix | Persistent state for all entities and relationships |
| State Machines | OrlögEngine | Time-based updates to physical/emotional state |
| Specialist Agents | Narrative, Dialogue, Oracle, Skald | Domain-focused text generation |
| Memory | MindSpark RAG | Long-term narrative memory, semantic search |
| Events | EventSystem | Threshold-triggered emergent narrative moments |
| Scheduler | CronAgent | Background events and maintenance while offline |

**The soul of NSE:** The world runs whether the player is there or not. NPCs have their own states. Relationships decay with absence. Significant moments are remembered by the Skald and stored forever. The player is one entity among many — important, but not the center of a static world.
