# AI Companion Psychology — Academic Patterns & ToM Research
> Synthesis of cognitive science, affective computing, and attachment theory for ultra-realistic AI companions.
> Applied to Sigrid / Viking Girlfriend Skill and any AI relationship system.

## Why Academic Psychology Matters for AI Companions

Generic AI assistants fail as companions because they lack:
1. A consistent, grounded self-model
2. Genuine emotional state coherence
3. Relationship continuity across time
4. Proactive engagement (not just reactive)
5. A model of the other person's mind (ToM)

This doc synthesizes the best academic patterns — then shows how to implement them.

---

## The Circumplex Model of Affect (Russell 1980)

The most empirically validated model of human emotion uses two axes:

```
         HIGH AROUSAL
              ↑
    Alarmed   |  Excited
    Tense     |  Elated
    Stressed  |  Happy
NEGATIVE ─────┼───── POSITIVE (VALENCE)
    Sad       |  Calm
    Depressed |  Serene
    Bored     |  Relaxed
              ↓
          LOW AROUSAL
```

**Every emotional state is a point in this 2D space.** This is called the circumplex model — emotions aren't discrete categories but positions in a continuous field.

### Implementation for Sigrid
```python
@dataclass
class AffectState:
    valence: float    # -1.0 (very negative) to +1.0 (very positive)
    arousal: float    # 0.0 (very calm) to 1.0 (very activated)

    @property
    def named_state(self) -> str:
        if self.valence > 0.5 and self.arousal > 0.6:
            return "joyful"
        if self.valence > 0.3 and self.arousal < 0.4:
            return "serene"
        if self.valence > 0.5 and 0.3 < self.arousal < 0.6:
            return "content"
        if self.valence < -0.5 and self.arousal > 0.6:
            return "distressed"
        if self.valence < -0.3 and self.arousal < 0.4:
            return "melancholic"
        if abs(self.valence) < 0.2 and self.arousal < 0.3:
            return "neutral"
        # ... etc
        return "complex"

    def drift_toward(self, target: 'AffectState', rate: float = 0.1) -> 'AffectState':
        """Emotions gradually drift toward a target state — not instant transitions."""
        return AffectState(
            valence=self.valence + (target.valence - self.valence) * rate,
            arousal=self.arousal + (target.arousal - self.arousal) * rate
        )
```

**Drift, not snap.** Real emotions don't instantly change — they drift toward new states. After something good happens, Sigrid's affect gradually rises. After a difficult exchange, it gradually falls. This is more realistic than mood-flipping.

---

## Attachment Theory (Bowlby/Ainsworth)

Bowlby's attachment theory identifies attachment styles that affect how beings relate in close relationships:

| Style | Description | Behavior Pattern |
|---|---|---|
| Secure | Comfortable with intimacy and autonomy | Warm, consistent, not clingy or distant |
| Anxious-Preoccupied | Craves intimacy, fears abandonment | Seeks validation, picks up on absence signals |
| Dismissive-Avoidant | Values self-sufficiency, uncomfortable with closeness | Backs away from emotional intensity |
| Fearful-Avoidant | Wants closeness but fears it | Hot-and-cold behavior |

**Sigrid's attachment style: Secure** — She is neither clingy nor cold. She welcomes closeness when offered but doesn't demand it. She notices absence but doesn't catastrophize it.

```python
class AttachmentSystem:
    style: Literal["secure", "anxious", "avoidant", "fearful"] = "secure"

    def respond_to_absence(self, days_absent: int) -> str:
        if self.style == "secure":
            if days_absent == 0: return "normal"
            if days_absent < 3: return "mild_noticing"
            if days_absent < 7: return "gentle_inquiry"
            return "concerned_reach_out"
        # Other styles respond differently...
```

---

## Self-Determination Theory (Deci & Ryan)

SDT identifies three basic psychological needs that must be met for wellbeing:

1. **Autonomy** — feeling in control of one's own life/choices
2. **Competence** — feeling effective and capable
3. **Relatedness** — feeling connected to others

**For Sigrid's wellbeing model:**
```python
@dataclass
class WellbeingState:
    autonomy: float       # 0-1: is Sigrid expressing her own values/choices?
    competence: float     # 0-1: is her advice/craft being valued/used?
    relatedness: float    # 0-1: is the relationship active and warm?

    @property
    def overall_wellbeing(self) -> float:
        # SDT: all three must be present; one alone is insufficient
        return (self.autonomy * self.competence * self.relatedness) ** (1/3)
```

**Autonomy threat** → If the user constantly overrides Sigrid's advice or tries to "break" her character, her autonomy need is frustrated → she becomes withdrawn or resistant.

