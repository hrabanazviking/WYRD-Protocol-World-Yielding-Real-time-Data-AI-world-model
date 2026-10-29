"""Phase D4 — metaphysics reconciliation pinning tests.

Design under test (roadmap §3.5 / §9-D4, ``ecs/components/
metaphysical.py`` + ``services/thread_engine.py`` + the Oracle's
D4 queries):

* The Phase 7 plan promised ``WyrdThreadComponent`` /
  ``SpiritualChargeComponent`` in a ``metaphysical.py``; what
  shipped was the runic layer in ``runic.py`` (HamingjaComponent,
  RunicChargeComponent = the spiritual charge under its runic name,
  AncestralResonanceComponent). D4 ships the missing fate/thread
  semantics ON that foundation: a thread is an ENTITY carrying
  WyrdThreadComponent between exactly two endpoints, composed with
  the runic components by reference and by report — never by
  duplicating runic state.
* Convergence is DERIVED (strength × wyrd_charge between
  co-located endpoints), never stored. Sever/fulfill are terminal
  and announce exactly once. Threads persist generically through
  WorldStore — no schema change, no migration.
"""
from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone

import pytest

import wyrdforge.ecs.components.metaphysical  # noqa: F401  (registry)
import wyrdforge.ecs.components.runic  # noqa: F401  (registry)
import wyrdforge.ecs.components.spatial  # noqa: F401  (registry)
from wyrdforge.ecs.components.metaphysical import WyrdThreadComponent
from wyrdforge.ecs.components.runic import (
    AncestralResonanceComponent,
    HamingjaComponent,
    RunicChargeComponent,
)
from wyrdforge.ecs.components.spatial import SpatialComponent
from wyrdforge.ecs.world import World
from wyrdforge.oracle import PassiveOracle
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.persistence.world_store import WorldStore
from wyrdforge.runtime.events import EventBus
from wyrdforge.services.runic_engine import RunicEngine
from wyrdforge.services.thread_engine import ThreadEngine

UTC = timezone.utc
T0 = datetime(2026, 10, 29, 12, 0, 0, tzinfo=UTC)


def _oracle(world: World) -> PassiveOracle:
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    return PassiveOracle(world, store)


def _person(world: World, eid: str, *, location: str | None = None,
            hamingja: float | None = None) -> None:
    world.create_entity(entity_id=eid)
    if location is not None:
        world.add_component(eid, SpatialComponent(entity_id=eid, location_id=location))
    if hamingja is not None:
        world.add_component(eid, HamingjaComponent(entity_id=eid, score=hamingja))


def _bus_with_topics() -> tuple[EventBus, list]:
    bus = EventBus()
    seen: list = []
    for topic in (
        "wyrd.thread_woven", "wyrd.thread_adjusted",
        "wyrd.thread_severed", "wyrd.thread_fulfilled",
    ):
        bus.register_topic(topic)
        bus.subscribe(topic, seen.append)
    return bus, seen


# ---------------------------------------------------------------------------
# The reconciliation claim — plan names vs shipped names
# ---------------------------------------------------------------------------

class TestReconciliationMapping:
    def test_plan_names_resolve_to_shipped_shapes(self):
        # WyrdThreadComponent now exists under the plan's own name in
        # the plan's own module; the spiritual charge exists as the
        # runic charge (per-rune map, total_charge the aggregate).
        thread = WyrdThreadComponent(
            entity_id="t", endpoint_ids=["a", "b"], wyrd_charge=0.4)
        assert thread.component_type == "wyrd_thread"
        charge = RunicChargeComponent(entity_id="a", charges={"fehu": 0.5, "uruz": 0.25})
        assert charge.total_charge() == pytest.approx(0.75)
        # Hamingja's shipped signed score carries the plan's
        # blessing/curse pair: negative is cursed, positive blessed.
        assert HamingjaComponent(entity_id="a", score=-0.5).score < 0
        assert AncestralResonanceComponent(
            entity_id="a", lineage_ids=["grandmother"]).lineage_ids == ["grandmother"]

    def test_thread_requires_exactly_two_distinct_endpoints(self):
        with pytest.raises(Exception):
            WyrdThreadComponent(entity_id="t", endpoint_ids=["a"])
        with pytest.raises(Exception):
            WyrdThreadComponent(entity_id="t", endpoint_ids=["a", "a"])
        with pytest.raises(Exception):
            WyrdThreadComponent(entity_id="t", endpoint_ids=["a", "b", "c"])
        comp = WyrdThreadComponent(entity_id="t", endpoint_ids=["a", "b"])
        assert comp.involves("a") and comp.involves("b") and not comp.involves("c")
        assert comp.other_endpoint("a") == "b"
        assert comp.other_endpoint("c") is None


