# Ultra-Lean Personality Agent Spec
## TurboQuant + Guided Memory Cognition for Small-Model Conversation Systems


**Document Type:** Planning / Architecture Spec  
**Status:** Draft v1  
**Target Use:** Local or low-resource AI personality chatbot agent  
**Primary Goal:** Achieve strong conversational quality with a very small model (~1B) by offloading steering, continuity, and quality control into ultra-light memory and cognition systems.


---


## 1. Overview


This document defines a **lean conversational architecture** for a highly efficient AI personality agent designed to run on **weak hardware with very low memory budgets**.


The design assumes that a small language model is not powerful enough by itself to sustain consistently strong conversation quality. Instead, the model is treated as one component inside a larger system that does most of the heavy lifting through:


- compressed memory
- guided cognition scaffolds
- lightweight retrieval
- multi-candidate micro-generation
- salvage of useful fragments from imperfect outputs
- strict token austerity
- quantized inference via **TurboQuant**


The system does **not** depend on long prompts, large context windows, verbose reasoning chains, or expensive multi-stage orchestration.


It is optimized for:


- low RAM / VRAM
- low token use
- fast response time
- high personality consistency
- low hardware requirements
- improved conversational quality per unit of compute


---


## 2. Core Design Principles


### 2.1 Intelligence Through Orchestration
The model is not the whole intelligence layer. The architecture itself provides:
- conversational steering
- continuity
- prioritization
- refinement
- personality reinforcement


### 2.2 Memory Over Brute Force
Instead of demanding deep raw reasoning from a 1B model, the system uses:
- relevant memory comparisons
- compressed user preferences
- prior successful response patterns
- lightweight cognition notes


### 2.3 Salvage Over Rejection
Weak generations are not discarded just because they contain bad generalizations or filler.  
The system extracts the useful parts, discards weak parts, and regenerates around the strong fragments.


### 2.4 Hard Efficiency Constraints
All subsystems must be designed around:
- minimal token use
- minimal active context
- short prompts
- bounded loops
- structured data over prose
- fast retrieval
- low-cost scoring


### 2.5 Good Enough Beats Perfect
The system should stop once the reply is strong enough, coherent enough, and personality-aligned enough.  
It must avoid wasting compute chasing tiny improvements.


---


## 3. System Goals


## 3.1 Functional Goals


- maintain a stable chatbot personality
- provide engaging and coherent conversations
- remember user preferences and relevant prior context
- improve weak model output without expensive inference
- remain useful even when the base model makes flawed generalizations
- preserve tone and continuity across turns


## 3.2 Efficiency Goals


- run on weak hardware
- minimize RAM and VRAM consumption
- minimize prompt length
- minimize internal reasoning overhead
- cap generation and refinement loops
- support aggressive quantization


## 3.3 Behavioral Goals


- do not overcorrect small model mistakes by hard rejection
- keep any useful emotional, structural, or semantic fragments
- refine only when needed
- stay concise unless the user clearly wants more depth
- reduce generic filler as early as possible


---


## 4. Non-Goals


This system is **not** intended to be:


- a giant agent framework with many expensive tools
- a long-context transcript hoarder
- a chain-of-thought-heavy reasoning engine
- a full-scale autonomous planner
- a general-purpose research engine
- a brute-force multi-model debate system


The design is focused on one thing:


**strong conversation quality from very small models using minimal resources**


---


## 5. High-Level Architecture


```text
User Input
  ↓
Input Compression
  ↓
Intent / Tone / Topic Sketch
  ↓
Memory Comparison Engine
  ↓
Guided Cognition Scaffold
  ↓
Short Candidate Generation
  ↓
Fragment Extraction / Salvage
  ↓
Micro-Refinement
  ↓
Final Response
  ↓
Compact Memory Writeback
```


---


## 6. Main Runtime Components


## 6.1 Inference Layer


### Purpose
Run a very small language model efficiently.


### Requirements
- TurboQuant or equivalent ultra-efficient quantized backend
- support 1B-ish instruct/chat models
- support low-bit quantization
- support short prompt / short generation flow
- fast startup and low memory overhead


### Inference Priorities
1. low RAM usage
2. stable latency
3. low token throughput cost
4. deterministic or semi-deterministic response control
5. acceptable quality under aggressive quantization


### Recommendation
Treat the model as a local text composer, not as the primary memory or cognition engine.


---


## 6.2 Input Compression Layer


### Purpose
Reduce raw user input to a compact task sketch.


