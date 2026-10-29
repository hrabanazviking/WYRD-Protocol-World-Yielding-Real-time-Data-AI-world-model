"""Phase B2 — incremental persistence: dirty-row tracking, batched
savepoints, and the live-rate load harness.

Design under test (see ``WorldStore.save_with_report``): a save
snapshots the world under ``world.lock`` (the B1 surface), diffs each
serialized row byte-for-byte against the baseline of what the store
last persisted, upserts only dirty rows, and sweeps deletions. The
fingerprint IS the serialized row, so in-place component mutation
(``take_damage()``, container ``add_child()``, direct field writes)
is detected exactly like structural change.

The correctness harness is the heart of this file: one world is
driven through every mutation path, saved incrementally after every
step (and reloaded + compared after every step), then saved with
``full=True`` into a second store — the two databases must end up
byte-identical, table for table.

The live-rate harness exercises the B2 scenario from the roadmap:
1 Hz presence churn plus chat-burst-like writes against a
1,000-entity world, with the budget parsed out of
``docs/performance-budgets.md`` in the B1 style (the doc is the
source of the number; this test enforces it) plus a
machine-independent write-volume bound: an incremental tick writes
rows proportional to the change set, never to the world size.
"""

from __future__ import annotations

import json
import re
import sqlite3
import statistics
import tempfile
import time
from pathlib import Path

import pytest

import wyrdforge.ecs.components.character  # noqa: F401
import wyrdforge.ecs.components.identity  # noqa: F401
import wyrdforge.ecs.components.physical  # noqa: F401
import wyrdforge.ecs.components.spatial  # noqa: F401
from wyrdforge.ecs.components.character import HealthComponent
from wyrdforge.ecs.components.identity import NameComponent, StatusComponent
from wyrdforge.ecs.components.spatial import SpatialComponent
from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree
from wyrdforge.persistence.world_store import WorldStore

DOC = Path(__file__).resolve().parents[1] / "docs" / "performance-budgets.md"


def _temp_store() -> tuple[WorldStore, Path]:
    tmp = tempfile.mktemp(suffix=".db")
    return WorldStore(tmp), Path(tmp)


def _build_world(world_id: str = "b2_world") -> tuple[World, YggdrasilTree]:
    world = World(world_id=world_id, world_name="B2 World")
    tree = YggdrasilTree(world)
    tree.create_zone(zone_id="midgard", name="Midgard")
    tree.create_region(region_id="fjords", name="Fjords", parent_zone_id="midgard")
    tree.create_location(location_id="hall", name="Mead Hall", parent_region_id="fjords")
    tree.create_location(location_id="dock", name="Dock", parent_region_id="fjords")
    for i in range(1, 6):
        eid = f"av-{i}"
        world.create_entity(entity_id=eid, tags={"npc"})
        world.add_component(eid, NameComponent(entity_id=eid, name=f"Avatar {i}"))
        world.add_component(eid, HealthComponent(entity_id=eid, hp=100.0))
        world.add_component(eid, StatusComponent(entity_id=eid, state="idle"))
        tree.place_entity(eid, location_id="hall")
    return world, tree


def _fingerprint(world: World) -> dict:
    """Semantic fingerprint: entities (tags/active) + component payloads."""
    fp = {}
    for entity in world.all_entities(active_only=False):
        comps = {
            comp.component_type: json.loads(comp.model_dump_json())
            for comp in world.get_all_components(entity.entity_id)
        }
        fp[entity.entity_id] = (sorted(entity.tags), entity.active, comps)
    return fp


