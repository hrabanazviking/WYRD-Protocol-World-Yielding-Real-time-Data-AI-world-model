"""Phase D5 — multi-world operations pinning tests.

Design under test (roadmap §3.4 / §9 D5,
``services/multi_world.py`` + ``docs/specs/multi-world-operations.md``):

* **Serving**: a ``MultiWorldHost`` hosts several fully-composed
  world stacks (each its own World + stores + Oracle + EventBus) in
  one process and serves them concurrently — each Oracle query keeps
  its Phase B1 guarantee under that world's own lock.
* **Cross-world queries are read-only and registry-mediated**:
  registration requires a declared ``World.identify()`` identity and
  keys the world by its registry entry; dispatch goes only to the
  allowlisted read-only Oracle methods; every answer is a
  ``CrossWorldResult`` carrying its ``world_id`` and ``reality``,
  never merged with another world's answer. A cross-world write is
  absent by construction (the host exposes no world-mutating
  method) and refused by name at the dispatch gate.
* **Zero-bleed isolation** (the MTOM firewall doctrine extended from
  realities within a world to worlds within a process): entities,
  components, memories, bonds, events, and fate threads in one
  hosted world cannot leak into another's Oracle answers, stores,
  or bus traffic — including under concurrent load. Registration
  itself refuses the sharings that would bleed (same World /
  Oracle / store instance, same store file, same EventBus).
* **NOT federation**: one process, one owner. No network surface
  exists in the module under test.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from wyrdforge.ecs.components.identity import NameComponent
from wyrdforge.ecs.components.mtom import ZeroBleedError
from wyrdforge.ecs.components.world_identity import UnidentifiedWorldError
from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree
from wyrdforge.models.bond import BondDomain, BondEdge, BondVector
from wyrdforge.oracle import PassiveOracle
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.persistence.world_store import WorldStore
from wyrdforge.runtime.events import EventBus
from wyrdforge.services.bond_graph_service import BondGraphService
from wyrdforge.services.combat_engine import CombatEngine
from wyrdforge.services.multi_world import (
    READ_ONLY_ORACLE_QUERIES,
    CrossWorldWriteRefused,
    MultiWorldHost,
    UnregisteredWorldError,
    WorldSharingError,
)
from wyrdforge.services.thread_engine import ThreadEngine
from wyrdforge.services.writeback_engine import WritebackEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stack(tmp_path, label: str, world_id: str, *, reality: str = "manifest",
           bus: EventBus | None = None) -> SimpleNamespace:
    """One fully-composed world stack, as bridges compose it today."""
    world = World(world_id, label, bus=bus) if bus is not None else World(world_id, label)
    world.identify(reality=reality, description=f"{label} world")
    tree = YggdrasilTree(world)
    tree.create_zone(zone_id="z", name="Zone")
    tree.create_region(region_id="r", name="Region", parent_zone_id="z")
    tree.create_location(location_id=f"loc-{label}", name=label, parent_region_id="r")
    store = PersistentMemoryStore(tmp_path / f"{label}.db")
    bonds = BondGraphService()
    oracle = PassiveOracle(world, store, yggdrasil=tree, bond_service=bonds)
    return SimpleNamespace(
        label=label, world=world, tree=tree, store=store, bonds=bonds,
        oracle=oracle, bus=bus,
    )


def _host_with(tmp_path, *stacks: SimpleNamespace) -> MultiWorldHost:
    host = MultiWorldHost()
    for stack in stacks:
        host.register(stack.world, oracle=stack.oracle)
    return host


def _person(stack: SimpleNamespace, eid: str, name: str) -> None:
    stack.world.create_entity(entity_id=eid, tags={"character"})
    stack.world.add_component(eid, NameComponent(entity_id=eid, name=name))
    stack.tree.place_entity(eid, location_id=f"loc-{stack.label}")


def _run_threads(targets) -> list[BaseException]:
    barrier = threading.Barrier(len(targets))
    errors: list[BaseException] = []
    errors_lock = threading.Lock()

    def wrap(fn):
        def run():
            barrier.wait()
            try:
                fn()
            except BaseException as exc:  # noqa: BLE001 — collected + asserted
                with errors_lock:
                    errors.append(exc)
        return run

    threads = [threading.Thread(target=wrap(fn)) for fn in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return errors


# ---------------------------------------------------------------------------
# Registration — registry-mediated, sharing refused
# ---------------------------------------------------------------------------

def test_registration_requires_declared_identity(tmp_path):
    world = World("heimr-undeclared")  # identify() never called
    store = PersistentMemoryStore(tmp_path / "m.db")
    host = MultiWorldHost()
    with pytest.raises(UnidentifiedWorldError, match="call identify"):
        host.register(world, memory_store=store)
    assert host.world_ids() == []


def test_registration_requires_oracle_or_store(tmp_path):
    world = World("heimr-lonely")
    world.identify(reality="manifest")
    host = MultiWorldHost()
    with pytest.raises(ValueError, match="oracle= or a memory_store="):
        host.register(world)
    assert host.world_ids() == []


def test_registration_via_store_composes_oracle(tmp_path):
    world = World("heimr-composed", "Composed")
    world.identify(reality="potential", description="composed world")
    host = MultiWorldHost()
    returned = host.register(world, memory_store=PersistentMemoryStore(tmp_path / "m.db"))
    assert returned == "heimr-composed"
    assert isinstance(host.oracle("heimr-composed"), PassiveOracle)
    assert host.world("heimr-composed") is world


def test_registry_entries_describe_and_ids(tmp_path):
    a = _stack(tmp_path, "alpha", "heimr-alpha")
    b = _stack(tmp_path, "beta", "heimr-beta", reality="potential")
    host = _host_with(tmp_path, b, a)  # registration order must not matter
    assert host.world_ids() == ["heimr-alpha", "heimr-beta"]
    entries = host.registry_entries()
    assert [e["world_id"] for e in entries] == ["heimr-alpha", "heimr-beta"]
    assert entries[0] == a.world.registry_entry()
    assert entries[1]["reality"] == "potential"
    _person(a, "someone", "Someone")
    summaries = {s.world_id: s for s in host.describe_worlds()}
    assert summaries["heimr-alpha"].entity_count == a.world.entity_count()
    assert summaries["heimr-beta"].reality == "potential"
    assert summaries["heimr-alpha"].kind == "wyrd"


def test_duplicate_world_id_refused(tmp_path):
    a = _stack(tmp_path, "alpha", "heimr-same")
    b = _stack(tmp_path, "beta", "heimr-same")
    host = _host_with(tmp_path, a)
    with pytest.raises(WorldSharingError, match="already hosted"):
        host.register(b.world, oracle=b.oracle)
    assert host.world_ids() == ["heimr-same"]


def test_shared_instances_refused(tmp_path):
    a = _stack(tmp_path, "alpha", "heimr-alpha")
    host = _host_with(tmp_path, a)

    other_world = World("heimr-other", "Other")
    other_world.identify(reality="manifest")
    with pytest.raises(WorldSharingError, match="Oracle instance"):
        host.register(other_world, oracle=a.oracle)

    with pytest.raises(WorldSharingError):
        # Same World object under a second registration attempt: its
        # id is already hosted, so the duplicate-id guard fires
        # first — either guard is a refusal; assert the class.
        host.register(a.world, oracle=PassiveOracle(
            a.world, PersistentMemoryStore(tmp_path / "fresh.db")))

    c_world = World("heimr-third", "Third")
    c_world.identify(reality="manifest")
    with pytest.raises(WorldSharingError, match="memory store"):
        host.register(c_world, oracle=PassiveOracle(c_world, a.store))
    assert host.world_ids() == ["heimr-alpha"]


def test_shared_store_file_refused(tmp_path):
    a = _stack(tmp_path, "alpha", "heimr-alpha")
    host = _host_with(tmp_path, a)
    # A DIFFERENT store object opened on alpha's database file.
    same_file_store = PersistentMemoryStore(tmp_path / "alpha.db")
    b_world = World("heimr-beta", "Beta")
    b_world.identify(reality="manifest")
    with pytest.raises(WorldSharingError, match="one file"):
        host.register(b_world, oracle=PassiveOracle(b_world, same_file_store))
    assert host.world_ids() == ["heimr-alpha"]


def test_shared_bus_refused(tmp_path):
    bus = EventBus()
    a = _stack(tmp_path, "alpha", "heimr-alpha", bus=bus)
    b = _stack(tmp_path, "beta", "heimr-beta", bus=bus)
    host = _host_with(tmp_path, a)
    with pytest.raises(WorldSharingError, match="EventBus"):
        host.register(b.world, oracle=b.oracle)
    assert host.world_ids() == ["heimr-alpha"]


def test_unregister_and_unregistered_lookup(tmp_path):
    a = _stack(tmp_path, "alpha", "heimr-alpha")
    host = _host_with(tmp_path, a)
    host.unregister("heimr-alpha")
    assert host.world_ids() == []
    with pytest.raises(UnregisteredWorldError):
        host.unregister("heimr-alpha")
    with pytest.raises(UnregisteredWorldError):
        host.oracle("heimr-alpha")
    with pytest.raises(UnregisteredWorldError):
        host.query_across("what_is", "x", world_ids=["heimr-alpha"])


# ---------------------------------------------------------------------------
# Cross-world query surface — attributed, read-only, firewalled
# ---------------------------------------------------------------------------

def test_what_is_across_attributes_same_entity_per_world(tmp_path):
    a = _stack(tmp_path, "alpha", "heimr-alpha")
    b = _stack(tmp_path, "beta", "heimr-beta")
    _person(a, "yrsa", "Yrsa of Alpha")
    _person(b, "yrsa", "Yrsa of Beta")
    host = _host_with(tmp_path, a, b)

    results = host.what_is_across("yrsa")
    assert [(r.world_id, r.value.name) for r in results] == [
        ("heimr-alpha", "Yrsa of Alpha"),
        ("heimr-beta", "Yrsa of Beta"),
    ]
    assert all(r.query == "what_is" and r.reality == "manifest" for r in results)
    # Absent in both worlds → no result at all (absence is not an answer).
    assert host.what_is_across("nobody") == []
    # Present in one world only → exactly that world's result.
    _person(b, "beta-only", "Only Beta")
    only = host.what_is_across("beta-only")
    assert [(r.world_id, r.value.name) for r in only] == [("heimr-beta", "Only Beta")]


def test_where_is_across_uses_each_worlds_own_tree(tmp_path):
    a = _stack(tmp_path, "alpha", "heimr-alpha")
    b = _stack(tmp_path, "beta", "heimr-beta")
    _person(a, "wanderer", "Wanderer")
    _person(b, "wanderer", "Wanderer")
    host = _host_with(tmp_path, a, b)
    results = host.where_is_across("wanderer")
    assert [(r.world_id, r.value.location_id) for r in results] == [
        ("heimr-alpha", "loc-alpha"),
        ("heimr-beta", "loc-beta"),
    ]


def test_facts_and_search_across_are_per_world(tmp_path):
    a = _stack(tmp_path, "alpha", "heimr-alpha")
    b = _stack(tmp_path, "beta", "heimr-beta")
    WritebackEngine(a.store).write_canonical_fact(
        fact_subject_id="yrsa", fact_key="home", fact_value="Alpha Hall")
    WritebackEngine(b.store).write_canonical_fact(
        fact_subject_id="yrsa", fact_key="home", fact_value="Beta Hall")
    host = _host_with(tmp_path, a, b)

    facts = host.get_facts_across("yrsa")
    assert [r.world_id for r in facts] == ["heimr-alpha", "heimr-beta"]
    assert [r.value[0].content.structured_payload.fact_value for r in facts] == [
        "Alpha Hall", "Beta Hall",
    ]
    # Each world's own Oracle sees only its own fact.
    assert a.oracle.get_fact("yrsa", "home").content.structured_payload.fact_value == "Alpha Hall"
    assert b.oracle.get_fact("yrsa", "home").content.structured_payload.fact_value == "Beta Hall"

    found = host.search_facts_across("Alpha")
    by_world = {r.world_id: len(r.value) for r in found}
    assert by_world["heimr-alpha"] >= 1
    assert by_world["heimr-beta"] == 0


def test_recent_observations_across_are_per_world(tmp_path):
    a = _stack(tmp_path, "alpha", "heimr-alpha")
    b = _stack(tmp_path, "beta", "heimr-beta")
    WritebackEngine(a.store).write_observation(
        title="Alpha bell", summary="the alpha bell rang",
        observation_kind="world_event", place_id="loc-alpha")
    WritebackEngine(b.store).write_observation(
        title="Beta bell", summary="the beta bell rang",
        observation_kind="world_event", place_id="loc-beta")
    host = _host_with(tmp_path, a, b)

    results = host.recent_observations_across()
    assert [(r.world_id, [o.title for o in r.value]) for r in results] == [
        ("heimr-alpha", ["Alpha bell"]),
        ("heimr-beta", ["Beta bell"]),
    ]
    placed = host.recent_observations_across(place_id="loc-beta")
    assert [(r.world_id, len(r.value)) for r in placed] == [
        ("heimr-alpha", 0), ("heimr-beta", 1),
    ]


def test_generic_query_across_dispatches_allowlisted_reads(tmp_path):
    a = _stack(tmp_path, "alpha", "heimr-alpha")
    b = _stack(tmp_path, "beta", "heimr-beta")
    a.world.create_entity(entity_id="rock")
    a.world.set_position("rock", 1.0, 2.0, 3.0)
    host = _host_with(tmp_path, a, b)
    results = host.query_across("get_position", "rock")
    assert results[0].world_id == "heimr-alpha"
    assert (results[0].value.x, results[0].value.y, results[0].value.z) == (1.0, 2.0, 3.0)
    assert results[1].world_id == "heimr-beta" and results[1].value is None
    # Targeting a subset, in the caller's order.
    subset = host.query_across("what_is", "rock", world_ids=["heimr-beta", "heimr-alpha"])
    assert [r.world_id for r in subset] == ["heimr-beta", "heimr-alpha"]


def test_allowlist_is_exactly_read_only_oracle_methods():
    for name in READ_ONLY_ORACLE_QUERIES:
        assert callable(getattr(PassiveOracle, name)), name
        assert not name.startswith("_")
    # A sample of mutating / private names that must never be in it.
    for forbidden in ("create_entity", "add_component", "remove_entity",
                      "set_position", "add", "save", "delete", "process_turn"):
        assert forbidden not in READ_ONLY_ORACLE_QUERIES


def test_cross_world_write_attempts_refused_and_mutate_nothing(tmp_path):
    a = _stack(tmp_path, "alpha", "heimr-alpha")
    b = _stack(tmp_path, "beta", "heimr-beta")
    _person(a, "yrsa", "Yrsa of Alpha")
    host = _host_with(tmp_path, a, b)
    counts_before = (a.world.entity_count(), b.world.entity_count())

    for attempt in ("create_entity", "add_component", "remove_entity",
                    "set_position", "_entities", "register", "unregister"):
        with pytest.raises(CrossWorldWriteRefused, match="not a read-only"):
            host.query_across(attempt, "yrsa")
    # Absent by construction: the host has no world-mutating surface.
    for mutator in ("create_entity", "add_component", "remove_entity",
                    "set_position", "write_observation", "write_canonical_fact"):
        assert not hasattr(host, mutator), mutator
    assert (a.world.entity_count(), b.world.entity_count()) == counts_before
    assert a.oracle.what_is("yrsa").name == "Yrsa of Alpha"


def test_as_manifest_firewall_across_worlds(tmp_path):
    a = _stack(tmp_path, "alpha", "heimr-alpha", reality="manifest")
    b = _stack(tmp_path, "beta", "heimr-beta", reality="potential")
    _person(a, "yrsa", "Yrsa Manifest")
    _person(b, "yrsa", "Yrsa Potential")
    host = _host_with(tmp_path, a, b)

    # Default: both answer, each reality-tagged — potential never
    # poses as manifest because its tag travels with the answer.
    results = host.what_is_across("yrsa")
    assert [(r.world_id, r.reality) for r in results] == [
        ("heimr-alpha", "manifest"), ("heimr-beta", "potential"),
    ]
    # as_manifest across a potential world: refused before any query.
    with pytest.raises(ZeroBleedError, match="Zero-bleed"):
        host.what_is_across("yrsa", as_manifest=True)
    # Targeting only the manifest world is the caller's explicit
    # choice and works.
    manifest_only = host.what_is_across(
        "yrsa", world_ids=["heimr-alpha"], as_manifest=True)
    assert [(r.world_id, r.value.name) for r in manifest_only] == [
        ("heimr-alpha", "Yrsa Manifest"),
    ]


# ---------------------------------------------------------------------------
# Zero-bleed isolation — two live worlds, every surface
# ---------------------------------------------------------------------------

def test_isolation_entities_and_components(tmp_path):
    a = _stack(tmp_path, "alpha", "heimr-alpha")
    b = _stack(tmp_path, "beta", "heimr-beta")
    _person(a, "shared-id", "Alpha Name")
    _person(b, "shared-id", "Beta Name")
    _person(a, "alpha-only", "Alpha Only")

    assert a.oracle.what_is("shared-id").name == "Alpha Name"
    assert b.oracle.what_is("shared-id").name == "Beta Name"
    assert b.oracle.what_is("alpha-only") is None
    assert {e.entity_id for e in b.world.query_by_tag("character")} == {"shared-id"}

    # Mutations in one world are invisible in the other.
    a.world.add_component("shared-id", NameComponent(entity_id="shared-id", name="Renamed"))
    assert a.oracle.what_is("shared-id").name == "Renamed"
    assert b.oracle.what_is("shared-id").name == "Beta Name"
    a.world.remove_entity("shared-id")
    assert a.oracle.what_is("shared-id") is None
    assert b.oracle.what_is("shared-id").name == "Beta Name"
    assert b.world.entity_count() == 4  # zone, region, location, shared-id


def test_isolation_memories(tmp_path):
    a = _stack(tmp_path, "alpha", "heimr-alpha")
    b = _stack(tmp_path, "beta", "heimr-beta")
    WritebackEngine(a.store).write_observation(
        title="Alpha secret", summary="alpha only words",
        observation_kind="world_event", place_id="loc-alpha")
    WritebackEngine(a.store).write_canonical_fact(
        fact_subject_id="yrsa", fact_key="secret", fact_value="alpha-value")

    assert [o.title for o in a.oracle.recent_observations()] == ["Alpha secret"]
    assert b.oracle.recent_observations() == []
    assert b.oracle.get_facts("yrsa") == []
    assert b.oracle.search_facts("alpha") == []
    assert b.oracle.get_fact("yrsa", "secret") is None


def test_isolation_bonds(tmp_path):
    a = _stack(tmp_path, "alpha", "heimr-alpha")
    b = _stack(tmp_path, "beta", "heimr-beta")
    a.bonds.add_edge(BondEdge(
        bond_id="bond-a", entity_a="yrsa", entity_b="volmarr",
        domain=BondDomain.FRIENDSHIP,
        vector=BondVector(trust=0.9, warmth=0.9, familiarity=0.9, vulnerability=0.9),
    ))
    assert a.bonds.strength_between("yrsa", "volmarr") == pytest.approx(0.9)
    # Beta's bond graph knows nothing of alpha's bond — and the
    # Oracles were each composed with their own world's service.
    assert b.bonds.strength_between("yrsa", "volmarr") is None
    assert b.bonds.edges == {}


def test_isolation_events(tmp_path):
    bus_a, bus_b = EventBus(), EventBus()
    a = _stack(tmp_path, "alpha", "heimr-alpha", bus=bus_a)
    b = _stack(tmp_path, "beta", "heimr-beta", bus=bus_b)
    seen_a: list = []
    seen_b: list = []
    bus_a.subscribe("world.entity_created", seen_a.append)
    bus_b.subscribe("world.entity_created", seen_b.append)

    a.world.create_entity(entity_id="a-1")
    a.world.create_entity(entity_id="a-2")
    b.world.create_entity(entity_id="b-1")

    assert [e.payload["entity_id"] for e in seen_a] == ["a-1", "a-2"]
    assert [e.payload["entity_id"] for e in seen_b] == ["b-1"]


def test_isolation_threads_and_engagements(tmp_path):
    a = _stack(tmp_path, "alpha", "heimr-alpha")
    b = _stack(tmp_path, "beta", "heimr-beta")
    for stack in (a, b):
        _person(stack, "yrsa", "Yrsa")
        _person(stack, "volmarr", "Volmarr")
    host = _host_with(tmp_path, a, b)

    thread_id = ThreadEngine(a.world).weave("yrsa", "volmarr", kind="oath")
    CombatEngine(a.world).start_engagement(["yrsa", "volmarr"])

    assert [t.thread_id for t in a.oracle.get_wyrd_threads("yrsa")] == [thread_id]
    assert b.oracle.get_wyrd_threads("yrsa") == []
    assert b.oracle.get_thread_between("yrsa", "volmarr") == []
    assert a.oracle.get_engagement("yrsa") is not None
    assert b.oracle.get_engagement("yrsa") is None

    across = host.query_across("get_wyrd_threads", "yrsa")
    assert [(r.world_id, len(r.value)) for r in across] == [
        ("heimr-alpha", 1), ("heimr-beta", 0),
    ]


def test_isolation_persistence_round_trip_per_world(tmp_path):
    a = _stack(tmp_path, "alpha", "heimr-alpha")
    b = _stack(tmp_path, "beta", "heimr-beta")
    _person(a, "shared-id", "Alpha Name")
    _person(b, "shared-id", "Beta Name")
    _person(b, "beta-only", "Beta Only")

    store_a, store_b = WorldStore(tmp_path / "wa.db"), WorldStore(tmp_path / "wb.db")
    store_a.save(a.world)
    store_b.save(b.world)
    loaded_a = store_a.load("heimr-alpha")
    loaded_b = store_b.load("heimr-beta")
    assert loaded_a.get_component("shared-id", "name").name == "Alpha Name"
    assert loaded_b.get_component("shared-id", "name").name == "Beta Name"
    assert loaded_a.get_entity("beta-only") is None
    assert loaded_b.get_entity("beta-only") is not None


# ---------------------------------------------------------------------------
# Concurrent multi-world serving (B1 style — exact final state)
# ---------------------------------------------------------------------------

def test_concurrent_serving_two_worlds_exact_final_state(tmp_path):
    a = _stack(tmp_path, "alpha", "heimr-alpha")
    b = _stack(tmp_path, "beta", "heimr-beta")
    host = _host_with(tmp_path, a, b)
    n_threads, n_each = 4, 75

    def make_writer(stack: SimpleNamespace, tid: int):
        def writer():
            for i in range(n_each):
                eid = f"{stack.label}-{tid}-{i}"
                stack.world.create_entity(entity_id=eid, tags={"npc"})
                stack.world.add_component(
                    eid, NameComponent(entity_id=eid, name=f"{stack.label}:{eid}"))
        return writer

    def make_cross_reader():
        def reader():
            for _ in range(60):
                for result in host.query_across("what_is", "alpha-0-0"):
                    if result.value is not None and result.value.name is not None:
                        # An answer attributed to a world must be
                        # THAT world's answer — never the other's.
                        # (name is None only in the legitimate instant
                        # between a writer's create_entity and its
                        # add_component — a consistent snapshot of a
                        # half-built entity, not a cross-world leak.)
                        assert result.value.name.startswith(result.world_id.removeprefix("heimr-"))
                host.describe_worlds()
                host.registry_entries()
        return reader

    targets = (
        [make_writer(a, t) for t in range(n_threads)]
        + [make_writer(b, t) for t in range(n_threads)]
        + [make_cross_reader(), make_cross_reader()]
    )
    errors = _run_threads(targets)
    assert errors == []

    base_a = 3  # zone, region, location — the tree's own entities
    expected_a = {f"alpha-{t}-{i}" for t in range(n_threads) for i in range(n_each)}
    expected_b = {f"beta-{t}-{i}" for t in range(n_threads) for i in range(n_each)}
    assert {e.entity_id for e in a.world.query_by_tag("npc", active_only=False)} == expected_a
    assert {e.entity_id for e in b.world.query_by_tag("npc", active_only=False)} == expected_b
    assert a.world.entity_count() == len(expected_a) + base_a
    assert b.world.entity_count() == len(expected_b) + base_a
    sample = host.what_is_across("beta-2-10")
    assert [(r.world_id, r.value.name) for r in sample] == [
        ("heimr-beta", "beta:beta-2-10"),
    ]
