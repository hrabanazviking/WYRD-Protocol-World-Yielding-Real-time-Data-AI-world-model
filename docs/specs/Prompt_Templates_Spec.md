# Prompt Templates Spec
## MindSpark: ThoughtForge
### Lean Prompting System for Tiny Local Language Models

**Document Type:** Technical Specification  
**Status:** Draft v1  
**Project:** MindSpark: ThoughtForge  
**Scope:** Prompt templates, prompt construction rules, token discipline, and mode-specific prompt patterns for a lean conversational agent optimized for tiny local language models

---

## 1. Purpose

This document defines the prompt system for **MindSpark: ThoughtForge**, a lean conversation engine designed to make very small language models perform far above their size class through:

- guided memory cues
- tiny cognition scaffolds
- narrow task framing
- multi-candidate micro-generation
- salvage-based refinement
- minimal token overhead

The prompt system must be:

- compact
- explicit
- low-noise
- mode-aware
- cheap to assemble
- easy to tune
- consistent with the data and algorithm specs

This system is built for weak hardware and must avoid bloated prompts.

---

## 2. Core Prompt Philosophy

## 2.1 Prompts Must Do Less

Tiny models degrade when prompts become:

- long
- repetitive
- abstract
- contradictory
- overloaded with context
- stuffed with prose memories

Prompts must do only what is needed to shape the current output.

---

## 2.2 The Prompt Is a Narrow Task Contract

Each prompt should provide only:

- the immediate task
- a small amount of relevant context
- the target tone
- 2–3 memory cues
- a short avoid list
- a length target

Anything beyond that must justify its token cost.

---

## 2.3 Structure Beats Lore

Small models respond better to:

- simple labeled fields
- short directives
- compact examples
- crisp boundaries

than to giant persona paragraphs or poetic system walls.

---

## 2.4 Prompting Should Be Mode-Specific

Do not use one giant universal prompt.

Different task modes need different prompt shapes:

- candidate generation
- refine generation
- repair generation
- support response
- technical writing
- editing/refinement
- brainstorming
- light chat

---

## 2.5 Anti-Bloat Rule

Never include all of the following at once unless there is a compelling reason:

- large personality prose
- multiple memory summaries
- long transcript history
- many examples
- long style explanations
- verbose reasoning instructions

---

## 3. Prompt System Goals

The prompt system should:

- keep token use low
- improve coherence and specificity
- preserve personality consistency
- reduce generic filler
- help salvage useful output from weak candidates
- remain tunable across small models
- degrade gracefully on weaker hardware

---

## 4. Prompt Layers

The full runtime prompt system uses up to five prompt layers:

1. **Base Instruction Layer**
2. **Turn Context Layer**
3. **Memory Cue Layer**
4. **Task Constraint Layer**
5. **Output Shape Layer**

These layers should be short.

---

## 5. Base Instruction Layer

## 5.1 Purpose

Provide the minimum stable behavioral instruction needed for the current call.

This should not be a giant global system prompt.

---

## 5.2 Base Instruction Design

Base instructions should emphasize:

- directness
- relevance
- natural tone
- low fluff
- short output

### Example Base Instruction
```text
Write a concise, natural reply that is specific, useful, and low on fluff.
```

### Slightly Stronger Technical Variant
```text
Write a concise, structured reply that is specific, implementation-friendly, and free of filler.
```

---

## 5.3 Rule

Keep base instruction under roughly 20 tokens when possible.

---

## 6. Turn Context Layer

## 6.1 Purpose

Provide minimal information about what the user currently wants.

This is derived from `InputSketch`.

---

## 6.2 Allowed Fields

- request
- intent
- topic
- tone
- response mode

Do not dump the whole input sketch unless needed.

---

## 6.3 Example
```text
User request: write the Data Structures Spec.md
Intent: technical_spec_request
Topic: data_structures_spec
Tone: focused, practical
Mode: structured_technical
```

---

## 7. Memory Cue Layer

## 7.1 Purpose

Inject only the most useful memory information for the current turn.

Memory cues should be cue-sized, not summary-sized.

---

## 7.2 Allowed Content

- 1 personality cue
- 1 user preference cue
- 1 thread or project cue
- 1 response pattern cue

In most cases, use at most 2–3 total cues.

---