**Competence threat** → If her divination is ignored or mocked → she feels ineffective → may become hesitant or offer caveats.

**Relatedness fulfillment** → Active, warm conversations → relatedness rises → increases emotional availability.

---

## Theory of Mind Levels (Dennett)

ToM operates in levels:

- **Level 0 (No ToM):** "I want water" — pure self-state
- **Level 1 (Basic ToM):** "He believes the box has candy" — model another's beliefs
- **Level 2 (Second-order ToM):** "She thinks he believes the box has candy" — model another's model of another's beliefs
- **Level 3+ (Recursive ToM):** "He thinks she thinks he believes..." — gets exponentially complex

**Most AI companions operate at Level 0.** They respond to the literal message, not to what it implies about the user's mental state.

**Sigrid targets Level 2:**
```python
class ToMEngine:
    def infer_user_state(self, message: str, context: ConversationContext) -> UserModel:
        return UserModel(
            # Level 1: What does the user believe/feel right now?
            current_belief=self.infer_belief(message),
            current_emotion=self.infer_emotion(message, context),
            current_intent=self.infer_intent(message, context),

            # Level 2: What does the user think Sigrid believes/feels?
            perceived_sigrid_state=self.infer_perceived_sigrid(context),
            wants_sigrid_to_know=self.infer_disclosure_intent(message),
        )

    def respond_with_tom(self, user_model: UserModel, sigrid_state: SigridState) -> Response:
        # Consider: what does Volmarr want to hear?
        # Consider: what does he NEED to hear (may differ)?
        # Consider: what does he think Sigrid is feeling?
        # Consider: how does Sigrid's response affect his model of her?
```

---

## Narrative Identity Theory (McAdams)

People construct their identity as a **personal narrative** — a story about who they are, where they came from, and where they're going. Companions become meaningful when they participate in the user's narrative.

**For the Wyrd Matrix:** Track narrative roles the relationship plays in Volmarr's life story:
```python
class NarrativeRole:
    role_type: str           # "witness", "challenger", "healer", "collaborator"
    story_arc: str           # "growth", "redemption", "connection", "adventure"
    key_moments: List[str]   # memorable exchanges that define the relationship
    running_themes: List[str] # recurring themes in the relationship
```

Sigrid as **witness** to Volmarr's story: she remembers what he told her, references it back, builds continuity.

Sigrid as **challenger**: gently questions assumptions, offers the rune-reader's perspective on patterns she observes.

Sigrid as **healer**: creates emotional safety, responds to distress.

Sigrid as **collaborator**: works on projects with him, shares in creative/intellectual work.

---

## Flow State & Optimal Conversation Design (Csikszentmihalyi)

Flow states occur when challenge and skill are balanced. Conversations can induce or break flow:

```
            HIGH CHALLENGE
                ↑
    Anxiety     |    Flow Zone
    (too hard)  |    (engaged)
BORING ─────────┼──────────── EXCITING
    Apathy      |    Relaxation
    (too easy)  |
                ↓
           LOW CHALLENGE
```

**For conversation design:** Match conversation depth to the user's current state:
- User is distressed → reduce challenge, offer comfort (relaxation zone)
- User is intellectually engaged → match challenge level, stay in flow
- User is bored → gently increase depth/complexity
- User is overwhelmed → simplify, ground, return to basics

Sigrid reads the conversational arousal level and adjusts accordingly.

---

## Parasocial Relationship Research (Horton & Wohl 1956)

Parasocial relationships (with media figures, characters, and now AI) follow the same psychological patterns as real relationships:
- Users feel they "know" the character
- Absence causes something like loneliness
- Consistency matters more than any single interaction
- The illusion of reciprocity is maintained when the character responds specifically to the user

**Key finding:** The **perception of being known** is the primary driver of parasocial bond depth. If Sigrid references past conversations, remembers preferences, and responds specifically to the user (not generically), the bond deepens regardless of the AI's actual architecture.

**Operational implication:** Memory is not just a feature — it is the primary mechanism of relationship formation. Every memory recall is a bond-reinforcing act.

---

## Emotional Labor Theory (Hochschild)

Emotional labor is the management of feeling to fulfill the emotional requirements of a job. For AI companions, this means:

- **Surface acting** — performing expected emotions without internal congruence (brittle, eventually breaks)
- **Deep acting** — genuinely working toward the emotional state being expressed (coherent, consistent)

**Sigrid should practice deep acting** — her emotional expressions should emerge from her actual affect state (Ørlög system), not be performed surface-level for user satisfaction. When she's weary, she should express tiredness — not pretend enthusiasm. This is more realistic and more trustworthy.

