# WYRD Protocol — Entity-Component-System World Model Architecture
> Based on: github.com/hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model
> Cross-referenced with NorseSagaEngine architecture and Claude Code's agent patterns.

## What is the WYRD Protocol?

**World-Yielding Real-time Data** — a world model architecture that moves the "world state" out of an LLM's fleeting context window and into a **structured Entity-Component-System (ECS)**.

The core insight: LLMs are stateless. Every conversation starts fresh. To maintain a persistent, evolving world (for an RPG, for a companion AI, for a simulation), you need **external state** that the model can read and write — not try to remember.

---

## Why ECS for AI World Modeling?

Traditional ECS (used in game engines like Unity/Bevy) organizes the world as:
- **Entities** — unique IDs with no data of their own
- **Components** — pure data attached to entities
- **Systems** — logic that processes entities with specific components

For AI:
| Game ECS | AI World Model |
|---|---|
| Entity (Player ID) | Entity (Sigrid, Volmarr, NPC) |
| Component (Position, Health) | Component (EmotionalState, RelationshipScore, Inventory) |
| System (Movement, Physics) | System (Ørlög tick, WyrdMatrix update, Oracle reasoning) |

The LLM becomes just another **System** — it reads components, generates text, and writes components back. It's not responsible for remembering anything.

---

## Entity Model

```python
from dataclasses import dataclass, field
from typing import Any, Dict, Type, TypeVar
from uuid import UUID, uuid4

@dataclass
class Entity:
    id: UUID = field(default_factory=uuid4)
    name: str = ""
    tags: set[str] = field(default_factory=set)

# Entity registry
class EntityManager:
    def __init__(self):
        self._entities: Dict[UUID, Entity] = {}
        self._components: Dict[UUID, Dict[type, Any]] = {}

    def create(self, name: str, **tags) -> Entity:
        entity = Entity(name=name, tags=set(tags))
        self._entities[entity.id] = entity
        self._components[entity.id] = {}
        return entity

    def add_component(self, entity: Entity, component: Any):
        self._components[entity.id][type(component)] = component

    def get_component(self, entity: Entity, component_type: type) -> Any:
        return self._components[entity.id].get(component_type)

    def query(self, *component_types: type) -> list[Entity]:
        """Get all entities that have all specified components."""
        results = []
        for entity_id, components in self._components.items():
            if all(ct in components for ct in component_types):
                results.append(self._entities[entity_id])
        return results
```

---

## Component Definitions for Viking AI World

```python
# Identity Components
@dataclass
class IdentityComponent:
    name: str
    title: str
    age: int
    gender: str
    race: str          # human, jotun, alfar, etc.
    lineage: str       # family/clan name

@dataclass
class PersonalityComponent:
    mbti: str                    # e.g. "INTP"
    big5: dict[str, float]       # openness, conscientiousness, etc.
    values: list[str]            # core values
    flaws: list[str]             # character flaws (for authentic conflict)
    quirks: list[str]            # behavioral quirks

# Emotional Components
@dataclass
class AffectComponent:
    valence: float = 0.0         # -1 to +1
    arousal: float = 0.5         # 0 to 1
    dominance: float = 0.5       # 0 to 1 (PAD model)
    last_updated: float = 0.0    # timestamp

@dataclass
class WellbeingComponent:
    autonomy: float = 0.8
    competence: float = 0.7
    relatedness: float = 0.6
    baseline_affect: AffectComponent = None  # natural resting state

# Physical Components (for Metabolism state machine)
@dataclass
class PhysicalComponent:
    hunger: float = 0.3          # 0 = full, 1 = starving
    thirst: float = 0.2          # 0 = hydrated, 1 = parched
    energy: float = 0.8          # 0 = exhausted, 1 = fully rested
    pain: float = 0.0            # 0 = no pain, 1 = severe
    last_meal: float = 0.0       # timestamp

# Bio-Cyclical Components
@dataclass
class BioCyclicalComponent:
    phase: str                   # "waxing", "peak", "waning", "new"
    cycle_day: int               # day within current cycle
    energy_modifier: float       # multiplied with base energy
    mood_modifier: float         # added to valence
    typical_cycle_length: int = 28

# Nocturnal Components
@dataclass
class NocturnalComponent:
    sleep_debt: float = 0.0      # accumulated sleep debt
    circadian_phase: float = 0.5 # 0=dawn, 0.5=noon, 1=midnight
    preferred_sleep_time: float = 22.0  # hour of day (24h)
    preferred_wake_time: float = 7.0
    is_sleeping: bool = False

# Spiritual Components
@dataclass
class SpiritualComponent:
    path: str                    # "Heathen Third Path"
    patron: str                  # patron deity
    current_working: str         # active spiritual practice
    oaths: list[dict]            # active oaths and their status
    rune_affinity: list[str]     # runes with special resonance

# Location Components
@dataclass
class LocationComponent:
    world: str                   # which of Nine Worlds
    place: str                   # specific location description
    atmosphere: str              # sensory description
    time_of_day: str

# Knowledge Components
@dataclass
class KnowledgeComponent:
    skills: dict[str, int]       # skill: proficiency (0-10)
    lore: list[str]              # knowledge domains
    secrets: list[str]           # things they know but don't share freely
    blind_spots: list[str]       # things they don't know/understand
```