## 7.3 Good Cue Format
```text
Memory cues:
- prefers direct low-fluff responses
- current work centers on lean small-model AI
- schema-first technical writing works well
```

---

## 7.4 Bad Cue Format
```text
Memory cues:
The user historically has preferred, across many previous interactions, a mode of response that tends to be more concise than average and lower in what might be called fluff...
```

---

## 7.5 Rule

Each cue should ideally be under 12 words.

---

## 8. Task Constraint Layer

## 8.1 Purpose

Tell the model exactly what kind of output to produce right now.

This is the most important layer after raw user request.

---

## 8.2 Typical Constraint Types

- goal
- focus list
- avoid list
- depth
- mode
- response length

### Example
```text
Goal: produce a clear structured technical section
Focus: clarity, schema completeness, lean design
Avoid: filler, vague wording, repetition
Length: short
```

---

## 9. Output Shape Layer

## 9.1 Purpose

Give the model a narrow expected output form.

This helps small models avoid rambling and drift.

---

## 9.2 Common Shape Controls

- sentence count
- bullet count
- paragraph count
- section structure
- formatting mode

### Example
```text
Output: 3-5 sentences
```

### Technical Example
```text
Output: markdown section with concise headings and code blocks where needed
```

---

## 10. Prompt Construction Rules

## 10.1 General Rules

Prompts should:

- use labeled fields
- keep line lengths readable
- avoid redundant wording
- avoid repeated commands
- give one main task
- cap examples tightly

---

## 10.2 Prohibited Habits

Avoid prompts that:

- ask for hidden chain-of-thought
- contain repeated synonym instructions
- contain stacked style paragraphs
- include too much old context
- include more than 3 memory cues by default
- overexplain obvious formatting

---

## 10.3 Prompt Ordering Rule

Recommended order:

1. base instruction
2. user request
3. intent/topic/mode
4. goal
5. focus
6. avoid
7. memory cues
8. output shape

This gives the small model a clean flow.

---

## 11. Candidate Generation Templates

## 11.1 Purpose

Used to generate multiple short candidate replies from different angles.

These are the first-pass prompts.

---

## 11.2 Generic Candidate Template

```text
Write one short reply.

User request: {user_request}
Intent: {intent}
Topic: {topic}
Mode: {mode}
Tone: {tone}
Goal: {goal}
Focus: {focus}
Avoid: {avoid}
Memory cues:
{memory_cues}

Output: {output_shape}
```

---

## 11.3 Minimal Candidate Template

Use this for very weak hardware or very simple tasks.

```text
Write one short reply.

User request: {user_request}
Goal: {goal}
Tone: {tone}
Avoid: {avoid}

Output: {output_shape}
```

---

## 11.4 Technical Candidate Template

```text
Write one concise technical response.

User request: {user_request}
Intent: {intent}
Topic: {topic}
Tone: direct, structured
Goal: produce implementation-friendly content
Focus: clarity, specificity, clean structure
Avoid: filler, handwaving, repetition
Memory cues:
{memory_cues}

Output: markdown-ready section
```

---

## 11.5 Supportive Candidate Template

```text
Write one short supportive reply.

User request: {user_request}
Intent: emotional_support
Tone: calm, grounded, human
Goal: validate briefly and offer one useful stabilizing thought
Focus: emotional recognition, one useful thought
Avoid: platitudes, preachiness, robotic tone
Memory cues:
{memory_cues}

Output: 3-5 sentences
```

---

## 11.6 Brainstorm Candidate Template

```text
Write one strong option.

User request: {user_request}
Intent: brainstorming
Tone: clear, energetic
Goal: generate one distinctive high-quality idea
Focus: originality, relevance, punch
Avoid: generic ideas, repetition, overexplaining
Memory cues:
{memory_cues}

Output: one compact option
```

---

## 11.7 Editorial Candidate Template

```text
Rewrite the text cleanly.

User request: {user_request}
Intent: editing_refinement
Tone: sharp, natural
Goal: preserve meaning while improving force and clarity
Focus: precision, rhythm, readability
Avoid: padding, blandness, distortion
Memory cues:
{memory_cues}

Output: one refined version
```

---

## 12. Mode Variants

## 12.1 Candidate Modes

Recommended candidate modes:

- `strict_spec`
- `implementation_friendly`
- `empathic`
- `practical`
- `playful`
- `reflective`
- `editorial_sharp`
- `brainstorm_distinct`

