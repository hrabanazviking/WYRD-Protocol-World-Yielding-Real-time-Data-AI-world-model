"""Phase A persistence hardening pack — pinning tests.

Before this pack, the three SQLite state stores opened connections by
hand and had drifted apart (WYRD advancement roadmap §9 A1, evidence
in roadmap doc §2.1):

- durability rested on SQLite's unpinned ``synchronous`` default —
  zero ``PRAGMA synchronous`` anywhere in the tree;
- the bond store never enabled ``foreign_keys`` and its schema
  declared no FK for vows/hurts -> bond_edges;
- busy timeouts disagreed (world/bond: connect timeout only; memory:
  connect timeout 10 s contradicted by PRAGMA busy_timeout=5000).

These tests pin the unified behaviour: every store connection comes
from ``hardening.state_io.connect_state_db`` and carries WAL +
synchronous=FULL + foreign_keys=ON + the unified busy timeout, and
the bond store enforces its declared references.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from wyrdforge.hardening.state_io import (
    STATE_BUSY_TIMEOUT_MS,
    connect_state_db,
    open_state_db,
)
from wyrdforge.models.bond import BondDomain, BondEdge, Hurt, Vow
from wyrdforge.persistence.bond_store import PersistentBondStore
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.persistence.world_store import WorldStore


def _pragma(conn: sqlite3.Connection, name: str):
    return conn.execute(f"PRAGMA {name}").fetchone()[0]


def _assert_hardened(conn: sqlite3.Connection) -> None:
    assert _pragma(conn, "journal_mode") == "wal"
    assert _pragma(conn, "synchronous") == 2  # FULL, pinned — never the default
    assert _pragma(conn, "foreign_keys") == 1
    assert _pragma(conn, "busy_timeout") == STATE_BUSY_TIMEOUT_MS


# ---------------------------------------------------------------------------
# The factory itself
# ---------------------------------------------------------------------------

def test_factory_applies_the_pack(tmp_path: Path) -> None:
    conn = connect_state_db(tmp_path / "factory.db")
    try:
        _assert_hardened(conn)
    finally:
        conn.close()


def test_open_state_db_connections_are_hardened(tmp_path: Path) -> None:
    """The guarded-open path every store's schema init uses."""
    conn = open_state_db(tmp_path / "guarded.db", current_version=1)
    try:
        _assert_hardened(conn)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Every store's operational connections
# ---------------------------------------------------------------------------

def test_world_store_connections_are_hardened(tmp_path: Path) -> None:
    store = WorldStore(tmp_path / "world.db")
    with store._connect() as conn:
        _assert_hardened(conn)


def test_bond_store_connections_are_hardened(tmp_path: Path) -> None:
    store = PersistentBondStore(tmp_path / "bonds.db")
    with store._connect() as conn:
        _assert_hardened(conn)


def test_memory_store_connections_are_hardened(tmp_path: Path) -> None:
    store = PersistentMemoryStore(tmp_path / "memory.db")
    try:
        _assert_hardened(store._connect())
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Bond store: the declared references are enforced
# ---------------------------------------------------------------------------

def _edge(bond_id: str = "bond-001") -> BondEdge:
    return BondEdge(
        bond_id=bond_id,
        entity_a="user:volmarr",
        entity_b="persona:sigrid",
        domain=BondDomain.COMPANION,
    )


def _vow(bond_id: str = "bond-001") -> Vow:
    return Vow(
        vow_id="vow-001",
        bond_id=bond_id,
        vow_text="I will stand by you through storm and fire.",
        vow_kind="loyalty",
        created_from_record_id="rec-001",
    )


def _hurt(bond_id: str = "bond-001") -> Hurt:
    return Hurt(
        hurt_id="hurt-001",
        bond_id=bond_id,
        source_event_id="evt-001",
        hurt_kind="neglect",
        severity="low",
    )


def test_orphan_vow_is_refused(tmp_path: Path) -> None:
    """A vow naming a bond that does not exist can no longer be
    silently stored — the deferred FK fires at the save's commit."""
    store = PersistentBondStore(tmp_path / "bonds.db")
    with pytest.raises(sqlite3.IntegrityError):
        store.save_vow(_vow("no-such-bond"))
    assert store.count_vows() == 0


def test_orphan_hurt_is_refused(tmp_path: Path) -> None:
    store = PersistentBondStore(tmp_path / "bonds.db")
    with pytest.raises(sqlite3.IntegrityError):
        store.save_hurt(_hurt("no-such-bond"))
    assert store.count_hurts() == 0


def test_vow_with_edge_saves_and_delete_edge_clears_children(
    tmp_path: Path,
) -> None:
    """The deferred FK keeps delete_edge's one-transaction cascade
    (edge, then vows, then hurts) working: the check lands at commit,
    when no orphans remain."""
    store = PersistentBondStore(tmp_path / "bonds.db")
    store.save_edge(_edge())
    store.save_vow(_vow())
    store.save_hurt(_hurt())
    assert store.delete_edge("bond-001") is True
    assert store.count_vows() == 0
    assert store.count_hurts() == 0


# ---------------------------------------------------------------------------
# Backwards compatibility: pre-hardening v1 bond DBs still open
# ---------------------------------------------------------------------------

_PRE_A1_BOND_SCHEMA = """
CREATE TABLE bond_edges (
    bond_id     TEXT PRIMARY KEY,
    entity_a    TEXT NOT NULL,
    entity_b    TEXT NOT NULL,
    domain      TEXT NOT NULL,
    status      TEXT NOT NULL,
    data_json   TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE vows (
    vow_id      TEXT PRIMARY KEY,
    bond_id     TEXT NOT NULL,
    data_json   TEXT NOT NULL
);
CREATE TABLE hurts (
    hurt_id     TEXT PRIMARY KEY,
    bond_id     TEXT NOT NULL,
    data_json   TEXT NOT NULL
);
PRAGMA user_version=1;
"""


def test_pre_hardening_bond_db_still_opens(tmp_path: Path) -> None:
    """A v1 bond DB written before the pack has no FK declarations
    (CREATE TABLE IF NOT EXISTS does not retrofit them). It must keep
    opening and serving its rows. Since Phase A2 that open runs the
    real v1 -> v2 migration, which rebuilds vows/hurts with the FK
    schema (see tests/test_bond_migration.py); this test pins that
    the A1-era file still opens and serves either way."""
    db_path = tmp_path / "legacy_bonds.db"
    raw = sqlite3.connect(str(db_path))
    raw.executescript(_PRE_A1_BOND_SCHEMA)
    raw.close()

    store = PersistentBondStore(db_path)
    store.save_edge(_edge())
    store.save_vow(_vow())
    store.save_hurt(_hurt())
    assert store.count_edges() == 1
    assert store.count_vows() == 1
    assert store.count_hurts() == 1
    assert store.integrity_check()
