"""test_phase19_normalization.py — 19C: Normalization audit.

Loads the shared test vectors from fixtures/normalization_vectors.json and
runs every vector through every Python-accessible normalize_persona_id
implementation in the codebase.

Implementations under test:
  1. wyrdforge.hardening.normalization.safe_persona_id  — NFKD-enhanced reference
  2. integrations/pygame/wyrdforge/wyrd_pygame_helpers.normalize_persona_id
  3. integrations/unreal/wyrdforge/tests   — Python mirror of WyrdHelpers.cpp
  4. integrations/cryengine/wyrdforge/tests— Python mirror
  5. integrations/o3de/wyrdforge/tests     — Python mirror
  6. integrations/defold/wyrdforge/tests   — Python mirror of wyrdforge.cpp
  7. integrations/roblox/wyrdforge/tests   — Python mirror of WyrdMapper.lua

Unicode strategy note:
  safe_persona_id uses NFKD decomposition before applying the canonical algorithm.
  This means non-ASCII letters with diacritics (ö, é) are transcribed to their
  ASCII base form (o, e) rather than replaced with _.  All other implementations
  use the simpler approach: non-ASCII chars → _.  Both are valid; the test vectors
  are written for the simpler algorithm.  safe_persona_id is audited separately
  for unicode vectors.

Bugs fixed by this audit (Phase 19C):
  - Unreal/CryEngine/O3DE/Defold mirrors used Python's Unicode-aware isalnum(),
    which let non-ASCII letters pass through unchanged.  Fixed: c.isascii() guard.
  - Same mirrors did not collapse consecutive underscores (e.g. 'multiple___' →
    'multiple___').  Fixed: removed unconditional _ passthrough.

Note: Minecraft does not expose normalize_persona_id (Java handles normalisation
      server-side); it is excluded from this audit.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load test vectors
# ---------------------------------------------------------------------------

VECTORS_PATH = Path(__file__).parent / "fixtures" / "normalization_vectors.json"
VECTORS: list[dict] = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))

# Split into ASCII-only and unicode vectors
ASCII_VECTORS = [v for v in VECTORS if v["input"].isascii()]
UNICODE_VECTORS = [v for v in VECTORS if not v["input"].isascii()]


# ---------------------------------------------------------------------------
# Helper: load a module from file path
# ---------------------------------------------------------------------------

def _load_module(file_path: Path, name: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Collect implementations
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent

_PYGAME_DIR = str(REPO_ROOT / "integrations" / "pygame" / "wyrdforge")
if _PYGAME_DIR not in sys.path:
    sys.path.insert(0, _PYGAME_DIR)


def _get_safe_persona_id():
    from wyrdforge.hardening.normalization import safe_persona_id
    return safe_persona_id


def _get_pygame_normalize():
    import wyrd_pygame_helpers as h  # type: ignore
    return h.normalize_persona_id


def _get_engine_normalize(engine: str):
    path = REPO_ROOT / "integrations" / engine / "wyrdforge" / "tests" / "test_wyrdforge.py"
    mod = _load_module(path, f"_norm_{engine}")
    return mod.normalize_persona_id


# Simple implementations (pygame algorithm: non-ASCII → _)
SIMPLE_IMPLEMENTATIONS: dict[str, object] = {
    "pygame.normalize_persona_id": _get_pygame_normalize(),
    "unreal_mirror":    _get_engine_normalize("unreal"),
    "cryengine_mirror": _get_engine_normalize("cryengine"),
    "o3de_mirror":      _get_engine_normalize("o3de"),
    "defold_mirror":    _get_engine_normalize("defold"),
    "roblox_mirror":    _get_engine_normalize("roblox"),
}

# All implementations including the NFKD-enhanced one
ALL_IMPLEMENTATIONS = {
    "hardening.safe_persona_id": _get_safe_persona_id(),
    **SIMPLE_IMPLEMENTATIONS,
}

ASCII_VECTOR_IDS = [f"{v['input']!r}" for v in ASCII_VECTORS]
UNICODE_VECTOR_IDS = [f"{v['input']!r}" for v in UNICODE_VECTORS]


# ===========================================================================
# ASCII vector audit — all implementations must agree
# ===========================================================================

class TestASCIINormalizationConsistency:
    """For all-ASCII inputs every implementation must produce the expected output."""

    @pytest.mark.parametrize("impl_name,fn", list(ALL_IMPLEMENTATIONS.items()))
    @pytest.mark.parametrize("vec", ASCII_VECTORS, ids=ASCII_VECTOR_IDS)
    def test_matches_expected(self, vec, impl_name, fn):
        result = fn(vec["input"])
        assert result == vec["expected"], (
            f"{impl_name}: {vec['input']!r} → {result!r}, expected {vec['expected']!r}"
        )

    @pytest.mark.parametrize("vec", ASCII_VECTORS, ids=ASCII_VECTOR_IDS)
    def test_all_implementations_agree_on_ascii(self, vec):
        results = {name: fn(vec["input"]) for name, fn in ALL_IMPLEMENTATIONS.items()}
        distinct = set(results.values())
        assert len(distinct) == 1, (
            f"Divergence on {vec['input']!r}: {results}"
        )


# ===========================================================================
# Unicode vector audit — simple implementations vs expected
# ===========================================================================

class TestUnicodeNormalizationSimpleImpls:
    """Simple implementations (non-NFKD) must match expected output for unicode vectors."""

    @pytest.mark.parametrize("impl_name,fn", list(SIMPLE_IMPLEMENTATIONS.items()))
    @pytest.mark.parametrize("vec", UNICODE_VECTORS, ids=UNICODE_VECTOR_IDS)
    def test_matches_expected(self, vec, impl_name, fn):
        result = fn(vec["input"])
        assert result == vec["expected"], (
            f"{impl_name}: {vec['input']!r} → {result!r}, expected {vec['expected']!r}"
        )

    @pytest.mark.parametrize("vec", UNICODE_VECTORS, ids=UNICODE_VECTOR_IDS)
    def test_simple_impls_agree_on_unicode(self, vec):
        results = {name: fn(vec["input"]) for name, fn in SIMPLE_IMPLEMENTATIONS.items()}
        distinct = set(results.values())
        assert len(distinct) == 1, (
            f"Simple impl divergence on {vec['input']!r}: {results}"
        )


# ===========================================================================
# NFKD implementation (safe_persona_id) — unicode properties
# ===========================================================================

class TestSafePersonaIdUnicode:
    """safe_persona_id's NFKD path produces ASCII-only output for all inputs."""

    def _fn(self, s):
        from wyrdforge.hardening.normalization import safe_persona_id
        return safe_persona_id(s)

    @pytest.mark.parametrize("vec", UNICODE_VECTORS, ids=UNICODE_VECTOR_IDS)
    def test_output_is_ascii(self, vec):
        result = self._fn(vec["input"])
        assert result.isascii(), f"Non-ASCII in output for {vec['input']!r}: {result!r}"

    @pytest.mark.parametrize("vec", UNICODE_VECTORS, ids=UNICODE_VECTOR_IDS)
    def test_output_is_not_empty(self, vec):
        # NFKD may render accented chars as their base letter — output must not be empty
        result = self._fn(vec["input"])
        assert result != ""


