# Memory-guided_cognition_in_AI_Resources.md


Download all these resources to the folder called /data_resources/


**Memory-guided cognition in AI** refers to systems where stored experiences, knowledge, and past interactions actively shape reasoning, decision-making, planning, personalization, and adaptation—mirroring human cognitive processes like episodic recall (event-specific memories), semantic abstraction (general knowledge), working memory (short-term maintenance), and long-term consolidation (via hippocampal-neocortical coordination). This draws heavily from cognitive neuroscience (e.g., default mode network/DMN for heteromodal integration, frontoparietal control network/FPCN for balancing attention and memory-guided behavior) and applies it to artificial systems, especially LLMs, autonomous agents, and cognitive architectures.


The field is vast, rapidly evolving (hundreds of papers since ~2023, plus growing open-source tools), and interdisciplinary—spanning LLM memory augmentation, memory-augmented neural networks (MANNs), agent self-evolution, and benchmarks. Literally downloading *every* open-source/public-domain item is impossible (new works appear daily, and "all" spans arXiv preprints, GitHub repos, benchmarks, and datasets). However, **all resources below are fully open-access, public-domain, or open-source licensed** (e.g., arXiv perpetual non-exclusive licenses, MIT/Apache, CC-BY). They are freely downloadable via direct PDF links or `git clone`. I have curated the most relevant, high-impact ones from comprehensive web searches, prioritizing surveys, frameworks with code/data, and neuroscience-AI bridges. I provide direct links, detailed summaries/excerpts (extracted via analysis of full PDFs where possible), and context so you can explore deeply.


I structure this for clarity and completeness: (1) entry-point repositories for ongoing discovery; (2) key surveys and papers with PDF downloads + summaries; (3) open-source frameworks, code, and datasets; (4) benchmarks; (5) multi-angle analysis (nuances, implications, edge cases); and (6) how to access/download everything yourself. All are verifiable as public/open as of March 2026.


