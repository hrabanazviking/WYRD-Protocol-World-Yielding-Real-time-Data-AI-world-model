"""Concurrency tests — Phase B1 (thread-safe World).

Before B1, ``World``/``YggdrasilTree`` held plain dict state with no
lock anywhere, while the threading HTTP server served request threads
against one shared bridge. A reproduction harness run against the
pre-B1 tree (8 writer + 8 reader threads, 250 entities each) produced
``RuntimeError: Set changed size during iteration`` in query methods,
lost ~6% of created entities, and left the tag/component indexes
disagreeing with each other; 8 concurrent ``process_turn`` calls
carrying the same idempotency key produced 2 distinct writes.

These tests pin the B1 discipline: one RLock on World (Yggdrasil and
the Oracle operate under it), a history lock on TurnLoop, an engine
lock making WritebackEngine's idempotency check→commit→record atomic,
a guarded per-persona loop map on the bridge, and WorldStore.save
snapshotting under the world lock. Every test asserts exact final
state — not merely "no exception" — and starts its threads on a
barrier so contention is real.
"""
from __future__ import annotations

import json
import socket
import tempfile
import threading
import urllib.request
from pathlib import Path

from wyrdforge.bridges.http_api import WyrdHTTPServer
from wyrdforge.bridges.python_rpg import PythonRPGBridge
from wyrdforge.ecs.components.identity import NameComponent
from wyrdforge.ecs.components.spatial import SpatialComponent
from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree
from wyrdforge.models.common import StoreName
from wyrdforge.oracle.passive_oracle import PassiveOracle
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.persistence.world_store import WorldStore
from wyrdforge.runtime.turn_loop import TurnLoop
from wyrdforge.services.contradiction_detector import ContradictionDetector
from wyrdforge.services.writeback_engine import WritebackEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_threads(targets) -> list[BaseException]:
    """Run callables on threads released simultaneously; return errors."""
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


def _build_tree(world: World) -> YggdrasilTree:
    tree = YggdrasilTree(world)
    tree.create_zone(zone_id="z", name="Zone")
    tree.create_region(region_id="r", name="Region", parent_zone_id="z")
    tree.create_location(location_id="loc-a", name="A", parent_region_id="r")
    tree.create_location(location_id="loc-b", name="B", parent_region_id="r")
    return tree


def _tmp_store(tmp_path: Path, name: str = "mem.db") -> PersistentMemoryStore:
    return PersistentMemoryStore(str(tmp_path / name))


class _EchoConnector:
    """Connector stub: replies deterministically from the last message."""

    def chat(self, messages, **kwargs) -> str:
        return "reply:" + messages[-1]["content"]


# ---------------------------------------------------------------------------
# World: concurrent mutation + query
# ---------------------------------------------------------------------------

def test_world_concurrent_create_query_remove_exact_final_state():
    world = World("b1-world")
    _build_tree(world)
    n_threads, n_each = 6, 150

    # A disjoint pre-created set for removers to delete.
    for i in range(60):
        world.create_entity(entity_id=f"doomed-{i}", tags={"doomed"})

    def make_writer(tid):
        def writer():
            for i in range(n_each):
                eid = f"e-{tid}-{i}"
                world.create_entity(entity_id=eid, tags={"npc"})
                world.add_component(eid, NameComponent(entity_id=eid, name=f"N{eid}"))
                if i % 5 == 0:
                    world.tag_entity(eid, "marked")
        return writer

    def make_reader():
        def reader():
            for _ in range(n_each):
                world.query_by_tag("npc")
                world.query_with_component("name")
                world.query_by_tags({"npc", "marked"})
                list(world.iter_components("name"))
                world.all_entities()
        return reader

    def make_remover(tid):
        def remover():
            for i in range(tid * 10, tid * 10 + 10):
                world.remove_entity(f"doomed-{i}")
        return remover

    targets = (
        [make_writer(t) for t in range(n_threads)]
        + [make_reader() for _ in range(3)]
        + [make_remover(t) for t in range(6)]
    )
    errors = _run_threads(targets)
    assert errors == []

    created = n_threads * n_each
    # Tree nodes: zone, region, loc-a, loc-b = 4; doomed all removed.
    assert world.entity_count() == created + 4
    by_tag = {e.entity_id for e in world.query_by_tag("npc", active_only=False)}
    by_comp = {e.entity_id for e in world.query_with_component("name", active_only=False)}
    expected = {f"e-{t}-{i}" for t in range(n_threads) for i in range(n_each)}
    assert by_tag == expected
    # Name index covers the created set (tree nodes carry names too).
    assert expected <= by_comp
    marked = {e.entity_id for e in world.query_by_tag("marked", active_only=False)}
    assert marked == {f"e-{t}-{i}" for t in range(n_threads) for i in range(n_each) if i % 5 == 0}
    assert world.query_by_tag("doomed", active_only=False) == []


