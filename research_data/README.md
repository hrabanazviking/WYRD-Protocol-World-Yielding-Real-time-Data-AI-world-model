![https://raw.githubusercontent.com/hrabanazviking/coolvikingstuff/refs/heads/development/211a251a-b23d-4d38-a63d-325fcbcd3c10.jpg](https://raw.githubusercontent.com/hrabanazviking/coolvikingstuff/refs/heads/development/211a251a-b23d-4d38-a63d-325fcbcd3c10.jpg)

# Clean-Room Research Pack for Agentic Systems

## Purpose

This pack distills **publicly discussable engineering lessons** relevant to agentic coding tools, persistent memory systems, theory-of-mind style user/world modeling, and exploit resistance. It is designed for builders creating **original systems** for AI tooling, games, RPG engines, and world simulators.

This pack is **not** a copy of proprietary source code, and it is **not** intended to reconstruct any leaked implementation. It is a **clean-room synthesis** based on:

- public reporting about the March 31, 2026 Claude Code source exposure
- official Anthropic documentation on Claude Code memory, security, hooks, subagents, and permissioning
- OWASP guidance for LLM prompt injection, agent security, and secure AI model operations
- independent architectural synthesis tailored to memory-heavy and simulation-heavy projects

## Why this matters

Recent public reporting says Anthropic accidentally exposed a source map in Claude Code v2.1.88, allowing broad reconstruction of a large portion of the CLI/app TypeScript code. Anthropic said it was a packaging error rather than a breach, and that no customer data or credentials were exposed. Public reporting also says people inspecting the exposed material discussed memory architecture, feature flags, and unlaunched agent-like features. Rather than reproducing internals, this pack extracts the **useful classes of ideas** worth reimagining in original systems. [R1][R2][R3]

## Core lessons worth carrying forward

1. **Separate policy memory from learned memory.**
   Persistent instructions and accumulated observations should not live in the same bucket.
2. **Treat memory as advisory, not sacred.**
   Memory should carry confidence, provenance, scope, and expiration.
3. **Assume every external input is hostile.**
   Documents, websites, emails, tool output, logs, and even memory can all carry injections.
4. **Autonomy without permission design becomes self-sabotage.**
   Users accept too many prompts when the system asks constantly; the answer is not “skip all permissions,” but better risk classification and sandboxing. [R4][R5]
5. **Hooks and subagents are power multipliers.**
   They are also attack-surface multipliers, so scoping, monitoring, and compartmentalization matter.
6. **Memory poisoning is a first-class threat.**
   If your agent can write its own long-term memory, you need validation, isolation, and review paths. [R6]
7. **Release engineering is security.**
   Debug files, open artifact stores, hardcoded secrets, and bad dependency hygiene can undo otherwise solid architecture. [R1][R2][R7]

![https://raw.githubusercontent.com/hrabanazviking/coolvikingstuff/refs/heads/development/ChatGPT%20Image%20Mar%2031%2C%202026%2C%2009_28_17%20PM.png](https://raw.githubusercontent.com/hrabanazviking/coolvikingstuff/refs/heads/development/ChatGPT%20Image%20Mar%2031%2C%202026%2C%2009_28_17%20PM.png)

## Included files

- `01_clean_room_protocol.md`
- `02_memory_architecture_patterns.md`
- `03_theory_of_mind_and_user_world_modeling.md`
- `04_exploit_resistance_and_agent_security.md`
- `05_permissioning_sandboxing_and_tool_design.md`
- `06_hooks_subagents_and_observability.md`
- `07_project_backlog_for_memory_heavy_ai_systems.md`

## Suggested use

Use these docs as:

- design references
- backlog fuel
- spec seeds for new modules
- guardrails for agentic workflows
- a knowledge base for writing **original code only**

## Clean-room rules

- Do not copy proprietary code.
- Do not preserve distinctive identifiers from leaked internals.
- Do not mirror a proprietary file tree or module layout.
- Record **problem → pattern → tradeoffs → original implementation**.
- Prefer fresh experiments, benchmarks, and adversarial tests over imitation.

![https://raw.githubusercontent.com/hrabanazviking/coolvikingstuff/refs/heads/development/Gemini_Generated_Image_ib7m8sib7m8sib7m.png](https://raw.githubusercontent.com/hrabanazviking/coolvikingstuff/refs/heads/development/Gemini_Generated_Image_ib7m8sib7m8sib7m.png)

## Source notes

[R1] The Verge, *Claude Code leak exposes a Tamagotchi-style 'pet' and an always-on agent* (Mar 31, 2026)  
https://www.theverge.com/ai-artificial-intelligence/904776/anthropic-claude-source-code-leak

[R2] Axios, *Anthropic leaked 500,000 lines of its own source code* (Mar 31, 2026)  
https://www.axios.com/2026/03/31/anthropic-leaked-source-code-ai

[R3] VentureBeat, *Claude Code's source code appears to have leaked: Here's what we know* (Mar 31, 2026)  
https://venturebeat.com/technology/claude-codes-source-code-appears-to-have-leaked-heres-what-we-know

[R4] Anthropic Engineering, *Claude Code auto mode: a safer way to skip permissions* (Mar 25, 2026)  
https://www.anthropic.com/engineering/claude-code-auto-mode

[R5] Claude Code Docs, *Security*  
https://code.claude.com/docs/en/security

[R6] OWASP Cheat Sheet, *AI Agent Security Cheat Sheet*  
https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html

[R7] OWASP Cheat Sheet, *Secure AI Model Ops Cheat Sheet*  
https://cheatsheetseries.owasp.org/cheatsheets/Secure_AI_Model_Ops_Cheat_Sheet.html

![https://raw.githubusercontent.com/hrabanazviking/coolvikingstuff/refs/heads/development/6ba83f82-8dec-4d49-85ab-36348802056d.jpg](https://raw.githubusercontent.com/hrabanazviking/coolvikingstuff/refs/heads/development/6ba83f82-8dec-4d49-85ab-36348802056d.jpg)

## Expansion pack added

A second-wave set of docs now extends the original pack into more concrete build material:

- `08_memory_lifecycle_and_promotion_engine.md`
- `09_world_model_belief_graph_spec.md`
- `10_theory_of_mind_inference_engine.md`
- `11_agent_security_attack_taxonomy.md`
- `12_permission_classifier_and_sandbox_blueprint.md`
- `13_eval_red_team_and_failure_analysis.md`
- `14_project_branches_world_rpg_companion_coding_agent.md`
- `15_original_theories_and_design_hypotheses.md`
- `16_build_sequence_v2.md`

These new files go beyond summary notes. They add:
- memory promotion/decay state machines
- graph-shaped truth vs belief modeling
- explicit theory-of-mind inference layers
- attack taxonomies for memory poisoning and tool abuse
- a classifier-first permission design
- eval/red-team plans
- project-specific branches for world engines, companions, and coding agents
- original theories worth testing rather than merely copying patterns


## Third-wave expansion pack added

A third-wave set of docs now deepens the pack for companion systems, cyber-Viking world design, ultra-realistic personalities, and small-model accuracy via memory scaffolding:

- `17_small_model_memory_scaffolding_and_accuracy_engine.md`
- `18_personality_lattice_and_trait_stability.md`
- `19_symbolic_memory_and_cyber_viking_world_layer.md`
- `20_relationship_continuity_and_bond_model.md`
- `21_scene_director_and_emotional_presence_engine.md`
- `22_memory_compression_distillation_and_rehydration.md`
- `23_multi_scale_retrieval_and_micro_rag_for_small_models.md`
- `24_truth_calibration_and_confabulation_control.md`
- `25_persona_compiler_and_memory_assembly_pipeline.md`

These files add:
- memory scaffolding patterns that let smaller models become more accurate within bounded domains
- a lattice-based personality system for long-term character stability
- symbolic and ritual memory for mythic/cyber-Viking settings
- relationship continuity models for companions
- scene-presence control for stronger emotional realism
- compression and rehydration methods for long-running memory systems
- multi-scale retrieval tuned for small-model context budgets
- claim-level truth calibration to reduce confabulation
- a persona compiler that assembles scene-specific character runtime packets


## Fourth-wave implementation pack added

A fourth-wave implementation set now turns the research pack into concrete build specs:

- `V4_IMPLEMENTATION_INDEX.md`
- `MemorySchemas.md`
- `BondGraphSpec.md`
- `PersonaCompilerSpec.md`
- `MicroRAGPipelineSpec.md`
- `TruthCalibrationEvalSet.md`

These files add:
- a full base memory envelope and store layout
- canonical fact, relationship, symbolic, contradiction, and policy schemas
- a structured bond graph with vows, hurts, repair debt, and sacred resonance
- a deterministic persona compiler with precedence rules and packet budgets
- a typed MicroRAG pipeline for smaller models with contradiction-aware packet assembly
- an eval harness for false memory, canon drift, code-truth integrity, and prompt injection resistance

![https://raw.githubusercontent.com/hrabanazviking/coolvikingstuff/refs/heads/development/efda5776-58ee-41fb-a53a-995758e03022.png](https://raw.githubusercontent.com/hrabanazviking/coolvikingstuff/refs/heads/development/efda5776-58ee-41fb-a53a-995758e03022.png)
