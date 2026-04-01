# The TurboQuant + Guided Memory Cognition Blueprint: Implementation Research Document

## Introduction
This document serves as an extensive and detailed research guide for implementing the architectural concepts defined in the "TurboQuant + Guided Memory Cognition for Small-Model Conversation Systems" spec. The goal is to build an ultra-lean personality agent capable of running on weak hardware, using very small models (1B - 3B parameters) by employing compressed memory, guided cognition scaffolds, and rigorous quantization techniques.

## 1. Hardware & Model Selection
The core philosophy is to extract maximum performance from limited hardware (older laptops, low-RAM desktops, CPU-only systems).

### 1.1 Small Language Models (SLMs)
The target model size is in the 1B to 3B parameter range. These models offer faster inference, lower memory footprint, and are easier to quantize and deploy on edge devices.

Recommended Models:
- **Granite 3.0 1B-A400M**: Features 1 billion total parameters with only 400 million active at inference, minimizing latency while maintaining quality.
- **Granite 3.0 3B-A800M**: A larger sibling providing better reasoning while keeping active parameters low (800 million) for efficient inference.
- **TinyLlama**: A classic 1.1B model, well-suited for straightforward and specific use-cases.

### 1.2 Model Architecture (Dense vs. Mixture-of-Experts)
- **Dense SLMs (e.g., TinyLlama)**: Use 100% of weights per token. Simpler to train and deploy, offering constant memory per token but slower inference at the same parameter size compared to MoE.
- **MoE SLMs (e.g., Granite models)**: Activate only a subset of "experts" for each token. This drastically lowers compute cost per inference step, making them highly suitable for resource-constrained devices where efficiency is paramount.

## 2. Token Budgeting & Quantization Techniques
To fit within strict RAM/VRAM constraints, aggressive quantization is required.

### 2.1 Quantization Frameworks
- **GGUF (GPT-Generated Unified Format)**: Designed for minimal setup and optimal CPU/GPU hybrid inference locally. Best for users running models on consumer hardware without dedicated high-end GPUs.
- **GPTQ**: A post-training quantization method highly efficient for 4-bit quantization, focusing on GPU execution.
- **AWQ (Activation-aware Weight Quantization)**: Intelligently preserves critical weights, maintaining higher accuracy at extremely low bit widths (e.g., 4-bit). Excellent for maintaining conversational quality in SLMs.
- **EXL2 (ExLlamaV2)**: Optimized for blazing-fast inference on modern GPUs, supporting variable bitrates for precise memory fitting.

### 2.2 Calibration & Trade-offs
When quantizing 1B parameters, expect noticeable quality degradation, particularly in reasoning. However, using representative calibration data during quantization significantly improves results. Keeping embeddings and output layers in full precision while quantizing intermediate layers is a standard practice to mitigate quality loss without consuming excessive memory.

## 3. Component-by-Component Implementation Guide

### 3.1 Input Compression Layer
Goal: Reduce raw input into a structured YAML task sketch (`intent`, `topic`, `tone_in`, `response_mode`, etc.).

**Implementation Idea**: Use an extremely lightweight regex/keyword-based heuristic initially, or a fast quantized embedding model to map user input into predefined intent categories to save token budgets.

### 3.2 Lightweight Memory & Retrieval
Goal: Retrieve 3-5 memory cues efficiently without heavy reasoning overhead.

**Implementation Idea**:
- Use lightweight sparse retrieval methods like **BM25** for keyword-matching episodic memories and active thread states.
- Alternatively, use tiny embedding models (e.g., all-MiniLM-L6-v2) combined with simple Cosine Similarity for semantic matching of user profiles and response patterns.
- The scoring formula should strictly follow the weights: semantic similarity (0.35) + tone (0.20) + preference (0.20) + recency (0.10) + importance (0.15).

### 3.3 Guided Cognition Scaffolding
Goal: Generate a minimal YAML control object to guide the SLM.

**Implementation Idea**: Precompute and cache common cognition scaffolds. Instead of generating scaffolds on the fly every time, map the compressed input intent to a cached YAML scaffold (e.g., "emotional_support" scaffold or "light_conversation" scaffold) to save inference cycles.

## 4. The Candidate Generation and Salvage-and-Refine Pipeline
This is the heart of improving SLM output without relying on large context windows or massive models.

### 4.1 Candidate Generation
Generate 2 to 4 short candidate responses using different "modes" (e.g., practical vs. empathic) specified in the cognition scaffold. Use low-to-moderate temperature settings to reduce rambling.

### 4.2 Fragment Extraction
Do not discard flawed candidates entirely.
**Implementation Idea**:
- Split candidate responses into sentences using basic NLP tools (like NLTK or spaCy's lightweight English core model).
- Alternatively, use simple regex punctuation splitting (`[.!?,]`) to isolate clauses.

### 4.3 Heuristic Scoring & Salvage
Score each extracted sentence based on:
- Relevance to the topic
- Absence of generic filler (e.g., penalize phrases like "A lot of people feel this way" or "As an AI").
- Length and conciseness.
Select the top-scoring fragments.

### 4.4 Micro-Refinement (Merge)
Feed the top fragments back into the quantized SLM with a strict prompt: "Using these useful fragments: [list], write one clean, concise response in 3-5 sentences avoiding filler."
Stop after a maximum of 2 refinement passes to adhere to the strict latency and hardware caps.

## 5. Token Budgets & Memory Writeback
Strict token austerity must be enforced. The final response should be under 180 tokens.
After the turn, the Memory Writeback Layer updates the JSONL/YAML stores. It should extract only the core topic and successful tone shift, avoiding full transcript storage to keep the memory database ultra-lightweight and retrieval fast.

## 6. Conclusion
By meticulously orchestrating highly optimized Small Language Models (like Granite 1B or TinyLlama) via frameworks like GGUF or AWQ, and pairing them with a structured, multi-candidate salvage-and-refine pipeline, it is possible to achieve robust conversational intelligence on severely constrained hardware. The intelligence resides in the system's architecture—memory, retrieval, and scaffolding—rather than the raw parameter count of the model itself.
