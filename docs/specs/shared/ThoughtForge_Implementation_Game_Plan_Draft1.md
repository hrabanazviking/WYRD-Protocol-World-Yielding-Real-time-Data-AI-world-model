# ThoughtForge Implementation Game Plan
## Massive Structured Blueprint for MindSpark: ThoughtForge


**Version:** Draft v1  
**Target:** Small-model conversation engine (<4GB RAM, CPU/IGPU)  
**Core Philosophy:** Guided memory, lean cognition, fragment salvage, deterministic steering


---


## 1. Vision & Architecture Overview


### 1.1. The Third Path Principles
- **Self-Reliance:** No API calls; fully local.
- **Rune-Forged Precision:** Structured cognition scaffolds (prompt templates, state machines).
- **Fragment Salvage:** Combine best parts of multiple generations.
- **Iron-Clad Efficiency:** 8-bit quantization, <4GB VRAM, ~200 internal tokens/turn.


### 1.2. High-Level Architecture
```


┌─────────────────────────────────────────────────────────────┐
│                     Orchestrator (Python)                    │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐ │
│  │ Memory    │  │ Cognition │  │ Generator │  │ Salvager  │ │
│  │ Manager   │◄─┤ Steerer   │─►│ (LM)      │─►│ (Fragment │ │
│  └───────────┘  └───────────┘  └───────────┘  │  Combiner)│ │
│        ▲              ▲              ▲         └───────────┘ │
│        └──────────────┴──────────────┴─────────────────┘    │
│                      │                                       │
│            ┌─────────▼─────────┐                            │
│            │ SQLite Knowledge  │                            │
│            │ Graph + Vector    │                            │
│            └───────────────────┘                            │
└─────────────────────────────────────────────────────────────┘


```


---


## 2. Phase 0: Foundation (Weeks 1–2)


### 2.1. Repository Setup & Tooling
- [ ] Create monorepo with `/src`, `/tests`, `/docs`, `/models`, `/data`
- [ ] Set up Python environment (3.10+) with:
  - `transformers`, `torch`, `onnxruntime` (CPU/DirectML)
  - `sqlite3`, `faiss-cpu` (or `chromadb`)
  - `pytest`, `black`, `mypy`
- [ ] Define project structure:
```


src/
memory/
sqlite_store.py
graph_builder.py
vector_store.py
cognition/
scaffold_manager.py
prompt_templates.py
generation/
turboquant.py
sampler.py
salvage/
fragment_extractor.py
combiner.py
orchestration/
engine.py
utils/
config.py
logger.py


```


### 2.2. Core Data Structures (from Data_Structures_Spec.md)
Implement base classes:
- **TurnContext:** `{user_input, system_prompt, timestamp, memory_snapshot, cognition_state}`
- **MemoryFragment:** `{content, embedding, source, timestamp, importance_score}`
- **CognitionState:** `{intent, mood, topic, active_scaffold, token_budget_used}`
- **SalvagePool:** `{candidates: list[str], scores: list[float], selected_phrases: list[str]}`


### 2.3. TurboQuant Inference Backend (from TurboQuant_Cognition_Blueprint)
- [ ] Load model in 8-bit using `bitsandbytes` or `torch.quantization`
- [ ] Create inference wrapper with:
  - Token budget enforcement (250 max per turn)
  - Temperature / top-p / repetition penalty
  - CPU fallback with ONNX Runtime
- [ ] Benchmark latency on target hardware (Raspberry Pi 4, low-end laptop)


**Milestone:** Basic inference working with a 1B model (e.g., TinyLlama, Phi-2) under 4GB RAM.


---


## 3. Phase 1: Memory System (Weeks 3–4)


### 3.1. SQLite + Graph Memory
- [ ] Design schema (from Data_Structures_Spec.md):
  ```sql
  CREATE TABLE turns (
    id INTEGER PRIMARY KEY,
    timestamp DATETIME,
    user_input TEXT,
    response TEXT,
    cognition_state_json TEXT
  );
  CREATE TABLE fragments (
    id INTEGER PRIMARY KEY,
    content TEXT,
    embedding BLOB,  -- optional, can be separate vector store
    importance REAL,
    turn_id INTEGER,
    FOREIGN KEY(turn_id) REFERENCES turns(id)
  );
  CREATE TABLE entities (
    id INTEGER PRIMARY KEY,
    name TEXT,
    type TEXT
  );
  CREATE TABLE relations (
    entity1_id INTEGER,
    entity2_id INTEGER,
    relation_type TEXT,
    turn_id INTEGER
  );
```


· Implement MemoryManager class:
  · store_turn(user_input, response, fragments)
  · retrieve_relevant(user_input, top_k=5) using hybrid search (keyword + vector)
  · build_entity_graph() for conversation topics


3.2. Vector Store Integration


· Use sentence-transformers/all-MiniLM-L6-v2 for embeddings (lightweight)
· Implement FAISS index (or SQLite sqlite-vec extension) for fast retrieval
· Add periodic importance scoring (TF‑IDF + recency)


3.3. Wikidata ETL Pipeline (from Detailed_Wikidata_ETL_Pipeline)


· Optional: download a small Wikidata subset (e.g., people, places) into SQLite
· Create import script to map entities to local knowledge graph
· Enable --with-wikidata flag for enhanced general knowledge


Milestone: Memory system can recall past conversation details and answer factual questions using stored knowledge.


---


4. Phase 2: Cognition Steering (Weeks 5–6)


