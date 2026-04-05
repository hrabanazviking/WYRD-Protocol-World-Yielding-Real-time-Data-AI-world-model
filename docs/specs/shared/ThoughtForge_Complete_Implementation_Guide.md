# ThoughtForge: Complete Implementation Guide 15f5kb


A 50‑Page Code & Architecture Compendium


Version: 1.0
Date: March 2026
License: CC BY 4.0
Author: RuneForgeAI


This document contains the full source code, configuration examples, and architectural details for MindSpark: ThoughtForge – a rune‑forged conversation engine for tiny local models.
It is structured as a ready‑to‑implement reference. All code is written in Python 3.10+ and uses standard libraries plus a few key dependencies (transformers, torch, sqlite3, faiss‑cpu, etc.).


---


Table of Contents


1. Project Overview
2. Environment & Dependencies
3. Core Data Structures
4. Memory System
   · SQLite Schema
   · Vector Store (FAISS)
   · Graph Builder
   · Memory Manager
5. Cognition Steering
   · Scaffold Manager
   · State Machine
   · Intent Classifier
6. Generation Engine
   · TurboQuant Wrapper
   · Sampler
   · Quantization Support
7. Fragment Salvage
   · Fragment Extractor
   · Combiner
   · Self‑Correction Loop
8. Orchestration Engine
9. Optional: Wikidata ETL
10. Optional: Alternative Knowledge Graphs
11. CLI & Web UI
12. Testing & Benchmarking
13. Deployment & Packaging
14. Extension Features
    · Voice I/O (Whisper.cpp + TTS)
    · Local Fine‑tuning (LoRA)
    · Multi‑modal Input
15. Conclusion & Contribution


---


1. Project Overview


ThoughtForge is a lightweight, deterministic framework that acts as a "cognitive exoskeleton" for small language models (1B–3B parameters). It uses:


· Guided memory – persistent SQLite + vector storage.
· Lean cognition – structured prompts (scaffolds) and state machines.
· Fragment salvage – combine best parts of multiple generations.
· TurboQuant – aggressive quantization for edge devices.


The system is fully local, no external APIs.


---


2. Environment & Dependencies


Create a requirements.txt:


```txt
torch>=2.0.0
transformers>=4.35.0
accelerate>=0.25.0
bitsandbytes>=0.41.0  # for quantization
faiss-cpu>=1.7.4
sentence-transformers>=2.2.0
numpy>=1.24.0
scipy>=1.10.0
pydantic>=2.0.0
sqlite3  # built-in
click>=8.1.0   # CLI
streamlit>=1.28.0   # optional web UI
```


Install with:


```bash
pip install -r requirements.txt
```


---


3. Core Data Structures


We define Pydantic models for type safety and serialization.


src/data_models.py


```python
from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
import numpy as np


class TurnContext(BaseModel):
    user_input: str
    system_prompt: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    memory_snapshot: Optional[Dict[str, Any]] = None
    cognition_state: Optional[Dict[str, Any]] = None


class MemoryFragment(BaseModel):
    content: str
    embedding: Optional[List[float]] = None   # or numpy array
    source: str                               # "user" or "assistant"
    timestamp: datetime = Field(default_factory=datetime.now)
    importance: float = 1.0
    turn_id: Optional[int] = None


class CognitionState(BaseModel):
    intent: str = "chat"           # "chat", "question", "creative", ...
    mood: str = "neutral"          # "neutral", "playful", "serious"
    topic: Optional[str] = None
    active_scaffold: str = "default"
    token_budget_used: int = 0
    persona: Dict[str, Any] = Field(default_factory=dict)


class SalvagePool(BaseModel):
    candidates: List[str] = Field(default_factory=list)
    scores: List[float] = Field(default_factory=list)
    selected_phrases: List[str] = Field(default_factory=list)


# For database records, we'll use SQLite rows; these models help with serialization.
```


---


4. Memory System


4.1 SQLite Schema


src/memory/sqlite_store.py