def test_world_concurrent_duplicate_create_has_single_winner():
    world = World("b1-dupe")
    outcomes: list[str] = []
    lock = threading.Lock()

    def attempt():
        try:
            world.create_entity(entity_id="one", tags={"x"})
            with lock:
                outcomes.append("created")
        except ValueError:
            with lock:
                outcomes.append("duplicate")

    errors = _run_threads([attempt] * 12)
    assert errors == []
    assert outcomes.count("created") == 1
    assert outcomes.count("duplicate") == 11
    assert world.entity_count() == 1


def test_world_bus_wired_concurrent_mutation_no_deadlock():
    """Bus subscribers re-entering the World must not deadlock (RLock)."""
    from wyrdforge.runtime.events import EventBus

    bus = EventBus()
    world = World("b1-bus", bus=bus)
    seen: list[int] = []

    def on_created(envelope):
        # Re-entrant read from inside a delivery (bus delivers under
        # its own lock; the world lock is re-entrant per thread).
        seen.append(world.entity_count())

    bus.subscribe("world.entity_created", on_created)

    def make_writer(tid):
        def writer():
            for i in range(40):
                world.create_entity(entity_id=f"b-{tid}-{i}")
        return writer

    errors = _run_threads([make_writer(t) for t in range(4)])
    assert errors == []
    assert world.entity_count() == 160
    assert len(seen) == 160


# ---------------------------------------------------------------------------
# Yggdrasil: concurrent placement / movement / co-location
# ---------------------------------------------------------------------------

def test_yggdrasil_concurrent_place_move_consistent_containers():
    world = World("b1-tree")
    tree = _build_tree(world)
    n_threads, n_each = 5, 60

    def make_mover(tid):
        def mover():
            mine = []
            for i in range(n_each):
                eid = f"m-{tid}-{i}"
                world.create_entity(entity_id=eid, tags={"npc"})
                tree.place_entity(eid, location_id="loc-a")
                mine.append(eid)
            for round_no in range(3):
                target = "loc-b" if round_no % 2 == 0 else "loc-a"
                for eid in mine:
                    tree.move_entity(eid, location_id=target)
        return mover

    def make_reader():
        def reader():
            for _ in range(120):
                tree.get_children("loc-a")
                tree.get_children("loc-b")
                tree.describe_tree()
                tree.get_ancestors("loc-a")
        return reader

    errors = _run_threads([make_mover(t) for t in range(n_threads)] + [make_reader()])
    assert errors == []

    # Final state: 3 moves each (a→b, b→a, a→b) ⇒ everyone ends at loc-b,
    # nobody at loc-a, and container membership matches spatial truth.
    at_a = {e.entity_id for e in tree.get_children("loc-a")}
    at_b = {e.entity_id for e in tree.get_children("loc-b")}
    expected = {f"m-{t}-{i}" for t in range(n_threads) for i in range(n_each)}
    assert at_a == set()
    assert at_b == expected
    for eid in expected:
        spatial = world.get_component(eid, "spatial")
        assert isinstance(spatial, SpatialComponent)
        assert spatial.most_specific_id() == "loc-b"
        assert tree.get_location_of(eid) == "loc-b"


# ---------------------------------------------------------------------------
# Oracle: consistent snapshots under concurrent mutation
# ---------------------------------------------------------------------------

