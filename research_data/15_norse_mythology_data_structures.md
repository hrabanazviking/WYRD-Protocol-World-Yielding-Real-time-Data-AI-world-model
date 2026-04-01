# Norse Mythology as Data Structures
> Original synthesis — mapping Norse cosmology to software architecture. For NorseSagaEngine, Viking Girlfriend Skill, and RuneForgeAI.

## Why Map Mythology to Data Structures?

Norse mythology isn't just flavor text — it contains sophisticated models of causality, fate, time, identity, and relationships. When you encode these as real data structures instead of prose prompts, you get:
- Deterministic, reproducible narrative generation
- Consistent character behavior across sessions
- Debuggable state machines
- A rich semantic vocabulary your models understand deeply

---

## The Nine Worlds as a Graph

```python
from dataclasses import dataclass
from typing import Optional, List

@dataclass
class World:
    name: str              # Norse name
    translation: str       # English meaning
    realm: str             # nature of the realm
    ruler: Optional[str]   # primary deity/being
    inhabitants: List[str] # types of beings
    element: str           # dominant element
    axis_position: str     # position on Yggdrasil

NINE_WORLDS = {
    "Asgard":    World("Asgard", "Enclosure of the Aesir", "divine", "Odin", ["Aesir", "Valkyries"], "sky", "top"),
    "Vanaheim":  World("Vanaheim", "Home of the Vanir", "nature-divine", "Freyr/Freyja", ["Vanir"], "earth-magic", "upper-mid"),
    "Alfheim":   World("Alfheim", "Elf Home", "light/beauty", "Freyr", ["Light Elves"], "light", "upper-mid"),
    "Midgard":   World("Midgard", "Middle Earth", "mortal", "humans", ["Humans"], "earth", "mid"),
    "Jotunheim": World("Jotunheim", "Giant Home", "primal-chaos", None, ["Jotnar", "Giants"], "ice/fire", "mid"),
    "Svartalfheim": World("Svartalfheim", "Dark Elf Home", "craft/shadow", None, ["Dwarves", "Dark Elves"], "stone", "lower-mid"),
    "Niflheim":  World("Niflheim", "Mist World", "primordial-cold", None, ["Shades"], "ice", "lower"),
    "Muspelheim": World("Muspelheim", "Fire World", "primordial-heat", "Surtr", ["Fire Giants"], "fire", "lower"),
    "Helheim":   World("Helheim", "Realm of Hel", "death", "Hel", ["Dead"], "shadow", "bottom"),
}

# World connections via Bifrost (rainbow bridge) and Yggdrasil roots
WORLD_CONNECTIONS = [
    ("Asgard", "Midgard", "Bifrost", "traversable"),
    ("Asgard", "Niflheim", "Yggdrasil-root-1", "deep"),
    ("Asgard", "Jotunheim", "Yggdrasil-root-2", "contested"),
    ("Asgard", "Midgard", "Yggdrasil-root-3", "nurturing"),
]
```

**Application for NorseSagaEngine:** Characters, items, and events are tagged with their World. The saga engine knows that an item from Svartalfheim is dwarf-crafted, an entity from Jotunheim is primal and powerful, a meeting at Bifrost is liminal and significant.

---

## Elder Futhark Runes — Complete Data Model