def _tables(db_path: Path) -> dict[str, list[tuple]]:
    conn = sqlite3.connect(db_path)
    try:
        return {
            table: conn.execute(f"SELECT * FROM {table} ORDER BY 1, 2, 3").fetchall()
            for table in ("worlds", "entities", "components")
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# SaveReport pins — what a save writes, exactly
# ---------------------------------------------------------------------------


def test_first_save_writes_everything_second_save_writes_nothing() -> None:
    store, _ = _temp_store()
    world, _tree = _build_world()
    first = store.save_with_report(world)
    assert first.entities_written == world.entity_count()
    assert first.components_written == sum(
        len(world.get_all_components(e.entity_id))
        for e in world.all_entities(active_only=False)
    )
    assert first.entities_deleted == 0 and first.components_deleted == 0

    second = store.save_with_report(world)
    assert second.entities_written == 0
    assert second.components_written == 0
    assert second.entities_deleted == 0 and second.components_deleted == 0
    assert second.world_row_written is False
    assert second.entities_unchanged == world.entity_count()


def test_in_place_component_mutation_writes_exactly_one_row() -> None:
    store, _ = _temp_store()
    world, _tree = _build_world()
    store.save(world)
    health = world.get_component("av-1", "health")
    assert isinstance(health, HealthComponent)
    health.take_damage(25.0)  # in-place field mutation, no World call
    report = store.save_with_report(world)
    assert report.components_written == 1
    assert report.entities_written == 0
    loaded = store.load(world.world_id)
    loaded_health = loaded.get_component("av-1", "health")
    assert isinstance(loaded_health, HealthComponent)
    assert loaded_health.hp == 75.0


def test_direct_field_assignment_and_touch_are_dirty() -> None:
    store, _ = _temp_store()
    world, _tree = _build_world()
    store.save(world)
    name = world.get_component("av-2", "name")
    assert isinstance(name, NameComponent)
    name.name = "Renamed"
    report = store.save_with_report(world)
    assert report.components_written == 1
    health = world.get_component("av-3", "health")
    assert isinstance(health, HealthComponent)
    health.touch()  # only updated_at changes — still persisted content
    report = store.save_with_report(world)
    assert report.components_written == 1


def test_tag_change_writes_one_entity_and_no_components() -> None:
    store, _ = _temp_store()
    world, _tree = _build_world()
    store.save(world)
    world.tag_entity("av-1", "hero")
    report = store.save_with_report(world)
    assert report.entities_written == 1
    assert report.components_written == 0


def test_yggdrasil_move_writes_spatial_plus_two_containers() -> None:
    store, _ = _temp_store()
    world, tree = _build_world()
    store.save(world)
    tree.move_entity("av-1", location_id="dock")
    report = store.save_with_report(world)
    # The moved entity's spatial component + the old and new
    # locations' container components (mutated in place + touch()).
    assert report.components_written == 3
    assert report.entities_written == 0
    loaded = store.load(world.world_id)
    spatial = loaded.get_component("av-1", "spatial")
    assert isinstance(spatial, SpatialComponent)
    assert spatial.location_id == "dock"


def test_component_replace_is_one_write() -> None:
    store, _ = _temp_store()
    world, _tree = _build_world()
    store.save(world)
    world.add_component("av-1", StatusComponent(entity_id="av-1", state="fighting"))
    report = store.save_with_report(world)
    assert report.components_written == 1
    loaded = store.load(world.world_id)
    status = loaded.get_component("av-1", "status")
    assert isinstance(status, StatusComponent)
    assert status.state == "fighting"


# ---------------------------------------------------------------------------
# Deletion sweep — entities, components, and the resurrection fix
# ---------------------------------------------------------------------------


def test_removed_component_is_swept_and_does_not_resurrect() -> None:
    store, path = _temp_store()
    world, _tree = _build_world()
    store.save(world)
    world.remove_component("av-1", "status")
    report = store.save_with_report(world)
    assert report.components_deleted == 1
    rows = sqlite3.connect(path).execute(
        "SELECT COUNT(*) FROM components WHERE entity_id='av-1' AND component_type='status'"
    ).fetchone()
    assert rows[0] == 0
    loaded = store.load(world.world_id)
    assert loaded.get_component("av-1", "status") is None


def test_removed_entity_sweeps_its_components() -> None:
    store, path = _temp_store()
    world, _tree = _build_world()
    store.save(world)
    world.remove_entity("av-1")
    report = store.save_with_report(world)
    assert report.entities_deleted == 1
    # name + health + status + spatial
    assert report.components_deleted == 4
    conn = sqlite3.connect(path)
    assert conn.execute("SELECT COUNT(*) FROM entities WHERE entity_id='av-1'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM components WHERE entity_id='av-1'").fetchone()[0] == 0
    loaded = store.load(world.world_id)
    assert loaded.get_entity("av-1") is None


def test_full_save_also_sweeps_and_matches_incremental() -> None:
    world, _tree = _build_world()
    world.remove_component("av-1", "status")
    world.remove_entity("av-2")
    store_a, path_a = _temp_store()
    store_a.save(world)  # incremental (cold-cache, DB-seeded baseline)
    store_b, path_b = _temp_store()
    store_b.save(world, full=True)
    assert _tables(path_a) == _tables(path_b)


# ---------------------------------------------------------------------------
# Baselines: load-seeded, fresh-instance (DB-seeded), failure honesty
# ---------------------------------------------------------------------------


def test_load_seeds_baseline_first_save_after_load_is_incremental() -> None:
    store, _ = _temp_store()
    world, _tree = _build_world()
    store.save(world)
    loaded = store.load(world.world_id)
    report = store.save_with_report(loaded)
    assert report.entities_written == 0
    assert report.components_written == 0
    health = loaded.get_component("av-1", "health")
    assert isinstance(health, HealthComponent)
    health.take_damage(10.0)
    report = store.save_with_report(loaded)
    assert report.components_written == 1


def test_fresh_store_instance_seeds_baseline_from_database() -> None:
    store, path = _temp_store()
    world, _tree = _build_world()
    store.save(world)
    # A new WorldStore on the same file (process-restart simulation):
    # its first save diffs against the database's own rows.
    store2 = WorldStore(path)
    report = store2.save_with_report(world)
    assert report.entities_written == 0
    assert report.components_written == 0
    health = world.get_component("av-1", "health")
    assert isinstance(health, HealthComponent)
    health.take_damage(5.0)
    report = store2.save_with_report(world)
    assert report.components_written == 1


def test_failed_save_leaves_everything_dirty(monkeypatch: pytest.MonkeyPatch) -> None:
    store, _ = _temp_store()
    world, _tree = _build_world()
    real_connect = store._connect

    def boom() -> None:
        raise RuntimeError("injected save failure")

    monkeypatch.setattr(store, "_connect", boom)
    with pytest.raises(RuntimeError):
        store.save(world)
    monkeypatch.setattr(store, "_connect", real_connect)
    report = store.save_with_report(world)
    assert report.entities_written == world.entity_count()
    assert report.components_written > 0
    # And the world really is in the store now.
    assert store.load(world.world_id).entity_count() == world.entity_count()


def test_quarantined_component_row_is_pinned_not_swept() -> None:
    store, path = _temp_store()
    world, _tree = _build_world()
    store.save(world)
    # Corrupt one stored component so the next load quarantines it
    # (payload's own type is unregistered -> unknown-type failure).
    conn = sqlite3.connect(path)
    conn.execute(
        "UPDATE components SET data_json=? WHERE entity_id='av-1' AND component_type='health'",
        (json.dumps({"component_type": "no_such_type", "entity_id": "av-1"}),),
    )
    conn.commit()
    conn.close()

    loaded, report_load = store.load_with_report(world.world_id)
    assert len(report_load.failures) == 1
    assert loaded.get_component("av-1", "health") is None

    # Saving the loaded world must NOT sweep the quarantined row:
    # A4's doctrine is that the original row stays untouched.
    store.save(loaded)
    rows = sqlite3.connect(path).execute(
        "SELECT COUNT(*) FROM components WHERE entity_id='av-1' AND component_type='health'"
    ).fetchone()
    assert rows[0] == 1

    # But deleting the entity drops the pin with it (stale-entity
    # sweep semantics): the row goes, the quarantine copy remains.
    loaded.remove_entity("av-1")
    store.save(loaded)
    rows = sqlite3.connect(path).execute(
        "SELECT COUNT(*) FROM components WHERE entity_id='av-1'"
    ).fetchone()
    assert rows[0] == 0
    assert len(store.quarantined_components(world.world_id)) == 1


# ---------------------------------------------------------------------------
# Correctness harness — every mutation path, incremental vs full
# ---------------------------------------------------------------------------


def test_correctness_harness_incremental_matches_full() -> None:
    world, tree = _build_world("harness_world")
    store_a, path_a = _temp_store()
    store_a.save(world)

    def step_avatar6(w: World, t: YggdrasilTree) -> None:
        w.create_entity(entity_id="av-6", tags={"npc", "guest"})
        w.add_component("av-6", NameComponent(entity_id="av-6", name="Guest"))
        w.add_component("av-6", HealthComponent(entity_id="av-6", hp=50.0))
        t.place_entity("av-6", location_id="dock")

    def step_damage(w: World, t: YggdrasilTree) -> None:
        health = w.get_component("av-1", "health")
        assert isinstance(health, HealthComponent)
        health.take_damage(40.0)

    def step_rename(w: World, t: YggdrasilTree) -> None:
        name = w.get_component("av-2", "name")
        assert isinstance(name, NameComponent)
        name.name = "Renamed Two"

    def step_move(w: World, t: YggdrasilTree) -> None:
        t.move_entity("av-3", location_id="dock")

    def step_tags(w: World, t: YggdrasilTree) -> None:
        w.tag_entity("av-4", "hero")
        w.untag_entity("av-4", "npc")

    def step_deactivate(w: World, t: YggdrasilTree) -> None:
        entity = w.get_entity("av-5")
        assert entity is not None
        entity.deactivate()

    def step_replace(w: World, t: YggdrasilTree) -> None:
        w.add_component("av-1", StatusComponent(entity_id="av-1", state="fighting"))
        w.add_component("av-1", StatusComponent(entity_id="av-1", state="resting"))

    def step_remove_component(w: World, t: YggdrasilTree) -> None:
        w.remove_component("av-2", "health")

    def step_remove_entity(w: World, t: YggdrasilTree) -> None:
        w.remove_entity("av-6")

    def step_world_rename(w: World, t: YggdrasilTree) -> None:
        w.world_name = "Harness Renamed"

    def step_touch(w: World, t: YggdrasilTree) -> None:
        health = w.get_component("av-4", "health")
        assert isinstance(health, HealthComponent)
        health.touch()

    steps = [
        step_avatar6, step_damage, step_rename, step_move, step_tags,
        step_deactivate, step_replace, step_remove_component,
        step_remove_entity, step_world_rename, step_touch,
    ]
    for step in steps:
        step(world, tree)
        store_a.save(world)
        # After EVERY incremental save, a reload must reproduce the
        # live world exactly — a lost mutation fails at its own step.
        reloaded = store_a.load(world.world_id)
        assert _fingerprint(reloaded) == _fingerprint(world), f"after {step.__name__}"
        assert reloaded.world_name == world.world_name

    # The reference: the same final world, written with a forced
    # full save into a fresh store. Table-for-table identical.
    store_b, path_b = _temp_store()
    store_b.save(world, full=True)
    assert _tables(path_a) == _tables(path_b)


# ---------------------------------------------------------------------------
# Live-rate load harness — 1 Hz presence churn + chat bursts (B7)
# ---------------------------------------------------------------------------

LIVE_ENTITIES = 1_000
LIVE_TICKS = 30
CHURN_PER_TICK = 10
BURST_EVERY_TICKS = 5
BURST_SIZE = 100


def _live_budget_ms() -> float:
    text = DOC.read_text(encoding="utf-8")
    m = re.search(r"```budgets\n(.*?)```", text, re.S)
    assert m, "performance-budgets.md lost its ```budgets block"
    budgets = {}
    for line in m.group(1).strip().splitlines():
        key, _, value = line.partition(":")
        budgets[key.strip()] = float(value.strip())
    assert "live_save_tick_ms" in budgets, "B7 budget missing from doc"
    return budgets["live_save_tick_ms"]


def _build_live_world() -> tuple[World, YggdrasilTree]:
    world = World(world_id="live_world", world_name="Live World")
    tree = YggdrasilTree(world)
    tree.create_zone(zone_id="z", name="Zone")
    tree.create_region(region_id="r", name="Region", parent_zone_id="z")
    tree.create_location(location_id="loc-a", name="A", parent_region_id="r")
    tree.create_location(location_id="loc-b", name="B", parent_region_id="r")
    for i in range(LIVE_ENTITIES):
        eid = f"av-{i:04d}"
        world.create_entity(entity_id=eid, tags={"avatar"})
        world.add_component(eid, NameComponent(entity_id=eid, name=f"Avatar {i}"))
        world.add_component(eid, HealthComponent(entity_id=eid, hp=100.0))
        world.add_component(eid, StatusComponent(entity_id=eid, state="idle"))
        tree.place_entity(eid, location_id="loc-a")
    return world, tree


def test_live_rate_harness_within_budget() -> None:
    store, _ = _temp_store()
    world, tree = _build_live_world()
    store.save(world)

    tick_times: list[float] = []
    total_components_written = 0
    total_entities_written = 0
    for tick in range(LIVE_TICKS):
        # 1 Hz presence churn: avatars move between locations.
        for i in range(CHURN_PER_TICK):
            eid = f"av-{(tick * CHURN_PER_TICK + i) % LIVE_ENTITIES:04d}"
            tree.move_entity(eid, location_id="loc-b" if tick % 2 == 0 else "loc-a")
        # Chat-burst-like writes: a burst of status changes.
        if tick % BURST_EVERY_TICKS == 0:
            for i in range(BURST_SIZE):
                eid = f"av-{i:04d}"
                world.add_component(
                    eid, StatusComponent(entity_id=eid, state=f"chatting-{tick}")
                )
        t0 = time.perf_counter()
        report = store.save_with_report(world)
        tick_times.append(time.perf_counter() - t0)
        total_components_written += report.components_written
        total_entities_written += report.entities_written

    median_ms = statistics.median(tick_times) * 1e3
    budget_ms = _live_budget_ms()
    assert median_ms <= budget_ms, (
        f"B7 RED: live-rate save tick median {median_ms:.1f}ms over "
        f"{LIVE_TICKS} ticks (1 Hz churn x{CHURN_PER_TICK} + bursts "
        f"x{BURST_SIZE} every {BURST_EVERY_TICKS} ticks, "
        f"{LIVE_ENTITIES} entities) exceeds the {budget_ms:.0f}ms "
        f"budget — finding, see docs/performance-budgets.md"
    )
    # Machine-independent bound: writes track the change set, not
    # the world. A full-save implementation would write
    # LIVE_TICKS x ~4,000 component rows (~120,000); the churn above
    # touches at most 3 rows per move (spatial + 2 containers, with
    # repeat moves of one container pair amortising) plus one row
    # per burst write.
    full_save_rows = LIVE_TICKS * LIVE_ENTITIES * 4
    assert total_components_written < full_save_rows // 20, (
        f"incremental writes crept toward full-save volume: "
        f"{total_components_written} component rows over {LIVE_TICKS} ticks"
    )
    assert total_entities_written == 0
    # Final state is exactly right after the whole run.
    reloaded = store.load(world.world_id)
    assert reloaded.entity_count() == world.entity_count()
    assert _fingerprint(reloaded) == _fingerprint(world)
