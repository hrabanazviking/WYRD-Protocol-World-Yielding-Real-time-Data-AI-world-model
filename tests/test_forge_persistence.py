"""Forge tests: verify-on-open wiring, schema-version constants, repair_memory_db.

Covers forge slices 12-15 (dawn run "Helheim Hardening — resilience weave"):
- slice 12: stores open via open_verified_state_db; a byte-tampered memory
  DB (single-byte flip inside a data page, 100-byte header intact) opens
  fresh with recovered=True and the corrupt bytes preserved under quarantine/.
- slice 13: each persistence module exposes CURRENT_SCHEMA_VERSION and the
  opened DB's PRAGMA user_version equals it.
- slice 14: repair_memory_db returns an honest report dict.
- slice 15: bond_store multi-statement writes are atomic (regression test:
  forcing the second statement of delete_edge to fail leaves zero rows
  deleted — the write paths were already fully transactional via the
  connection context manager, so this slice is a regression test, not a fix).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from wyrdforge.hardening.state_io import open_verified_state_db
from wyrdforge.models.bond import BondDomain, BondEdge, Vow
from wyrdforge.persistence import bond_store, memory_store, world_store
from wyrdforge.persistence.bond_store import PersistentBondStore
from wyrdforge.persistence.memory_store import PersistentMemoryStore, repair_memory_db
from wyrdforge.persistence.world_store import WorldStore
from wyrdforge.runtime.demo_seed import build_seed_fact

#: Byte offset of the single-byte flip used in the tamper test. Offset 105
#: sits inside page 1's b-tree cell header — past the 100-byte SQLite file
#: header (which stays intact) but inside a real data page, so
#: PRAGMA integrity_check reports corruption while the header still parses.
_TAMPER_OFFSET = 105


def _flip_db_byte(path: Path, offset: int = _TAMPER_OFFSET) -> tuple[bytes, bytes]:
    """Checkpoint WAL, then flip one byte at *offset*.

    Returns ``(pre_flip, tampered)`` — ``pre_flip`` is the exact byte
    content the file had immediately before the flip (post-checkpoint,
    so header counters are stable).
    """
    raw = sqlite3.connect(str(path))
    raw.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    raw.close()
    pre_flip = path.read_bytes()
    assert pre_flip[:16] == b"SQLite format 3\x00", "expected a real SQLite file"
    assert offset < len(pre_flip)
    data = bytearray(pre_flip)
    data[offset] ^= 0xFF
    tampered = bytes(data)
    path.write_bytes(tampered)
    return pre_flip, tampered


# ---------------------------------------------------------------------------
# Slice 12 — verify-on-open: byte-tampered DB opens fresh, bytes preserved
# ---------------------------------------------------------------------------

def test_tampered_memory_db_opens_fresh_with_recovered_true(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    store = PersistentMemoryStore(db_path)
    record = build_seed_fact()
    store.add(record)
    assert store.count() == 1

    pre_flip, tampered = _flip_db_byte(db_path)
    # The 100-byte SQLite file header is intact; exactly one byte inside
    # a data page was flipped.
    assert tampered[:100] == pre_flip[:100]
    assert sum(1 for a, b in zip(tampered, pre_flip) if a != b) == 1
    assert tampered[:16] == b"SQLite format 3\x00"

    conn, recovered = open_verified_state_db(
        db_path, current_version=memory_store.CURRENT_SCHEMA_VERSION
    )
    try:
        assert recovered is True
        # Fresh DB: stamped to current version, no records survived.
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == memory_store.CURRENT_SCHEMA_VERSION
    finally:
        conn.close()

    # The corrupt bytes were preserved under quarantine/, not deleted.
    quarantined = list((tmp_path / "quarantine").glob("memory-*.db"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == tampered

    # The store constructor now opens the fresh file without crashing.
    store2 = PersistentMemoryStore(db_path)
    assert store2.count() == 0
    assert store2.integrity_check() is True


def test_healthy_memory_db_opens_without_recovery(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    PersistentMemoryStore(db_path)
    conn, recovered = open_verified_state_db(
        db_path, current_version=memory_store.CURRENT_SCHEMA_VERSION
    )
    conn.close()
    assert recovered is False
    assert not (tmp_path / "quarantine").exists()


# ---------------------------------------------------------------------------
# Slice 13 — CURRENT_SCHEMA_VERSION constants stamped as user_version
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "module,store_cls,db_name",
    [
        (memory_store, PersistentMemoryStore, "memory.db"),
        (bond_store, PersistentBondStore, "bonds.db"),
        (world_store, WorldStore, "world.db"),
    ],
)
def test_user_version_matches_module_constant(
    tmp_path: Path, module, store_cls, db_name: str
) -> None:
    assert isinstance(module.CURRENT_SCHEMA_VERSION, int)
    assert module.CURRENT_SCHEMA_VERSION >= 1
    store_cls(tmp_path / db_name)
    raw = sqlite3.connect(str(tmp_path / db_name))
    try:
        version = raw.execute("PRAGMA user_version").fetchone()[0]
    finally:
        raw.close()
    assert version == module.CURRENT_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Slice 14 — repair_memory_db honest reporting
# ---------------------------------------------------------------------------

def test_repair_memory_db_healthy_reports_all_true(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    store = PersistentMemoryStore(db_path)
    store.add(build_seed_fact())
    report = repair_memory_db(db_path)
    assert set(report.keys()) == {"integrity_ok", "vacuumed", "reindexed"}
    assert report == {"integrity_ok": True, "vacuumed": True, "reindexed": True}
    # The DB is still fully usable afterwards.
    assert store.count() == 1


def test_repair_memory_db_garbage_file_reports_honestly(tmp_path: Path) -> None:
    db_path = tmp_path / "garbage.db"
    db_path.write_bytes(b"\x00\x01\x02not a database at all" * 64)
    report = repair_memory_db(db_path)  # must not raise
    assert set(report.keys()) == {"integrity_ok", "vacuumed", "reindexed"}
    assert all(isinstance(v, bool) for v in report.values())
    assert report["integrity_ok"] is False
    assert report["vacuumed"] is False
    assert report["reindexed"] is False


# ---------------------------------------------------------------------------
# Slice 15 — bond_store write atomicity regression test
# ---------------------------------------------------------------------------

def _edge(bond_id: str = "bond-001") -> BondEdge:
    return BondEdge(
        bond_id=bond_id,
        entity_a="user:volmarr",
        entity_b="persona:sigrid",
        domain=BondDomain.COMPANION,
    )


def _vow(bond_id: str = "bond-001", vow_id: str = "vow-001") -> Vow:
    return Vow(
        vow_id=vow_id,
        bond_id=bond_id,
        vow_text="I will stand by you through storm and fire.",
        vow_kind="loyalty",
        created_from_record_id="rec-001",
    )


def test_delete_edge_is_atomic_when_second_statement_fails(tmp_path: Path) -> None:
    """delete_edge runs 3 DELETEs (edges, vows, hurts) in one transaction.

    A trigger forces the *second* statement (DELETE FROM vows) to fail.
    Atomicity requires zero rows persisted as deleted: the edge and the
    vow must both still be there after the rollback.
    """
    db_path = tmp_path / "bonds.db"
    store = PersistentBondStore(db_path)
    store.save_edge(_edge())
    store.save_vow(_vow())
    assert store.count_edges() == 1
    assert store.count_vows() == 1

    raw = sqlite3.connect(str(db_path))
    raw.execute(
        "CREATE TRIGGER forge_atomicity_boom BEFORE DELETE ON vows "
        "BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
    )
    raw.commit()
    raw.close()

    with pytest.raises(sqlite3.Error):
        store.delete_edge("bond-001")

    # Nothing was deleted: the failed multi-statement write rolled back whole.
    assert store.load_edge("bond-001") is not None
    assert store.count_edges() == 1
    assert store.count_vows() == 1
    assert store.load_vow("vow-001") is not None


def test_delete_edge_still_deletes_all_rows_on_success(tmp_path: Path) -> None:
    """Sanity: without injected failure the cascade still deletes everything."""
    store = PersistentBondStore(tmp_path / "bonds.db")
    store.save_edge(_edge())
    store.save_vow(_vow())
    assert store.delete_edge("bond-001") is True
    assert store.count_edges() == 0
    assert store.count_vows() == 0