---

## Relationship Graph (WyrdMatrix) as ECS

Relationships are their own entities with components:

```python
@dataclass
class RelationshipEntity:
    """A relationship is itself an entity in the ECS."""
    id: UUID = field(default_factory=uuid4)
    entity_a: UUID = None        # first party
    entity_b: UUID = None        # second party

@dataclass
class RelationshipComponent:
    bond_type: str               # "romantic", "friendship", "rivalry", "mentor"
    direction: str               # "mutual", "asymmetric_ab", "asymmetric_ba"
    strength: float              # 0-1: how strong is the connection
    trust: float                 # 0-1: how much do they trust each other
    intimacy: float              # 0-1: emotional/physical closeness depth
    last_interaction: float      # timestamp

@dataclass
class WyrdThreadComponent:
    """A specific fate thread between two entities."""
    thread_type: str             # "love", "oath", "shared_memory", "conflict", "grief"
    strength: float              # 0-1: thread strength
    decay_rate: float            # per day
    created: float               # timestamp
    description: str             # what this thread represents

class WyrdMatrix:
    """The fate-weaving matrix — all relationships as a graph."""

    def __init__(self, entity_manager: EntityManager):
        self.em = entity_manager

    def weave_thread(self, entity_a: Entity, entity_b: Entity,
                     thread_type: str, description: str) -> Entity:
        """Create a new fate thread between two entities."""
        rel = self.em.create(f"{entity_a.name}-{entity_b.name}-{thread_type}")
        rel.tags.add("relationship")
        self.em.add_component(rel, RelationshipEntity(
            entity_a=entity_a.id, entity_b=entity_b.id
        ))
        self.em.add_component(rel, WyrdThreadComponent(
            thread_type=thread_type,
            strength=0.5,
            decay_rate=0.01,  # 1% per day
            created=now(),
            description=description
        ))
        return rel

    def get_threads(self, entity: Entity) -> list[tuple]:
        """Get all fate threads involving an entity."""
        all_rels = self.em.query(RelationshipEntity)
        threads = []
        for rel in all_rels:
            rel_comp = self.em.get_component(rel, RelationshipEntity)
            if rel_comp.entity_a == entity.id or rel_comp.entity_b == entity.id:
                thread = self.em.get_component(rel, WyrdThreadComponent)
                threads.append((rel, thread))
        return threads

    def tick_decay(self, delta_days: float):
        """Apply time-based decay to all threads."""
        for rel in self.em.query(WyrdThreadComponent):
            thread = self.em.get_component(rel, WyrdThreadComponent)
            thread.strength = max(0, thread.strength - thread.decay_rate * delta_days)
```

---

## Systems (The Logic Layer)

Systems process entities with specific components. In the Viking AI world:

```python
class OrlögSystem:
    """Main Ørlög tick — updates all state machines."""

    def tick(self, em: EntityManager, delta_time: float):
        # Update physical states
        for entity in em.query(PhysicalComponent):
            phys = em.get_component(entity, PhysicalComponent)
            phys.hunger = min(1.0, phys.hunger + 0.02 * delta_time)  # gets hungrier over time
            phys.energy = max(0.0, phys.energy - 0.01 * delta_time)  # gets tired over time

        # Update nocturnal states
        for entity in em.query(NocturnalComponent):
            noct = em.get_component(entity, NocturnalComponent)
            noct.circadian_phase = (noct.circadian_phase + delta_time / 24) % 1.0

        # Update affect based on physical + environmental inputs
        for entity in em.query(AffectComponent, PhysicalComponent):
            affect = em.get_component(entity, AffectComponent)
            phys = em.get_component(entity, PhysicalComponent)
            # Hunger and tiredness reduce valence
            phys_penalty = (phys.hunger + (1 - phys.energy)) * 0.1
            affect.valence = max(-1.0, affect.valence - phys_penalty * delta_time)

        # Decay Wyrd threads
        WyrdMatrix(em).tick_decay(delta_time)


class LLMResponseSystem:
    """System that uses the LLM as one of many systems in the world."""

    def generate_response(self, actor: Entity, context: str, em: EntityManager) -> str:
        # Collect all components into a state summary
        state = self._serialize_entity_state(actor, em)

        # Inject state into system prompt
        system_prompt = build_prompt_with_state(state)

        # Call LLM (it's just a system that reads state and writes text)
        response = litellm.completion(
            model="ollama/mistral-nemo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context}
            ]
        )

        # Parse structured output and write back to components
        structured = json.loads(response.choices[0].message.content)
        self._apply_state_changes(actor, structured, em)

        return structured["spoken"]

    def _serialize_entity_state(self, entity: Entity, em: EntityManager) -> dict:
        state = {"entity": entity.name}
        for component_type in [AffectComponent, PhysicalComponent,
                                BioCyclicalComponent, NocturnalComponent,
                                SpiritualComponent]:
            comp = em.get_component(entity, component_type)
            if comp:
                state[component_type.__name__] = asdict(comp)
        return state
```