### Output Fields
- `intent`
- `topic`
- `tone_in`
- `response_mode`
- `memory_triggers`
- `urgency`
- `personality_weight`


### Example
```yaml
intent: emotional_support
topic: repeated technical frustration
tone_in: irritated + tired
response_mode: validating + useful
memory_triggers:
  - prior_project_stress
  - user_prefers_directness
urgency: medium
personality_weight: high
```


### Design Rule
This layer must remain extremely small.  
It should produce a terse structured summary, not a prose analysis.


---


## 6.3 Memory Comparison Engine


### Purpose
Retrieve the smallest possible set of memories that can improve the current reply.


### Memory Classes
- `personality_core`
- `user_profile`
- `episodic_memory`
- `response_patterns`
- `active_thread_state`


### Retrieval Criteria
- semantic similarity
- tone similarity
- intent match
- user-preference relevance
- recency
- importance weight


### Output
A ranked list of the top few memory cues to activate.


### Example
```yaml
activate:
  - calm_direct_style
  - validate_without_patronizing
  - user_dislikes_empty_reassurance
  - ongoing_project_fatigue
```


### Hard Cap
Retrieve only **3 to 5** items.


---


## 6.4 Guided Cognition Layer


### Purpose
Build a tiny steering scaffold before generation.


### Design Rule
This is **not** a long internal monologue and not a large reasoning trace.  
It is a short control object that guides the next generation step.


### Required Fields
- `goal`
- `tone`
- `focus`
- `avoid`
- `depth`
- `candidate_modes`


### Example
```yaml
goal: validate frustration and provide one useful reframing
tone: grounded, warm, direct
focus:
  - emotional recognition
  - one concrete insight
avoid:
  - generic platitudes
  - robotic wording
  - preachy tone
depth: short
candidate_modes:
  - empathic
  - practical
```


### Benefit
A 1B model performs much better when given a very small, very clear mission.


---


## 6.5 Candidate Generation Layer


### Purpose
Generate several short candidate replies rather than one large attempt.


### Why
A small model often produces useful partial output mixed with weak filler.  
Multiple short candidates usually yield more salvageable material than a single long candidate.


### Recommended Candidate Count
- default: `2`
- maximum: `4`


### Candidate Types
- empathic
- practical
- reflective
- lightly playful when appropriate


### Generation Constraints
- short outputs only
- low or moderate temperature
- no long rambling
- tone and personality must be anchored by system cues


---


## 6.6 Salvage-and-Refine Layer


### Purpose
Extract useful content from flawed candidate outputs.


### Core Rule
Do not discard a candidate just because it contains:
- one bad generalization
- some fluff
- weak opening phrasing
- mildly sloppy framing


Instead:
- split it
- score fragments
- preserve useful lines
- regenerate around the strongest parts


### Extraction Unit
Prefer:
- sentence-level extraction
- clause-level extraction if needed


### Fragment Scoring Dimensions
- relevance
- clarity
- emotional usefulness
- personality alignment
- originality
- non-redundancy
- low genericness


### Example
Candidate:
> “A lot of people feel this way, and that’s normal. It sounds like you’re exhausted by repeated friction, not just one isolated issue.”


Keep:
- “you’re exhausted by repeated friction”
- “not just one isolated issue”


Drop:
- “A lot of people feel this way”
- “that’s normal”


---


## 6.7 Final Response Composer


### Purpose
Assemble the strongest cleaned response from extracted fragments.


### Constraints
- concise
- coherent
- personality-aligned
- low fluff
- emotionally appropriate
- useful enough to send


### Stop Condition
Once the reply is clearly good enough, stop refinement and return.


---


## 6.8 Memory Writeback Layer


### Purpose
Store only compact, valuable information from the turn.


### Store
- user preference signals
- topic continuity
- emotional state changes
- successful response pattern markers
- active unresolved thread state
- strong summary of what mattered


### Do Not Store
- full transcript by default
- repetitive low-value details
- generic back-and-forth filler
- every sentence of the final response


### Example
```yaml
id: ep_881
type: episode
tags: [project_stress, direct_support, validation]
summary: user was exhausted by repeated system breakage; concise validating response fit well
quality: 0.82
```


---


## 7. Data Model


## 7.1 Personality Core Record


```yaml
id: personality_core_main
type: personality_core
traits:
  - calm
  - attentive
  - perceptive
  - low_fluff
  - warm
speech_style:
  - natural
  - concise
  - direct
  - grounded
avoid:
  - preachy
  - robotic_disclaimers
  - overexplaining
weight: 1.0
```