```python
import sqlite3
import json
from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime


class SQLiteStore:
    def __init__(self, db_path: str = "thoughtforge.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()


    def _init_tables(self):
        with self.conn:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    user_input TEXT NOT NULL,
                    response TEXT NOT NULL,
                    cognition_state_json TEXT
                );


                CREATE TABLE IF NOT EXISTS fragments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    embedding BLOB,          -- optional, can be stored separately
                    importance REAL DEFAULT 1.0,
                    source TEXT,             -- 'user' or 'assistant'
                    turn_id INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(turn_id) REFERENCES turns(id)
                );


                CREATE TABLE IF NOT EXISTS entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    type TEXT
                );


                CREATE TABLE IF NOT EXISTS relations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity1_id INTEGER,
                    entity2_id INTEGER,
                    relation_type TEXT,
                    turn_id INTEGER,
                    FOREIGN KEY(entity1_id) REFERENCES entities(id),
                    FOREIGN KEY(entity2_id) REFERENCES entities(id),
                    FOREIGN KEY(turn_id) REFERENCES turns(id)
                );
            """)


    def store_turn(self, user_input: str, response: str, cognition_state: Dict[str, Any]) -> int:
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO turns (timestamp, user_input, response, cognition_state_json) VALUES (?, ?, ?, ?)",
                (datetime.now(), user_input, response, json.dumps(cognition_state))
            )
            turn_id = cursor.lastrowid
        return turn_id


    def store_fragment(self, fragment: Dict[str, Any]) -> int:
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO fragments (content, embedding, importance, source, turn_id) VALUES (?, ?, ?, ?, ?)",
                (fragment['content'], fragment.get('embedding'), fragment.get('importance', 1.0),
                 fragment.get('source'), fragment.get('turn_id'))
            )
            return cursor.lastrowid


    def get_recent_turns(self, limit: int = 5) -> List[sqlite3.Row]:
        cursor = self.conn.execute(
            "SELECT * FROM turns ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        return cursor.fetchall()


    def get_turn(self, turn_id: int) -> Optional[sqlite3.Row]:
        cursor = self.conn.execute("SELECT * FROM turns WHERE id = ?", (turn_id,))
        return cursor.fetchone()
```


4.2 Vector Store (FAISS)


src/memory/vector_store.py


```python
import faiss
import numpy as np
import pickle
from pathlib import Path
from typing import List, Tuple, Optional


class VectorStore:
    def __init__(self, dim: int = 384, index_path: Optional[str] = None):
        self.dim = dim
        self.index = faiss.IndexFlatL2(dim)
        self.id_to_fragment_id = []  # list mapping index position to fragment id
        if index_path and Path(index_path).exists():
            self.load(index_path)


    def add(self, embeddings: np.ndarray, fragment_ids: List[int]):
        # embeddings: (n, dim) numpy array float32
        if embeddings.shape[0] != len(fragment_ids):
            raise ValueError("Mismatch between embeddings and fragment_ids count")
        self.index.add(embeddings)
        self.id_to_fragment_id.extend(fragment_ids)


    def search(self, query_emb: np.ndarray, k: int = 5) -> Tuple[np.ndarray, np.ndarray]:
        # Returns distances, indices
        distances, indices = self.index.search(query_emb, k)
        # indices are positions in the index; convert to fragment_ids
        fragment_ids = [[self.id_to_fragment_id[i] for i in row] for row in indices]
        return distances, fragment_ids


    def save(self, path: str):
        faiss.write_index(self.index, f"{path}.faiss")
        with open(f"{path}.meta", "wb") as f:
            pickle.dump(self.id_to_fragment_id, f)


    def load(self, path: str):
        self.index = faiss.read_index(f"{path}.faiss")
        with open(f"{path}.meta", "rb") as f:
            self.id_to_fragment_id = pickle.load(f)
```


4.3 Graph Builder


src/memory/graph_builder.py


```python
import sqlite3
from typing import List, Tuple
import networkx as nx


class GraphBuilder:
    def __init__(self, db_path: str):
        self.db_path = db_path


    def build_graph(self, turn_id: int = None) -> nx.Graph:
        """Build a graph of entities mentioned in conversation."""
        conn = sqlite3.connect(self.db_path)
        G = nx.Graph()
        if turn_id:
            # Query relations for a specific turn
            rows = conn.execute("""
                SELECT e1.name AS e1, e2.name AS e2, r.relation_type
                FROM relations r
                JOIN entities e1 ON r.entity1_id = e1.id
                JOIN entities e2 ON r.entity2_id = e2.id
                WHERE r.turn_id = ?
            """, (turn_id,)).fetchall()
        else:
            # All relations
            rows = conn.execute("""
                SELECT e1.name AS e1, e2.name AS e2, r.relation_type
                FROM relations r
                JOIN entities e1 ON r.entity1_id = e1.id
                JOIN entities e2 ON r.entity2_id = e2.id
            """).fetchall()
        for e1, e2, rel in rows:
            G.add_edge(e1, e2, relation=rel)
        conn.close()
        return G


    def extract_entities_from_text(self, text: str) -> List[str]:
        """Simple entity extraction using NER from spaCy (optional). For now, basic keyword split."""
        # Placeholder: you can integrate a lightweight NER like `flair` or `transformers`.
        # For simplicity, we split by spaces and take capitalized words.
        import re
        words = re.findall(r'\b[A-Z][a-z]+\b', text)
        return list(set(words))


    def add_entity(self, name: str, entity_type: str = "unknown") -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "INSERT OR IGNORE INTO entities (name, type) VALUES (?, ?)",
            (name, entity_type)
        )
        conn.commit()
        # Get id
        cursor = conn.execute("SELECT id FROM entities WHERE name = ?", (name,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None


    def add_relation(self, e1_id: int, e2_id: int, relation_type: str, turn_id: int):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO relations (entity1_id, entity2_id, relation_type, turn_id) VALUES (?, ?, ?, ?)",
            (e1_id, e2_id, relation_type, turn_id)
        )
        conn.commit()
        conn.close()
```