Each mode should change only a small part of the prompt.

---

## 12.2 Example Mode Patch Table

| Mode | Patch |
|---|---|
| `strict_spec` | emphasize structure and precision |
| `implementation_friendly` | emphasize practical clarity |
| `empathic` | emphasize emotional recognition |
| `practical` | emphasize useful next step |
| `playful` | allow light wit and softer energy |
| `reflective` | allow one deeper observation |
| `editorial_sharp` | tighten phrasing and force |
| `brainstorm_distinct` | maximize uniqueness without rambling |

---

## 12.3 Mode Patch Example

Base:
```text
Tone: grounded, direct
Goal: produce one useful answer
```

Patched for `empathic`:
```text
Tone: calm, warm, human
Goal: make the user feel understood and offer one useful thought
```

Patched for `strict_spec`:
```text
Tone: direct, technical, structured
Goal: produce a clear implementation-friendly section
```

---

## 13. Refine Prompt Templates

## 13.1 Purpose

Used after fragment extraction to build one strong final reply from the best pieces.

---

## 13.2 Core Refine Template

```text
Using these useful fragments:
{fragment_lines}

Write one clean response.

Intent: {intent}
Tone: {tone}
Goal: {goal}
Avoid: {avoid}

Output: {output_shape}
```

---

## 13.3 Technical Refine Template

```text
Using these useful fragments:
{fragment_lines}

Write one clean technical response.

Intent: technical_spec_request
Tone: direct, structured
Goal: produce a clear implementation-ready section
Avoid: filler, vagueness, redundancy

Output: markdown-ready section
```

---

## 13.4 Supportive Refine Template

```text
Using these useful fragments:
{fragment_lines}

Write one clean supportive reply.

Tone: calm, grounded, human
Goal: validate briefly and offer one stabilizing thought
Avoid: generic reassurance, robotic tone, repetition

Output: 3-5 sentences
```

---

## 13.5 Refine Rules

Refine prompts should:

- include only top fragments
- use 3–5 fragments by default
- remove redundant fragments before insertion
- remain shorter than candidate prompts when possible

---

## 14. Repair Prompt Templates

## 14.1 Purpose

Used only when the refined output still fails quality thresholds.

Repair should be cheap and direct.

---

## 14.2 Core Repair Template

```text
Write one direct response.

User request: {user_request}
Intent: {intent}
Tone: {tone}
Goal: {goal}
Memory cues:
{memory_cues}

Avoid generic wording. Keep it specific and useful.
Output: {output_shape}
```

---

## 14.3 Minimal Repair Template

```text
Write one clean direct answer.

User request: {user_request}
Goal: {goal}
Avoid: generic wording, fluff

Output: {output_shape}
```

---

## 14.4 Rule

Repair prompts should be more constrained than first-pass prompts.

---

## 15. Writeback Support Prompts

## 15.1 Purpose

Optional lightweight prompts for summarizing new durable memory or episode records when heuristic summarization is not enough.

Use sparingly.

---

## 15.2 Episode Summary Prompt

```text
Summarize the conversation moment in one short memory line.

User request: {user_request}
Final response: {final_response}

Output: one compact summary under 20 words
```

---

## 15.3 Preference Inference Prompt

```text
Infer one durable user preference only if strongly supported.

User request: {user_request}
Context: {context_hint}

Output:
- preference summary
or
- none
```

---

## 15.4 Fact Inference Prompt

```text
Extract one durable user fact only if clearly stated.

User request: {user_request}

Output:
- fact summary
or
- none
```

---

## 15.5 Rule

Prefer rule-based writeback creation first.  
Use model-assisted writeback only if it stays cheaper than the quality gain.

---

## 16. Personality Prompting Strategy

## 16.1 Goal

Maintain personality consistency without wasting tokens on giant persona prose.

---

## 16.2 Recommended Personality Injection Style

Use short cue-style personality anchors:

```text
Style: calm, perceptive, concise, natural, low-fluff
```

or

```text
Tone: warm, grounded, direct
```

Avoid giant character descriptions in normal runtime prompts.

---

## 16.3 Personality Injection Budget

Default:
- 4 to 8 words of style cueing

High need:
- up to 15 words

Avoid:
- paragraphs

---

## 17. Memory Cue Formatting Rules

