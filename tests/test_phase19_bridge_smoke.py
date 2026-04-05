"""test_phase19_bridge_smoke.py — 19B: Bridge smoke tests.

Verifies importability, interface compliance, and basic behaviour across
all Python-accessible bridge groups:
  - Core Python bridges (src/wyrdforge/bridges/)
  - WyrdHTTPServer (HTTP/Bifrost)
  - pygame integration bridge modules
  - Engine mirror modules: Unreal, CryEngine, O3DE, Defold, Minecraft, Roblox
  - Hardening modules (backoff, normalization, pool, config_validator)

JS/C# bridges (Foundry, Roll20, Unity, etc.) are covered by their own
Jest / xUnit suites and are not importable in Python.
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import os
import socket
import sys
import threading
import time
import types
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent


def _load_module(file_path: Path, name: str) -> types.ModuleType:
    """Load a .py file as a module without touching sys.modules."""
    spec = importlib.util.spec_from_file_location(name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ===========================================================================
# 1. Core Python bridge imports
# ===========================================================================

class TestCoreBridgeImports:
    """All modules in src/wyrdforge/bridges/ must be importable."""

    def test_base_importable(self):
        from wyrdforge.bridges.base import BifrostBridge
        assert BifrostBridge is not None

    def test_python_rpg_importable(self):
        from wyrdforge.bridges.python_rpg import PythonRPGBridge, BridgeConfig
        assert PythonRPGBridge is not None

    def test_nse_bridge_importable(self):
        from wyrdforge.bridges.nse_bridge import NSEWyrdBridge
        assert NSEWyrdBridge is not None

    def test_openclaw_bridge_importable(self):
        from wyrdforge.bridges.openclaw_bridge import OpenClawWyrdBridge
        assert OpenClawWyrdBridge is not None

    def test_voxta_bridge_importable(self):
        from wyrdforge.bridges.voxta_bridge import VoxtaWyrdBridge
        assert VoxtaWyrdBridge is not None

    def test_kindroid_bridge_importable(self):
        from wyrdforge.bridges.kindroid_bridge import KindroidWyrdBridge
        assert KindroidWyrdBridge is not None

    def test_hermes_bridge_importable(self):
        from wyrdforge.bridges.hermes_bridge import HermesWyrdBridge, WyrdTool, WyrdToolResult
        assert HermesWyrdBridge is not None

    def test_agentzero_bridge_importable(self):
        from wyrdforge.bridges.agentzero_bridge import (
            AgentZeroWyrdBridge, WyrdReadTool, WyrdWriteTool,
            WyrdReadResult, WyrdWriteResult,
        )
        assert AgentZeroWyrdBridge is not None

    def test_http_api_importable(self):
        from wyrdforge.bridges.http_api import WyrdHTTPServer, DEFAULT_MAX_REQUEST_BYTES
        assert WyrdHTTPServer is not None
        assert DEFAULT_MAX_REQUEST_BYTES > 0


# ===========================================================================
# 2. BifrostBridge ABC compliance
# ===========================================================================

class TestBifrostBridgeCompliance:
    """Concrete bridge classes must satisfy the BifrostBridge ABC."""

    def _has_query(self, cls):
        return callable(getattr(cls, "query", None))

    def _has_push_event(self, cls):
        return callable(getattr(cls, "push_event", None))

    def test_python_rpg_has_query(self):
        from wyrdforge.bridges.python_rpg import PythonRPGBridge
        assert self._has_query(PythonRPGBridge)

    def test_nse_bridge_has_query_npc(self):
        from wyrdforge.bridges.nse_bridge import NSEWyrdBridge
        # NSEWyrdBridge exposes query_npc (NSE-specific surface)
        assert callable(getattr(NSEWyrdBridge, "query_npc", None))

    def test_openclaw_has_enrich_method(self):
        from wyrdforge.bridges.openclaw_bridge import OpenClawWyrdBridge
        assert callable(getattr(OpenClawWyrdBridge, "enrich_system_prompt", None))

    def test_bifrostbridge_is_abstract(self):
        from wyrdforge.bridges.base import BifrostBridge
        with pytest.raises(TypeError):
            BifrostBridge()  # type: ignore[abstract]

    def test_bifrostbridge_push_event_default(self):
        from wyrdforge.bridges.base import BifrostBridge

        class _Concrete(BifrostBridge):
            def query(self, persona_id, user_input, **kw):
                return "ok"

        b = _Concrete()
        # Default push_event is a no-op (must not raise)
        b.push_event("observation", {"title": "T", "summary": "S"})

    def test_bifrostbridge_teardown_default(self):
        from wyrdforge.bridges.base import BifrostBridge

        class _Concrete(BifrostBridge):
            def query(self, persona_id, user_input, **kw):
                return "ok"

        b = _Concrete()
        b.teardown()  # must not raise


# ===========================================================================
# 3. AI companion bridge interfaces
# ===========================================================================

class TestAICompanionBridgeInterfaces:
    """Voxta, Kindroid, Hermes, AgentZero have expected surface area."""

    def _mock_bridge(self):
        b = MagicMock()
        b.query.return_value = "The mead flows well."
        return b

    def test_voxta_has_start_background(self):
        from wyrdforge.bridges.voxta_bridge import VoxtaWyrdBridge
        assert callable(getattr(VoxtaWyrdBridge, "start_background", None))

    def test_voxta_has_handle_payload(self):
        from wyrdforge.bridges.voxta_bridge import VoxtaWyrdBridge
        assert callable(getattr(VoxtaWyrdBridge, "handle_voxta_payload", None))

    def test_voxta_has_shutdown(self):
        from wyrdforge.bridges.voxta_bridge import VoxtaWyrdBridge
        assert callable(getattr(VoxtaWyrdBridge, "shutdown", None))

    def test_kindroid_has_start_background(self):
        from wyrdforge.bridges.kindroid_bridge import KindroidWyrdBridge
        assert callable(getattr(KindroidWyrdBridge, "start_background", None))

    def test_kindroid_has_handle_payload(self):
        from wyrdforge.bridges.kindroid_bridge import KindroidWyrdBridge
        assert callable(getattr(KindroidWyrdBridge, "handle_kindroid_payload", None))

    def test_hermes_has_get_tool(self):
        from wyrdforge.bridges.hermes_bridge import HermesWyrdBridge
        assert callable(getattr(HermesWyrdBridge, "get_tool", None))

    def test_hermes_get_tool_returns_wyrd_tool(self):
        from wyrdforge.bridges.hermes_bridge import HermesWyrdBridge, WyrdTool
        # HermesWyrdBridge builds its own internal bridge; no external bridge arg
        bridge = HermesWyrdBridge()
        tool = bridge.get_tool()
        assert isinstance(tool, WyrdTool)

    def test_agentzero_has_get_tools(self):
        from wyrdforge.bridges.agentzero_bridge import AgentZeroWyrdBridge
        assert callable(getattr(AgentZeroWyrdBridge, "get_tools", None))

    def test_agentzero_get_tools_returns_list(self):
        from wyrdforge.bridges.agentzero_bridge import AgentZeroWyrdBridge
        # AgentZeroWyrdBridge builds its own internal bridge; no external bridge arg
        bridge = AgentZeroWyrdBridge()
        tools = bridge.get_tools()
        assert isinstance(tools, list)
        assert len(tools) >= 2


# ===========================================================================
# 4. WyrdHTTPServer smoke
# ===========================================================================

class TestHTTPBridgeSmoke:
    """WyrdHTTPServer starts, handles /health, and shuts down cleanly."""

    def _find_port(self) -> int:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def _make_bridge(self):
        bridge = MagicMock()
        bridge.query.return_value = "Skål!"
        packet = MagicMock()
        packet.model_dump_json.return_value = json.dumps({"world_name": "test", "entities": []})
        bridge.oracle.build_context_packet.return_value = packet
        bridge.oracle.get_facts.return_value = []
        bridge.push_event.return_value = None
        return bridge

    def test_starts_and_health_returns_ok(self):
        from wyrdforge.bridges.http_api import WyrdHTTPServer
        port = self._find_port()
        srv = WyrdHTTPServer(self._make_bridge(), host="127.0.0.1", port=port)
        thread = srv.start_background()
        try:
            deadline = time.time() + 3.0
            status = None
            while time.time() < deadline:
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as r:
                        status = r.status
                        break
                except Exception:
                    time.sleep(0.05)
            assert status == 200
        finally:
            srv.shutdown()

    def test_max_request_bytes_attribute_exposed(self):
        from wyrdforge.bridges.http_api import WyrdHTTPServer
        port = self._find_port()
        srv = WyrdHTTPServer(self._make_bridge(), host="127.0.0.1", port=port, max_request_bytes=512)
        assert srv.max_request_bytes == 512


# ===========================================================================
# 5. pygame bridge modules
# ===========================================================================

class TestPygameBridgeModules:
    """pygame bridge helpers/client/loop are importable and have expected API."""

    _PYGAME_DIR = str(REPO_ROOT / "integrations" / "pygame" / "wyrdforge")

    def _with_path(self):
        if self._PYGAME_DIR not in sys.path:
            sys.path.insert(0, self._PYGAME_DIR)

    def test_helpers_importable(self):
        self._with_path()
        import wyrd_pygame_helpers as h  # type: ignore
        assert callable(h.normalize_persona_id)
        assert callable(h.build_query_body)
        assert callable(h.parse_response)

    def test_client_importable(self):
        self._with_path()
        from wyrd_pygame_client import WyrdPygameClient  # type: ignore
        assert WyrdPygameClient is not None

    def test_loop_importable(self):
        self._with_path()
        from wyrd_pygame_loop import WyrdPygameLoop  # type: ignore
        assert WyrdPygameLoop is not None

    def test_client_has_query(self):
        self._with_path()
        from wyrd_pygame_client import WyrdPygameClient  # type: ignore
        assert callable(getattr(WyrdPygameClient, "query", None))

    def test_client_has_fire_and_forget_methods(self):
        self._with_path()
        from wyrd_pygame_client import WyrdPygameClient  # type: ignore
        assert callable(getattr(WyrdPygameClient, "push_observation", None))
        assert callable(getattr(WyrdPygameClient, "push_fact", None))

    def test_loop_has_npc_interact(self):
        self._with_path()
        from wyrd_pygame_loop import WyrdPygameLoop  # type: ignore
        assert callable(getattr(WyrdPygameLoop, "on_npc_interact", None))

    def test_helpers_normalize_sigrid(self):
        self._with_path()
        import wyrd_pygame_helpers as h  # type: ignore
        assert h.normalize_persona_id("Sigrid Stormborn") == "sigrid_stormborn"


# ===========================================================================
# 6. Engine test-mirror modules
# ===========================================================================
#
# C++ and native-language integrations ship Python mirror tests that define
# the same pure-logic functions (escape_json, normalize_persona_id, etc.)
# in Python so they can be CI-tested without an engine runtime.
# We load each mirror module and verify normalize_persona_id is present and
# produces correct output.
# ---------------------------------------------------------------------------

_ENGINE_MIRRORS = [
    ("unreal",    REPO_ROOT / "integrations/unreal/wyrdforge/tests/test_wyrdforge.py"),
    ("cryengine", REPO_ROOT / "integrations/cryengine/wyrdforge/tests/test_wyrdforge.py"),
    ("o3de",      REPO_ROOT / "integrations/o3de/wyrdforge/tests/test_wyrdforge.py"),
    ("defold",    REPO_ROOT / "integrations/defold/wyrdforge/tests/test_wyrdforge.py"),
    ("roblox",    REPO_ROOT / "integrations/roblox/wyrdforge/tests/test_wyrdforge.py"),
]

# Minecraft and GameMaker mirrors don't define normalize_persona_id (Java/GML IDs
# are passed through without client-side normalisation in those SDKs).
_ENGINE_MIRRORS_NO_NORM = [
    ("minecraft", REPO_ROOT / "integrations/minecraft/wyrdforge/tests/test_wyrdforge.py"),
]


class TestEngineTestMirrors:
    """Each engine mirror module is loadable and exposes expected helpers."""

    @pytest.mark.parametrize("engine,path", _ENGINE_MIRRORS)
    def test_module_loadable(self, engine, path):
        mod = _load_module(path, f"_mirror_{engine}")
        assert mod is not None

    @pytest.mark.parametrize("engine,path", _ENGINE_MIRRORS)
    def test_has_normalize_persona_id(self, engine, path):
        mod = _load_module(path, f"_mirror_{engine}")
        assert callable(getattr(mod, "normalize_persona_id", None))

    @pytest.mark.parametrize("engine,path", _ENGINE_MIRRORS)
    def test_normalize_sigrid_stormborn(self, engine, path):
        mod = _load_module(path, f"_mirror_{engine}")
        assert mod.normalize_persona_id("Sigrid Stormborn") == "sigrid_stormborn"

    @pytest.mark.parametrize("engine,path", _ENGINE_MIRRORS)
    def test_normalize_uppercase(self, engine, path):
        mod = _load_module(path, f"_mirror_{engine}")
        assert mod.normalize_persona_id("GUARD") == "guard"

    @pytest.mark.parametrize("engine,path", _ENGINE_MIRRORS)
    def test_has_build_query_body(self, engine, path):
        mod = _load_module(path, f"_mirror_{engine}")
        assert callable(getattr(mod, "build_query_body", None))

    @pytest.mark.parametrize("engine,path", _ENGINE_MIRRORS)
    def test_has_parse_response(self, engine, path):
        mod = _load_module(path, f"_mirror_{engine}")
        assert callable(getattr(mod, "parse_response", None))

    @pytest.mark.parametrize("engine,path", _ENGINE_MIRRORS_NO_NORM)
    def test_no_norm_module_loadable(self, engine, path):
        mod = _load_module(path, f"_mirror_{engine}")
        assert mod is not None

    @pytest.mark.parametrize("engine,path", _ENGINE_MIRRORS_NO_NORM)
    def test_no_norm_has_build_query_body(self, engine, path):
        mod = _load_module(path, f"_mirror_{engine}")
        assert callable(getattr(mod, "build_query_body", None))


# ===========================================================================
# 7. Hardening module smoke
# ===========================================================================

class TestHardeningModules:
    """All Phase 18 hardening modules are importable and expose key symbols."""

    def test_backoff_importable(self):
        from wyrdforge.hardening.backoff import BackoffConfig, retry_with_backoff, compute_delays
        assert BackoffConfig is not None

    def test_normalization_importable(self):
        from wyrdforge.hardening.normalization import safe_persona_id, is_valid_persona_id
        assert safe_persona_id is not None

    def test_pool_importable(self):
        from wyrdforge.hardening.pool import BoundedThreadPool
        assert BoundedThreadPool is not None

    def test_config_validator_importable(self):
        from wyrdforge.hardening.config_validator import (
            validate_world_config, coerce_env, ConfigValidationError,
        )
        assert validate_world_config is not None

    def test_backoff_config_delay_for(self):
        from wyrdforge.hardening.backoff import BackoffConfig
        cfg = BackoffConfig(max_attempts=3, base_delay=0.1)
        d = cfg.delay_for(0)
        assert d >= 0

    def test_safe_persona_id_basic(self):
        from wyrdforge.hardening.normalization import safe_persona_id
        assert safe_persona_id("Sigrid Stormborn") == "sigrid_stormborn"

    def test_bounded_pool_submit_and_shutdown(self):
        from wyrdforge.hardening.pool import BoundedThreadPool
        results = []
        pool = BoundedThreadPool(max_workers=2, max_queue=8)
        pool.submit(results.append, 42)
        pool.shutdown(wait=True, timeout=2.0)
        assert 42 in results