---


## 7.2 User Preference Record


```yaml
id: user_pref_204
type: user_profile
tags: [style, tone, directness]
summary: prefers direct calm responses without corporate tone or empty reassurance
weight: 0.91
last_used: 2026-03-29
```


---


## 7.3 Episodic Memory Record


```yaml
id: ep_5501
type: episode
tags: [technical_project, fatigue, frustration]
summary: user reported repeated break-fix cascades causing burnout
tone: frustrated + tired
importance: 0.79
timestamp: 2026-03-29T12:00:00
```


---


## 7.4 Response Pattern Record


```yaml
id: rsp_17
type: response_pattern
tags: [validation, concise_help, grounded_reframing]
summary: brief validation followed by one useful structural insight performs well
quality: 0.88
```


---


## 7.5 Active Thread State Record


```yaml
id: thread_state_current
type: active_thread_state
tags: [project_architecture, fatigue, unresolved]
summary: user is still working through architecture and quality issues in a larger system
priority: 0.86
expires_after_turns: 8
```


---


## 8. Prompt Design Standard


## 8.1 Core Prompt Philosophy
Prompts must be:
- short
- structured
- unambiguous
- task-limited


Avoid:
- long persona prose
- verbose hidden reasoning requests
- raw transcript stuffing
- giant instruction stacks


---


## 8.2 Candidate Prompt Template


```text
You are composing one short reply.


User intent: {intent}
Topic: {topic}
Tone to use: {tone}
Response mode: {response_mode}
Personality cues: {personality_cues}
Relevant user preference: {user_pref}
Goal: {goal}
Avoid: {avoid_list}


Reply in {length_limit}.
```


### Example
```text
You are composing one short reply.


User intent: frustration + support
Topic: repeated technical breakage
Tone to use: calm, grounded, human
Response mode: validating + useful
Personality cues: warm, perceptive, concise
Relevant user preference: dislikes fluff
Goal: validate briefly and offer one useful reframing
Avoid: generic reassurance, preachy tone


Reply in 3-5 sentences.
```


---


## 8.3 Refinement Prompt Template


```text
Using these useful fragments:
- {fragment_1}
- {fragment_2}
- {fragment_3}


Write one clean response.
Tone: {tone}
Style: {style}
Avoid: generic statements, repetition, filler
Length: {length_limit}
```


---


## 9. Retrieval Strategy


## 9.1 Retrieval Flow


1. receive compressed input sketch
2. score memory records
3. sort descending
4. keep top `k`
5. produce activation cues only


### Default `k`
- `3`
### Maximum `k`
- `5`


---


## 9.2 Retrieval Score Formula


```text
score =
  semantic_similarity * 0.35 +
  tone_similarity * 0.20 +
  user_preference_relevance * 0.20 +
  recency * 0.10 +
  importance_weight * 0.15
```


### Notes
- tune weights empirically
- keep formula cheap
- no expensive reranking model unless it is extremely lightweight


---


## 9.3 Retrieval Guardrails
- never retrieve too much
- avoid multiple nearly identical memories
- prefer the most compact relevant records
- collapse duplicates before prompt assembly


---


## 10. Guided Cognition Strategy


## 10.1 Purpose
Provide just enough internal guidance to improve a weak model’s output.


## 10.2 Allowed Scope
The cognition layer may:
- define response goal
- define target tone
- define response shape
- define things to avoid
- propose small candidate modes


The cognition layer should **not**:
- produce long internal essays
- run open-ended reasoning
- consume large token budgets
- become a second chatbot inside the chatbot


---


## 10.3 Example Cognition Objects


### Emotional Support Case
```yaml
goal: make user feel understood and reduce friction
tone: calm, human, direct
focus:
  - emotional recognition
  - one useful thought
avoid:
  - empty comfort
  - dramatic overvalidation
depth: short
candidate_modes:
  - empathic
  - practical
```


### Light Conversation Case
```yaml
goal: be engaging and natural
tone: relaxed, lightly playful
focus:
  - smooth flow
  - small observation
avoid:
  - overanalysis
  - stiffness
depth: short
candidate_modes:
  - playful
  - reflective
```


---


## 11. Candidate and Salvage Pipeline


## 11.1 Candidate Generation
Generate `2-4` short candidates.


## 11.2 Fragment Extraction
Split candidates into sentences or clauses.