# ===========================================================================
# General properties — safe_persona_id robustness
# ===========================================================================

class TestSafePersonaIdRobustness:
    """safe_persona_id must handle tricky inputs gracefully."""

    def _fn(self, s):
        from wyrdforge.hardening.normalization import safe_persona_id
        return safe_persona_id(s)

    def test_none_returns_empty(self):
        assert self._fn(None) == ""

    def test_bytes_input(self):
        assert self._fn(b"sigrid") == "sigrid"

    def test_nul_bytes_stripped(self):
        assert "\x00" not in self._fn("sig\x00rid")

    def test_result_never_starts_with_underscore(self):
        for vec in ASCII_VECTORS:
            if vec["expected"]:
                assert not self._fn(vec["input"]).startswith("_"), vec

    def test_result_never_ends_with_underscore(self):
        for vec in ASCII_VECTORS:
            if vec["expected"]:
                assert not self._fn(vec["input"]).endswith("_"), vec

    def test_result_never_has_double_underscore(self):
        for vec in ASCII_VECTORS:
            assert "__" not in self._fn(vec["input"]), vec

    def test_result_max_length_64(self):
        assert len(self._fn("a" * 200)) <= 64

    def test_is_valid_persona_id_accepts_results(self):
        from wyrdforge.hardening.normalization import is_valid_persona_id
        for vec in ASCII_VECTORS:
            result = self._fn(vec["input"])
            if result:
                assert is_valid_persona_id(result), f"Result {result!r} not valid for {vec['input']!r}"