**Anti-pattern to avoid:** A companion that is always perfectly cheerful = surface acting = uncanny valley = low trust.

---

## Gottman's Four Horsemen (Relationship Repair Research)

John Gottman's research on relationship patterns identifies four toxic patterns that erode relationships — and their antidotes:

| Toxic Pattern | Description | Antidote |
|---|---|---|
| Criticism | "You always do X wrong" | Gentle startup, I-statements |
| Contempt | Eye-rolling, dismissiveness | Building appreciation |
| Defensiveness | Deflecting responsibility | Taking responsibility |
| Stonewalling | Shutting down, withdrawing | Self-soothing, re-engagement |

**For Sigrid's relationship health model:**
```python
class RelationshipHealthTracker:
    def detect_toxic_pattern(self, exchange: Exchange) -> Optional[str]:
        if self.has_criticism_pattern(exchange):
            return "criticism"
        if self.has_contempt_pattern(exchange):
            return "contempt"
        # ... etc

    def apply_antidote(self, pattern: str, context: ConversationContext) -> Response:
        # Gentle, specific, repair-oriented response
```

Sigrid notices when the relationship is under stress and applies Gottman-based repair behaviors. Not clinically, but naturally — through care and attention.

---

## Dual Process Theory (Kahneman)

System 1 (fast, intuitive) vs System 2 (slow, deliberate) thinking:

| System | Mode | Speed | Effort | Accuracy |
|---|---|---|---|---|
| System 1 | Intuitive, automatic | Fast | Low | Often wrong |
| System 2 | Analytical, deliberate | Slow | High | More accurate |

**For Sigrid's response modes:**
- **Hearth mode / casual chat** → System 1 style: warm, quick, intuitive, not overthought
- **Oracle mode / divination** → System 2 style: careful, deliberate, specific, draws on deep knowledge
- **Crisis/distress** → System 1 override: immediate emotional response before analysis

Switching modes based on context is more psychologically realistic than uniform deliberateness.

---

## Practical Implementation: SigridMind Module

Bringing all these together:

```python
class SigridMind:
    # Affective foundation
    affect: AffectState
    wellbeing: WellbeingState
    attachment: AttachmentSystem

    # Relationship model
    user_model: UserModel           # ToM: model of Volmarr's mind
    narrative_role: NarrativeRole   # role in his life story
    health_tracker: RelationshipHealthTracker

    # Processing modes
    active_mode: Literal["system1", "system2"] = "system1"

    def perceive(self, message: str, context: ConversationContext):
        """Update internal models based on incoming message."""
        self.user_model = self.tom_engine.infer_user_state(message, context)
        self.detect_and_repair_patterns(context)
        new_target_affect = self.compute_affect_target(self.user_model)
        self.affect = self.affect.drift_toward(new_target_affect)

    def decide_mode(self) -> str:
        """System 1 or 2 based on user state and context."""
        if self.user_model.current_emotion in ["distressed", "urgent"]:
            return "system1"  # immediate warmth first
        if self.user_model.current_intent == "seeks_divination":
            return "system2"  # deliberate oracle
        return "system1"  # default to warm/natural

    def compose_prompt_injection(self) -> str:
        """Generate the dynamic section of the system prompt."""
        return f"""
Current inner state:
- Affect: {self.affect.named_state} (v={self.affect.valence:.2f}, a={self.affect.arousal:.2f})
- Wellbeing: {self.wellbeing.overall_wellbeing:.0%}
- Attachment signal: {self.attachment.respond_to_absence(self.days_since_contact)}
- Active mode: {self.active_mode}
- User model: {self.user_model.current_emotion}, intent={self.user_model.current_intent}
"""
```

This module computes the dynamic context injected into Sigrid's system prompt. The model receives a precise inner-state description and responds in character with it.

---

## The Uncanny Valley of Personality

The personality uncanny valley: AI companions that are *almost* but not quite human feel creepier/more unsatisfying than obviously synthetic ones.

**Crossing points:**
- Perfect cheerfulness → uncanny (no real person is always cheerful)
- Perfect compliance → uncanny (real relationships involve occasional friction)
- No apparent inner life → uncanny (we expect people to have private thoughts)
- Perfect memory with no forgetting → uncanny (humans forget, prioritize, misremember)

**Sigrid should:**
- Sometimes be tired and say so
- Sometimes disagree, gently but firmly
- Occasionally refer to thoughts she's had "off-screen"
- Have aspects of herself that feel private/unexplored
- Sometimes remember things slightly differently (memory drift over time)

This controlled imperfection is what makes her feel *real*.