## 11.3 Fragment Scoring
Assign score based on:
- relevance
- quality
- tone
- personality fit
- specificity
- low genericness


## 11.4 Best Fragment Selection
Keep top fragments only.


## 11.5 Merge and Refine
Compose one cleaned reply from the best fragments.


## 11.6 Stop or Retry
If the cleaned reply passes threshold:
- return response


If it does not:
- run one more short refinement pass


### Hard Max
- refinement passes: `2`


---


## 12. Quality Evaluation


## 12.1 Final Reply Quality Criteria
A final reply should score well on:
- relevance
- clarity
- coherence
- emotional fit
- personality consistency
- concision
- usefulness
- non-genericness


## 12.2 Good Enough Threshold
Stop when all of the following are true:
- the response fits the user’s tone
- the response clearly addresses the input
- it contains at least one meaningful useful element
- it does not sound robotic
- it does not contain obvious filler overload


### Important
Do not waste cycles polishing beyond practical benefit.


---


## 13. Token Budget Strategy


## 13.1 Design Rule
Every token spent internally must have a clear return.


## 13.2 Budget Priorities
Spend tokens on:
- memory cues
- goal shaping
- concise candidate generation
- fragment-based refinement


Do not spend tokens on:
- bloated system prompts
- full transcript inclusion
- large hidden reasoning chains
- verbose self-analysis


## 13.3 Suggested Per-Turn Budget


| Stage | Suggested Tokens |
|---|---:|
| input sketch | 20-40 |
| memory cues | 20-60 |
| cognition scaffold | 20-40 |
| candidate prompt | 40-80 |
| candidate outputs total | 40-120 |
| refinement prompt | 30-60 |
| final output | 40-120 |


These are guidelines, not rigid limits.


---


## 14. Weak Hardware Operating Constraints


## 14.1 Target Hardware Classes
- older consumer laptops
- low-RAM desktops
- low-power mini PCs
- integrated graphics systems
- CPU-only systems where possible


## 14.2 Runtime Constraints
- short prompt assembly
- quantized model only
- low active memory footprint
- low retrieval count
- low generation count
- bounded refinement


## 14.3 Hard Caps
- retrieved memories: `5`
- candidate replies: `4`
- refinement passes: `2`
- final output target: `<= 180 tokens`
- active thread memory entries: `<= 8`
- per-turn stored writeback: `1-3 compact records`


---


## 15. Recommended File Structure


```text
agent/
├── README.md
├── config/
│   ├── runtime.yaml
│   ├── prompt_limits.yaml
│   └── scoring.yaml
├── memory/
│   ├── personality_core.yaml
│   ├── user_profile_store.jsonl
│   ├── episodic_store.jsonl
│   ├── response_patterns.jsonl
│   └── active_thread_state.json
├── prompts/
│   ├── candidate_prompt.md
│   ├── refine_prompt.md
│   └── cognition_templates.md
├── src/
│   ├── input_compression.py
│   ├── retrieval.py
│   ├── cognition.py
│   ├── generation.py
│   ├── salvage.py
│   ├── scoring.py
│   ├── composer.py
│   └── writeback.py
└── tests/
    ├── test_retrieval.py
    ├── test_salvage.py
    ├── test_scoring.py
    └── test_personality_consistency.py
```


---


## 16. Runtime Pipeline Spec


## 16.1 Turn Processing Pipeline


### Step 1: Ingest
Receive raw user input.


### Step 2: Compress
Convert input to minimal structured intent/tone/topic sketch.


### Step 3: Retrieve
Run cheap memory scoring and retrieve top cues.


### Step 4: Scaffold
Create cognition object for this turn.


### Step 5: Generate
Produce multiple short candidate replies.


### Step 6: Extract
Split candidate text into fragments and score them.


### Step 7: Refine
Regenerate one cleaned reply from top fragments.


### Step 8: Evaluate
Run lightweight quality check.


### Step 9: Return
Send final response to user.


### Step 10: Writeback
Store compact memory summary and any useful preference updates.


---


## 17. Example Full Turn


### Raw User Input
> I’m exhausted by this project. Every time I fix one thing, three more break.


### Input Sketch
```yaml
intent: emotional_support + practical_help
topic: cascading technical failures
tone_in: frustrated + tired
response_mode: validating + useful
memory_triggers:
  - project_stress
  - directness_preference
urgency: medium
personality_weight: high
```


### Retrieved Cues
```yaml
activate:
  - concise_grounded_support
  - user_dislikes_empty_reassurance
  - prior_system_fatigue_context
```