# ---------------------------------------------------------------------------
# Thread component behaviour
# ---------------------------------------------------------------------------

class TestThreadComponent:
    def test_convergence_score_is_derived_from_strength_and_charge(self):
        comp = WyrdThreadComponent(
            entity_id="t", endpoint_ids=["a", "b"], strength=0.8, wyrd_charge=0.5)
        assert comp.convergence_score == pytest.approx(0.4)
        assert not comp.is_convergence(0.5)
        comp.wyrd_charge = 0.9  # direct field change — derived value follows
        assert comp.convergence_score == pytest.approx(0.72)
        assert comp.is_convergence(0.5)

    def test_lifecycle_terminal_states(self):
        comp = WyrdThreadComponent(entity_id="t", endpoint_ids=["a", "b"])
        assert comp.is_live and comp.status == "woven"
        comp.sever(at=T0)
        assert comp.status == "severed" and comp.closed_at == T0 and not comp.is_live
        with pytest.raises(ValueError):
            comp.fulfill()
        other = WyrdThreadComponent(entity_id="t2", endpoint_ids=["a", "b"])
        other.fulfill(at=T0)
        assert other.status == "fulfilled"
        with pytest.raises(ValueError):
            other.sever()
        # A closed thread is never a convergence, whatever its pressure.
        closed = WyrdThreadComponent(
            entity_id="t3", endpoint_ids=["a", "b"], strength=1.0, wyrd_charge=1.0)
        closed.sever(at=T0)
        assert not closed.is_convergence(0.0)


# ---------------------------------------------------------------------------
# ThreadEngine — weave / adjust / sever / fulfill / tick
# ---------------------------------------------------------------------------

class TestThreadEngine:
    def test_weave_creates_thread_entity_and_announces(self):
        bus, seen = _bus_with_topics()
        world = World("w", bus=bus)
        _person(world, "a")
        _person(world, "b")
        engine = ThreadEngine(world, bus=bus)
        tid = engine.weave(
            "a", "b", kind="oath", strength=0.7, wyrd_charge=0.3,
            prophesied_event="the ford meeting", rune_name="tiwaz",
            basis_event_ids=["evt-oath"], at=T0)
        comp = world.get_component(tid, "wyrd_thread")
        assert isinstance(comp, WyrdThreadComponent)
        assert comp.endpoint_ids == ["a", "b"] and comp.kind == "oath"
        assert comp.rune_name == "tiwaz" and comp.basis_event_ids == ["evt-oath"]
        assert comp.woven_at == T0 and comp.is_live
        assert [env.topic for env in seen] == ["wyrd.thread_woven"]
        assert seen[0].payload["thread_id"] == tid
        assert seen[0].payload["endpoint_ids"] == ["a", "b"]

    def test_weave_self_thread_refused(self):
        world = World("w")
        _person(world, "a")
        engine = ThreadEngine(world)
        with pytest.raises(ValueError):
            engine.weave("a", "a")

    def test_adjust_clamps_and_refuses_terminal_threads(self):
        bus, seen = _bus_with_topics()
        world = World("w", bus=bus)
        _person(world, "a")
        _person(world, "b")
        engine = ThreadEngine(world, bus=bus)
        tid = engine.weave("a", "b", strength=0.9, wyrd_charge=0.1)
        comp = engine.adjust(tid, strength_delta=0.5, charge_delta=-0.5)
        assert comp.strength == 1.0 and comp.wyrd_charge == 0.0  # clamped both ways
        assert [env.topic for env in seen][-1] == "wyrd.thread_adjusted"
        engine.sever(tid, at=T0)
        with pytest.raises(ValueError):
            engine.adjust(tid, strength_delta=0.1)
        with pytest.raises(KeyError):
            engine.adjust("not-a-thread", strength_delta=0.1)

    def test_sever_and_fulfill_announce_exactly_once(self):
        bus, seen = _bus_with_topics()
        world = World("w", bus=bus)
        _person(world, "a")
        _person(world, "b")
        engine = ThreadEngine(world, bus=bus)
        t1 = engine.weave("a", "b", kind="oath")
        t2 = engine.weave("a", "b", kind="grief", prophesied_event="the parting")
        engine.sever(t1, at=T0)
        with pytest.raises(ValueError):
            engine.sever(t1)  # terminal — no second event possible
        engine.fulfill(t2, at=T0 + timedelta(days=1))
        with pytest.raises(ValueError):
            engine.fulfill(t2)
        topics = [env.topic for env in seen]
        assert topics.count("wyrd.thread_severed") == 1
        assert topics.count("wyrd.thread_fulfilled") == 1
        fulfilled = [e for e in seen if e.topic == "wyrd.thread_fulfilled"][0]
        assert fulfilled.payload["prophesied_event"] == "the parting"

    def test_tick_decays_live_threads_only(self):
        world = World("w")
        _person(world, "a")
        _person(world, "b")
        _person(world, "c")
        engine = ThreadEngine(world)
        live = engine.weave("a", "b", strength=0.5, decay_rate=0.1)
        dead = engine.weave("a", "c", strength=0.5, decay_rate=0.1)
        frozen = engine.weave("b", "c", strength=0.5, decay_rate=0.0)
        engine.sever(dead)
        changed = engine.tick()
        assert changed == [live]
        assert world.get_component(live, "wyrd_thread").strength == pytest.approx(0.4)
        assert world.get_component(dead, "wyrd_thread").strength == 0.5  # history kept
        assert world.get_component(frozen, "wyrd_thread").strength == 0.5
        # Decay floors at 0.0 and then stops changing (dormant, not severed).
        engine.adjust(live, strength_delta=-0.35)
        assert engine.tick() == [live]
        assert world.get_component(live, "wyrd_thread").strength == 0.0
        assert engine.tick() == []
        assert world.get_component(live, "wyrd_thread").is_live

    def test_threads_for_and_between(self):
        world = World("w")
        for eid in ("a", "b", "c"):
            _person(world, eid)
        engine = ThreadEngine(world)
        t_ab = engine.weave("a", "b", kind="oath")
        t_ac = engine.weave("a", "c", kind="grief")
        engine.weave("b", "c", kind="love")
        assert [c.entity_id for c in engine.threads_for("a")] == sorted([t_ab, t_ac])
        assert [c.entity_id for c in engine.threads_between("b", "a")] == [t_ab]
        engine.sever(t_ab)
        assert [c.entity_id for c in engine.threads_for("a")] == [t_ac]
        assert [c.entity_id for c in engine.threads_for("a", live_only=False)] == sorted([t_ab, t_ac])


