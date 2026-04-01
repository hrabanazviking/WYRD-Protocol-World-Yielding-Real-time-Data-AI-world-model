# MindSpark ThoughtForge — Phase 7 & 8 Architecture Design
> Synthesized from: Claude Code utils/services patterns (doc 08), MCP protocol (doc 12),
> config/settings (doc 14), multi-agent patterns (doc 07), Rust runtime patterns (doc 11).
> Phase 7: Setup Wizard + Backend Adapters + Interactive Chat
> Phase 8: Robustness + Self-Heal + Production Hardening

## Current State (v1.0.1, Phases 0-6 Complete)

MindSpark ThoughtForge is a universal cognitive enhancement layer:
- Sovereign RAG (SQLite-VSS for private vector search)
- TurboQuant (quantization-aware inference)
- Cognition Scaffolds (chain-of-thought injection)
- Fragment Salvage (partial response recovery)
- Memory-Enforced Loop (RAG-informed conversation)
- 447 tests passing on HEAD 123dce7

Phase 7 and 8 are specced but not started. This document designs them from patterns learned.

---

## Phase 7A: Setup Wizard

The Claude Code boot sequence (`loadSettings → validateConfig → initMcp → loadMemdir`) shows the right pattern: **structured initialization with clear failure modes**. MindSpark needs its own.

