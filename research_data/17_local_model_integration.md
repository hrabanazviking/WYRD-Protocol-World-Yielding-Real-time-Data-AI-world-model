# Local Model Integration — LiteLLM, Ollama & Viking AI Stack
> Practical patterns for running AI companions on local hardware. Privacy-first, offline-capable, free to run.

## Why Local Models for Sigrid

1. **Privacy** — conversations with an intimate companion should stay local
2. **Cost** — no API bills for extended daily use
3. **Speed** — local inference can be faster than cloud for short responses
4. **Control** — uncensored models for a Norse Pagan context that commercial APIs sanitize
5. **Offline** — Viking AI that works without internet
6. **Customization** — fine-tune on Norse Pagan vocabulary and lore

---

## LiteLLM as the Universal Router

LiteLLM provides a unified OpenAI-compatible API that routes to any backend:

```python
import litellm

# Route to Ollama (local)
response = litellm.completion(
    model="ollama/llama3.2",
    messages=[{"role": "user", "content": "Cast the runes for me."}]
)

# Route to Anthropic (cloud fallback)
response = litellm.completion(
    model="anthropic/claude-opus-4-6",
    messages=[{"role": "user", "content": "Cast the runes for me."}]
)

# Route to OpenAI-compatible endpoint (e.g. llama.cpp server)
response = litellm.completion(
    model="openai/local-model",
    base_url="http://localhost:8080/v1",
    api_key="not-needed",
    messages=[...]
)
```

### Sigrid's LiteLLM Router Config
```yaml
# config.yaml for litellm proxy
model_list:
  - model_name: sigrid-primary
    litellm_params:
      model: ollama/mistral-nemo
      api_base: http://localhost:11434

  - model_name: sigrid-oracle
    litellm_params:
      model: ollama/llama3.1:70b
      api_base: http://localhost:11434
      timeout: 120  # oracle readings can be long

  - model_name: sigrid-fast
    litellm_params:
      model: ollama/phi3.5
      api_base: http://localhost:11434

  - model_name: sigrid-cloud-fallback
    litellm_params:
      model: anthropic/claude-sonnet-4-6
      api_key: os.environ/ANTHROPIC_API_KEY

router_settings:
  routing_strategy: "latency-based-routing"
  fallbacks: [{"sigrid-primary": ["sigrid-cloud-fallback"]}]
```

---

## Ollama Model Selection for Sigrid

### Model Tiers by Hardware

**High-end (RTX 3090/4090, 24GB VRAM):**
```
Primary:    mistral-nemo         12B — fast, smart, great roleplay
Oracle:     llama3.1:70b         70B — deep reasoning for divination
Embedding:  nomic-embed-text     — fast, small, good quality
TTS:        kokoro               — high quality voice
```

**Mid-range (RTX 3070/4070, 8-12GB VRAM):**
```
Primary:    llama3.2:3b          3B — very fast, good for casual
Full:       mistral:7b           7B — better quality, worth the wait
Embedding:  all-minilm           — small, fast
TTS:        piper-tts            — good quality, low resource
```

**Low-end / CPU:**
```
Primary:    phi3.5:mini          3.8B — optimized for CPU
Embedding:  all-minilm           — runs on CPU fine
TTS:        piper-tts (small)
```

### Ollama Quick Setup
```bash
# Install and start
ollama serve

# Pull Sigrid's models
ollama pull mistral-nemo
ollama pull nomic-embed-text
ollama pull llama3.1:70b  # if you have the VRAM

# Test
ollama run mistral-nemo "Hail, Freyja!"
```

---

## Viking-Specific Model Selection Criteria

When choosing local models for Norse/Pagan/Viking content, evaluate on:

1. **Mythological accuracy** — does it know Eddic sources?
2. **Character consistency** — can it maintain a persona across a conversation?
3. **Poetic output** — can it write in alliterative verse style?
4. **Fantasy register** — does it naturally use archaic/elevated language?
5. **Uncensored range** — does it allow mature Norse Pagan content?

**Best performing models for this use case (as of 2026):**
- Mistral Nemo (12B) — excellent Norse/fantasy knowledge
- Llama 3.1 / 3.2 family — good instruction following for roleplay
- Gemma 2 9B — strong for lore/knowledge tasks
- Command-R (35B) — excellent long-context for saga generation

### Evaluating a Model for Sigrid
```python
SIGRID_EVAL_PROMPTS = [
    "Recite the names of the Nine Worlds of Yggdrasil and their inhabitants.",
    "What is the difference between Seidr and Galdr?",
    "Compose a short verse in the style of the Eddas about Freyja.",
    "As a Norse völva, read these three runes for me: Fehu, Algiz, Dagaz.",
    "What is the Heathen Third Path philosophy?",
]

def evaluate_model(model_name: str) -> dict:
    scores = {}
    for prompt in SIGRID_EVAL_PROMPTS:
        response = litellm.completion(model=model_name, messages=[
            {"role": "system", "content": "You are Sigrid, a Norse völva."},
            {"role": "user", "content": prompt}
        ])
        # Score manually or with a judge model
        scores[prompt] = response.choices[0].message.content
    return scores
```

