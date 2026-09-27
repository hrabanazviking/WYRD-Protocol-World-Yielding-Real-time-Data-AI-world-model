"""Tests for OllamaConnector — HTTP client for Ollama."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from wyrdforge.llm.ollama_connector import (
    OllamaConnector,
    OllamaResponseError,
    OllamaUnavailableError,
    _is_loopback_target,
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
    with patch.object(OllamaConnector, "_urlopen", return_value=fake):
        assert c.is_available() is True


def test_is_available_returns_false_when_unreachable() -> None:
    c = OllamaConnector()
    with patch.object(OllamaConnector, "_urlopen", side_effect=_url_error()):
        assert c.is_available() is False


# ---------------------------------------------------------------------------
# list_models
# ---------------------------------------------------------------------------

def test_list_models_returns_model_names() -> None:
    c = OllamaConnector()
    data = {"models": [{"name": "llama3"}, {"name": "mistral"}]}
    with patch.object(OllamaConnector, "_urlopen", return_value=_fake_response(data)):
        models = c.list_models()
    assert "llama3" in models
    assert "mistral" in models


def test_list_models_empty_when_no_models() -> None:
    c = OllamaConnector()
    with patch.object(OllamaConnector, "_urlopen", return_value=_fake_response({"models": []})):
        assert c.list_models() == []


def test_list_models_raises_unavailable_on_error() -> None:
    c = OllamaConnector()
    with patch.object(OllamaConnector, "_urlopen", side_effect=_url_error()):
        with pytest.raises(OllamaUnavailableError):
            c.list_models()


# ---------------------------------------------------------------------------
# chat
# ---------------------------------------------------------------------------

def test_chat_returns_response_content() -> None:
    c = OllamaConnector()
    data = {"message": {"role": "assistant", "content": "Hail, wanderer!"}}
    with patch.object(OllamaConnector, "_urlopen", return_value=_fake_response(data)):
        result = c.chat([{"role": "user", "content": "Hello"}])
    assert result == "Hail, wanderer!"


def test_chat_raises_unavailable_when_server_down() -> None:
    c = OllamaConnector()
    with patch.object(OllamaConnector, "_urlopen", side_effect=_url_error()):
        with pytest.raises(OllamaUnavailableError):
            c.chat([{"role": "user", "content": "Hello"}])


def test_chat_raises_response_error_on_bad_json_shape() -> None:
    c = OllamaConnector()
    # Response missing "message" key
    bad_data = {"result": "oops"}
    with patch.object(OllamaConnector, "_urlopen", return_value=_fake_response(bad_data)):
        with pytest.raises(OllamaResponseError):
            c.chat([{"role": "user", "content": "Hello"}])


def test_chat_uses_default_model() -> None:
    c = OllamaConnector(model="phi3")
    data = {"message": {"role": "assistant", "content": "ok"}}
    captured: list[bytes] = []

    def fake_urlopen(req, timeout=None):
        captured.append(req.data)
        return _fake_response(data)

    with patch.object(OllamaConnector, "_urlopen", side_effect=fake_urlopen):
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

    with patch.object(OllamaConnector, "_urlopen", side_effect=fake_urlopen):
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

    with patch.object(OllamaConnector, "_urlopen", side_effect=fake_urlopen):
        c.chat([{"role": "user", "content": "hi"}])

    payload = json.loads(captured[0].decode())
    assert payload["stream"] is False


# ---------------------------------------------------------------------------
# Proxy-env posture (Track 1, P2 — Slice 4)
# ---------------------------------------------------------------------------

def test_loopback_bypasses_proxy_env(monkeypatch) -> None:
    """Localhost traffic must not be routed through proxy env vars."""
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:8080")
    c = OllamaConnector()  # localhost
    req = urllib.request.Request("http://localhost:11434/api/tags")
    fake_opener = MagicMock()
    fake_opener.open.return_value = _fake_response({"models": []})
    with patch("urllib.request.build_opener",
               return_value=fake_opener) as mock_build:
        c._urlopen(req, timeout=5)
    (handler,), _ = mock_build.call_args
    assert isinstance(handler, urllib.request.ProxyHandler)
    assert handler.proxies == {}
    fake_opener.open.assert_called_once_with(req, timeout=5)


def test_non_loopback_honors_proxy_env() -> None:
    """Non-localhost targets keep normal proxy behavior."""
    c = OllamaConnector(host="ollama.lan")
    req = urllib.request.Request("http://ollama.lan:11434/api/tags")
    fake = _fake_response({"models": []})
    with patch("urllib.request.urlopen",
               return_value=fake) as mock_urlopen, \
         patch("urllib.request.build_opener") as mock_build:
        c._urlopen(req, timeout=5)
    mock_urlopen.assert_called_once_with(req, timeout=5)
    mock_build.assert_not_called()


@pytest.mark.parametrize("host", [
    "localhost", "LOCALHOST", "LocalHost", " localhost ",
    "127.0.0.1", "127.0.0.2", "::1", "[::1]",
    "0:0:0:0:0:0:0:1",
])
def test_loopback_target_forms(host) -> None:
    """Every loopback spelling must be classified as loopback."""
    assert _is_loopback_target(host)


@pytest.mark.parametrize("host", [
    "ollama.lan", "0.0.0.0", "192.168.1.10", "", "example.com",
])
def test_non_loopback_target_forms(host) -> None:
    """Non-loopback hosts (and garbage) keep normal proxy behavior."""
    assert not _is_loopback_target(host)