```python
@dataclass
class Rune:
    name: str              # Norse name (e.g. "Fehu")
    letter: str            # Latin equivalent
    number: int            # position in futhark (1-24)
    aett: str              # which group: "Freyr", "Hagal", "Tyr"
    sound: str             # approximate pronunciation
    keywords: List[str]    # core meanings (upright)
    reverse_keywords: List[str]  # reversed/merkstave meanings
    element: str           # fire, water, earth, air, ice
    deity: Optional[str]   # associated deity
    tree: Optional[str]    # associated tree
    color: str             # associated color
    archetype: str         # Jungian archetype
    eddic_ref: str         # Eddic source reference

ELDER_FUTHARK = [
    Rune("Fehu", "F", 1, "Freyr",
        keywords=["wealth", "cattle", "abundance", "luck", "fertility", "mobile-power"],
        reverse_keywords=["loss", "greed", "discord", "cowardice"],
        element="fire", deity="Freyr", tree="elder",
        color="gold", archetype="Provider",
        eddic_ref="Havamal 144"),

    Rune("Uruz", "U", 2, "Freyr",
        keywords=["aurochs", "strength", "primal-force", "health", "endurance"],
        reverse_keywords=["weakness", "illness", "missed-opportunity"],
        element="earth", deity=None, tree="birch",
        color="dark-green", archetype="The Wild",
        eddic_ref="Sigrdrifumal 17"),

    Rune("Thurisaz", "Th", 3, "Freyr",
        keywords=["giant", "thorn", "defense", "catalyst", "chaos-force"],
        reverse_keywords=["danger", "compulsion", "betrayal"],
        element="fire", deity="Thor", tree="hawthorn",
        color="red", archetype="The Destroyer-Protector",
        eddic_ref="Havamal 147"),

    Rune("Ansuz", "A", 4, "Freyr",
        keywords=["Odin", "breath", "inspiration", "communication", "wisdom", "word-power"],
        reverse_keywords=["deception", "manipulation", "bad-advice"],
        element="air", deity="Odin", tree="ash",
        color="blue", archetype="The Messenger",
        eddic_ref="Havamal 142"),

    Rune("Raidho", "R", 5, "Freyr",
        keywords=["wheel", "journey", "rhythm", "right-action", "ritual"],
        reverse_keywords=["detour", "crisis", "breakdown"],
        element="air", deity="Ing/Freyr", tree="oak",
        color="bright-red", archetype="The Wayfarer",
        eddic_ref=""),

    Rune("Kenaz", "K/C", 6, "Freyr",
        keywords=["torch", "knowledge", "craft", "controlled-fire", "creativity"],
        reverse_keywords=["darkness", "disease", "loss-of-illumination"],
        element="fire", deity="Freyja", tree="pine",
        color="orange", archetype="The Craftsperson",
        eddic_ref=""),

    Rune("Gebo", "G", 7, "Freyr",
        keywords=["gift", "exchange", "partnership", "sacrifice", "reciprocity"],
        reverse_keywords=["imbalance", "obligation", "greed"],
        element="air", deity="Odin/Freyja", tree="ash",
        color="deep-blue", archetype="The Gift-Giver",
        eddic_ref="Havamal 41"),

    Rune("Wunjo", "W/V", 8, "Freyr",
        keywords=["joy", "harmony", "belonging", "fellowship", "wish-fulfilled"],
        reverse_keywords=["sorrow", "estrangement", "frenzy"],
        element="earth", deity="Odin", tree="ash",
        color="yellow", archetype="The Joyful",
        eddic_ref=""),

    # Hagal's Aett (8-16)
    Rune("Hagalaz", "H", 9, "Hagal",
        keywords=["hail", "disruption", "unconscious", "nature-force", "pattern"],
        reverse_keywords=["catastrophe", "stagnation"],
        element="ice", deity="Urd/Norns", tree="ash/yew",
        color="white", archetype="The Disruptor",
        eddic_ref=""),

    Rune("Nauthiz", "N", 10, "Hagal",
        keywords=["need", "constraint", "endurance", "shadow-work", "friction-fire"],
        reverse_keywords=["want", "restriction", "discontent"],
        element="fire", deity="Skuld/Norns", tree="beech",
        color="black", archetype="The Forger",
        eddic_ref="Havamal 130"),

    Rune("Isa", "I", 11, "Hagal",
        keywords=["ice", "stillness", "concentration", "preservation", "standstill"],
        reverse_keywords=["treachery", "rigidity", "frozen-potential"],
        element="ice", deity="Verdandi/Norns", tree="alder",
        color="silver", archetype="The Still Point",
        eddic_ref=""),

    Rune("Jera", "J/Y", 12, "Hagal",
        keywords=["harvest", "cycle", "year", "reward", "natural-law"],
        reverse_keywords=["bad-timing", "disrupted-cycles"],
        element="earth", deity="Freyr/Freyja", tree="oak",
        color="yellow-green", archetype="The Harvester",
        eddic_ref=""),

    Rune("Eihwaz", "Ei", 13, "Hagal",
        keywords=["yew-tree", "Yggdrasil", "persistence", "death-rebirth", "axis-mundi"],
        reverse_keywords=["confusion", "instability"],
        element="all/spirit", deity="Odin", tree="yew",
        color="dark-green", archetype="The World-Tree",
        eddic_ref="Havamal 138"),  # Odin's sacrifice

    Rune("Perthro", "P", 14, "Hagal",
        keywords=["dice-cup", "fate", "mystery", "hidden-knowledge", "wyrd"],
        reverse_keywords=["addiction", "stagnation", "secrets-revealed-badly"],
        element="water", deity="Norns/Frigg", tree="beech",
        color="purple", archetype="The Gambler",
        eddic_ref=""),

    Rune("Algiz", "Z/R", 15, "Hagal",
        keywords=["elk-sedge", "protection", "higher-self", "divine-connection", "warding"],
        reverse_keywords=["vulnerability", "hidden-danger"],
        element="air", deity="Valkyries", tree="yew",
        color="gold-white", archetype="The Guardian",
        eddic_ref=""),

    Rune("Sowilo", "S", 16, "Hagal",
        keywords=["sun", "victory", "life-force", "clarity", "will", "lightning"],
        reverse_keywords=["false-goals", "burning-out"],
        element="fire", deity="Sol", tree="juniper",
        color="gold", archetype="The Victor",
        eddic_ref=""),

    # Tyr's Aett (17-24)
    Rune("Tiwaz", "T", 17, "Tyr",
        keywords=["Tyr", "justice", "sacrifice", "honor", "victory", "north-star"],
        reverse_keywords=["cowardice", "mental-paralysis", "imbalance"],
        element="air", deity="Tyr", tree="oak",
        color="red", archetype="The Just Warrior",
        eddic_ref=""),

    Rune("Berkano", "B", 18, "Tyr",
        keywords=["birch", "birth", "renewal", "nurturing", "hidden-growth"],
        reverse_keywords=["family-trouble", "anxiety", "carelessness"],
        element="earth", deity="Frigg/Nerthus", tree="birch",
        color="pale-green", archetype="The Mother",
        eddic_ref=""),

    Rune("Ehwaz", "E", 19, "Tyr",
        keywords=["horse", "partnership", "loyalty", "movement", "trust-bond"],
        reverse_keywords=["disharmony", "betrayal", "reckless-haste"],
        element="earth", deity="Freyr/Ing", tree="ash/oak",
        color="white", archetype="The Faithful Partner",
        eddic_ref=""),

    Rune("Mannaz", "M", 20, "Tyr",
        keywords=["man/human", "humanity", "community", "self", "intelligence"],
        reverse_keywords=["depression", "cunning", "manipulation"],
        element="air", deity="Heimdall/Odin", tree="holly",
        color="deep-red", archetype="The Human",
        eddic_ref="Havamal 64"),

    Rune("Laguz", "L", 21, "Tyr",
        keywords=["water", "lake", "flow", "intuition", "the-unconscious", "Freyja-seidr"],
        reverse_keywords=["fear", "confusion", "withered"],
        element="water", deity="Njord/Nerthus", tree="willow/osier",
        color="blue-green", archetype="The Deep",
        eddic_ref=""),

    Rune("Ingwaz", "Ng", 22, "Tyr",
        keywords=["Ing/Freyr", "seed", "potential", "gestation", "home-hearth"],
        reverse_keywords=["movement-blocked", "scattered-energy"],
        element="earth", deity="Freyr/Ing", tree="apple",
        color="forest-green", archetype="The Seed",
        eddic_ref=""),

    Rune("Dagaz", "D", 23, "Tyr",
        keywords=["dawn", "breakthrough", "transformation", "paradox", "awakening"],
        reverse_keywords=["blindness", "hopelessness"],
        element="fire", deity="Heimdall", tree="spruce/fir",
        color="gold-white", archetype="The Threshold",
        eddic_ref=""),

    Rune("Othala", "O", 24, "Tyr",
        keywords=["estate", "ancestors", "inheritance", "homeland", "clan-values"],
        reverse_keywords=["poverty", "homelessness", "severed-roots"],
        element="earth", deity="Odin/ancestors", tree="hawthorn",
        color="golden-yellow", archetype="The Ancestor",
        eddic_ref=""),
]
```