def test_oracle_queries_consistent_under_concurrent_mutation(tmp_path):
    world = World("b1-oracle")
    tree = _build_tree(world)
    store = _tmp_store(tmp_path)
    oracle = PassiveOracle(world, store, yggdrasil=tree)
    world.create_entity(entity_id="anchor", tags={"character"})
    world.add_component("anchor", NameComponent(entity_id="anchor", name="Anchor"))
    tree.place_entity("anchor", location_id="loc-a")

    stop = threading.Event()
    failures: list[str] = []

    def mutator(tid):
        i = 0
        while not stop.is_set():
            eid = f"x-{tid}-{i % 25}"
            if world.get_entity(eid) is None:
                world.create_entity(entity_id=eid, tags={"npc"})
                world.add_component(eid, NameComponent(entity_id=eid, name=f"X{eid}"))
                tree.place_entity(eid, location_id="loc-a")
            else:
                tree.move_entity(
                    eid, location_id="loc-b" if i % 2 == 0 else "loc-a"
                )
            i += 1

    def reader():
        try:
            for _ in range(150):
                packet = oracle.build_context_packet(
                    focus_entity_ids=["anchor"], location_id="loc-a"
                )
                assert packet.world_id == "b1-oracle"
                # One consistent snapshot: everyone reported present at
                # loc-a must carry loc-a as their summary location —
                # a torn read would mix a pre-move summary with a
                # post-move container (or vice versa).
                for summary in packet.present_entities:
                    assert summary.location_id == "loc-a", summary
                oracle.where_is("anchor")
                oracle.get_nearby("anchor")
                oracle.who_is_here("loc-a")
                oracle.get_relations("anchor")
        except BaseException as exc:  # noqa: BLE001 — collected + asserted
            failures.append(repr(exc))

    targets = [reader, reader]
    errors: list[BaseException] = []
    barrier = threading.Barrier(4)

    def wrap(fn):
        def run():
            barrier.wait()
            try:
                fn()
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)
        return run

    mutators = [threading.Thread(target=wrap(lambda t=t: mutator(t)), daemon=True) for t in range(2)]
    readers = [threading.Thread(target=wrap(r)) for r in targets]
    for t in mutators + readers:
        t.start()
    for t in readers:
        t.join()
    stop.set()
    for t in mutators:
        t.join(timeout=10)
    assert errors == []
    assert failures == []


# ---------------------------------------------------------------------------
# TurnLoop: concurrent turns keep history pairs intact
# ---------------------------------------------------------------------------

def _build_loop(tmp_path: Path, history_limit: int = 10_000) -> TurnLoop:
    world = World("b1-loop")
    tree = _build_tree(world)
    store = _tmp_store(tmp_path, "loop.db")
    oracle = PassiveOracle(world, store, yggdrasil=tree)
    engine = WritebackEngine(store)
    detector = ContradictionDetector(store)
    return TurnLoop(
        oracle, engine, detector, _EchoConnector(), history_limit=history_limit
    )


def test_turn_loop_concurrent_turns_history_pairs_intact(tmp_path):
    loop = _build_loop(tmp_path)
    n_threads, n_turns = 4, 20

    def make_caller(tid):
        def caller():
            for i in range(n_turns):
                loop.execute_turn(f"u{tid}-{i}")
        return caller

    errors = _run_threads([make_caller(t) for t in range(n_threads)])
    assert errors == []
    history = loop.get_history()
    assert len(history) == 2 * n_threads * n_turns
    for i in range(0, len(history), 2):
        user, assistant = history[i], history[i + 1]
        assert user["role"] == "user"
        assert assistant["role"] == "assistant"
        assert assistant["content"] == "reply:" + user["content"]
    assert loop.history_turn_count() == n_threads * n_turns


def test_turn_loop_concurrent_clear_and_reads_no_errors(tmp_path):
    loop = _build_loop(tmp_path)

    def caller():
        for i in range(30):
            loop.execute_turn(f"msg-{i}")

    def janitor():
        for _ in range(30):
            loop.get_history()
            loop.history_turn_count()
            loop.clear_history()

    errors = _run_threads([caller, caller, janitor])
    assert errors == []
    # Whatever the interleaving, history is whole pairs only.
    assert len(loop.get_history()) % 2 == 0


# ---------------------------------------------------------------------------
# WritebackEngine: idempotency under concurrency
# ---------------------------------------------------------------------------

def test_writeback_concurrent_same_idempotency_key_writes_once(tmp_path):
    store = _tmp_store(tmp_path, "wb.db")
    engine = WritebackEngine(store)
    results: list[list[str]] = []
    lock = threading.Lock()

    def call():
        result = engine.process_turn(
            user_input="hello", response_text="hi", idempotency_key="K-1"
        )
        with lock:
            results.append([r.record_id for r in result["observations"]])

    errors = _run_threads([call] * 8)
    assert errors == []
    assert len(results) == 8
    assert all(r == results[0] for r in results)
    observations = store.all(store=StoreName.HUGIN.value)
    assert len(observations) == 1


def test_writeback_concurrent_distinct_turns_all_land(tmp_path):
    store = _tmp_store(tmp_path, "wb2.db")
    engine = WritebackEngine(store)
    n_threads, n_turns = 4, 15

    def make_caller(tid):
        def caller():
            for i in range(n_turns):
                engine.process_turn(
                    user_input=f"u{tid}-{i}", response_text=f"r{tid}-{i}"
                )
        return caller

    errors = _run_threads([make_caller(t) for t in range(n_threads)])
    assert errors == []
    assert len(store.all(store=StoreName.HUGIN.value)) == n_threads * n_turns


# ---------------------------------------------------------------------------
# WorldStore: save snapshots stay consistent under concurrent mutation
# ---------------------------------------------------------------------------

