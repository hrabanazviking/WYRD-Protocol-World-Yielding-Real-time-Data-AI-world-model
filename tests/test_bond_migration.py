"""Phase A2 — bond store schema v1 -> v2: the first real migration.

Before A2 the migration framework in ``hardening/state_io`` had never
run a real migration: every store sat at v1 and the 0 -> 1 transition
was stamp-only. A2 ships the bond store's 1 -> 2 migration, which
retrofits the Phase A1 foreign-key declarations
(``vows.bond_id`` / ``hurts.bond_id`` REFERENCES bond_edges) onto
existing v1 files via a table rebuild — ``CREATE TABLE IF NOT EXISTS``
cannot retrofit a declaration onto a table that already exists.

Pinned here, on real-shaped data:

- a genuine v1 file (pre-A1 schema, no FK declarations) opens through
  ``PersistentBondStore`` and is stamped ``user_version = 2``;
- the migration really ran (it is not stamp-only): the rebuilt tables
  carry the REFERENCES declarations afterwards, and a spy on the
  registered migration step proves ``_run_migrations`` called it;
- every legacy row survives, including orphan vow/hurt rows whose
  bond_id names no edge — preserved and reported in the log, never
  silently dropped;
- a migrated file then behaves exactly like a fresh v2 file: new
  orphan saves are refused at commit, normal edge+vow flow works,
  and ``delete_edge``'s cascade still commits cleanly.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

import pytest

from wyrdforge.models.bond import BondDomain, BondEdge, Hurt, Vow
from wyrdforge.persistence import bond_store
from wyrdforge.persistence.bond_store import (
    BOND_MIGRATIONS,
    CURRENT_SCHEMA_VERSION,
    PersistentBondStore,
)

# The genuine pre-A1 v1 schema: no FK declarations, no indexes baked
# into this fixture's DDL, user_version stamped 1. (Indexes existed in
# some v1 files and not others; the rebuild recreates them either way.)
_V1_SCHEMA = """
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
"""


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


def _hurt(bond_id: str = "bond-001", hurt_id: str = "hurt-001") -> Hurt:
    return Hurt(
        hurt_id=hurt_id,
        bond_id=bond_id,
        source_event_id="evt-001",
        hurt_kind="neglect",
        severity="low",
    )


def _make_v1_db(path: Path, *, with_orphans: bool = True) -> None:
    """Write a real-shaped v1 bond DB by hand (raw sqlite, old schema).

    Rows are inserted exactly as the store itself would write them —
    ``data_json`` is the model's own JSON — so the migrated file is
    indistinguishable from a file a pre-A2 install produced.
    """
    edge = _edge()
    vow = _vow()
    hurt = _hurt()
    orphan_vow = _vow(bond_id="ghost-bond", vow_id="vow-orphan")
    orphan_hurt = _hurt(bond_id="ghost-bond", hurt_id="hurt-orphan")
    raw = sqlite3.connect(str(path))
    try:
        raw.executescript(_V1_SCHEMA)
        raw.execute("PRAGMA user_version=1")
        raw.execute(
            "INSERT INTO bond_edges VALUES (?,?,?,?,?,?,?,?)",
            (
                edge.bond_id,
                edge.entity_a,
                edge.entity_b,
                edge.domain.value,
                edge.status.value,
                edge.model_dump_json(),
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        raw.execute(
            "INSERT INTO vows VALUES (?,?,?)",
            (vow.vow_id, vow.bond_id, vow.model_dump_json()),
        )
        raw.execute(
            "INSERT INTO hurts VALUES (?,?,?)",
            (hurt.hurt_id, hurt.bond_id, hurt.model_dump_json()),
        )
        if with_orphans:
            raw.execute(
                "INSERT INTO vows VALUES (?,?,?)",
                (orphan_vow.vow_id, orphan_vow.bond_id, orphan_vow.model_dump_json()),
            )
            raw.execute(
                "INSERT INTO hurts VALUES (?,?,?)",
                (
                    orphan_hurt.hurt_id,
                    orphan_hurt.bond_id,
                    orphan_hurt.model_dump_json(),
                ),
            )
        raw.commit()
    finally:
        raw.close()


def _user_version(path: Path) -> int:
    raw = sqlite3.connect(str(path))
    try:
        return int(raw.execute("PRAGMA user_version").fetchone()[0])
    finally:
        raw.close()


def _table_sql(path: Path, table: str) -> str:
    raw = sqlite3.connect(str(path))
    try:
        row = raw.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
    finally:
        raw.close()
    assert row is not None
    return str(row[0])


# ---------------------------------------------------------------------------
# The migration lands: version, schema, and every row
# ---------------------------------------------------------------------------

def test_v1_db_is_migrated_to_v2_with_fk_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    _make_v1_db(db_path, with_orphans=False)
    assert _user_version(db_path) == 1
    assert "REFERENCES" not in _table_sql(db_path, "vows")

    store = PersistentBondStore(db_path)

    assert CURRENT_SCHEMA_VERSION == 2
    assert _user_version(db_path) == 2
    # Not stamp-only: the rebuilt tables really carry the FK schema.
    for table in ("vows", "hurts"):
        sql = _table_sql(db_path, table)
        assert "REFERENCES bond_edges(bond_id)" in sql
        assert "DEFERRABLE INITIALLY DEFERRED" in sql
    assert store.count_edges() == 1
    assert store.count_vows() == 1
    assert store.count_hurts() == 1
    assert store.load_vow("vow-001") is not None
    assert store.integrity_check()


def test_run_migrations_step_is_actually_exercised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A spy wrapped around the registered 1 -> 2 step proves
    ``_run_migrations`` invoked it for a v1 file (not just stamped)."""
    db_path = tmp_path / "legacy.db"
    _make_v1_db(db_path, with_orphans=False)
    calls: list[int] = []
    real_step = BOND_MIGRATIONS[1]

    def spy(conn: sqlite3.Connection) -> None:
        calls.append(1)
        real_step(conn)

    monkeypatch.setitem(BOND_MIGRATIONS, 1, spy)
    PersistentBondStore(db_path)
    assert calls == [1]
    assert _user_version(db_path) == 2