4.4 Memory Manager (Coordinator)


src/memory/memory_manager.py


```python
from typing import List, Dict, Any, Optional
from pathlib import Path
import numpy as np
from sentence_transformers import SentenceTransformer
from .sqlite_store import SQLiteStore
from .vector_store import VectorStore
from .graph_builder import GraphBuilder
from ..data_models import MemoryFragment, TurnContext


class MemoryManager:
    def __init__(self, db_path: str = "thoughtforge.db", embed_model_name: str = "all-MiniLM-L6-v2"):
        self.db = SQLiteStore(db_path)
        self.embedder = SentenceTransformer(embed_model_name)
        self.vector = VectorStore(dim=self.embedder.get_sentence_embedding_dimension())
        self.graph = GraphBuilder(db_path)
        self._load_existing_fragments()


    def _load_existing_fragments(self):
        # Load all fragments from DB into vector index
        rows = self.db.conn.execute("SELECT id, content FROM fragments WHERE embedding IS NOT NULL").fetchall()
        if rows:
            embeddings = []
            ids = []
            for row in rows:
                # For simplicity, we assume embedding stored as blob (serialized float32 array)
                # In production, you'd decode it.
                emb = np.frombuffer(row['embedding'], dtype=np.float32)
                if len(emb) == self.vector.dim:
                    embeddings.append(emb)
                    ids.append(row['id'])
            if embeddings:
                self.vector.add(np.array(embeddings, dtype=np.float32), ids)


    def store_turn(self, user_input: str, response: str, cognition_state: Dict[str, Any]):
        turn_id = self.db.store_turn(user_input, response, cognition_state)
        # Extract fragments from both user and assistant
        for text, source in [(user_input, "user"), (response, "assistant")]:
            fragment = MemoryFragment(content=text, source=source, turn_id=turn_id)
            self._store_fragment(fragment)
        # Build entity graph for this turn (optional)
        entities = self.graph.extract_entities_from_text(user_input + " " + response)
        entity_ids = {}
        for ent in entities:
            eid = self.graph.add_entity(ent)
            entity_ids[ent] = eid
        # For simplicity, add relations between consecutive entities (naive)
        for i in range(len(entities)-1):
            if entity_ids[entities[i]] and entity_ids[entities[i+1]]:
                self.graph.add_relation(entity_ids[entities[i]], entity_ids[entities[i+1]], "co_occurs", turn_id)


    def _store_fragment(self, fragment: MemoryFragment):
        # Compute embedding
        emb = self.embedder.encode([fragment.content])[0].astype(np.float32)
        fragment.embedding = emb.tolist()  # for JSON serialization; store blob later
        # Insert into DB
        with self.db.conn:
            cursor = self.db.conn.execute(
                "INSERT INTO fragments (content, embedding, importance, source, turn_id) VALUES (?, ?, ?, ?, ?)",
                (fragment.content, emb.tobytes(), fragment.importance, fragment.source, fragment.turn_id)
            )
            frag_id = cursor.lastrowid
        # Add to vector index
        self.vector.add(emb.reshape(1, -1), [frag_id])


    def retrieve_relevant(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        # Compute query embedding
        query_emb = self.embedder.encode([query])[0].astype(np.float32)
        distances, frag_ids = self.vector.search(query_emb.reshape(1, -1), k=top_k)
        # Fetch fragment content from DB
        results = []
        for row in frag_ids[0]:
            if row:
                frag = self.db.conn.execute(
                    "SELECT id, content, source, importance FROM fragments WHERE id = ?", (row,)
                ).fetchone()
                if frag:
                    results.append(dict(frag))
        return results


    def get_recent_context(self, limit: int = 3) -> List[str]:
        turns = self.db.get_recent_turns(limit)
        context = []
        for turn in turns:
            context.append(f"User: {turn['user_input']}\nAI: {turn['response']}")
        return context
```


---


5. Cognition Steering


5.1 Scaffold Manager


src/cognition/scaffold_manager.py