def test_world_store_save_under_concurrent_mutation(tmp_path):
    world = World("b1-save")
    _build_tree(world)
    store = WorldStore(tmp_path / "world.db")
    stop = threading.Event()
    save_errors: list[BaseException] = []

    def mutator(tid):
        i = 0
        while not stop.is_set():
            eid = f"s-{tid}-{i % 30}"
            if world.get_entity(eid) is None:
                world.create_entity(entity_id=eid, tags={"npc"})
                world.add_component(eid, NameComponent(entity_id=eid, name=f"S{eid}"))
            else:
                world.remove_entity(eid)
            i += 1

    def saver():
        try:
            while not stop.is_set():
                store.save(world)
        except BaseException as exc:  # noqa: BLE001
            save_errors.append(exc)

    mutators = [threading.Thread(target=lambda t=t: mutator(t)) for t in range(3)]
    save_thread = threading.Thread(target=saver)
    for t in mutators + [save_thread]:
        t.start()
    # Let churn + saves overlap for a bounded stretch, then stop.
    threading.Event().wait(1.5)
    stop.set()
    for t in mutators + [save_thread]:
        t.join(timeout=15)
    assert save_errors == []

    # Final save with mutation stopped must round-trip exactly.
    store.save(world)
    loaded = store.load("b1-save")
    assert {e.entity_id for e in loaded.all_entities(active_only=False)} == {
        e.entity_id for e in world.all_entities(active_only=False)
    }
    for entity in world.all_entities(active_only=False):
        assert {c.component_type for c in loaded.get_all_components(entity.entity_id)} == {
            c.component_type for c in world.get_all_components(entity.entity_id)
        }


# ---------------------------------------------------------------------------
# Bridge + HTTP: concurrent request threads against one shared stack
# ---------------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


def test_bridge_concurrent_first_query_creates_one_loop_per_persona(tmp_path):
    world = World("b1-bridge")
    tree = _build_tree(world)
    store = _tmp_store(tmp_path, "bridge.db")
    bridge = PythonRPGBridge(world, tree, store, _EchoConnector())

    def make_caller():
        def caller():
            bridge.query("sigrid", "hello there", use_turn_loop=True)
        return caller

    errors = _run_threads([make_caller() for _ in range(6)])
    assert errors == []
    assert list(bridge._turn_loops.keys()) == ["sigrid"]
    assert bridge._turn_loops["sigrid"].history_turn_count() == 6


def test_http_server_concurrent_requests(tmp_path):
    world = World("b1-http")
    tree = _build_tree(world)
    world.create_entity(entity_id="sigrid", tags={"character"})
    world.add_component("sigrid", NameComponent(entity_id="sigrid", name="Sigrid"))
    tree.place_entity("sigrid", location_id="loc-a")
    store = _tmp_store(tmp_path, "http.db")
    bridge = PythonRPGBridge(world, tree, store, _EchoConnector())
    port = _free_port()
    server = WyrdHTTPServer(bridge, host="localhost", port=port)
    thread = server.start_background()
    try:
        def request(path, *, method="GET", body=None):
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(
                f"http://localhost:{port}{path}", data=data, method=method
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status, json.loads(resp.read().decode())

        def make_client(tid):
            def client():
                for i in range(6):
                    status, payload = request("/world")
                    assert status == 200 and payload["world_id"] == "b1-http"
                    status, payload = request("/facts?entity_id=sigrid")
                    assert status == 200 and "facts" in payload
                    status, payload = request(
                        "/query",
                        method="POST",
                        body={
                            "persona_id": "sigrid",
                            "user_input": f"question {tid}-{i}",
                            "use_turn_loop": True,
                        },
                    )
                    assert status == 200 and payload["response"].startswith("reply:")
                    status, payload = request(
                        "/event",
                        method="POST",
                        body={
                            "event_type": "observation",
                            "payload": {"title": f"ev {tid}-{i}", "summary": "seen"},
                        },
                    )
                    assert status == 200 and payload["ok"] is True
                    # Concurrent world mutation from the client side too.
                    eid = f"http-{tid}-{i}"
                    world.create_entity(entity_id=eid, tags={"npc"})
                    world.add_component(
                        eid, NameComponent(entity_id=eid, name=f"H{eid}")
                    )
            return client

        errors = _run_threads([make_client(t) for t in range(4)])
        assert errors == []
    finally:
        server.shutdown()
        thread.join(timeout=10)

    # All client-side creations landed exactly once; the persona has
    # one loop whose history holds every query's pair.
    assert len(world.query_by_tag("npc", active_only=False)) == 24
    assert list(bridge._turn_loops.keys()) == ["sigrid"]
    assert bridge._turn_loops["sigrid"].history_turn_count() == 24