def test_migration_is_not_rerun_on_a_v2_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "legacy.db"
    _make_v1_db(db_path, with_orphans=False)
    PersistentBondStore(db_path)
    calls: list[int] = []
    real_step = BOND_MIGRATIONS[1]

    def spy(conn: sqlite3.Connection) -> None:
        calls.append(1)
        real_step(conn)

    monkeypatch.setitem(BOND_MIGRATIONS, 1, spy)
    PersistentBondStore(db_path)  # already v2: no migration step runs
    assert calls == []


# ---------------------------------------------------------------------------
# Orphans: preserved and reported, never dropped
# ---------------------------------------------------------------------------

def test_orphan_rows_are_preserved_and_reported(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    db_path = tmp_path / "legacy.db"
    _make_v1_db(db_path, with_orphans=True)

    with caplog.at_level(logging.WARNING, logger="wyrdforge.persistence.bond_store"):
        store = PersistentBondStore(db_path)

    assert _user_version(db_path) == 2
    # Every row survived, orphans included, and is readable via the store.
    assert store.count_edges() == 1
    assert store.count_vows() == 2
    assert store.count_hurts() == 2
    orphan_vow = store.load_vow("vow-orphan")
    assert orphan_vow is not None
    assert orphan_vow.bond_id == "ghost-bond"
    orphan_hurt = store.load_hurt("hurt-orphan")
    assert orphan_hurt is not None
    assert orphan_hurt.bond_id == "ghost-bond"
    assert len(store.vows_for_bond("ghost-bond")) == 1
    assert len(store.hurts_for_bond("ghost-bond")) == 1
    # ... and the preservation was reported, naming the orphans.
    warnings = [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.WARNING
        and r.name == "wyrdforge.persistence.bond_store"
    ]
    assert len(warnings) == 1
    assert "preserved 1 orphan vow" in warnings[0]
    assert "1 orphan hurt" in warnings[0]
    assert "vow-orphan" in warnings[0]
    assert "hurt-orphan" in warnings[0]
    assert "never dropped" in warnings[0]


# ---------------------------------------------------------------------------
# A migrated file behaves exactly like a fresh v2 file
# ---------------------------------------------------------------------------

def test_migrated_db_refuses_new_orphans_and_flows_normally(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "legacy.db"
    _make_v1_db(db_path, with_orphans=True)
    store = PersistentBondStore(db_path)

    # New orphan saves are refused at commit, legacy orphans or not.
    with pytest.raises(sqlite3.IntegrityError):
        store.save_vow(_vow(bond_id="no-such-bond", vow_id="vow-new-orphan"))
    with pytest.raises(sqlite3.IntegrityError):
        store.save_hurt(_hurt(bond_id="no-such-bond", hurt_id="hurt-new-orphan"))
    # The refusals did not disturb the preserved legacy rows.
    assert store.count_vows() == 2
    assert store.count_hurts() == 2

    # Normal flow works on the migrated file...
    store.save_edge(_edge("bond-002"))
    store.save_vow(_vow(bond_id="bond-002", vow_id="vow-002"))
    store.save_hurt(_hurt(bond_id="bond-002", hurt_id="hurt-002"))
    assert store.count_edges() == 2

    # ...including delete_edge's one-transaction cascade.
    assert store.delete_edge("bond-002") is True
    assert store.vows_for_bond("bond-002") == []
    assert store.hurts_for_bond("bond-002") == []
    # The pre-existing bond and the legacy orphans are untouched.
    assert store.load_edge("bond-001") is not None
    assert store.load_vow("vow-orphan") is not None


def test_fresh_db_is_created_directly_at_v2_with_fk_schema(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "fresh.db"
    store = PersistentBondStore(db_path)
    assert _user_version(db_path) == 2
    for table in ("vows", "hurts"):
        assert "REFERENCES bond_edges(bond_id)" in _table_sql(db_path, table)
    with pytest.raises(sqlite3.IntegrityError):
        store.save_vow(_vow(bond_id="no-such-bond"))
    store.save_edge(_edge())
    store.save_vow(_vow())
    assert store.count_vows() == 1


def test_migrated_data_round_trips_through_json_payloads(
    tmp_path: Path,
) -> None:
    """The rebuild copies rows verbatim: payloads survive byte-faithful
    (checked at the model level the store actually serves)."""
    db_path = tmp_path / "legacy.db"
    _make_v1_db(db_path, with_orphans=True)
    store = PersistentBondStore(db_path)
    edge = store.load_edge("bond-001")
    assert edge is not None
    assert edge.entity_a == "user:volmarr"
    assert json.loads(store.load_vow("vow-001").model_dump_json())["vow_kind"] == "loyalty"  # type: ignore[union-attr]
    # bond_store module constant is what the file was stamped with.
    assert bond_store.CURRENT_SCHEMA_VERSION == 2