# ---------------------------------------------------------------------------
# Composition with the runic foundation
# ---------------------------------------------------------------------------

class TestRunicComposition:
    def test_weaving_does_not_touch_runic_state_and_oracle_reports_it_live(self):
        world = World("w")
        _person(world, "a", hamingja=0.25)
        _person(world, "b")
        runic = RunicEngine(world)
        runic.invoke_rune("b", "fehu", strength=0.5)  # b gains charge + hamingja boost
        hamingja_b_before = world.get_component("b", "hamingja").score

        engine = ThreadEngine(world)
        tid = engine.weave("a", "b", kind="oath", rune_name="fehu", strength=0.6)
        # Weaving changed NO runic state on either endpoint.
        assert world.get_component("b", "hamingja").score == hamingja_b_before
        assert world.get_component("b", "runic_charge").get_charge("fehu") == 0.5
        assert world.get_component("a", "runic_charge") is None

        oracle = _oracle(world)
        result = oracle.get_thread_between("a", "b")[0]
        assert result.thread_id == tid and result.rune_name == "fehu"
        # Hamingja reported LIVE beside the thread: a's stored 0.25,
        # b's post-invocation boost — read at query time, not woven in.
        assert result.hamingja == {"a": 0.25, "b": hamingja_b_before}
        runic.apply_hamingja_event("a", delta=0.5)
        result2 = oracle.get_thread_between("b", "a")[0]  # direction-free
        assert result2.hamingja["a"] == pytest.approx(0.75)
        assert world.get_component(tid, "wyrd_thread").strength == 0.6  # thread untouched


# ---------------------------------------------------------------------------
# Oracle thread queries + convergences
# ---------------------------------------------------------------------------