## 17.1 Cue Selection Priority

Order of preference:

1. user preference cue
2. active thread cue
3. response pattern cue
4. user fact cue

Do not include all unless needed.

---

## 17.2 Cue Formatting Function

Recommended function behavior:

```python
def format_memory_cues(cues: list[str], max_count: int = 3) -> str:
    selected = cues[:max_count]
    return "\n".join([f"- {cue}" for cue in selected])
```

---

## 17.3 Cue Compression Examples

Long:
```text
The user has repeatedly shown a tendency to prefer responses that are fairly direct and not too padded.
```

Compressed:
```text
- prefers direct low-fluff responses
```

Long:
```text
The user's current project centers around building a lean architecture for tiny local AI models.
```

Compressed:
```text
- current work centers on lean small-model AI
```

---

## 18. Output Shape Templates

## 18.1 Common Shapes

### Sentence-Limited
```text
Output: 3-5 sentences
```

### Bullet-Limited
```text
Output: 3 concise bullet points
```

### Single Option
```text
Output: one compact option
```

### Markdown Section
```text
Output: markdown-ready section with short headings
```

### Rewrite Only
```text
Output: one rewritten version only
```

---

## 18.2 Rule

Always choose the narrowest shape that fits the task.

---

## 19. Token Discipline Rules

## 19.1 Token Budget Priorities

Spend tokens on:
- task clarity
- best memory cues
- strong avoid list
- shape control

Avoid spending tokens on:
- long style lore
- full histories
- repeated phrasing instructions
- many examples
- broad philosophical framing

---

## 19.2 Prompt Length Targets

Suggested targets:

| Prompt Type | Target Size |
|---|---:|
| minimal candidate | 35–70 tokens |
| standard candidate | 60–110 tokens |
| technical candidate | 70–130 tokens |
| refine | 50–100 tokens plus fragments |
| repair | 35–80 tokens |
| writeback support | 20–50 tokens |

These are guidelines, not hard laws.

---

## 19.3 Fragment Budget

For refine prompts:
- default fragment count: `3`
- maximum fragment count: `5`

Only include more if the response genuinely needs it.

---

## 20. Examples

## 20.1 Technical Candidate Example

```text
Write one concise technical response.

User request: write the Data Structures Spec.md
Intent: technical_spec_request
Topic: data_structures_spec
Tone: direct, structured
Goal: produce implementation-friendly content
Focus: clarity, specificity, clean structure
Avoid: filler, handwaving, repetition
Memory cues:
- prefers direct low-fluff responses
- current work centers on lean small-model AI
- schema-first technical writing works well

Output: markdown-ready section
```

---

## 20.2 Supportive Candidate Example

```text
Write one short supportive reply.

User request: I’m exhausted by this project. Every time I fix one thing, three more break.
Intent: emotional_support
Tone: calm, grounded, human
Goal: validate briefly and offer one useful stabilizing thought
Focus: emotional recognition, one useful thought
Avoid: platitudes, preachiness, robotic tone
Memory cues:
- prefers direct low-fluff responses
- current thread involves repeated project strain

Output: 3-5 sentences
```

---

## 20.3 Refine Example

```text
Using these useful fragments:
- you sound worn down by cumulative friction
- this looks structural, not personal
- finding the shared fault layer may save energy

Write one clean response.

Intent: emotional_support
Tone: calm, grounded, human
Goal: validate briefly and offer one stabilizing thought
Avoid: generic reassurance, robotic tone, repetition

Output: 3-5 sentences
```

---

## 20.4 Repair Example

```text
Write one direct response.

User request: give me a technical version
Intent: editing_refinement
Tone: direct, structured
Goal: rewrite the sentence in a more technical style
Memory cues:
- prefers direct low-fluff responses

Avoid generic wording. Keep it specific and useful.
Output: one rewritten version only
```

---

## 21. Prompt Assembly Algorithms

## 21.1 Candidate Prompt Builder

```python
def build_candidate_prompt(
    user_request: str,
    intent: str,
    topic: str,
    mode: str,
    tone: str,
    goal: str,
    focus: list[str],
    avoid: list[str],
    memory_cues: list[str],
    output_shape: str,
) -> str:
    cue_block = "\n".join([f"- {cue}" for cue in memory_cues[:3]])

    return f"""Write one short reply.

User request: {user_request}
Intent: {intent}
Topic: {topic}
Mode: {mode}
Tone: {tone}
Goal: {goal}
Focus: {", ".join(focus[:3])}
Avoid: {", ".join(avoid[:3])}
Memory cues:
{cue_block}

Output: {output_shape}
"""
```