```python
# setup_wizard.py — First-run wizard for MindSpark

from enum import Enum
from dataclasses import dataclass
from typing import Optional
import json, os

class SetupStep(str, Enum):
    DETECT_HARDWARE = "detect_hardware"
    SELECT_BACKEND = "select_backend"
    CONFIGURE_MODELS = "configure_models"
    SETUP_RAG = "setup_rag"
    TEST_CONNECTION = "test_connection"
    WRITE_CONFIG = "write_config"
    COMPLETE = "complete"

@dataclass
class HardwareProfile:
    vram_gb: float               # 0 if CPU-only
    ram_gb: float
    cpu_cores: int
    has_cuda: bool
    has_metal: bool              # Mac Apple Silicon
    has_vulkan: bool             # AMD GPU
    recommended_tier: str        # "cpu_tiny", "gpu_small", "gpu_medium", "gpu_large"

@dataclass
class WizardState:
    current_step: SetupStep = SetupStep.DETECT_HARDWARE
    hardware: Optional[HardwareProfile] = None
    selected_backend: Optional[str] = None  # "ollama", "llamacpp", "lmstudio", "openai_compat"
    model_config: dict = None
    rag_config: dict = None
    errors: list = None

class SetupWizard:
    """
    Interactive first-run configuration wizard.
    Modeled on Claude Code's config init: detect → validate → write.
    """

    CONFIG_PATH = os.path.expanduser("~/.config/mindspark/config.json")

    def run(self) -> bool:
        """Run the full setup sequence. Returns True if successful."""
        state = WizardState()

        steps = [
            self.detect_hardware,
            self.select_backend,
            self.configure_models,
            self.setup_rag_store,
            self.test_connection,
            self.write_config,
        ]

        for step in steps:
            print(f"\n{'='*50}")
            success = step(state)
            if not success:
                print(f"Setup failed at step: {state.current_step}")
                return False

        self.show_completion(state)
        return True

    def detect_hardware(self, state: WizardState) -> bool:
        """Auto-detect hardware and recommend a tier."""
        print("Detecting your hardware...")
        hardware = self._probe_hardware()
        state.hardware = hardware

        print(f"  RAM: {hardware.ram_gb:.0f} GB")
        print(f"  VRAM: {hardware.vram_gb:.0f} GB {'(CUDA)' if hardware.has_cuda else '(CPU only)' if hardware.vram_gb == 0 else ''}")
        print(f"  Recommended tier: {hardware.recommended_tier}")
        state.current_step = SetupStep.SELECT_BACKEND
        return True

    def _probe_hardware(self) -> HardwareProfile:
        import psutil
        ram = psutil.virtual_memory().total / (1024**3)

        vram = 0.0
        has_cuda = False
        try:
            import torch
            if torch.cuda.is_available():
                has_cuda = True
                vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        except ImportError:
            pass

        has_metal = False
        try:
            import platform
            if platform.system() == "Darwin":
                import subprocess
                result = subprocess.run(["sysctl", "hw.memsize"], capture_output=True, text=True)
                if result.returncode == 0:
                    has_metal = True
                    vram = ram  # Unified memory — all RAM is effectively VRAM
        except Exception:
            pass

        if vram >= 16:
            tier = "gpu_large"
        elif vram >= 8:
            tier = "gpu_medium"
        elif vram >= 4:
            tier = "gpu_small"
        else:
            tier = "cpu_tiny"

        return HardwareProfile(
            vram_gb=vram, ram_gb=ram,
            cpu_cores=psutil.cpu_count(logical=False) or 4,
            has_cuda=has_cuda, has_metal=has_metal, has_vulkan=False,
            recommended_tier=tier
        )

    def select_backend(self, state: WizardState) -> bool:
        """Let user choose their model backend."""
        backends = {
            "1": ("ollama", "Ollama (recommended — easy install, local models)"),
            "2": ("llamacpp", "llama.cpp (fastest raw performance, CLI)"),
            "3": ("lmstudio", "LM Studio (GUI model manager, OpenAI-compatible)"),
            "4": ("openai_compat", "OpenAI-compatible server (custom endpoint)"),
        }

        print("\nSelect your AI backend:")
        for k, (_, desc) in backends.items():
            print(f"  {k}. {desc}")

        choice = input("\nChoice [1]: ").strip() or "1"
        if choice not in backends:
            print("Invalid choice")
            return False

        state.selected_backend = backends[choice][0]
        state.current_step = SetupStep.CONFIGURE_MODELS
        return True

    def configure_models(self, state: WizardState) -> bool:
        """Set up model recommendations based on hardware + backend."""
        tier = state.hardware.recommended_tier
        backend = state.selected_backend

        MODEL_TIERS = {
            "cpu_tiny": {
                "primary": "phi3.5:mini",
                "embedding": "all-minilm",
                "context_size": 2048,
            },
            "gpu_small": {
                "primary": "mistral:7b",
                "embedding": "nomic-embed-text",
                "context_size": 4096,
            },
            "gpu_medium": {
                "primary": "mistral-nemo",
                "embedding": "nomic-embed-text",
                "context_size": 8192,
            },
            "gpu_large": {
                "primary": "llama3.1:70b",
                "embedding": "nomic-embed-text",
                "context_size": 32768,
                "secondary": "mistral-nemo",  # for fast calls
            },
        }

        recommended = MODEL_TIERS[tier]
        print(f"\nRecommended models for your hardware ({tier}):")
        for k, v in recommended.items():
            print(f"  {k}: {v}")

        use_recommended = input("\nUse these? [Y/n]: ").strip().lower()
        if use_recommended == "n":
            primary = input("Primary model name: ").strip()
            recommended["primary"] = primary

        state.model_config = recommended
        state.current_step = SetupStep.SETUP_RAG
        return True

    def setup_rag_store(self, state: WizardState) -> bool:
        """Configure the SQLite-VSS RAG store."""
        default_path = os.path.expanduser("~/.local/share/mindspark/rag.db")
        print(f"\nRAG store location [{default_path}]: ", end="")
        path = input().strip() or default_path

        os.makedirs(os.path.dirname(path), exist_ok=True)
        state.rag_config = {
            "db_path": path,
            "embedding_model": state.model_config.get("embedding", "all-minilm"),
            "chunk_size": 512,
            "chunk_overlap": 64,
            "top_k": 5,
        }
        state.current_step = SetupStep.TEST_CONNECTION
        return True

    def test_connection(self, state: WizardState) -> bool:
        """Verify the backend is reachable and the model is available."""
        import requests
        backend = state.selected_backend
        primary = state.model_config["primary"]

        endpoints = {
            "ollama": "http://localhost:11434",
            "llamacpp": "http://localhost:8080",
            "lmstudio": "http://localhost:1234",
        }

        if backend in endpoints:
            url = endpoints[backend]
            try:
                r = requests.get(url, timeout=3)
                if r.ok:
                    print(f"  Backend at {url}: OK")
                else:
                    print(f"  Backend returned status {r.status_code}")
                    return False
            except requests.ConnectionError:
                print(f"  Cannot reach {url}. Is {backend} running?")
                print(f"  Tip: for Ollama, run: ollama serve")
                return False

        print(f"  Model '{primary}': assuming available")
        return True

    def write_config(self, state: WizardState) -> bool:
        """Write the final config to disk."""
        config = {
            "version": "1.0",
            "backend": state.selected_backend,
            "models": state.model_config,
            "rag": state.rag_config,
            "hardware_tier": state.hardware.recommended_tier,
            "cognitive_scaffolds": {
                "chain_of_thought": True,
                "fragment_salvage": True,
                "memory_enforced_loop": True,
            }
        }

        os.makedirs(os.path.dirname(self.CONFIG_PATH), exist_ok=True)
        with open(self.CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=2)

        print(f"\nConfig written to: {self.CONFIG_PATH}")
        return True

    def show_completion(self, state: WizardState):
        print("\n" + "="*50)
        print("MindSpark ThoughtForge is ready!")
        print(f"Backend: {state.selected_backend}")
        print(f"Primary model: {state.model_config['primary']}")
        print(f"RAG store: {state.rag_config['db_path']}")
        print("\nRun: python -m mindspark chat")
```

