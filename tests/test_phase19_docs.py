"""test_phase19_docs.py — 19E: Documentation accuracy audit.

Verifies that:
  1. All Python code blocks in WYRD's primary docs have valid syntax
     (parseable by ast.parse without SyntaxError)
  2. Every wyrdforge import mentioned in docs is actually importable
  3. Key symbols referenced in CLAUDE.md and docs are present in the codebase
  4. All file paths referenced in CLAUDE.md exist on disk
  5. Key WYRD module paths mentioned in CLAUDE.md table are importable

Coverage:
  - docs/index.md
  - docs/guides/quickstart.md
  - docs/guides/architecture.md
  - docs/api/http-api.md
  - docs/integrations/overview.md
  - CLAUDE.md (key file table)
"""
from __future__ import annotations

import ast
import importlib
import re
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent

# Primary docs to audit for Python syntax
_WYRD_DOCS: list[Path] = [
    REPO_ROOT / "docs" / "index.md",
    REPO_ROOT / "docs" / "guides" / "quickstart.md",
    REPO_ROOT / "docs" / "guides" / "architecture.md",
    REPO_ROOT / "docs" / "api" / "http-api.md",
    REPO_ROOT / "docs" / "integrations" / "overview.md",
]

# Key WYRD symbols: (module_path, symbol_name, display_label)
_KEY_SYMBOLS: list[tuple[str, str, str]] = [
    # Core ECS
    ("wyrdforge.ecs.world",           "World",                  "ECS World"),
    ("wyrdforge.ecs.yggdrasil",       "YggdrasilTree",          "Yggdrasil spatial hierarchy"),
    # Oracle
    ("wyrdforge.oracle.passive_oracle", "PassiveOracle",        "PassiveOracle"),
    # Bridges
    ("wyrdforge.bridges.base",        "BifrostBridge",          "BifrostBridge ABC"),
    ("wyrdforge.bridges.http_api",    "WyrdHTTPServer",         "WyrdHTTPServer"),
    ("wyrdforge.bridges.http_api",    "DEFAULT_MAX_REQUEST_BYTES", "DEFAULT_MAX_REQUEST_BYTES"),
    ("wyrdforge.bridges.python_rpg",  "PythonRPGBridge",        "PythonRPGBridge"),
    ("wyrdforge.bridges.python_rpg",  "BridgeConfig",           "BridgeConfig"),
    ("wyrdforge.bridges.nse_bridge",  "NSEWyrdBridge",          "NSEWyrdBridge"),
    ("wyrdforge.bridges.openclaw_bridge", "OpenClawWyrdBridge", "OpenClawWyrdBridge"),
    ("wyrdforge.bridges.voxta_bridge",    "VoxtaWyrdBridge",    "VoxtaWyrdBridge"),
    ("wyrdforge.bridges.kindroid_bridge", "KindroidWyrdBridge", "KindroidWyrdBridge"),
    ("wyrdforge.bridges.hermes_bridge",   "HermesWyrdBridge",   "HermesWyrdBridge"),
    ("wyrdforge.bridges.hermes_bridge",   "WyrdTool",           "HermesWyrdBridge.WyrdTool"),
    ("wyrdforge.bridges.agentzero_bridge","AgentZeroWyrdBridge","AgentZeroWyrdBridge"),
    # Persistence
    ("wyrdforge.persistence.memory_store","PersistentMemoryStore","PersistentMemoryStore"),
    # Runtime
    ("wyrdforge.runtime.turn_loop",   "TurnLoop",               "TurnLoop"),
    # Hardening
    ("wyrdforge.hardening.backoff",       "BackoffConfig",       "BackoffConfig"),
    ("wyrdforge.hardening.backoff",       "retry_with_backoff",  "retry_with_backoff"),
    ("wyrdforge.hardening.normalization", "safe_persona_id",     "safe_persona_id"),
    ("wyrdforge.hardening.normalization", "is_valid_persona_id", "is_valid_persona_id"),
    ("wyrdforge.hardening.pool",          "BoundedThreadPool",   "BoundedThreadPool"),
    ("wyrdforge.hardening.config_validator","validate_world_config","validate_world_config"),
    ("wyrdforge.hardening.config_validator","coerce_env",         "coerce_env"),
    ("wyrdforge.hardening.config_validator","ConfigValidationError","ConfigValidationError"),
]

