"""Lint: every blocking call in src/ + tools/ must carry a named timeout.

AST-based guard for the Track 4 P2 inventory (docs/timeouts.md).
Fails if a timeout-less risky call is introduced:

1. urlopen / httpx.Client/AsyncClient / subprocess.* / socket.create_connection /
   Lock.acquire / Event.wait / Thread.join WITHOUT a ``timeout=`` kwarg.
   (str.join and os.path.join are not threading joins and are excluded.)
2. ``.get()`` / ``.put()`` on queue-ish receivers (dotted name contains
   "queue") WITHOUT ``timeout=``. (``put_nowait`` is exempt by name.)
3. Any file calling socket ``.connect()`` must also contain ``settimeout``.
   (``sqlite3.connect`` is exempt — it takes ``timeout=`` directly.)

Verified 2026-09-26: the tree passes all three checks with zero false
positives — this test pins the clean state, it doesn't excavate it.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOTS = [REPO / "src", REPO / "tools"]

RISKY_ATTRS = {"acquire", "wait", "join"}


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        value = _dotted(node.value)
        return f"{value}.{node.attr}" if value else node.attr
    return ""


def _iter_py_files():
    for root in ROOTS:
        for path in sorted(root.rglob("*.py")):
            yield path


def _check_call(path: Path, node: ast.Call) -> list[str]:
    """Return violation messages for one Call node (empty = clean)."""
    func = node.func
    dotted = _dotted(func)
    base = dotted.rsplit(".", 1)[-1]
    has_timeout = any(kw.arg == "timeout" for kw in node.keywords)
    violations: list[str] = []

    # Rule 1: risky blocking calls must name a timeout.
    risky = False
    if base == "urlopen":
        risky = True
    elif dotted in ("httpx.Client", "httpx.AsyncClient"):
        risky = True
    elif dotted.startswith("subprocess."):
        risky = True
    elif dotted == "socket.create_connection":
        risky = True
    elif isinstance(func, ast.Attribute) and func.attr in ("acquire", "wait"):
        risky = True
    elif (
        isinstance(func, ast.Attribute)
        and func.attr == "join"
        and not isinstance(func.value, ast.Constant)
        and _dotted(func.value) != "os.path"
    ):
        # Thread.join — but not " ".join / os.path.join.
        risky = True
    if risky and not has_timeout:
        violations.append(
            f"{path.relative_to(REPO)}:{node.lineno}: {dotted or base}() "
            "without timeout="
        )

    # Rule 2: queue get/put must name a timeout (put_nowait exempt by name).
    if base in ("get", "put") and "queue" in dotted.lower() and not has_timeout:
        violations.append(
            f"{path.relative_to(REPO)}:{node.lineno}: {dotted}() "
            "without timeout="
        )
    return violations


def test_no_timeoutless_blocking_calls() -> None:
    violations: list[str] = []
    for path in _iter_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                violations.extend(_check_call(path, node))
    assert not violations, (
        "timeout-less blocking calls (see docs/timeouts.md):\n"
        + "\n".join(violations)
    )


def test_socket_connect_requires_settimeout() -> None:
    offenders: list[str] = []
    for path in _iter_py_files():
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        connects = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "connect"
            and not _dotted(node.func.value).endswith("sqlite3")
        ]
        if connects and "settimeout" not in text:
            lines = sorted({n.lineno for n in connects})
            offenders.append(f"{path.relative_to(REPO)}:{lines}")
    assert not offenders, (
        "socket .connect() without settimeout in file:\n" + "\n".join(offenders)
    )