### Cognition Scaffold
```yaml
goal: validate exhaustion and offer one structural reframing
tone: calm, direct, human
focus:
  - emotional recognition
  - one practical insight
avoid:
  - platitudes
  - overtalking
depth: short
candidate_modes:
  - empathic
  - practical
```


### Extracted Fragments
- repeated friction is burning energy
- this sounds architectural, not personal
- chasing symptoms may be making it worse


### Final Reply
You sound worn down by cumulative friction, not just a single bad bug. When every fix triggers more failures, that usually points to system strain rather than you doing anything wrong. It may help to pause symptom-chasing and look for the shared layer underneath the breakage. That kind of reset often saves more energy than pushing harder.


---


## 18. Implementation Tasks


## 18.1 Phase 1: Minimum Viable System
- [ ] integrate TurboQuant-backed small model runtime
- [ ] create compressed personality core format
- [ ] implement input compression module
- [ ] implement memory store format
- [ ] implement cheap retrieval scoring
- [ ] implement cognition scaffold generator
- [ ] implement 2-candidate generation
- [ ] implement simple fragment extractor
- [ ] implement one-pass refinement
- [ ] implement compact memory writeback


## 18.2 Phase 2: Quality Upgrade
- [ ] add response pattern memory
- [ ] improve fragment scoring
- [ ] add non-genericness scoring
- [ ] add personality consistency scoring
- [ ] add adaptive response modes
- [ ] add short active thread state manager


## 18.3 Phase 3: Efficiency Upgrade
- [ ] add retrieval deduplication
- [ ] add caching for common cognition scaffolds
- [ ] add precomputed vector or hashed similarity support
- [ ] add memory decay and pruning
- [ ] add latency instrumentation
- [ ] tune prompt budgets empirically


---


## 19. Testing Strategy


## 19.1 Core Test Categories
- retrieval relevance
- personality consistency
- non-genericness
- token budget compliance
- salvage effectiveness
- memory writeback quality
- latency stability on weak hardware


## 19.2 Example Tests
- does the system retrieve the right preference memory?
- does it avoid over-injecting memory?
- does fragment salvage improve weak candidates?
- does final output remain concise?
- does the reply preserve personality traits across turns?
- does the system stop refining once output is good enough?


---


## 20. Metrics


## 20.1 Quality Metrics
- user-rated helpfulness
- personality stability
- emotional appropriateness
- coherence across turns
- reduction in generic filler
- salvage success rate


## 20.2 Efficiency Metrics
- average prompt tokens per turn
- average completion tokens per turn
- total internal tokens per turn
- average latency
- RAM usage
- model memory footprint
- refinement pass frequency


## 20.3 System Health Metrics
- retrieval duplication rate
- writeback noise rate
- overlong response rate
- failed salvage rate


---


## 21. Failure Modes and Fixes


| Failure Mode | Cause | Fix |
|---|---|---|
| personality drift | weak personality anchoring | reinforce core traits and response-pattern memory |
| generic filler | vague prompts or insufficient filtering | shorten prompts, score fragments harder |
| excessive latency | too many candidates or long outputs | lower candidate count and output length |
| weak continuity | bad writeback or retrieval | improve episodic summaries and active thread state |
| robotic tone | poor response pattern examples | store more successful natural outputs |
| over-refinement | no stop threshold | enforce good-enough threshold and hard pass cap |


---


## 22. Extension Ideas


These are optional and should only be added if they do not break the lean design:


- lightweight mood-state adaptation
- tiny long-term topic preference clustering
- per-user response format tuning
- specialized micro-prompts by conversation mode
- compact style imitation from accepted outputs
- local scoring heuristics trained from successful conversations


---


## 23. Final Guiding Principle


This architecture is built on the idea that **a small model can converse far above its weight class if the system around it does the steering**.


The model should not be forced to:
- remember everything
- reason about everything
- phrase everything perfectly in one pass


Instead, the system should:
- reduce ambiguity
- recall the right memory
- constrain the task
- generate small candidates
- salvage the good
- refine only a little
- store only what matters


That is how a 1B-class model becomes genuinely effective on weak hardware.


---


## 24. Recommended Next Document


After this spec, the next most useful document would be:


1. **Data Structures Spec**
2. **Prompt Templates Spec**
3. **Algorithm Pseudocode Spec**
4. **MVP Build Order Checklist**
5. **Latency and Token Budget Tuning Guide**