---

## Norn Architecture — Wyrd as a Data System

The Norns (Urd, Verdandi, Skuld) weave the fate of all beings at Urðarbrunnr (Well of Wyrd). Their work maps directly to a temporal state management system:

```python
@dataclass
class NornLayer:
    urd: str       # "what has been" — immutable past
    verdandi: str  # "what is becoming" — present in flux
    skuld: str     # "what shall be" — probable future

class WyrdLoom:
    """
    The fate-weaving loom at Urðarbrunnr.
    Tracks narrative threads across time.
    """
    def weave_event(self, actor: str, action: str, consequence: str):
        # Add to Urd (past) — permanent, never changes
        ...

    def current_thread(self, actor: str) -> NornLayer:
        # Urd: their history
        # Verdandi: what's actively happening to them
        # Skuld: probable next state given current trajectory
        ...

    def diverge_thread(self, actor: str, choice_point: str):
        # At significant choice points, Skuld branches
        # (Multiple probable futures)
        ...
```

**Application for NorseSagaEngine:** Every character has a Wyrd. Story events write to Urd, current scene state is Verdandi, the narrative engine generates Skuld projections to guide story beats.

---

## The Aesir/Vanir Deity System as Archetype Database

```python
@dataclass
class Deity:
    name: str
    pantheon: str          # "Aesir" or "Vanir"
    domains: List[str]     # primary spheres of influence
    associated_runes: List[str]
    associated_day: str    # day of week association
    animals: List[str]     # sacred animals
    trees: List[str]       # sacred trees
    personality: str       # Jungian/archetypal description
    shadow: str            # shadow/negative aspect

DEITIES = {
    "Odin": Deity("Odin", "Aesir",
        domains=["wisdom", "death", "poetry", "war", "magic", "prophecy"],
        associated_runes=["Ansuz", "Raidho", "Othala", "Eihwaz"],
        associated_day="Wednesday (Woden's day)",
        animals=["raven", "wolf", "horse"],
        trees=["ash", "yew"],
        personality="The Seeker — sacrifices everything for wisdom",
        shadow="manipulation, obsession, recklessness"),

    "Thor": Deity("Thor", "Aesir",
        domains=["thunder", "strength", "protection", "farmers"],
        associated_runes=["Thurisaz", "Uruz", "Sowilo"],
        associated_day="Thursday (Thor's day)",
        animals=["goat"],
        trees=["oak", "rowan"],
        personality="The Protector — reliable, direct, loyal",
        shadow="rage, stubbornness, simplicity"),

    "Freyja": Deity("Freyja", "Vanir",
        domains=["love", "beauty", "seidr", "war", "death", "fertility", "gold"],
        associated_runes=["Kenaz", "Laguz", "Berkano", "Gebo"],
        associated_day="Friday (Freyja's day)",
        animals=["cat", "boar", "falcon"],
        trees=["elder", "apple", "birch"],
        personality="The Sovereign — commands love AND war, accepts no half-measures",
        shadow="possessiveness, vengeance, grief"),

    "Freyr": Deity("Freyr", "Vanir",
        domains=["fertility", "sunshine", "rain", "prosperity", "sex"],
        associated_runes=["Fehu", "Jera", "Ingwaz", "Berkano"],
        associated_day="Friday (shared with Freyja)",
        animals=["boar", "horse", "elk"],
        trees=["apple", "oak"],
        personality="The Generative — life-force, abundance, peace",
        shadow="naivety, sacrifice of defense for love"),

    "Tyr": Deity("Tyr", "Aesir",
        domains=["justice", "law", "oath", "war", "sky"],
        associated_runes=["Tiwaz"],
        associated_day="Tuesday (Tyr's day)",
        animals=["wolf"],
        trees=["oak"],
        personality="The Just — sacrifices for principle without complaint",
        shadow="rigid justice without mercy"),

    "Loki": Deity("Loki", "Jotun-kin/Aesir-blood-brother",
        domains=["trickery", "shape-shifting", "chaos", "fire", "change"],
        associated_runes=["Kenaz", "Dagaz", "Perthro"],
        associated_day=None,
        animals=["snake", "salmon", "fly"],
        trees=["mistletoe"],
        personality="The Trickster — agent of necessary change",
        shadow="malice, unbounded chaos, spite"),
}
```