---

## Phase 7B: Backend Adapter System

Claude Code's `ApiClient` trait (from Rust runtime) shows the pattern: **abstract the backend behind a trait so the engine doesn't care which model provider it's using**.

```python
# backends/base.py — Backend abstraction layer

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Optional

@dataclass
class LLMRequest:
    messages: list[dict]
    system: Optional[str] = None
    max_tokens: int = 2048
    temperature: float = 0.7
    stream: bool = False
    tools: Optional[list] = None
    tool_choice: Optional[str] = None

@dataclass
class LLMResponse:
    content: str
    finish_reason: str          # "stop", "length", "tool_use"
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: list = None

class BaseBackend(ABC):
    """Abstract backend — all model providers implement this."""

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Single completion call."""
        pass

    @abstractmethod
    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Streaming completion — yields tokens."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the backend is reachable."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

# backends/ollama.py
import aiohttp

class OllamaBackend(BaseBackend):
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "mistral-nemo"):
        self.base_url = base_url
        self.model = model

    @property
    def name(self) -> str:
        return f"ollama/{self.model}"

    def is_available(self) -> bool:
        import requests
        try:
            return requests.get(f"{self.base_url}/api/tags", timeout=2).ok
        except Exception:
            return False

    async def complete(self, request: LLMRequest) -> LLMResponse:
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": self.model,
                "messages": request.messages,
                "stream": False,
                "options": {
                    "temperature": request.temperature,
                    "num_predict": request.max_tokens,
                }
            }
            if request.system:
                payload["system"] = request.system

            async with session.post(f"{self.base_url}/api/chat", json=payload) as r:
                data = await r.json()
                msg = data.get("message", {})
                return LLMResponse(
                    content=msg.get("content", ""),
                    finish_reason="stop",
                    input_tokens=data.get("prompt_eval_count", 0),
                    output_tokens=data.get("eval_count", 0),
                )

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": self.model,
                "messages": request.messages,
                "stream": True,
                "options": {"temperature": request.temperature}
            }
            async with session.post(f"{self.base_url}/api/chat", json=payload) as r:
                async for line in r.content:
                    if line:
                        import json
                        chunk = json.loads(line.decode())
                        delta = chunk.get("message", {}).get("content", "")
                        if delta:
                            yield delta
                        if chunk.get("done"):
                            break

# backends/openai_compat.py — works with LM Studio, llama.cpp, etc.
from openai import AsyncOpenAI

class OpenAICompatBackend(BaseBackend):
    def __init__(self, base_url: str, model: str, api_key: str = "not-needed"):
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    @property
    def name(self) -> str:
        return f"openai-compat/{self.model}"

    def is_available(self) -> bool:
        import requests
        try:
            return requests.get(f"{self.client.base_url}/models", timeout=2).ok
        except Exception:
            return False

    async def complete(self, request: LLMRequest) -> LLMResponse:
        messages = request.messages
        if request.system:
            messages = [{"role": "system", "content": request.system}] + messages

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )
        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content,
            finish_reason=choice.finish_reason,
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        messages = request.messages
        if request.system:
            messages = [{"role": "system", "content": request.system}] + messages

        stream = await self.client.chat.completions.create(
            model=self.model, messages=messages,
            max_tokens=request.max_tokens, stream=True
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

# Router — with fallback (Claude Code pattern)
class BackendRouter:
    """Routes requests to available backends with automatic fallback."""

    def __init__(self, backends: list[BaseBackend]):
        self.backends = backends  # ordered by preference

    def get_backend(self) -> BaseBackend:
        for backend in self.backends:
            if backend.is_available():
                return backend
        raise RuntimeError("No available backends. Is Ollama running?")

    async def complete(self, request: LLMRequest) -> LLMResponse:
        backend = self.get_backend()
        return await backend.complete(request)
```