```python
from typing import Dict, Any
import json


class ScaffoldManager:
    """Manages prompt templates (scaffolds) and inserts context."""
    def __init__(self, scaffolds_file: str = None):
        self.scaffolds = {
            "default": """
You are a helpful AI assistant. Respond concisely and naturally.
Conversation history:
{history}
Current user: {user_input}
AI:""",
            "casual_chat": """
You are a friendly conversationalist. Keep it light and engaging.
{history}
User: {user_input}
AI:""",
            "deep_think": """
Think step by step. Break down the question.
{history}
User: {user_input}
AI:""",
            "creative": """
Write an imaginative, poetic response.
{history}
User: {user_input}
AI:"""
        }
        if scaffolds_file:
            with open(scaffolds_file, 'r') as f:
                custom = json.load(f)
                self.scaffolds.update(custom)


    def get_prompt(self, scaffold_name: str, user_input: str, history: str = "", extra: Dict[str, Any] = None) -> str:
        template = self.scaffolds.get(scaffold_name, self.scaffolds["default"])
        # Fill placeholders
        prompt = template.format(user_input=user_input, history=history)
        if extra:
            for k, v in extra.items():
                prompt = prompt.replace(f"{{{k}}}", str(v))
        return prompt


    def list_scaffolds(self) -> list:
        return list(self.scaffolds.keys())
```


5.2 State Machine


src/cognition/state_machine.py


```python
from enum import Enum
from typing import Optional, Dict, Any


class State(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    GENERATING = "generating"
    SALVAGING = "salvaging"
    RESPONDING = "responding"


class CognitionStateMachine:
    def __init__(self):
        self.state = State.IDLE
        self.intent: Optional[str] = None
        self.mood: str = "neutral"
        self.topic: Optional[str] = None


    def transition(self, new_state: State) -> bool:
        allowed = {
            State.IDLE: [State.LISTENING],
            State.LISTENING: [State.PROCESSING, State.IDLE],
            State.PROCESSING: [State.GENERATING, State.IDLE],
            State.GENERATING: [State.SALVAGING, State.RESPONDING],
            State.SALVAGING: [State.RESPONDING],
            State.RESPONDING: [State.IDLE],
        }
        if new_state in allowed.get(self.state, []):
            self.state = new_state
            return True
        return False


    def update_intent(self, intent: str):
        self.intent = intent


    def update_mood(self, mood: str):
        self.mood = mood


    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "intent": self.intent,
            "mood": self.mood,
            "topic": self.topic,
        }
```


5.3 Intent Classifier


src/cognition/intent_classifier.py


```python
import re
from typing import Tuple
from sentence_transformers import SentenceTransformer
import numpy as np


class IntentClassifier:
    """Simple classifier using keyword rules + optionally embeddings."""
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.embedder = SentenceTransformer(model_name)
        self.intent_keywords = {
            "question": ["what", "how", "why", "who", "where", "when", "?"],
            "creative": ["write", "poem", "story", "imagine", "create"],
            "casual": ["hello", "hi", "how are you", "nice", "cool"],
            "deep": ["explain", "analyze", "break down", "reason", "think step"],
        }


    def classify(self, text: str) -> Tuple[str, float]:
        """Return intent name and confidence."""
        text_lower = text.lower()
        # Check keywords
        for intent, keywords in self.intent_keywords.items():
            for kw in keywords:
                if kw in text_lower:
                    return intent, 0.8
        # If no keyword match, use embedding similarity (optional)
        # For simplicity, return "chat" as default.
        return "chat", 0.5


    def classify_with_embedding(self, text: str) -> str:
        # Example: compute embedding and compare to predefined examples.
        # Placeholder.
        return "chat"
```


---


6. Generation Engine


6.1 TurboQuant Wrapper


src/generation/turboquant.py


```python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import bitsandbytes as bnb
from typing import List, Optional, Dict, Any


class TurboQuantLM:
    def __init__(self, model_name: str, quantization: str = "8bit", device: str = "cpu"):
        self.model_name = model_name
        self.quantization = quantization
        self.device = device


        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token


        # Load model with quantization
        if quantization == "8bit":
            self.model = AutoModelForCausalLM.from_pretrained(
                model_name,
                load_in_8bit=True,
                device_map="auto" if device != "cpu" else None,
                torch_dtype=torch.float16,
            )
        elif quantization == "4bit":
            self.model = AutoModelForCausalLM.from_pretrained(
                model_name,
                load_in_4bit=True,
                device_map="auto" if device != "cpu" else None,
            )
        else:
            self.model = AutoModelForCausalLM.from_pretrained(model_name)
        # Move to CPU if needed
        if device == "cpu":
            self.model = self.model.to("cpu")


        self.model.eval()


    def generate(self, prompt: str, max_new_tokens: int = 150, temperature: float = 0.7, top_p: float = 0.9, repetition_penalty: float = 1.1) -> str:
        inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1024)
        # Move to same device as model
        inputs = {k: v.to(self.model.device) for k, v in inputs.items()}


        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                top_p=top_p,
                repetition_penalty=repetition_penalty,
                do_sample=True,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
            )
        generated = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        # Remove the prompt part
        response = generated[len(prompt):].strip()
        return response
```


