"""Tests for OllamaConnector — HTTP client for Ollama."""
from __future__ import annotations

import json
import urllib.error
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from wyrdforge.llm.ollama_connector import (
    OllamaConnector,
    OllamaResponseError,
    OllamaUnavailableError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_response(data: dict) -> MagicMock:
    """Build a mock urllib response that returns JSON bytes."""
    body = json.dumps(data).encode("utf-8")
    mock = MagicMock()
    mock.read.return_value = body
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def _url_error() -> urllib.error.URLError:
    return urllib.error.URLError("Connection refused")


# ---------------------------------------------------------------------------
# Constructor / properties
# ---------------------------------------------------------------------------

def test_default_host_and_port() -> None:
    c = OllamaConnector()
    assert c.host == "localhost"
    assert c.port == 11434


def test_default_model() -> None:
    c = OllamaConnector()
    assert c.model == "llama3"


def test_custom_model() -> None:
    c = OllamaConnector(model="mistral")
    assert c.model == "mistral"


def test_base_url() -> None:
    c = OllamaConnector(host="myhost", port=9999)
    assert c.base_url == "http://myhost:9999"


def test_repr() -> None:
    c = OllamaConnector(model="gemma")
    assert "gemma" in repr(c)


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------

def test_is_available_returns_true_when_reachable() -> None:
    c = OllamaConnector()
    fake = _fake_response({"models": []})
    with patch("urllib.request.urlopen", return_value=fake):
        assert c.is_available() is True


def test_is_available_returns_false_when_unreachable() -> None:
    c = OllamaConnector()
    with patch("urllib.request.urlopen", side_effect=_url_error()):
        assert c.is_available() is False


# ---------------------------------------------------------------------------
# list_models
# ---------------------------------------------------------------------------

def test_list_models_returns_model_names() -> None:
    c = OllamaConnector()
    data = {"models": [{"name": "llama3"}, {"name": "mistral"}]}
    with patch("urllib.request.urlopen", return_value=_fake_response(data)):
        models = c.list_models()
    assert "llama3" in models
    assert "mistral" in models


def test_list_models_empty_when_no_models() -> None:
    c = OllamaConnector()
    with patch("urllib.request.urlopen", return_value=_fake_response({"models": []})):
        assert c.list_models() == []


def test_list_models_raises_unavailable_on_error() -> None:
    c = OllamaConnector()
    with patch("urllib.request.urlopen", side_effect=_url_error()):
        with pytest.raises(OllamaUnavailableError):
            c.list_models()


# ---------------------------------------------------------------------------
# chat
# ---------------------------------------------------------------------------

def test_chat_returns_response_content() -> None:
    c = OllamaConnector()
    data = {"message": {"role": "assistant", "content": "Hail, wanderer!"}}
    with patch("urllib.request.urlopen", return_value=_fake_response(data)):
        result = c.chat([{"role": "user", "content": "Hello"}])
    assert result == "Hail, wanderer!"


def test_chat_raises_unavailable_when_server_down() -> None:
    c = OllamaConnector()
    with patch("urllib.request.urlopen", side_effect=_url_error()):
        with pytest.raises(OllamaUnavailableError):
            c.chat([{"role": "user", "content": "Hello"}])


def test_chat_raises_response_error_on_bad_json_shape() -> None:
    c = OllamaConnector()
    # Response missing "message" key
    bad_data = {"result": "oops"}
    with patch("urllib.request.urlopen", return_value=_fake_response(bad_data)):
        with pytest.raises(OllamaResponseError):
            c.chat([{"role": "user", "content": "Hello"}])


def test_chat_uses_default_model() -> None:
    c = OllamaConnector(model="phi3")
    data = {"message": {"role": "assistant", "content": "ok"}}
    captured: list[bytes] = []

    def fake_urlopen(req, timeout=None):
        captured.append(req.data)
        return _fake_response(data)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        c.chat([{"role": "user", "content": "hi"}])

    payload = json.loads(captured[0].decode())
    assert payload["model"] == "phi3"


def test_chat_model_override() -> None:
    c = OllamaConnector(model="llama3")
    data = {"message": {"role": "assistant", "content": "ok"}}
    captured: list[bytes] = []

    def fake_urlopen(req, timeout=None):
        captured.append(req.data)
        return _fake_response(data)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        c.chat([{"role": "user", "content": "hi"}], model="mistral")

    payload = json.loads(captured[0].decode())
    assert payload["model"] == "mistral"


def test_chat_sends_stream_false() -> None:
    c = OllamaConnector()
    data = {"message": {"role": "assistant", "content": "ok"}}
    captured: list[bytes] = []

    def fake_urlopen(req, timeout=None):
        captured.append(req.data)
        return _fake_response(data)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        c.chat([{"role": "user", "content": "hi"}])

    payload = json.loads(captured[0].decode())
    assert payload["stream"] is False