---

## Phase 7C: Interactive Chat Interface

Pattern from Claude Code REPL: **streaming output, keyboard handlers, clean exit**.

```python
# chat.py — Interactive streaming chat interface

import asyncio
import sys
from mindspark.core import ThoughtForge
from mindspark.backends import BackendRouter

class MindSparkChat:
    """
    Interactive chat loop for MindSpark ThoughtForge.
    Modeled on Claude Code's REPL: streaming, clean, keyboard-aware.
    """

    SYSTEM_PROMPT = """You are ThoughtForge, a cognitive enhancement layer.
You have access to the user's RAG knowledge store. When relevant information is found,
integrate it naturally into your response.

Always think step-by-step for complex questions.
Be direct. Don't pad responses. Don't start with filler affirmations."""

    def __init__(self):
        self.forge = ThoughtForge.from_config()
        self.history = []

    async def run(self):
        print("MindSpark ThoughtForge — Interactive Chat")
        print("Type 'exit' or Ctrl+C to quit. '/forget' to clear history.")
        print("-" * 50)

        while True:
            try:
                user_input = await self._get_input()
            except (EOFError, KeyboardInterrupt):
                print("\nGodspeed.")
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", ":q"):
                print("Godspeed.")
                break
            if user_input.lower() == "/forget":
                self.history = []
                print("History cleared.")
                continue

            await self._process_turn(user_input)

    async def _get_input(self) -> str:
        print("\nYou: ", end="", flush=True)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, input)

    async def _process_turn(self, user_input: str):
        # Retrieve relevant RAG context
        rag_context = await self.forge.retrieve_relevant(user_input, top_k=3)

        # Build messages
        messages = self.history.copy()
        if rag_context:
            # Inject RAG as a system reminder (XML-tagged as data, not instruction)
            context_msg = f"<retrieved_context>\n{rag_context}\n</retrieved_context>"
            messages.append({"role": "user", "content": f"{context_msg}\n\n{user_input}"})
        else:
            messages.append({"role": "user", "content": user_input})

        # Stream the response
        print("\nThoughtForge: ", end="", flush=True)
        full_response = ""

        try:
            async for token in self.forge.stream_response(messages, system=self.SYSTEM_PROMPT):
                print(token, end="", flush=True)
                full_response += token
        except Exception as e:
            print(f"\n[Error: {e}]")
            return

        print()  # newline after streaming completes

        # Update history
        self.history.append({"role": "user", "content": user_input})
        self.history.append({"role": "assistant", "content": full_response})

        # Trim history to prevent context overflow (sliding window pattern)
        self._trim_history()

        # Optionally save notable moments to memory
        await self.forge.maybe_save_memory(user_input, full_response)

    def _trim_history(self, max_exchanges: int = 10):
        """Keep the last N exchanges in history. Summarize older ones if needed."""
        max_messages = max_exchanges * 2
        if len(self.history) > max_messages:
            # Keep the last max_messages, drop the oldest
            self.history = self.history[-max_messages:]
```

---

## Phase 8: Robustness + Self-Heal

### 8A: Self-Diagnostics (Claude Code's health check pattern)