6.2 Sampler (with multiple candidates)


src/generation/sampler.py


```python
from .turboquant import TurboQuantLM
from typing import List


class Sampler:
    def __init__(self, model: TurboQuantLM):
        self.model = model


    def generate_candidates(self, prompt: str, n: int = 3, temp_range: List[float] = None) -> List[str]:
        if temp_range is None:
            temp_range = [0.6, 0.8, 1.0]
        candidates = []
        for i in range(n):
            temp = temp_range[i % len(temp_range)]
            response = self.model.generate(prompt, temperature=temp, max_new_tokens=150)
            candidates.append(response)
        return candidates
```


---


7. Fragment Salvage


7.1 Fragment Extractor


src/salvage/extractor.py


```python
import re
from typing import List, Tuple
import numpy as np
from sentence_transformers import SentenceTransformer


class FragmentExtractor:
    def __init__(self, embedder: SentenceTransformer):
        self.embedder = embedder


    def extract_sentences(self, text: str) -> List[str]:
        # Simple sentence split
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]


    def score_fragments(self, fragments: List[str], user_input: str, context: List[str]) -> List[Tuple[str, float]]:
        # Compute embeddings
        all_texts = [user_input] + context + fragments
        embeddings = self.embedder.encode(all_texts)
        user_emb = embeddings[0]
        context_emb = np.mean(embeddings[1:1+len(context)], axis=0) if context else np.zeros_like(user_emb)
        fragment_embs = embeddings[1+len(context):]


        scores = []
        for i, frag in enumerate(fragments):
            # Similarity to user + context
            sim_user = np.dot(fragment_embs[i], user_emb) / (np.linalg.norm(fragment_embs[i]) * np.linalg.norm(user_emb) + 1e-8)
            sim_context = np.dot(fragment_embs[i], context_emb) / (np.linalg.norm(fragment_embs[i]) * np.linalg.norm(context_emb) + 1e-8)
            # Combined score (user weight higher)
            score = 0.7 * sim_user + 0.3 * sim_context
            scores.append((frag, score))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores
```


7.2 Fragment Combiner


src/salvage/combiner.py


```python
from typing import List, Tuple
import random


class FragmentCombiner:
    def __init__(self, max_length: int = 300):
        self.max_length = max_length


    def combine(self, fragments: List[Tuple[str, float]], max_fragments: int = 3) -> str:
        # Select top fragments, avoid redundancy
        selected = []
        seen_phrases = set()
        for frag, score in fragments:
            # Simple check: if fragment not too similar to already selected
            if len(selected) >= max_fragments:
                break
            if frag in seen_phrases:
                continue
            selected.append(frag)
            seen_phrases.update(frag.split()[:5])  # crude dedup
        combined = " ".join(selected)
        if len(combined) > self.max_length:
            combined = combined[:self.max_length].rsplit(' ', 1)[0]
        return combined
```


7.3 Self-Correction Loop


src/salvage/self_correction.py


```python
from typing import List, Dict, Any
from .extractor import FragmentExtractor
from .combiner import FragmentCombiner
from ..generation.sampler import Sampler
from ..generation.turboquant import TurboQuantLM


class SelfCorrection:
    def __init__(self, model: TurboQuantLM, embedder, scaffold_manager):
        self.model = model
        self.embedder = embedder
        self.extractor = FragmentExtractor(embedder)
        self.combiner = FragmentCombiner()
        self.sampler = Sampler(model)
        self.scaffold_manager = scaffold_manager


    def refine_response(self, user_input: str, history: str, scaffold: str = "default") -> str:
        # Step 1: Generate candidates
        prompt = self.scaffold_manager.get_prompt(scaffold, user_input, history)
        candidates = self.sampler.generate_candidates(prompt, n=3)
        # Step 2: Extract fragments from all candidates
        all_fragments = []
        for cand in candidates:
            all_fragments.extend(self.extractor.extract_sentences(cand))
        # Step 3: Score fragments
        scored = self.extractor.score_fragments(all_fragments, user_input, [history])
        # Step 4: Combine
        final_response = self.combiner.combine(scored, max_fragments=4)
        # Step 5: Optional: evaluate quality (simulate)
        # If too short, fallback to best candidate
        if len(final_response) < 20:
            final_response = candidates[0]
        return final_response
```