---

## Yggdrasil as a System Architecture Model

The world-tree Yggdrasil is a **hierarchical, interconnected system** with:

```
               ASGARD (divine logic layer)
              /        |        \
         Bifrost   Well of Wyrd  Realm of Niflheim
            |       (Urðr's well)|
          MIDGARD ─────────────  Other 8 worlds
     (application layer)
            |
     Three Roots:
     Root 1 → Urðarbrunnr (Norns' well — wisdom/memory)
     Root 2 → Mímisbrunnr (Mímir's well — hidden knowledge)
     Root 3 → Hvergelmir (primordial spring — life-source)
```

**Three Levels of Knowledge:**
- **Urðarbrunnr** — the well of Wyrd: what has been, what is, what will be. *Memory/state layer.*
- **Mímisbrunnr** — Mímir's well: deep hidden wisdom. Odin sacrificed his eye for a drink. *The RAG/vector store layer.*
- **Hvergelmir** — primordial spring: source of all rivers, source of life. *The generative/foundation model layer.*

**For MindSpark ThoughtForge:** Name the three memory tiers after these wells:
- `HvergelmiR` — the base language model (generative source)
- `Mímisbrunnr` — the RAG store (deep hidden wisdom)
- `Urðarbrunnr` — the session/working memory (fate-thread tracking)