4.1. Scaffold Templates (from Algorithms_and_Pseudocode_Spec)


Implement deterministic prompt scaffolds:


```python
SCAFFOLDS = {
    "casual_chat": """
You are a helpful AI. Respond naturally to the user.
Current memory context: {memory_summary}
User: {user_input}
AI:""",
    "deep_think": """
Break down the user's question step by step.
1. Restate the question.
2. List key concepts.
3. Synthesize answer.
User: {user_input}
AI:""",
    "creative": """
Write a poetic, imaginative response.
Use metaphors inspired by Norse mythology.
User: {user_input}
AI:"""
}
```


4.2. Cognition State Machine


· State transitions: idle → listening → processing → generating → salvaging → responding
· Intent classifier (simple keyword + embedding) to select scaffold
· Token budget manager: limit internal generation to ~180 tokens, enforce truncation


4.3. Multi-Turn Consistency


· Inject last 3 turns of memory into prompt (context window)
· Maintain persona key-value store (user preferences, traits)
· Use CognitionState to persist mood/topic across turns


Milestone: Model responds with consistent persona and scaffold selection, staying under token budget.


---


5. Phase 3: Fragment Salvage & Refinement (Weeks 7–8)


5.1. Fragment Extraction (from Algorithms_and_Pseudocode_Spec)


· Generate N candidate responses (N=2–4) with different temperature settings
· Extract fragments (sentences/clauses) from each candidate
· Score fragments by:
  · Semantic similarity to user input
  · Coherence with previous context
  · Diversity (avoid repetition)
· Implement FragmentSalvager with scoring function


5.2. Fragment Combiner


· Combine top-scoring fragments into a single response
· Ensure grammatical coherence (simple concatenation with re‑ordering)
· Fallback to best full candidate if combination fails


5.3. Self-Correction Loop


· Evaluate final response for quality (relevance, toxicity, length)
· If poor, regenerate using different scaffold
· Log salvage metrics for tuning


Milestone: Responses are consistently better than single‑pass generation in blind tests.


---


6. Phase 4: Optimization & Edge Deployment (Weeks 9–10)


6.1. Quantization & Compression


· Apply TurboQuant: 4‑bit or 8‑bit quantization using llama.cpp or AutoGPTQ
· Convert to ONNX for CPU inference (optional DirectML for Windows)
· Memory profiling: target <3GB RAM for 3B model


6.2. Packaging


· Create Docker image with all dependencies
· Build simple CLI (thoughtforge --model tinyllama --memory on)
· Optional web UI using Streamlit


6.3. Testing on Edge Hardware


· Raspberry Pi 4 (4GB) – CPU inference
· Old laptop (Intel i5, 8GB) – integrated GPU via OpenVINO
· Pine64 or similar ARM device


Milestone: Runs smoothly on at least two edge platforms with <4GB RAM.


---


7. Phase 5: Advanced Features & Refinement (Weeks 11–12)


7.1. Knowledge Graph Integration (from Alternative_Knowledge_Graphs)


· Integrate local graph databases (SQLite + networkx) for entity relationship queries
· Allow user to insert custom facts (e.g., "I like jazz")
· Query graph for contextual grounding


7.2. Multi-Modal Support (Future)


· Placeholder for image input (via BLIP captioning) or voice (whisper.cpp)


7.3. Continuous Learning


· User feedback loop (thumbs up/down) to adjust scaffold weights
· Periodic knowledge consolidation (summarize old turns into memory fragments)


Milestone: Feature‑complete v1 ready for alpha testers.


---


8. Testing & Quality Assurance


8.1. Unit Tests


· Each module (memory, cognition, generation, salvage) covered with pytest.


8.2. Integration Tests


· End‑to‑end conversation simulation with predefined dialogues.
· Performance benchmarks: tokens/sec, memory usage, latency.


8.3. User Testing


· Invite community from RuneForgeAI to test on their hardware.
· Gather feedback on personality, coherence, and efficiency.


---


9. Documentation & Release


9.1. User Docs


· Installation guide (pip, docker, from source)
· Configuration options (model selection, memory path, quantization flags)
· Quickstart tutorial (CLI and web UI)


9.2. Developer Docs


· Architecture overview (as above)
· API reference for each module
· Contribution guidelines


9.3. Release v1.0


· Tagged release on GitHub
· Pre‑built binaries (Windows/Linux/macOS) via GitHub Actions
· Announce on Reddit, Discord, and AI‑focused forums


---


10. Roadmap Beyond v1


Milestone Target Description
v1.1 Q3 2026 Add voice input/output (whisper.cpp, TTS)
v1.2 Q4 2026 Local fine‑tuning on user data (LoRA)
v2.0 2027 Full graph‑based memory with reasoning (RDF)


---


11. Contribution & Collaboration


We welcome contributors in:


· Quantization & inference optimization (llama.cpp, ONNX, OpenVINO)
· Memory/vector store (FAISS, SQLite extensions)
· NLP & prompt engineering (scaffold design, evaluation)
· UI/UX (web interface, mobile app)
· Testing (hardware compatibility, benchmarking)


Join the forge at GitHub Discussions.


---


This game plan synthesizes the research from all spec documents in the repository. For detailed pseudocode and data structures, refer to the original files.


```


This MD file provides a complete, actionable plan spanning architecture, implementation phases, testing, and community collaboration. It can be saved as `GAME_PLAN.md` and used as the project roadmap. Let me know if you need any sections expanded or additional details.