---


8. Orchestration Engine


src/orchestration/engine.py


```python
from ..memory.memory_manager import MemoryManager
from ..cognition.scaffold_manager import ScaffoldManager
from ..cognition.state_machine import CognitionStateMachine, State
from ..cognition.intent_classifier import IntentClassifier
from ..generation.turboquant import TurboQuantLM
from ..salvage.self_correction import SelfCorrection


class ThoughtForgeEngine:
    def __init__(self, model_name: str, db_path: str = "thoughtforge.db", quantization: str = "8bit", device: str = "cpu"):
        self.memory = MemoryManager(db_path)
        self.scaffolds = ScaffoldManager()
        self.state_machine = CognitionStateMachine()
        self.intent_classifier = IntentClassifier()
        self.model = TurboQuantLM(model_name, quantization, device)
        self.self_correction = SelfCorrection(self.model, self.memory.embedder, self.scaffolds)


    def process_turn(self, user_input: str) -> str:
        # Update state
        self.state_machine.transition(State.PROCESSING)
        # Classify intent
        intent, confidence = self.intent_classifier.classify(user_input)
        self.state_machine.update_intent(intent)
        # Select scaffold based on intent
        scaffold = self._map_intent_to_scaffold(intent)
        # Retrieve recent context from memory
        history = "\n".join(self.memory.get_recent_context(limit=3))
        # Generate response using fragment salvage
        response = self.self_correction.refine_response(user_input, history, scaffold)
        # Store turn in memory
        self.memory.store_turn(user_input, response, self.state_machine.to_dict())
        # Transition back to idle
        self.state_machine.transition(State.IDLE)
        return response


    def _map_intent_to_scaffold(self, intent: str) -> str:
        mapping = {
            "question": "deep_think",
            "creative": "creative",
            "casual": "casual_chat",
            "deep": "deep_think",
            "chat": "default",
        }
        return mapping.get(intent, "default")


    def get_state(self):
        return self.state_machine.to_dict()
```


---


9. Optional: Wikidata ETL


src/optional/wikidata_etl.py


```python
import requests
import sqlite3
from typing import List, Dict


class WikidataETL:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)


    def fetch_entity(self, qid: str) -> Dict:
        """Fetch entity data from Wikidata API."""
        url = f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
        resp = requests.get(url)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        return data.get('entities', {}).get(qid, {})


    def store_entity(self, qid: str, label: str, description: str):
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO entities (name, type) VALUES (?, ?)",
                (label, "wikidata")
            )
            cursor = self.conn.execute("SELECT id FROM entities WHERE name = ?", (label,))
            entity_id = cursor.fetchone()[0]
            # Store additional metadata in a separate table (optional)
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS wikidata_meta (entity_id INTEGER, qid TEXT, description TEXT)"
            )
            self.conn.execute(
                "INSERT OR REPLACE INTO wikidata_meta (entity_id, qid, description) VALUES (?, ?, ?)",
                (entity_id, qid, description)
            )


    def import_wikidata_for_entity(self, entity_name: str):
        # Simple: search Wikidata for entity name, take first result
        search_url = f"https://www.wikidata.org/w/api.php?action=wbsearchentities&search={entity_name}&language=en&format=json"
        resp = requests.get(search_url)
        if resp.status_code != 200:
            return
        data = resp.json()
        if not data.get('search'):
            return
        first = data['search'][0]
        qid = first['id']
        entity_data = self.fetch_entity(qid)
        if entity_data:
            label = entity_data.get('labels', {}).get('en', {}).get('value', entity_name)
            desc = entity_data.get('descriptions', {}).get('en', {}).get('value', '')
            self.store_entity(qid, label, desc)
```


---


10. Optional: Alternative Knowledge Graphs


src/optional/alternative_knowledge.py