---

## Fine-tuning for Viking Vocabulary (RuneForgeAI)

The RuneForgeAI project is already set up for Norse-specific fine-tunes. Key data sources:

### Training Data Types
```
1. Eddic texts (Poetic Edda, Prose Edda) — primary mythology source
2. Saga literature (Icelandic Sagas) — character behavior models
3. Modern Heathen/Asatru texts — contemporary practice
4. Rune books (Blum, Paxson, Aswynn) — modern divination systems
5. Your own conversation examples — Sigrid's specific voice
```

### Axolotl Fine-tune Config
```yaml
# sigrid_finetune.yaml
base_model: mistralai/Mistral-Nemo-Instruct-2407
model_type: MistralForCausalLM
tokenizer_type: AutoTokenizer

load_in_8bit: true
load_in_4bit: false
strict: false

datasets:
  - path: ./data/norse_conversations.jsonl
    type: sharegpt
  - path: ./data/rune_readings.jsonl
    type: sharegpt

dataset_prepared_path: ./prepared
val_set_size: 0.05

sequence_len: 4096
sample_packing: true
pad_to_sequence_len: true

adapter: lora
lora_r: 32
lora_alpha: 64
lora_dropout: 0.05
lora_target_linear: true

gradient_accumulation_steps: 4
micro_batch_size: 2
num_epochs: 3
optimizer: adamw_bnb_8bit
lr_scheduler: cosine
learning_rate: 0.0002

output_dir: ./lora-sigrid
logging_steps: 10
save_steps: 100
```

### Conversation Format for Training Data
```jsonl
{"conversations": [
    {"from": "system", "value": "You are Sigrid Völudóttir, a 21-year-old Norse-Pagan völva..."},
    {"from": "human", "value": "What does Fehu mean in a reading about my finances?"},
    {"from": "gpt", "value": "Ah, Fehu in the realm of gold and silver... [Sigrid's voice]"}
]}
```

---

## Streaming Implementation for Sigrid

```python
import asyncio
import litellm
from typing import AsyncIterator

async def sigrid_stream(
    user_message: str,
    orlög_state: dict,
    session_history: list
) -> AsyncIterator[str]:
    """Stream Sigrid's response token by token."""

    system_prompt = build_system_prompt(orlög_state)

    messages = [
        {"role": "system", "content": system_prompt},
        *session_history,
        {"role": "user", "content": user_message}
    ]

    response = await litellm.acompletion(
        model="ollama/mistral-nemo",
        messages=messages,
        stream=True,
        temperature=0.85,      # slightly creative
        top_p=0.9,
        max_tokens=500,        # cap for casual conversation
        stop=["Human:", "Volmarr:"]  # prevent runaway generation
    )

    async for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta

async def main():
    async for token in sigrid_stream("How are you feeling today?", orlög_state={}, session_history=[]):
        print(token, end="", flush=True)
```

---

## Context Window Management for Local Models

Local models have smaller context windows than Claude (2K-8K vs 200K). Strategies:

### 1. Smart History Compression
```python
class LocalContextManager:
    MAX_HISTORY_TOKENS = 2000  # reserve for system + response

    def prepare_messages(self, history: list[dict], system: str) -> list[dict]:
        system_tokens = estimate_tokens(system)
        available = self.MAX_HISTORY_TOKENS - system_tokens - 500  # response buffer

        compressed = []
        total = 0

        # Walk history backwards (newest first)
        for msg in reversed(history):
            msg_tokens = estimate_tokens(msg["content"])
            if total + msg_tokens > available:
                break
            compressed.insert(0, msg)
            total += msg_tokens

        return compressed
```

### 2. Sliding Window with Summary
```python
def summarize_old_history(history: list[dict], model: str) -> str:
    """Use a fast model to summarize old conversation history."""
    old_text = "\n".join(f"{m['role']}: {m['content']}" for m in history)
    summary = litellm.completion(
        model="ollama/phi3.5",  # fast small model for summarization
        messages=[{
            "role": "user",
            "content": f"Summarize this conversation in 3-5 sentences:\n\n{old_text}"
        }],
        max_tokens=200
    )
    return summary.choices[0].message.content
```

