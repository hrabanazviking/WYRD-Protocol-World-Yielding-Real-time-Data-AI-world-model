"""Forge tests: BifrostBridge contract conformance across all bridge modules.

Why this exists: ``wyrdforge/bridges/base.py`` defines the BifrostBridge
contract — the one abstract requirement is ``query(persona_id, user_input,
**kwargs) -> str``; ``push_event``/``teardown`` have default no-op
implementations. Today only ``PythonRPGBridge`` actually claims that
contract (by subclassing); the eight engine adapters (AgentZero, Hermes,
Kindroid, NSE, OpenClaw, Verdandi, Voxta, and the HTTP server) expose
engine-specific surfaces and deliberately do not. This test discovers all
nine bridge modules, collects each module's primary bridge class, and pins
the current conformance map — so drift in *either* direction fails loudly:
a conformant bridge that stops satisfying the contract, or an engine
adapter that silently starts (or stops) claiming it.

No invented requirements: conformance is exactly "subclass of the ABC or
implements every abstract member", and the query-shape check mirrors the
ABC's own signature — nothing the contract doesn't already say.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil

import pytest

import wyrdforge.bridges as _bridges_pkg
from wyrdforge.bridges.base import BifrostBridge


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

#: The nine bridge modules (base.py and runa_awareness.py carry no bridge
#: class and are excluded by design).
EXPECTED_BRIDGE_MODULES = sorted([
    "agentzero_bridge",
    "hermes_bridge",
    "http_api",
    "kindroid_bridge",
    "nse_bridge",
    "openclaw_bridge",
    "python_rpg",
    "verdandi_bridge",
    "voxta_bridge",
])


def _discover_bridge_modules() -> dict[str, object]:
    """Import every bridge module (excluding base and runa_awareness)."""
    modules = {}
    for info in pkgutil.iter_modules(_bridges_pkg.__path__):
        if info.name in ("base", "runa_awareness"):
            continue
        modules[info.name] = importlib.import_module(
            f"wyrdforge.bridges.{info.name}"
        )
    return modules


def _bridge_classes(module: object) -> list[type]:
    """Primary bridge classes defined in *module*.

    The primary class is the public ``*Bridge`` class (plus WyrdHTTPServer,
    the http_api module's adapter). Support classes (configs, handlers,
    tools) are excluded by the name rule.
    """
    classes = []
    for name, cls in inspect.getmembers(module, inspect.isclass):
        if cls.__module__ != module.__name__:
            continue
        if name.endswith("Bridge") or name == "WyrdHTTPServer":
            classes.append(cls)
    return classes


def _satisfies_contract(cls: type) -> bool:
    """True if *cls* is a BifrostBridge subclass or implements all of the
    ABC's abstract members (currently just ``query``)."""
    if issubclass(cls, BifrostBridge):
        return True
    return all(hasattr(cls, name) for name in BifrostBridge.__abstractmethods__)


#: Current conformance reality, pinned. Update this map (and only this map)
#: when a bridge's contract status intentionally changes.
EXPECTED_CONFORMANCE = {
    "wyrdforge.bridges.agentzero_bridge.AgentZeroWyrdBridge": False,
    "wyrdforge.bridges.hermes_bridge.HermesWyrdBridge": False,
    "wyrdforge.bridges.http_api.WyrdHTTPServer": False,
    "wyrdforge.bridges.kindroid_bridge.KindroidWyrdBridge": False,
    "wyrdforge.bridges.nse_bridge.NSEWyrdBridge": False,
    "wyrdforge.bridges.openclaw_bridge.OpenClawWyrdBridge": False,
    "wyrdforge.bridges.python_rpg.PythonRPGBridge": True,
    "wyrdforge.bridges.verdandi_bridge.VerdandiBridge": False,
    "wyrdforge.bridges.voxta_bridge.VoxtaWyrdBridge": False,
}


def _qualified(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


# ---------------------------------------------------------------------------
# Discovery integrity
# ---------------------------------------------------------------------------

def test_all_nine_bridge_modules_discovered() -> None:
    modules = _discover_bridge_modules()
    assert sorted(modules) == EXPECTED_BRIDGE_MODULES


def test_each_bridge_module_has_exactly_one_primary_bridge_class() -> None:
    modules = _discover_bridge_modules()
    for name, module in sorted(modules.items()):
        classes = _bridge_classes(module)
        assert len(classes) == 1, (
            f"wyrdforge.bridges.{name}: expected 1 primary bridge class, "
            f"found {[c.__name__ for c in classes]}"
        )


# ---------------------------------------------------------------------------
# Conformance map (the drift guard)
# ---------------------------------------------------------------------------

def test_conformance_matches_pinned_map() -> None:
    modules = _discover_bridge_modules()
    actual = {}
    for _name, module in sorted(modules.items()):
        for cls in _bridge_classes(module):
            actual[_qualified(cls)] = _satisfies_contract(cls)
    assert actual == EXPECTED_CONFORMANCE, (
        "Bridge contract conformance drifted. If intentional, update "
        "EXPECTED_CONFORMANCE in this file; if not, fix the bridge. "
        f"Diff: {set(actual.items()) ^ set(EXPECTED_CONFORMANCE.items())}"
    )


# ---------------------------------------------------------------------------
# Conformant bridges: the contract's actual requirements
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "qualified",
    [q for q, conforms in EXPECTED_CONFORMANCE.items() if conforms],
)
def test_conformant_bridge_subclasses_abc(qualified: str) -> None:
    module_name, _, class_name = qualified.rpartition(".")
    cls = getattr(importlib.import_module(module_name), class_name)
    assert issubclass(cls, BifrostBridge), f"{qualified} no longer subclasses BifrostBridge"
    # All abstract members implemented — the class must be instantiable
    # in the ABC sense (no remaining abstractmethods).
    assert not inspect.isabstract(cls), (
        f"{qualified} has unimplemented abstract members: "
        f"{cls.__abstractmethods__}"
    )


@pytest.mark.parametrize(
    "qualified",
    [q for q, conforms in EXPECTED_CONFORMANCE.items() if conforms],
)
def test_conformant_bridge_query_shape(qualified: str) -> None:
    # The contract's query surface: (persona_id, user_input, **kwargs).
    # A conformant bridge must accept those two positionally by name —
    # anything else breaks every caller written against the ABC.
    module_name, _, class_name = qualified.rpartition(".")
    cls = getattr(importlib.import_module(module_name), class_name)
    params = [
        p.name
        for p in inspect.signature(cls.query).parameters.values()
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    if params and params[0] == "self":
        params = params[1:]
    assert params[:2] == ["persona_id", "user_input"], (
        f"{qualified}.query positional params are {params[:2]}"
    )


# ---------------------------------------------------------------------------
# Non-conformant bridges: must not half-claim the contract
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "qualified",
    [q for q, conforms in EXPECTED_CONFORMANCE.items() if not conforms],
)
def test_engine_adapter_does_not_claim_abc(qualified: str) -> None:
    # Engine adapters use engine-specific surfaces; they must not
    # subclass BifrostBridge without implementing the contract, and
    # must not grow a query-shaped method that would silently opt them
    # into duck-type conformance.
    module_name, _, class_name = qualified.rpartition(".")
    cls = getattr(importlib.import_module(module_name), class_name)
    assert not issubclass(cls, BifrostBridge)
    assert "query" not in cls.__dict__, (
        f"{qualified} defines query but is pinned non-conformant — "
        "update EXPECTED_CONFORMANCE or remove the method"
    )