```python
import sqlite3
import networkx as nx
from typing import List, Tuple


class LocalKnowledgeGraph:
    """Build and query a local knowledge graph from SQLite relations."""
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.graph = nx.Graph()
        self._load_graph()


    def _load_graph(self):
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("""
            SELECT e1.name AS e1, e2.name AS e2, r.relation_type
            FROM relations r
            JOIN entities e1 ON r.entity1_id = e1.id
            JOIN entities e2 ON r.entity2_id = e2.id
        """).fetchall()
        for e1, e2, rel in rows:
            self.graph.add_edge(e1, e2, relation=rel)
        conn.close()


    def query_related(self, entity: str, max_depth: int = 2) -> List[str]:
        """Return entities connected to given entity up to depth."""
        if entity not in self.graph:
            return []
        # Use BFS
        visited = set()
        queue = [(entity, 0)]
        related = []
        while queue:
            node, depth = queue.pop(0)
            if node != entity and node not in visited:
                related.append(node)
                visited.add(node)
            if depth < max_depth:
                for neighbor in self.graph.neighbors(node):
                    if neighbor not in visited:
                        queue.append((neighbor, depth+1))
        return related


    def add_custom_fact(self, entity1: str, entity2: str, relation: str):
        # Add to graph and also to SQLite
        conn = sqlite3.connect(self.db_path)
        # Insert entities if not exist
        cursor = conn.execute("SELECT id FROM entities WHERE name = ?", (entity1,))
        e1 = cursor.fetchone()
        if not e1:
            cursor = conn.execute("INSERT INTO entities (name, type) VALUES (?, ?)", (entity1, "user"))
            e1 = (cursor.lastrowid,)
        cursor = conn.execute("SELECT id FROM entities WHERE name = ?", (entity2,))
        e2 = cursor.fetchone()
        if not e2:
            cursor = conn.execute("INSERT INTO entities (name, type) VALUES (?, ?)", (entity2, "user"))
            e2 = (cursor.lastrowid,)
        conn.execute(
            "INSERT INTO relations (entity1_id, entity2_id, relation_type, turn_id) VALUES (?, ?, ?, ?)",
            (e1[0], e2[0], relation, None)
        )
        conn.commit()
        conn.close()
        # Update graph
        self.graph.add_edge(entity1, entity2, relation=relation)
```


---


11. CLI & Web UI


11.1 CLI (using Click)


cli.py


```python
import click
from src.orchestration.engine import ThoughtForgeEngine


@click.command()
@click.option('--model', default='TinyLlama/TinyLlama-1.1B-Chat-v1.0', help='Model name or path')
@click.option('--db', default='thoughtforge.db', help='Path to SQLite DB')
@click.option('--quant', default='8bit', type=click.Choice(['none', '8bit', '4bit']), help='Quantization')
@click.option('--device', default='cpu', help='Device: cpu, cuda')
def chat(model, db, quant, device):
    engine = ThoughtForgeEngine(model, db, quant, device)
    print("ThoughtForge ready. Type 'exit' to quit.")
    while True:
        user_input = input("\nYou: ")
        if user_input.lower() == 'exit':
            break
        response = engine.process_turn(user_input)
        print(f"AI: {response}")


if __name__ == '__main__':
    chat()
```


11.2 Web UI (Streamlit)


web_ui.py


```python
import streamlit as st
from src.orchestration.engine import ThoughtForgeEngine


st.set_page_config(page_title="ThoughtForge", layout="wide")
st.title("⚡ MindSpark: ThoughtForge")


# Initialize engine in session
if 'engine' not in st.session_state:
    model_name = st.sidebar.text_input("Model name", "TinyLlama/TinyLlama-1.1B-Chat-v1.0")
    quant = st.sidebar.selectbox("Quantization", ["8bit", "4bit", "none"])
    device = st.sidebar.selectbox("Device", ["cpu", "cuda"])
    st.session_state.engine = ThoughtForgeEngine(model_name, "thoughtforge.db", quant, device)


if 'messages' not in st.session_state:
    st.session_state.messages = []


# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])


# Input
if prompt := st.chat_input("Your message"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Forging..."):
            response = st.session_state.engine.process_turn(prompt)
            st.write(response)
    st.session_state.messages.append({"role": "assistant", "content": response})
```


---


12. Testing & Benchmarking


tests/test_memory.py (example)


```python
import pytest
from src.memory.memory_manager import MemoryManager
import tempfile


def test_memory_store_and_retrieve():
    with tempfile.NamedTemporaryFile(suffix='.db') as tmp:
        mm = MemoryManager(tmp.name)
        mm.store_turn("Hello", "Hi there!", {"intent": "chat"})
        context = mm.get_recent_context(1)
        assert len(context) == 1
        assert "Hello" in context[0]
        # Test retrieval
        relevant = mm.retrieve_relevant("greeting", top_k=1)
        assert len(relevant) >= 1
```


Benchmark script:


```python
import time
from src.orchestration.engine import ThoughtForgeEngine


def benchmark(engine, prompts):
    times = []
    for p in prompts:
        start = time.time()
        engine.process_turn(p)
        times.append(time.time() - start)
    print(f"Avg time: {sum(times)/len(times):.2f}s, Max: {max(times):.2f}s")


if __name__ == '__main__':
    engine = ThoughtForgeEngine("TinyLlama/TinyLlama-1.1B-Chat-v1.0")
    prompts = ["Hello", "What is AI?", "Tell me a joke"] * 3
    benchmark(engine, prompts)
```