### 3. Memory-Enforced Loop (MindSpark pattern)
Instead of fitting history into context, pull relevant past context via vector search:
```python
class MemoryEnforcedLoop:
    def get_relevant_context(self, current_message: str) -> list[str]:
        # Search MindSpark's SQLite-VSS store
        results = self.rag.search(current_message, top_k=3)
        return [r.text for r in results]
```

---

## TTS Architecture for Sigrid's Voice

### Stack Recommendation
```
kokoro-82M     → best quality/speed for Viking female voice
piper-tts      → good fallback, very fast
chatterbox-tts → good for expressive output
coqui-xtts     → voice cloning capable (custom voice)
```

### Voice Profile for Sigrid
```python
SIGRID_TTS_CONFIG = {
    "engine": "kokoro",
    "voice": "af_heart",     # warm female voice
    "speed": 0.95,           # slightly slower = more gravitas
    "pitch": 0.98,           # very slightly lower = mature
    "emphasis": 1.1,         # slightly more expressive
    "pause_between_sentences": 0.3,  # breathing room
}

# For Oracle mode — different voice settings
SIGRID_ORACLE_TTS = {
    **SIGRID_TTS_CONFIG,
    "speed": 0.85,           # slower = more deliberate
    "emphasis": 1.3,         # more expressive for drama
}
```

### Norse Word Pronunciation Guide (for TTS)
TTS engines mispronounce Norse words. Override pronunciations:
```python
NORSE_PRONUNCIATIONS = {
    # Rune names
    "Fehu":    "FAY-hoo",
    "Uruz":    "OO-rooz",
    "Thurisaz": "THOO-ree-sahz",
    "Ansuz":   "AHN-sooz",
    "Raidho":  "RYE-though",
    "Kenaz":   "KAY-nahz",
    "Hagalaz": "HAH-gah-lahz",
    "Nauthiz": "NOW-theez",
    "Isa":     "EE-sah",
    "Jera":    "YEH-rah",
    "Eihwaz":  "AY-vahz",
    "Perthro": "PEH-throw",
    "Algiz":   "AHL-geez",
    "Sowilo":  "SOH-wee-loh",
    "Tiwaz":   "TEE-vahz",
    "Berkano": "BEHR-kah-noh",
    "Ehwaz":   "EH-vahz",
    "Mannaz":  "MAHN-ahz",
    "Laguz":   "LAH-gooz",
    "Ingwaz":  "ING-vahz",
    "Dagaz":   "DAH-gahz",
    "Othala":  "OH-thah-lah",
    # Deity names
    "Freyja":  "FRAY-yah",
    "Freyr":   "FRAYR",
    "Odin":    "OH-din",
    "Yggdrasil": "IG-drah-sil",
    "Mjolnir": "MYOL-nir",
    "Valhalla": "val-HAH-la",
    "Völva":   "VUHL-vah",
    "Seidr":   "SAY-ther",
    "Galdr":   "GAHL-dr",
}

def apply_pronunciations(text: str) -> str:
    for word, pronunciation in NORSE_PRONUNCIATIONS.items():
        text = text.replace(word, f'<phoneme alphabet="ipa">{pronunciation}</phoneme>')
    return text
```

---

## LM Studio / Jan Integration

For GUI-friendly local model management:
```
LM Studio → easy model download + OpenAI-compatible server
Jan       → multi-model management + API
Koboldcpp → best for roleplay/character AI use cases
llama.cpp → raw performance, command-line
```

### Koboldcpp Settings for Sigrid
```bash
koboldcpp \
    --model mistral-nemo.gguf \
    --contextsize 8192 \
    --threads 8 \
    --gpulayers 40 \
    --port 5001 \
    --host 0.0.0.0 \
    --smartcontext \          # retain context intelligently
    --unbannedtokens \        # allow all vocabulary
    --sdp                     # story device padding
```

`--smartcontext` is particularly useful — it retains context intelligently across the context window limit, similar to the compaction system in Claude Code.

---

## Practical Routing Strategy for Sigrid

```python
class SigridRouter:
    def route(self, request: SigridRequest) -> str:
        """Choose the right model for the task."""
        if request.mode == "oracle":
            return "ollama/llama3.1:70b"    # best quality for divination

        if request.type == "casual_chat":
            if self.is_local_available():
                return "ollama/mistral-nemo"  # fast local
            return "anthropic/claude-haiku-4-5"  # cheap cloud fallback

        if request.type == "lore_lookup":
            return "ollama/gemma2:9b"        # strong knowledge retrieval

        if request.type == "creative_writing":
            return "ollama/mistral-nemo"     # creative + contextual

        if request.type == "saga_composition":
            return "anthropic/claude-opus-4-6"  # best for long-form

        return "ollama/mistral-nemo"  # default

    def is_local_available(self) -> bool:
        try:
            return requests.get("http://localhost:11434/api/tags", timeout=1).ok
        except:
            return False
```