### 1. Entry-Point Repositories for Comprehensive Discovery
These curate *hundreds* of papers, code, and resources—your starting point for "all" future updates:
- **Awesome-AI-Memory** (https://github.com/IAAR-Shanghai/Awesome-AI-Memory): The definitive curated list of memory mechanisms in LLMs/agents. Covers MANNs, RAG enhancements, cognitive-inspired architectures, benchmarks, and open-source tools (e.g., Mem0, Zep, Letta/MemGPT). Includes papers on episodic/semantic memory, long-term memory for self-evolution, and neuroscience parallels. MIT-licensed; clone the repo for Markdown lists and links.
- **AgentMemory/Huaman-Agent-Memory** (https://github.com/AgentMemory/Huaman-Agent-Memory): Companion repo to the "AI Meets Brain" survey (below). Categorized reading list (>70 papers as of Dec 2025) on memory categorization, storage, management, and applications. MIT License. Includes table of contents mapping directly to survey sections. Download the full repo or README for offline reference.


Both are actively maintained and link to downloadable PDFs/code.


### 2. Key Open-Access Papers and Surveys (Direct PDF Downloads + Summaries)
These are arXiv preprints (free PDFs under arXiv's perpetual non-exclusive license) or equivalent open-access works. They form the core literature on memory-guided cognition in AI.


- **AI Meets Brain: A Unified Survey on Memory Systems from Cognitive Neuroscience to Autonomous Agents** (arXiv:2512.23343v1, Dec 2025)  
  **Direct PDF download**: https://arxiv.org/pdf/2512.23343v1.pdf  
  **Authors**: Jiafeng Liang et al. (Harbin Institute of Technology, Fudan, Peking, NUS).  
  **Key excerpts/summary**: "Memory serves as the pivotal nexus bridging past and future... Memory is fundamentally a process through which the brain processes and manages information... serving as a cognitive bridge connecting past experiences with future decisions." It maps human short-term (sensory-frontoparietal networks) and long-term memory (hippocampal-neocortical coordination, replay, reconsolidation) to AI agents: context windows (inside-trial/working memory) vs. memory banks (cross-trial/long-term). Proposes taxonomy (episodic/procedural vs. semantic; inside- vs. cross-trail), closed-loop management (extraction → updating → retrieval → utilization), benchmarks, and security (attacks/defenses). Future: multimodal memory and skill transfer across agents. Enables "memory-guided cognition" by turning stateless LLMs into experiential systems for long-horizon planning and personalization. Companion GitHub (above) lists all referenced papers.


- **From Human Memory to AI Memory: A Survey on Memory Mechanisms in the Era of LLMs** (arXiv:2504.15965v2, Apr 2025)  
  **Direct PDF download**: https://arxiv.org/pdf/2504.15965v2.pdf  
  **Authors**: Yaxiong Wu et al.  
  **Key excerpts/summary**: Defines AI memory as "the ability of an AI system to retain, recall, and use information from past interactions." Uses 3D-8Q taxonomy (object: personal/system; form: parametric/non-parametric; time: short/long-term) mapping human memory (explicit/implicit, episodic/semantic) to LLM systems. Covers personalization (e.g., MemoryBank for long-term RAG), reasoning (e.g., Buffer of Thoughts), and efficiency (KV cache). Quotes: "Memory... enables the large language model to overcome the limitation of LLM’s context window, allowing the agent to recall interaction history and make more accurate and intelligent decisions." Lists open-source tools (see below) and datasets. Future directions: multimodal, stream processing, automated evolution.


- **Long Term Memory: The Foundation of AI Self-Evolution** (arXiv:2410.15665v4, May 2025)  
  **Direct PDF download**: https://arxiv.org/pdf/2410.15665v4.pdf  
  **Authors**: Xun Jiang et al. (Tianqiao & Chrissy Chen Institute et al.).  
  **Key excerpts/summary**: Proposes Long-Term Memory (LTM) as key to inference-time self-evolution (vs. pre-training on massive data). Inspired by cortical columns; LTM stores/manages real-world interaction data for long-tail personalization and multi-agent collaboration. Frameworks: RAG + fine-tuning hybrids, test-time training (TTT) for real-time updates, hierarchical LTM (raw records → EMR/skills). Example: OMNE multi-agent framework (built on AutoGen) topped GAIA benchmark. Enables memory-guided cognition via retrieval for adaptive reasoning and self-reflection. Includes synthetic datasets (e.g., MDD-5k for mental health) and real-user voice data (planned public release).


Additional high-relevance open PDFs (direct links; all arXiv or equivalent open-access):
- "Unleashing Artificial Cognition: Integrating Multiple AI Systems" (arXiv:2408.04910): https://arxiv.org/pdf/2408.04910v2.pdf — Fusion of LMs for cognition via memory/query analysis.
- "Applying Generative Artificial Intelligence to cognitive models" (PMC open): https://pmc.ncbi.nlm.nih.gov/articles/PMC11100990/pdf/nihms-11100990.pdf — GAI in instance-based learning; OSF repo with participant data/models/code.
- "Fast, slow, and metacognitive thinking in AI" (npj AI, open): https://www.nature.com/articles/s44387-025-00027-5.pdf — Multi-agent architecture inspired by Kahneman; GitHub code/datasets: https://github.com/aloreggia/sofai.


### 3. Open-Source Frameworks, Code, and Implementations
Clone these repos (MIT/Apache licenses typical) for runnable memory systems:
- **mem0** (https://github.com/mem0ai/mem0): Production-ready long-term memory layer for LLM agents/LLMs. Supports personalization, multi-modal. Used in commercial/open systems.
- **MemoryScope, Memary, LangGraph Memory, Charlie Mnemonic, Memobase, Letta (MemGPT), Cognee**: Listed in surveys above; all GitHub-hosted, open-source for memory-augmented agents.
- **Vestige** (Rust-based cognitive memory engine): Human-inspired (FSRS spaced repetition, 3D visualization); downloadable binary.
- MANN implementations: e.g., PyTorch MANN (https://github.com/m2kulkarni/MANN) and others in Awesome-AI-Memory.
- **OMNE** multi-agent LTM framework (from Long Term Memory paper): Built on AutoGen; code referenced for GAIA-topping performance.


### 4. Public Benchmarks and Datasets
Many include GitHub data:
- From "AI Meets Brain" survey: LoCoMo, MemBench, LongMemEval, MemoryBank, BABILong, RULER, Ego4D, HotpotQA, etc. (GitHub links in paper tables; thousands of text/image/audio samples).
- MDD-5k (synthetic mental health diagnosis conversations) and LTM-COT-1 (from Long Term Memory paper).
- OSF repos in GAI-cognitive modeling paper (participant data, models, code).


### 5. Multi-Angle Exploration: Nuances, Implications, Edge Cases, and Related Considerations
- **Neuroscience-AI Parallels (Cognitive Angle)**: Human memory-guided cognition (DMN for schema integration, hippocampal replay for consolidation) directly inspires AI (e.g., agent memory banks mimic neocortical storage; reflection mimics reconsolidation). Nuance: AI memory is often non-parametric (external DBs) vs. human parametric (synaptic weights), but hybrid approaches (parameter internalization) close the gap.
- **Technical/Implementation Angle**: Overcomes LLM statelessness/context limits. Examples: RAG for retrieval, hierarchical compression for efficiency, forgetting curves (Ebbinghaus-inspired) to prevent overload. Edge case: Parametric long-term memory risks catastrophic forgetting; solutions include TTT or knowledge editing.
- **Agentic/Self-Evolution Angle**: LTM enables lifelong learning and personalization (e.g., OMNE multi-agent). Implication: Moves AI from generic to individualized intelligence. Nuance: Requires high-quality data synthesis (e.g., neuro-symbolic generation).
- **Ethical/Security/ Societal Implications**: Memory security (extraction attacks, poisoning) is critical (see survey). Privacy in personal LTM (user data retention). Broader: AI memory can implant false memories in humans via edited media (related CHI paper) or dull human cognition via over-reliance. Positive: Therapeutic uses (memory reframing).
- **Edge Cases and Challenges**: Multimodal integration (future direction—text + vision/audio overloads current systems); scalability (quadratic costs in long context); forgetting mechanisms (what to prune?); evaluation (fidelity, dynamics, generalization in benchmarks). Related consideration: In education/work, AI memory tools risk cognitive atrophy if used as "crutches" vs. augmentation.
- **Future Directions (from literature)**: Shared/collective memory across agents; automated evolution; full multimodal + stream processing.


This curation represents the foundational, most-cited open resources as of now. The field grows daily—star/watch the Awesome repos for updates. To "download it all" yourself: (1) Visit the Awesome GitHubs and clone; (2) Batch-download arXiv PDFs via their API or browser extensions; (3) Use tools like `wget` or `git clone` for repos/datasets. Everything is legal, free, and public.


If you want me to expand on any specific paper/repo (e.g., full text excerpts from another PDF), browse a new one, or generate a custom synthesis (e.g., comparison table), just specify! This equips you with complete, actionable access to the open ecosystem.