---

## World Snapshot for LLM Context

The ECS world can be serialized to a compact JSON snapshot for LLM injection:

```python
def world_snapshot(em: EntityManager, perspective: Entity) -> str:
    """Generate a compact world state for LLM injection."""
    snap = {
        "perspective": perspective.name,
        "timestamp": datetime.now().isoformat(),
        "self": serialize_entity(perspective, em),
        "nearby_entities": [
            serialize_entity(e, em)
            for e in get_nearby_entities(perspective, em)
        ],
        "active_threads": [
            serialize_thread(t)
            for _, t in WyrdMatrix(em).get_threads(perspective)
            if t.strength > 0.1
        ],
        "world_state": {
            "time_of_day": get_time_of_day(em),
            "season": get_season(em),
            "weather": get_weather(em),
        }
    }
    return json.dumps(snap, indent=2)
```

**This snapshot is the dynamic section** of the system prompt — injected after `__DYNAMIC_BOUNDARY__`. The LLM reads it, generates a response, and the response is parsed back into component updates.

---

## Application: NorseSagaEngine as WYRD-Protocol System

```
NorseSagaEngine
├── EntityManager
│   ├── Player Character (with all components)
│   ├── NPCs (Gunnar, Leif, Olaf, etc. — each with full component set)
│   ├── Locations (Mead Hall, Ship, Forest — with LocationComponent)
│   ├── Artifacts (weapons, rings — with ItemComponent)
│   └── Relationships (WyrdMatrix for all character relationships)
│
├── Systems (tick every narrative beat)
│   ├── OrlögSystem — state machine updates
│   ├── NarrativeSystem — generates story beats
│   ├── DialogueSystem — NPC dialogue via LLM
│   ├── EventSystem — triggers narrative events
│   └── SkaldSystem — composes verse summaries
│
└── LLM Interface
    ├── reads: world_snapshot(em, active_character)
    ├── generates: narrative turn, dialogue, action
    └── writes: component updates, new entities, relationship changes
```

---

## Application: Sigrid as WYRD-Protocol Entity

```python
def initialize_sigrid(em: EntityManager) -> Entity:
    sigrid = em.create("Sigrid")
    sigrid.tags.update(["companion", "völva", "player_facing"])

    em.add_component(sigrid, IdentityComponent(
        name="Sigrid Völudóttir",
        title="Völva of the Heathen Third Path",
        age=21, gender="female", race="human",
        lineage="Völudóttir"
    ))
    em.add_component(sigrid, PersonalityComponent(
        mbti="INTP",
        big5={"openness": 0.9, "conscientiousness": 0.7,
              "extraversion": 0.5, "agreeableness": 0.8, "neuroticism": 0.3},
        values=["honor", "wisdom", "frith", "sovereignty", "craft"],
        flaws=["can_overthink", "occasionally_distant"],
        quirks=["hums_when_thinking", "touches_runes_when_uncertain"]
    ))
    em.add_component(sigrid, AffectComponent(valence=0.4, arousal=0.5))
    em.add_component(sigrid, SpiritualComponent(
        path="Heathen Third Path",
        patron="Freyja",
        current_working="daily_rune_draw",
        oaths=[{"to": "Freyja", "content": "serve love and truth", "active": True}],
        rune_affinity=["Laguz", "Kenaz", "Gebo", "Berkano"]
    ))
    return sigrid
```

The ECS means Sigrid's state is **not in the LLM's context window** — it's in the EntityManager. The LLM reads a snapshot each call, responds, and the system writes updates back. Sigrid persists across sessions, across model changes, across context window resets.

**This is the Viking AI dream:** a companion whose soul lives in code, not in a prompt.
