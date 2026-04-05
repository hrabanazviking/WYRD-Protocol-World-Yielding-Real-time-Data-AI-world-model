"""Ollama HTTP connector.

Communicates with a locally-running Ollama server (http://localhost:11434).
Uses stdlib ``urllib`` only — no extra HTTP deps required.

Raises:
    OllamaUnavailableError  — server not reachable or connection refused
    OllamaResponseError     — server returned unexpected JSON shape
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.request import Request


class OllamaError(Exception):
    """Base class for Ollama connector errors."""


class OllamaUnavailableError(OllamaError):
    """Ollama server is not reachable."""


class OllamaResponseError(OllamaError):
    """Ollama returned an unexpected response."""


class OllamaConnector:
    """Thin HTTP client for the Ollama /api/chat endpoint.

    Args:
        host:    Hostname where Ollama is running.
        port:    Port Ollama is listening on.
        model:   Default model name (e.g. ``"llama3"``, ``"mistral"``).
        timeout: HTTP timeout in seconds.
    """

    def __init__(
        self,
        *,
        host: str = "localhost",
        port: int = 11434,
        model: str = "llama3",
        timeout: int = 60,
    ) -> None:
        self.host = host
        self.port = port
        self.model = model
        self.timeout = timeout

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return True if the Ollama server is reachable."""
        try:
            req = Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=5):
                return True
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """Return model names currently loaded in Ollama.

        Raises:
            OllamaUnavailableError: server not reachable.
        """
        try:
            req = Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m["name"] for m in data.get("models", [])]
        except urllib.error.URLError as e:
            raise OllamaUnavailableError(f"Cannot reach Ollama at {self.base_url}: {e}") from e
        except (KeyError, json.JSONDecodeError) as e:
            raise OllamaResponseError(f"Unexpected /api/tags response: {e}") from e

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        stream: bool = False,
    ) -> str:
        """Send a chat request and return the assistant response text.

        Args:
            messages:    OpenAI-style message list
                         ``[{"role": "system"|"user"|"assistant", "content": "..."}]``.
            model:       Override the default model for this call.
            temperature: Sampling temperature (0.0–2.0).
            stream:      If True, stream tokens.  Currently unsupported;
                         always set to False.

        Returns:
            The assistant's response string.

        Raises:
            OllamaUnavailableError: server not reachable.
            OllamaResponseError:    unexpected JSON in response.
        """
        payload = {
            "model": model or self.model,
            "messages": messages,
            "stream": False,  # streaming not yet handled
            "options": {"temperature": temperature},
        }
        body = json.dumps(payload).encode("utf-8")
        req = Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["message"]["content"]
        except urllib.error.URLError as e:
            raise OllamaUnavailableError(f"Cannot reach Ollama at {self.base_url}: {e}") from e
        except (KeyError, json.JSONDecodeError) as e:
            raise OllamaResponseError(f"Unexpected /api/chat response: {e}") from e

    def __repr__(self) -> str:
        return f"OllamaConnector(host={self.host!r}, port={self.port}, model={self.model!r})"