```python
# diagnostics.py

from dataclasses import dataclass
from typing import List

@dataclass
class DiagnosticResult:
    component: str
    status: str       # "ok", "warning", "error"
    message: str
    fix_command: str = ""

class MindSparkDiagnostics:
    """
    Self-diagnostic system — run on startup or via 'mindspark doctor'.
    Modeled on Claude Code's startup validation sequence.
    """

    def run_all(self) -> List[DiagnosticResult]:
        checks = [
            self.check_config,
            self.check_backend,
            self.check_rag_store,
            self.check_models,
            self.check_disk_space,
            self.check_dependencies,
        ]
        return [check() for check in checks]

    def check_config(self) -> DiagnosticResult:
        import os, json
        config_path = os.path.expanduser("~/.config/mindspark/config.json")
        if not os.path.exists(config_path):
            return DiagnosticResult(
                "config", "error",
                "No config found",
                "python -m mindspark setup"
            )
        try:
            with open(config_path) as f:
                config = json.load(f)
            required = ["backend", "models", "rag"]
            missing = [k for k in required if k not in config]
            if missing:
                return DiagnosticResult("config", "warning",
                    f"Config missing keys: {missing}",
                    "python -m mindspark setup --repair")
        except json.JSONDecodeError as e:
            return DiagnosticResult("config", "error",
                f"Config is invalid JSON: {e}",
                "python -m mindspark setup --reset")
        return DiagnosticResult("config", "ok", "Config valid")

    def check_backend(self) -> DiagnosticResult:
        from mindspark.backends import BackendRouter, load_backends
        try:
            backends = load_backends()
            router = BackendRouter(backends)
            backend = router.get_backend()
            return DiagnosticResult("backend", "ok", f"Using {backend.name}")
        except RuntimeError as e:
            return DiagnosticResult("backend", "error", str(e),
                "ollama serve  # or start your preferred backend")

    def check_rag_store(self) -> DiagnosticResult:
        import os
        from mindspark.rag import SovereignRAG
        try:
            rag = SovereignRAG.from_config()
            count = rag.document_count()
            return DiagnosticResult("rag_store", "ok",
                f"RAG store OK — {count} documents indexed")
        except Exception as e:
            return DiagnosticResult("rag_store", "error", str(e),
                "python -m mindspark rag init")

    def check_disk_space(self) -> DiagnosticResult:
        import shutil, os
        path = os.path.expanduser("~/.local/share/mindspark")
        if not os.path.exists(path):
            return DiagnosticResult("disk", "ok", "RAG store not yet created")
        total, used, free = shutil.disk_usage(path)
        free_gb = free / (1024**3)
        if free_gb < 1:
            return DiagnosticResult("disk", "warning",
                f"Low disk space: {free_gb:.1f} GB free")
        return DiagnosticResult("disk", "ok", f"{free_gb:.1f} GB free")

    def check_models(self) -> DiagnosticResult:
        """Check if configured models are available in Ollama."""
        import requests
        try:
            r = requests.get("http://localhost:11434/api/tags", timeout=2)
            if not r.ok:
                return DiagnosticResult("models", "warning", "Cannot list Ollama models")
            available = {m["name"] for m in r.json().get("models", [])}
            from mindspark.config import load_config
            config = load_config()
            primary = config["models"]["primary"]
            if primary not in available and primary.split(":")[0] not in available:
                return DiagnosticResult("models", "warning",
                    f"Primary model '{primary}' not found",
                    f"ollama pull {primary}")
            return DiagnosticResult("models", "ok", f"Model '{primary}' available")
        except Exception as e:
            return DiagnosticResult("models", "warning", f"Model check skipped: {e}")

    def check_dependencies(self) -> DiagnosticResult:
        required = ["aiohttp", "sentence_transformers", "sqlite_vss", "psutil"]
        missing = []
        for pkg in required:
            try:
                __import__(pkg.replace("-", "_"))
            except ImportError:
                missing.append(pkg)
        if missing:
            return DiagnosticResult("dependencies", "error",
                f"Missing: {', '.join(missing)}",
                f"pip install {' '.join(missing)}")
        return DiagnosticResult("dependencies", "ok", "All dependencies present")

    def print_report(self, results: List[DiagnosticResult]):
        print("\nMindSpark Diagnostics")
        print("=" * 50)
        icons = {"ok": "✓", "warning": "⚠", "error": "✗"}
        all_ok = True
        for r in results:
            icon = icons.get(r.status, "?")
            print(f"  {icon} {r.component}: {r.message}")
            if r.fix_command:
                print(f"      Fix: {r.fix_command}")
            if r.status != "ok":
                all_ok = False
        print()
        if all_ok:
            print("All systems nominal.")
        else:
            print("Issues found. Run the fix commands above.")
```

---

### 8B: Fragment Salvage Enhancement (Phase 8 extension)

Claude Code's SSE buffer accumulation pattern for handling partial responses:

```python
# salvage/enhanced_salvage.py

import json, re
from typing import Optional

class EnhancedFragmentSalvage:
    """
    Extended fragment salvage: recovers usable content from truncated/malformed LLM output.
    Handles structured output (JSON tool calls) and unstructured prose differently.
    """

    def salvage(self, raw_output: str, expected_format: str = "prose") -> Optional[str]:
        if not raw_output or not raw_output.strip():
            return None

        if expected_format == "json":
            return self._salvage_json(raw_output)
        elif expected_format == "tool_call":
            return self._salvage_tool_call(raw_output)
        else:
            return self._salvage_prose(raw_output)

    def _salvage_prose(self, text: str) -> str:
        """For prose: return what we have, up to the last complete sentence."""
        # Find last complete sentence ending
        sentence_endings = [m.end() for m in re.finditer(r'[.!?]["\')\]]*\s', text)]
        if sentence_endings:
            return text[:sentence_endings[-1]].strip()
        # No complete sentence — return as-is if it's substantial
        return text.strip() if len(text.strip()) > 20 else None

    def _salvage_json(self, text: str) -> Optional[str]:
        """For JSON: try to close open braces and parse."""
        text = text.strip()
        # Try as-is first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Count open braces and try to close them
        open_braces = text.count('{') - text.count('}')
        open_brackets = text.count('[') - text.count(']')
        salvaged = text + (']' * max(0, open_brackets)) + ('}' * max(0, open_braces))
        try:
            return json.loads(salvaged)
        except json.JSONDecodeError:
            pass

        # Extract whatever key:value pairs we can find
        pairs = re.findall(r'"(\w+)":\s*"([^"]*)"', text)
        if pairs:
            return dict(pairs)

        return None

    def _salvage_tool_call(self, text: str) -> Optional[dict]:
        """For tool calls: extract the partial input JSON if possible."""
        # Look for the input_json pattern from Claude tool use streaming
        input_match = re.search(r'"input":\s*(\{.*)', text, re.DOTALL)
        if input_match:
            return self._salvage_json(input_match.group(1))
        return None
```

---

### 8C: Circuit Breaker (Production Hardening)

From the Rust runtime retry pattern — but with circuit breaker for sustained failures:

```python
# resilience/circuit_breaker.py

import time
from enum import Enum
from dataclasses import dataclass, field

class CircuitState(str, Enum):
    CLOSED = "closed"      # normal operation
    OPEN = "open"          # failing — reject immediately
    HALF_OPEN = "half_open"  # testing recovery

@dataclass
class CircuitBreaker:
    """
    Circuit breaker for LLM backend calls.
    Prevents hammering a failing backend.
    """
    failure_threshold: int = 5      # failures before opening
    recovery_timeout: float = 60.0  # seconds before trying again
    success_threshold: int = 2      # successes in half-open before closing

    state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    failure_count: int = field(default=0, init=False)
    success_count: int = field(default=0, init=False)
    last_failure_time: float = field(default=0.0, init=False)

    def can_proceed(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                return True
            return False
        # HALF_OPEN — allow through
        return True

    def record_success(self):
        self.failure_count = 0
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self.state = CircuitState.CLOSED

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

    @property
    def status_string(self) -> str:
        return f"Circuit {self.state.value} (failures: {self.failure_count})"
```

---

## Phase Summary

| Phase | Component | Pattern Source |
|---|---|---|
| 7A | Setup Wizard | Claude Code boot sequence (loadSettings → validate → write) |
| 7B | Backend Adapters | Rust runtime ApiClient trait (abstract + swap) |
| 7C | Chat Interface | Claude Code REPL (streaming, history, keyboard) |
| 8A | Self-Diagnostics | Claude Code startup validation pattern |
| 8B | Fragment Salvage+ | SSE buffer accumulation + InputJsonDelta pattern |
| 8C | Circuit Breaker | Rust retry config + failure classification |

## CLI Interface (Phase 7 entry points)

```python
# __main__.py — MindSpark CLI

import argparse, asyncio

def main():
    parser = argparse.ArgumentParser(prog="mindspark")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("setup", help="Run the setup wizard")
    subparsers.add_parser("chat", help="Start interactive chat")
    subparsers.add_parser("doctor", help="Run diagnostics")

    ingest = subparsers.add_parser("ingest", help="Add documents to RAG store")
    ingest.add_argument("path", help="File or directory to ingest")

    subparsers.add_parser("stats", help="Show RAG store statistics")

    args = parser.parse_args()

    if args.command == "setup":
        from mindspark.setup_wizard import SetupWizard
        SetupWizard().run()
    elif args.command == "chat":
        from mindspark.chat import MindSparkChat
        asyncio.run(MindSparkChat().run())
    elif args.command == "doctor":
        from mindspark.diagnostics import MindSparkDiagnostics
        diag = MindSparkDiagnostics()
        diag.print_report(diag.run_all())
    elif args.command == "ingest":
        from mindspark.ingest import ingest_path
        asyncio.run(ingest_path(args.path))
    elif args.command == "stats":
        from mindspark.rag import SovereignRAG
        rag = SovereignRAG.from_config()
        print(f"Documents indexed: {rag.document_count()}")
        print(f"Store size: {rag.store_size_mb():.1f} MB")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
```