---


13. Deployment & Packaging


13.1 Dockerfile


```dockerfile
FROM python:3.10-slim


WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


COPY src/ ./src/
COPY cli.py .


ENTRYPOINT ["python", "cli.py"]
```


Build: docker build -t thoughtforge .
Run: docker run -it -v ./data:/app/data thoughtforge --db /app/data/thoughtforge.db


13.2 GitHub Actions for CI (.github/workflows/ci.yml)


```yaml
name: CI


on: [push, pull_request]


jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - run: pip install -r requirements.txt
      - run: pytest tests/
```


---


14. Extension Features


14.1 Voice I/O (Whisper.cpp + TTS)


src/extensions/voice.py


```python
import subprocess
import tempfile
import os


class VoiceHandler:
    def __init__(self, whisper_model="tiny", tts_model="tts"):
        self.whisper_model = whisper_model
        # Assume whisper.cpp binary is in PATH
        self.whisper_bin = "whisper"
        # TTS: use a simple command-line tool like espeak or piper
        self.tts_cmd = ["espeak", "-v", "en-us"]


    def transcribe(self, audio_file: str) -> str:
        # Convert audio to text using whisper.cpp
        cmd = [self.whisper_bin, "-m", f"models/ggml-{self.whisper_model}.bin", "-f", audio_file, "-otxt"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        # The output file is audio_file with .txt extension
        txt_file = audio_file + ".txt"
        if os.path.exists(txt_file):
            with open(txt_file, 'r') as f:
                text = f.read()
            os.remove(txt_file)
            return text.strip()
        return ""


    def synthesize(self, text: str, output_file: str = None):
        if not output_file:
            output_file = tempfile.NamedTemporaryFile(suffix=".wav").name
        cmd = self.tts_cmd + ["-w", output_file, text]
        subprocess.run(cmd, check=True)
        return output_file
```


14.2 Local Fine‑tuning (LoRA)


src/extensions/finetune.py


```python
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, Trainer
from peft import LoraConfig, get_peft_model, TaskType
import torch


def prepare_lora_model(base_model_name):
    model = AutoModelForCausalLM.from_pretrained(base_model_name, torch_dtype=torch.float16)
    tokenizer = AutoTokenizer.from_pretrained(base_model_name)
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=8,
        lora_alpha=32,
        lora_dropout=0.1,
        target_modules=["q_proj", "v_proj"],
    )
    model = get_peft_model(model, lora_config)
    return model, tokenizer


def fine_tune_on_conversations(model, tokenizer, conversations, output_dir):
    # conversations: list of dicts with "input" and "output"
    # Convert to dataset and train
    # (pseudo code)
    def tokenize_function(examples):
        texts = [f"User: {inp}\nAI: {out}" for inp, out in zip(examples['input'], examples['output'])]
        return tokenizer(texts, truncation=True, padding=True, max_length=512)


    from datasets import Dataset
    dataset = Dataset.from_dict({"input": [c['input'] for c in conversations], "output": [c['output'] for c in conversations]})
    tokenized_dataset = dataset.map(tokenize_function, batched=True)


    training_args = TrainingArguments(
        output_dir=output_dir,
        per_device_train_batch_size=2,
        num_train_epochs=3,
        save_steps=500,
    )
    trainer = Trainer(model=model, args=training_args, train_dataset=tokenized_dataset)
    trainer.train()
    model.save_pretrained(output_dir)
```


14.3 Multi‑modal Input (Image Captioning)


src/extensions/multimodal.py


```python
from transformers import BlipProcessor, BlipForConditionalGeneration
from PIL import Image
import torch


class ImageCaptioner:
    def __init__(self, model_name="Salesforce/blip-image-captioning-base"):
        self.processor = BlipProcessor.from_pretrained(model_name)
        self.model = BlipForConditionalGeneration.from_pretrained(model_name)


    def caption(self, image_path: str) -> str:
        image = Image.open(image_path).convert('RGB')
        inputs = self.processor(images=image, return_tensors="pt")
        with torch.no_grad():
            out = self.model.generate(**inputs)
        caption = self.processor.decode(out[0], skip_special_tokens=True)
        return caption
```


---


15. Conclusion & Contribution


This document provides the complete blueprint and code for ThoughtForge. It is designed to be modular, extensible, and edge‑friendly. We encourage you to:


· Fork the repository and experiment.
· Contribute improvements in quantization, memory, or scaffolding.
· Join the RuneForgeAI community to shape the Third Path.


All code is licensed under CC BY 4.0. Please credit RuneForgeAI when using or adapting.


May your thoughts be forged with iron clarity.


---


End of Document