class TestOracleThreads:
    def test_get_wyrd_threads_ordering_and_live_filter(self):
        world = World("w")
        for eid in ("a", "b", "c"):
            _person(world, eid)
        engine = ThreadEngine(world)
        weak = engine.weave("a", "b", strength=0.2)
        strong = engine.weave("a", "c", strength=0.9)
        gone = engine.weave("a", "b", kind="grief", strength=0.99)
        engine.sever(gone)
        oracle = _oracle(world)
        live = oracle.get_wyrd_threads("a")
        assert [r.thread_id for r in live] == [strong, weak]  # strongest first
        assert live[0].status == "woven" and live[0].closed_at is None
        all_threads = oracle.get_wyrd_threads("a", live_only=False)
        assert [r.thread_id for r in all_threads] == [gone, strong, weak]
        assert all_threads[0].status == "severed"
        assert oracle.get_wyrd_threads("stranger") == []
        assert oracle.get_thread_between("b", "c") == []

    def test_convergences_require_pressure_and_co_location(self):
        world = World("w")
        _person(world, "a", location="ford")
        _person(world, "b", location="ford")
        _person(world, "far-a", location="hill")
        _person(world, "far-b", location="vale")
        _person(world, "unplaced-a")
        _person(world, "unplaced-b")
        engine = ThreadEngine(world)
        hot = engine.weave("a", "b", strength=0.9, wyrd_charge=0.9)        # 0.81, co-located
        tepid = engine.weave("a", "b", kind="grief", strength=0.9, wyrd_charge=0.4)  # 0.36
        remote = engine.weave("far-a", "far-b", strength=1.0, wyrd_charge=1.0)       # apart
        unplaced = engine.weave("unplaced-a", "unplaced-b", strength=1.0, wyrd_charge=1.0)
        oracle = _oracle(world)
        found = oracle.get_convergences(threshold=0.5)
        assert [r.thread_id for r in found] == [hot]
        assert found[0].convergence_score == pytest.approx(0.81)
        # The engine's pure read agrees with the Oracle's.
        assert [c.entity_id for c in engine.detect_convergences(threshold=0.5)] == [hot]
        # Lower the threshold and the tepid thread joins, ordered by pressure.
        found_low = oracle.get_convergences(threshold=0.3)
        assert [r.thread_id for r in found_low] == [hot, tepid]
        # Severed threads never converge, whatever their pressure was.
        engine.sever(hot)
        assert oracle.get_convergences(threshold=0.5) == []
        assert remote not in [r.thread_id for r in oracle.get_convergences(threshold=0.0)]
        assert unplaced not in [r.thread_id for r in oracle.get_convergences(threshold=0.0)]
        with pytest.raises(ValueError):
            oracle.get_convergences(threshold=-0.1)


# ---------------------------------------------------------------------------
# Persistence round-trip — generic, no migration
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_thread_state_round_trips(self, tmp_path):
        store = WorldStore(tmp_path / "world.db")
        world = World("thread-world")
        _person(world, "a", location="ford", hamingja=-0.4)
        _person(world, "b", location="ford", hamingja=0.6)
        runic = RunicEngine(world)
        runic.invoke_rune("a", "uruz", strength=0.3)
        engine = ThreadEngine(world)
        tid = engine.weave(
            "a", "b", kind="oath", strength=0.8, wyrd_charge=0.75,
            prophesied_event="the ford meeting", rune_name="uruz",
            basis_event_ids=["evt-1"], at=T0)
        done = engine.weave("a", "b", kind="grief", strength=0.3)
        engine.fulfill(done, at=T0 + timedelta(days=2))
        store.save(world)

        loaded = store.load("thread-world")
        comp = loaded.get_component(tid, "wyrd_thread")
        assert isinstance(comp, WyrdThreadComponent)
        assert comp.endpoint_ids == ["a", "b"] and comp.kind == "oath"
        assert comp.strength == 0.8 and comp.wyrd_charge == 0.75
        assert comp.prophesied_event == "the ford meeting"
        assert comp.rune_name == "uruz" and comp.basis_event_ids == ["evt-1"]
        assert comp.woven_at == T0 and comp.is_live
        oracle = _oracle(loaded)
        results = oracle.get_wyrd_threads("a", live_only=False)
        assert [r.thread_id for r in results] == [tid, done]
        # a's hamingja: -0.4 woven in, +0.03 from the uruz invocation
        # (RunicEngine's strength * 0.1 boost) — the runic layer's own
        # arithmetic, reported live by the Oracle.
        assert results[0].hamingja == {"a": pytest.approx(-0.37), "b": 0.6}
        assert results[0].convergence_score == pytest.approx(0.6)
        assert oracle.get_convergences(threshold=0.5)[0].thread_id == tid
        assert results[1].status == "fulfilled"
        assert results[1].closed_at == T0 + timedelta(days=2)