# Key files referenced in CLAUDE.md (relative to repo root)
_CLAUDE_FILE_REFS: list[str] = [
    "src/wyrdforge/ecs/world.py",
    "src/wyrdforge/ecs/yggdrasil.py",
    "src/wyrdforge/oracle/passive_oracle.py",
    "src/wyrdforge/bridges/http_api.py",
    "src/wyrdforge/runtime/turn_loop.py",
    "src/wyrdforge/persistence/memory_store.py",
    "tools/wyrd_tui.py",
    "tools/wyrd_cloud_relay/relay.py",
    "wyrd_chat_cli.py",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_python_blocks(doc_path: Path) -> list[tuple[str, int]]:
    """Return list of (code, approx_line_no) for each ```python block.

    Blocks are dedented before returning so that MkDocs tab-indented blocks
    (e.g. inside ``=== "Python"`` sections) still parse cleanly.
    """
    content = doc_path.read_text(encoding="utf-8", errors="replace")
    results = []
    for m in re.finditer(r"```python\n(.*?)```", content, re.DOTALL):
        line_no = content[: m.start()].count("\n") + 1
        code = textwrap.dedent(m.group(1))
        results.append((code, line_no))
    return results


def _extract_wyrdforge_imports(doc_path: Path) -> list[str]:
    """Return unique wyrdforge import lines from the doc."""
    content = doc_path.read_text(encoding="utf-8", errors="replace")
    return list(set(re.findall(r"(?:from|import)\s+wyrdforge[^\n]*", content)))


# ===========================================================================
# 1. Python code block syntax audit
# ===========================================================================

class TestDocsPythonSyntax:
    """All Python code blocks in primary docs must parse without SyntaxError."""

    @pytest.mark.parametrize("doc_path", _WYRD_DOCS, ids=[d.name for d in _WYRD_DOCS])
    def test_doc_exists(self, doc_path):
        assert doc_path.exists(), f"Documentation file missing: {doc_path}"

    @pytest.mark.parametrize("doc_path", _WYRD_DOCS, ids=[d.name for d in _WYRD_DOCS])
    def test_python_blocks_have_valid_syntax(self, doc_path):
        if not doc_path.exists():
            pytest.skip(f"Doc not found: {doc_path}")
        blocks = _extract_python_blocks(doc_path)
        if not blocks:
            return  # nothing to check
        errors = []
        for code, line_no in blocks:
            try:
                ast.parse(code)
            except SyntaxError as e:
                errors.append(
                    f"{doc_path.name}:{line_no}: SyntaxError in python block: {e}"
                )
        assert not errors, "\n".join(errors)


# ===========================================================================
# 2. wyrdforge import lines from docs are importable
# ===========================================================================

def _collect_doc_imports() -> list[tuple[str, str]]:
    """Return list of (doc_name, import_line) pairs."""
    pairs = []
    for doc in _WYRD_DOCS:
        if not doc.exists():
            continue
        for imp_line in _extract_wyrdforge_imports(doc):
            pairs.append((doc.name, imp_line.strip()))
    return pairs


_DOC_IMPORT_CASES = _collect_doc_imports()


class TestDocsWyrdforgeImports:
    """All wyrdforge import statements in docs must succeed at runtime."""

    @pytest.mark.skipif(not _DOC_IMPORT_CASES, reason="No wyrdforge imports found in docs")
    @pytest.mark.parametrize("doc_name,import_line", _DOC_IMPORT_CASES,
                              ids=[f"{d}:{i[:40]}" for d, i in _DOC_IMPORT_CASES])
    def test_import_succeeds(self, doc_name, import_line):
        try:
            exec(import_line, {})  # noqa: S102
        except ImportError as e:
            pytest.fail(f"{doc_name}: import failed — {import_line!r}: {e}")


# ===========================================================================
# 3. Key WYRD symbols are importable
# ===========================================================================

class TestKeySymbolsExist:
    """Every key WYRD symbol must be importable from its documented module."""

    @pytest.mark.parametrize("module_path,symbol,label", _KEY_SYMBOLS,
                              ids=[s[2] for s in _KEY_SYMBOLS])
    def test_symbol_importable(self, module_path, symbol, label):
        try:
            mod = importlib.import_module(module_path)
        except ImportError as e:
            pytest.fail(f"Cannot import module {module_path}: {e}")
        assert hasattr(mod, symbol), (
            f"{label}: symbol {symbol!r} not found in {module_path}"
        )

    @pytest.mark.parametrize("module_path,symbol,label", _KEY_SYMBOLS,
                              ids=[s[2] for s in _KEY_SYMBOLS])
    def test_symbol_is_not_none(self, module_path, symbol, label):
        mod = importlib.import_module(module_path)
        obj = getattr(mod, symbol, None)
        assert obj is not None, f"{label}: {symbol} is None in {module_path}"


# ===========================================================================
# 4. CLAUDE.md file paths exist on disk
# ===========================================================================

class TestClaudeMdFilePaths:
    """All Python file paths referenced in CLAUDE.md must exist."""

    @pytest.mark.parametrize("rel_path", _CLAUDE_FILE_REFS)
    def test_file_exists(self, rel_path):
        full = REPO_ROOT / rel_path
        assert full.exists(), f"CLAUDE.md references non-existent file: {rel_path}"

    def test_claude_md_itself_exists(self):
        assert (REPO_ROOT / "CLAUDE.md").exists()


# ===========================================================================
# 5. WyrdHTTPServer endpoint list is consistent with implementation
# ===========================================================================

class TestHTTPAPIDocumentedEndpoints:
    """Endpoints documented in http-api.md must match WyrdHTTPServer handler."""

    _DOCUMENTED_ENDPOINTS = {
        ("POST", "/query"),
        ("POST", "/event"),
        ("GET",  "/world"),
        ("GET",  "/facts"),
        ("GET",  "/health"),
    }

    def _get_handler_routes(self) -> set[tuple[str, str]]:
        """Extract route-to-method mappings from the handler source."""
        import ast as _ast
        src_path = REPO_ROOT / "src/wyrdforge/bridges/http_api.py"
        tree = _ast.parse(src_path.read_text(encoding="utf-8"))
        routes = set()
        for node in _ast.walk(tree):
            if isinstance(node, _ast.FunctionDef):
                if node.name in ("do_GET", "do_POST"):
                    method = node.name.split("_")[1]  # GET or POST
                    # Look for string constants that look like path comparisons
                    for child in _ast.walk(node):
                        if isinstance(child, _ast.Constant) and isinstance(child.value, str):
                            v = child.value
                            if v.startswith("/"):
                                routes.add((method, v))
        return routes

    def test_all_documented_endpoints_handled(self):
        handler_routes = self._get_handler_routes()
        for method, path in self._DOCUMENTED_ENDPOINTS:
            assert (method, path) in handler_routes, (
                f"Documented endpoint {method} {path} not found in WyrdHTTPServer handler"
            )

    def test_http_api_doc_exists(self):
        assert (REPO_ROOT / "docs" / "api" / "http-api.md").exists()

    def test_http_api_doc_mentions_all_endpoints(self):
        doc = (REPO_ROOT / "docs" / "api" / "http-api.md").read_text(encoding="utf-8")
        for method, path in self._DOCUMENTED_ENDPOINTS:
            assert path in doc, f"{method} {path} not mentioned in http-api.md"
