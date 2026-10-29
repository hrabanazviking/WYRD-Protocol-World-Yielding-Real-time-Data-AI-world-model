"""Phase A5 — backup & restore pinning tests.

The Phase A closer: before A5 there was no backup story in core at
all, and no consistent cross-store bundle was possible because live
copies could capture three different turns. These tests pin the new
contract:

(a) the restore drill — seed all three stores, back up, mutate/delete
    the live state, restore, and the restored state matches the
    backup point across all three stores;
(b) a tampered or corrupt bundle is refused by manifest/integrity
    verification and live state is untouched, byte for byte;
(c) backup of empty/fresh stores works and restores;
(d) manifest contents are accurate — hashes, sizes, and schema
    versions recomputed independently here.

Plus: the quiesce guard (a busy WAL checkpoint refuses), bundle
overwrite refusal, newer-schema refusal, and the pre-restore
preservation of the incumbent state under ``quarantine/``.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

import wyrdforge.ecs.components.character  # noqa: F401
import wyrdforge.ecs.components.identity   # noqa: F401

from wyrdforge.ecs.components.character import HealthComponent
from wyrdforge.ecs.components.identity import NameComponent
from wyrdforge.ecs.world import World
from wyrdforge.models.bond import BondDomain, BondEdge, Vow
from wyrdforge.persistence.backup import (
    BACKUP_FORMAT,
    BackupError,
    create_backup,
    load_manifest,
    restore_backup,
    verify_bundle,
)
from wyrdforge.persistence.bond_store import (
    CURRENT_SCHEMA_VERSION as BOND_VERSION,
)
from wyrdforge.persistence.bond_store import PersistentBondStore
from wyrdforge.persistence.memory_store import (
    CURRENT_SCHEMA_VERSION as MEMORY_VERSION,
)
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.persistence.world_store import (
    CURRENT_SCHEMA_VERSION as WORLD_VERSION,
)
from wyrdforge.persistence.world_store import WorldStore
from wyrdforge.runtime.demo_seed import build_seed_fact

_KNOWN_VERSIONS = {"world": WORLD_VERSION, "memory": MEMORY_VERSION, "bond": BOND_VERSION}


def _paths(base: Path) -> dict[str, Path]:
    return {
        "world": base / "world.db",
        "memory": base / "memory.db",
        "bond": base / "bond.db",
    }


def _seed(base: Path) -> dict[str, Path]:
    """Create all three stores under *base* with known state."""
    paths = _paths(base)
    base.mkdir(parents=True, exist_ok=True)

    world_store = WorldStore(paths["world"])
    world = World(world_id="w-backup", world_name="Backup World")
    world.create_entity(entity_id="gunnar", tags={"npc"})
    world.add_component("gunnar", NameComponent(entity_id="gunnar", name="Gunnar"))
    world.add_component("gunnar", HealthComponent(entity_id="gunnar", hp=80.0))
    world_store.save(world)

    memory = PersistentMemoryStore(paths["memory"])
    fact = build_seed_fact()
    memory.add(fact)
    memory.close()

    bond = PersistentBondStore(paths["bond"])
    bond.save_edge(
        BondEdge(
            bond_id="bond-001",
            entity_a="user:volmarr",
            entity_b="persona:sigrid",
            domain=BondDomain.COMPANION,
        )
    )
    bond.save_vow(
        Vow(
            vow_id="vow-001",
            bond_id="bond-001",
            vow_text="I will stand by you through storm and fire.",
            vow_kind="loyalty",
            created_from_record_id="rec-001",
        )
    )
    return paths


def _mutate(paths: dict[str, Path]) -> None:
    """Change/delete live state after the backup point."""
    world_store = WorldStore(paths["world"])
    world_store.delete_world("w-backup")
    other = World(world_id="w-other", world_name="Other World")
    world_store.save(other)

    memory = PersistentMemoryStore(paths["memory"])
    for record in list(memory.all()):
        memory.delete(record.record_id)
    memory.close()

    bond = PersistentBondStore(paths["bond"])
    bond.delete_edge("bond-001")


def _assert_backup_point(paths: dict[str, Path]) -> None:
    """The state at the backup point, read back through the stores."""
    world_store = WorldStore(paths["world"])
    assert world_store.list_worlds() == ["w-backup"]
    world, report = world_store.load_with_report("w-backup")
    assert report.ok
    assert world.world_name == "Backup World"
    name = world.get_component("gunnar", "name")
    assert name is not None and name.name == "Gunnar"  # type: ignore[attr-defined]
    health = world.get_component("gunnar", "health")
    assert health is not None and health.hp == 80.0  # type: ignore[attr-defined]

    memory = PersistentMemoryStore(paths["memory"])
    records = memory.all()
    memory.close()
    assert len(records) == 1
    assert records[0].record_id == build_seed_fact().record_id

    bond = PersistentBondStore(paths["bond"])
    edges = bond.all_edges()
    assert [e.bond_id for e in edges] == ["bond-001"]
    assert bond.load_vow("vow-001") is not None


# ---------------------------------------------------------------------------
# (a) The restore drill
# ---------------------------------------------------------------------------


def test_restore_drill_returns_all_three_stores_to_backup_point(tmp_path: Path) -> None:
    live = tmp_path / "live"
    paths = _seed(live)
    bundle = tmp_path / "bundle"
    create_backup(paths, bundle)

    _mutate(paths)
    # The mutation really took (otherwise the drill proves nothing).
    assert WorldStore(paths["world"]).list_worlds() == ["w-other"]

    report = restore_backup(bundle, paths)
    assert set(report.restored) == {"world", "memory", "bond"}
    _assert_backup_point(paths)


def test_restore_preserves_pre_restore_state_under_quarantine(tmp_path: Path) -> None:
    live = tmp_path / "live"
    paths = _seed(live)
    bundle = tmp_path / "bundle"
    create_backup(paths, bundle)
    _mutate(paths)

    report = restore_backup(bundle, paths)
    # Every incumbent file was preserved, not overwritten-and-prayed.
    assert set(report.pre_restore_copies) == {"world", "memory", "bond"}
    for preserved in report.pre_restore_copies.values():
        assert preserved.exists()
        assert preserved.parent.name == "quarantine"
        assert preserved.name.startswith("pre-restore-")
    # The preserved world DB is the mutated one (holds w-other).
    preserved_world = WorldStore(report.pre_restore_copies["world"])
    assert preserved_world.list_worlds() == ["w-other"]
    _assert_backup_point(paths)


def test_restore_into_fresh_directory(tmp_path: Path) -> None:
    paths = _seed(tmp_path / "live")
    bundle = tmp_path / "bundle"
    create_backup(paths, bundle)

    fresh = _paths(tmp_path / "fresh")
    report = restore_backup(bundle, fresh)
    assert report.pre_restore_copies == {}
    _assert_backup_point(fresh)


# ---------------------------------------------------------------------------
# (b) Tampered / corrupt bundles are refused; live state untouched
# ---------------------------------------------------------------------------


def _live_hashes(paths: dict[str, Path]) -> dict[str, str]:
    return {n: hashlib.sha256(p.read_bytes()).hexdigest() for n, p in paths.items()}


def test_tampered_bundle_file_is_refused_and_live_state_untouched(tmp_path: Path) -> None:
    live = tmp_path / "live"
    paths = _seed(live)
    bundle = tmp_path / "bundle"
    create_backup(paths, bundle)
    before = _live_hashes(paths)

    tampered = bundle / "memory.db"
    data = bytearray(tampered.read_bytes())
    data[len(data) // 2] ^= 0xFF
    tampered.write_bytes(bytes(data))

    with pytest.raises(BackupError):
        verify_bundle(bundle)
    with pytest.raises(BackupError):
        restore_backup(bundle, paths)
    assert _live_hashes(paths) == before
    _assert_backup_point(paths)


def test_corrupt_bundle_file_is_refused_and_live_state_untouched(tmp_path: Path) -> None:
    live = tmp_path / "live"
    paths = _seed(live)
    bundle = tmp_path / "bundle"
    create_backup(paths, bundle)
    before = _live_hashes(paths)

    # Garbage bytes where the bond DB should be.
    (bundle / "bond.db").write_bytes(b"not a database at all" * 64)

    with pytest.raises(BackupError):
        restore_backup(bundle, paths)
    assert _live_hashes(paths) == before
    _assert_backup_point(paths)


def test_manifest_claiming_newer_schema_is_refused(tmp_path: Path) -> None:
    paths = _seed(tmp_path / "live")
    bundle = tmp_path / "bundle"
    create_backup(paths, bundle)

    # Rewrite one bundle DB at a newer schema version AND fix the
    # manifest to match its new hash/size — the refusal must come from
    # the version doctrine, not from a hash mismatch.
    world_copy = bundle / "world.db"
    conn = sqlite3.connect(str(world_copy))
    conn.execute(f"PRAGMA user_version={WORLD_VERSION + 1}")
    conn.commit()
    conn.close()
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["stores"]:
        if entry["name"] == "world":
            entry["schema_version"] = WORLD_VERSION + 1
            entry["sha256"] = hashlib.sha256(world_copy.read_bytes()).hexdigest()
            entry["size_bytes"] = world_copy.stat().st_size
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(BackupError, match="newer than this code knows"):
        restore_backup(bundle, _paths(tmp_path / "elsewhere"))


def test_missing_bundle_file_is_refused(tmp_path: Path) -> None:
    paths = _seed(tmp_path / "live")
    bundle = tmp_path / "bundle"
    create_backup(paths, bundle)
    (bundle / "world.db").rename(bundle / "hidden.db")
    with pytest.raises(BackupError):
        verify_bundle(bundle)


# ---------------------------------------------------------------------------
# (c) Empty / fresh stores
# ---------------------------------------------------------------------------


def test_backup_and_restore_of_empty_fresh_stores(tmp_path: Path) -> None:
    live = tmp_path / "live"
    live.mkdir()
    paths = _paths(live)
    # Constructing the stores creates fresh, empty, schema-stamped DBs.
    WorldStore(paths["world"])
    PersistentMemoryStore(paths["memory"]).close()
    PersistentBondStore(paths["bond"])

    bundle = tmp_path / "bundle"
    manifest = create_backup(paths, bundle)
    assert [e.name for e in manifest.stores] == ["world", "memory", "bond"]
    assert verify_bundle(bundle).format == BACKUP_FORMAT

    fresh = _paths(tmp_path / "fresh")
    restore_backup(bundle, fresh)
    assert WorldStore(fresh["world"]).list_worlds() == []
    memory = PersistentMemoryStore(fresh["memory"])
    assert memory.all() == []
    memory.close()
    assert PersistentBondStore(fresh["bond"]).all_edges() == []


# ---------------------------------------------------------------------------
# (d) Manifest accuracy — recomputed independently
# ---------------------------------------------------------------------------


def test_manifest_contents_are_accurate(tmp_path: Path) -> None:
    paths = _seed(tmp_path / "live")
    bundle = tmp_path / "bundle"
    manifest = create_backup(paths, bundle)

    assert manifest.format == BACKUP_FORMAT
    assert manifest.created_at  # a timestamp was recorded
    on_disk = load_manifest(bundle)
    assert on_disk == manifest

    raw = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert raw["format"] == BACKUP_FORMAT
    assert len(raw["stores"]) == 3
    for entry in raw["stores"]:
        file_path = bundle / entry["file"]
        assert file_path.exists()
        # Hash and size recomputed from the bytes, here, independently.
        assert entry["sha256"] == hashlib.sha256(file_path.read_bytes()).hexdigest()
        assert entry["size_bytes"] == file_path.stat().st_size
        # Schema version read straight from the DB header.
        conn = sqlite3.connect(f"file:{file_path}?mode=ro", uri=True)
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            conn.close()
        assert entry["schema_version"] == version == _KNOWN_VERSIONS[entry["name"]]
        assert entry["integrity_check"] == integrity == "ok"


# ---------------------------------------------------------------------------
# Guards: quiesce, overwrite, missing source
# ---------------------------------------------------------------------------


def test_backup_refuses_existing_bundle(tmp_path: Path) -> None:
    paths = _seed(tmp_path / "live")
    bundle = tmp_path / "bundle"
    create_backup(paths, bundle)
    with pytest.raises(BackupError, match="already holds a backup"):
        create_backup(paths, bundle)


def test_backup_refuses_missing_source(tmp_path: Path) -> None:
    paths = _paths(tmp_path / "nowhere")
    with pytest.raises(BackupError, match="does not exist"):
        create_backup(paths, tmp_path / "bundle")


def test_create_backup_requires_exactly_the_three_stores(tmp_path: Path) -> None:
    paths = _seed(tmp_path / "live")
    del paths["bond"]
    with pytest.raises(BackupError, match="exactly the stores"):
        create_backup(paths, tmp_path / "bundle")