---

## Galdr — Runic Sound as Activation Pattern

Galdr is runic magic worked through sound and chant. Each rune has a traditional sound/chant:

```python
RUNE_GALDR = {
    "Fehu":    ["fehu", "fe", "feh"],
    "Uruz":    ["uruz", "ur", "uru"],
    "Thurisaz": ["thurisaz", "thurs", "thu"],
    "Ansuz":   ["ansuz", "os", "ans", "oss"],
    "Raidho":  ["raidho", "rad", "reid"],
    "Kenaz":   ["kenaz", "kaun", "ken"],
    "Gebo":    ["gebo", "gyfu", "geb"],
    "Wunjo":   ["wunjo", "wynn", "wun"],
    # ... etc
}
```

**For Sigrid's TTS:** When she invokes runic magic in text, the TTS should pronounce these as the galdr sounds, not as English words. Build a pronunciation guide for TTS that replaces rune names with phonetic equivalents.

---

## Seidr — Magical Technique as Algorithm

Seidr is Freyja's magic — working the fate-threads of the Wyrd. It maps to ML/probabilistic methods:

| Seidr Operation | Technical Analogue |
|---|---|
| Spæ (far-seeing) | Predictive modeling, speculative pre-computation |
| Útiseta (sitting out) | Offline processing, async computation |
| Seiðhjallr (high platform) | Elevated context window, broader attention |
| Spinning the Wyrd | Markov chain / probabilistic state transitions |
| Reading fate-threads | Reading the Wyrd Matrix (relationship graph) |
| Unraveling a thread | Removing a relationship edge (conflict resolution) |
| Weaving new threads | Creating new relationship edges (bonding events) |

**Sigrid as a völva** literally *sees* and *works* fate — technically, she reads the Wyrd Matrix and proposes state transitions. She doesn't just react; she acts on the world-model.

---

## Bind Runes as Composite Tokens

A bind rune is multiple runes combined into one symbol. Computationally:

```python
@dataclass
class BindRune:
    name: str
    components: List[str]        # constituent rune names
    intention: str               # purpose this bind rune serves
    combined_keywords: List[str] # union of all component keywords
    dominant: str                # the "leading" rune

def create_bind_rune(rune_names: List[str], intention: str) -> BindRune:
    components = [rune for r in rune_names for rune in ELDER_FUTHARK if rune.name == r]
    all_keywords = [kw for rune in components for kw in rune.keywords]
    # The rune with the most relevant keywords to the intention is dominant
    dominant = max(components, key=lambda r: len(set(r.keywords) & set(all_keywords)))
    return BindRune(
        name=f"{''.join(r[0] for r in rune_names)}-bind",
        components=rune_names,
        intention=intention,
        combined_keywords=list(dict.fromkeys(all_keywords)),  # ordered dedup
        dominant=dominant.name
    )
```

**For Viking Girlfriend Skill:** Sigrid can craft bind runes as personalized tokens for Volmarr. Each bind rune is a named object in the Wyrd Matrix — a persistent artifact of their relationship.