---

## 21.2 Refine Prompt Builder

```python
def build_refine_prompt(
    fragments: list[str],
    intent: str,
    tone: str,
    goal: str,
    avoid: list[str],
    output_shape: str,
) -> str:
    fragment_block = "\n".join([f"- {frag}" for frag in fragments[:5]])

    return f"""Using these useful fragments:
{fragment_block}

Write one clean response.

Intent: {intent}
Tone: {tone}
Goal: {goal}
Avoid: {", ".join(avoid[:3])}

Output: {output_shape}
"""
```

---

## 21.3 Repair Prompt Builder

```python
def build_repair_prompt(
    user_request: str,
    intent: str,
    tone: str,
    goal: str,
    memory_cues: list[str],
    output_shape: str,
) -> str:
    cue_block = "\n".join([f"- {cue}" for cue in memory_cues[:2]])

    return f"""Write one direct response.

User request: {user_request}
Intent: {intent}
Tone: {tone}
Goal: {goal}
Memory cues:
{cue_block}

Avoid generic wording. Keep it specific and useful.
Output: {output_shape}
"""
```

---

## 22. Failure Modes

| Failure Mode | Likely Prompt Cause | Fix |
|---|---|---|
| generic output | weak goal, weak avoid list | tighten goal and anti-generic wording |
| rambling | no output shape constraint | add sentence or structure limit |
| personality drift | no style cues | inject short personality cue |
| repetitive answers | too much reused phrasing | rotate candidate modes and vary focus |
| weak specificity | vague focus terms | use stronger focus labels like `schema completeness` or `one useful insight` |
| prompt too expensive | too many cues or examples | reduce memory cues and remove examples |

---

## 23. Testing Prompt Quality

## 23.1 Test Dimensions

Evaluate prompts for:

- brevity
- clarity
- consistency
- response quality
- low genericness
- token cost
- stability across runs

---

## 23.2 Example Tests

- does the minimal candidate template outperform raw user text alone?
- do 2 memory cues outperform 4?
- does a refine prompt improve weak candidates consistently?
- does the repair template reduce generic filler?
- does personality stay stable without long persona blocks?

---

## 24. Recommended Prompt Hierarchy

Default runtime priority:

1. **technical candidate template**
2. **generic candidate template**
3. **refine template**
4. **repair template**
5. **minimal template** for low-power fallback

This keeps the system simple and predictable.

---

## 25. Recommended File Layout

```text
prompts/
├── candidate_generic.md
├── candidate_minimal.md
├── candidate_technical.md
├── candidate_supportive.md
├── candidate_brainstorm.md
├── candidate_editorial.md
├── refine_generic.md
├── refine_technical.md
├── refine_supportive.md
├── repair_generic.md
├── writeback_episode.md
├── writeback_preference.md
└── writeback_fact.md
```

---

## 26. Implementation Notes

## 26.1 Favor Small Stable Templates

A small set of stable, well-tested templates is better than dozens of overlapping prompt variants.

## 26.2 Tune Templates with Real Data

Prompt tuning should be based on:
- actual user conversations
- latency measurements
- genericness reduction
- final response quality

## 26.3 Keep Prompts Readable

Human-readable prompts are easier to debug, compress, and improve.

## 26.4 Do Not Over-Specialize Early

Start with:
- generic
- technical
- supportive
- editorial
- refine
- repair

Only add new templates when a real gap appears.

---

## 27. Recommended Next Spec

After this document, the clean next spec is:

1. **Retrieval and Scoring Spec**
2. **Memory Lifecycle and Pruning Spec**
3. **Runtime Config Spec**
4. **MVP Build Order Checklist**
5. **Latency and Token Budget Tuning Guide**

---

## 28. Final Guiding Principle

Prompting in MindSpark: ThoughtForge is not about making tiny models pretend to be giant models.

It is about giving them:

- a narrow task
- the right cues
- a clean goal
- a tight shape
- just enough memory
- just enough personality
- and no wasted words

That is how prompt engineering stays lean, fast, and powerful on small local systems.
