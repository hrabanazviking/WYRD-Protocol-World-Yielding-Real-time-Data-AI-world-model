"""SQLite persistence for BondEdge, Vow, and Hurt records.

BondGraphService is intentionally kept in-memory (fast, stateful).
PersistentBondStore is the durability layer: call it after every
mutating BondGraphService operation to keep disk in sync, and call
``load_into_service()`` on startup to restore prior state.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from wyrdforge.models.bond import BondEdge, Hurt, Vow
from wyrdforge.hardening.state_io import connect_state_db, open_verified_state_db

log = logging.getLogger(__name__)

#: Schema version stamped as ``PRAGMA user_version`` on the bond DB.
#: Bump when _SCHEMA gains a table/column, and add a forward migration.
#:
#: History:
#: - v1: original schema. As first shipped, ``vows``/``hurts`` declared
#:   no foreign key at all; the Phase A1 hardening pack added the FK
#:   declarations to ``_SCHEMA``, but ``CREATE TABLE IF NOT EXISTS``
#:   does not retrofit them onto database files that already exist.
#: - v2 (Phase A2, first real migration): the v1 -> v2 migration in
#:   :data:`BOND_MIGRATIONS` rebuilds ``vows``/``hurts`` on existing
#:   files so every bond DB — fresh or migrated — carries the
#:   ``REFERENCES bond_edges(bond_id) DEFERRABLE INITIALLY DEFERRED``
#:   declarations and enforces them.
CURRENT_SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bond_edges (
    bond_id     TEXT PRIMARY KEY,
    entity_a    TEXT NOT NULL,
    entity_b    TEXT NOT NULL,
    domain      TEXT NOT NULL,
    status      TEXT NOT NULL,
    data_json   TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vows (
    vow_id      TEXT PRIMARY KEY,
    bond_id     TEXT NOT NULL REFERENCES bond_edges(bond_id)
                DEFERRABLE INITIALLY DEFERRED,
    data_json   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hurts (
    hurt_id     TEXT PRIMARY KEY,
    bond_id     TEXT NOT NULL REFERENCES bond_edges(bond_id)
                DEFERRABLE INITIALLY DEFERRED,
    data_json   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_vows_bond   ON vows(bond_id);
CREATE INDEX IF NOT EXISTS idx_hurts_bond  ON hurts(bond_id);
"""

# ---------------------------------------------------------------------------
# Migrations (Phase A2 — the migration framework's first real migration)
# ---------------------------------------------------------------------------

#: Rebuilt-table DDL for the v1 -> v2 migration, keyed by child table:
#: (primary-key column, CREATE TABLE statement for the ``<table>_new``
#: staging table). The definitions are exactly the v2 ``_SCHEMA``
#: definitions for ``vows``/``hurts``, FK declarations included.
_V2_CHILD_TABLES: dict[str, tuple[str, str]] = {
    "vows": (
        "vow_id",
        """
        CREATE TABLE vows_new (
            vow_id      TEXT PRIMARY KEY,
            bond_id     TEXT NOT NULL REFERENCES bond_edges(bond_id)
                        DEFERRABLE INITIALLY DEFERRED,
            data_json   TEXT NOT NULL
        )
        """,
    ),
    "hurts": (
        "hurt_id",
        """
        CREATE TABLE hurts_new (
            hurt_id     TEXT PRIMARY KEY,
            bond_id     TEXT NOT NULL REFERENCES bond_edges(bond_id)
                        DEFERRABLE INITIALLY DEFERRED,
            data_json   TEXT NOT NULL
        )
        """,
    ),
}


def _orphan_rows(
    conn: sqlite3.Connection, table: str, pk_column: str, has_parent: bool
) -> list[tuple[str, str]]:
    """(pk, bond_id) pairs in *table* whose bond_id has no parent edge."""
    if has_parent:
        rows = conn.execute(
            f"SELECT {pk_column}, bond_id FROM {table} "  # noqa: S608 - fixed names
            "WHERE bond_id NOT IN (SELECT bond_id FROM bond_edges) "
            f"ORDER BY {pk_column}"
        ).fetchall()
    else:
        # No parent table at all: every child row is an orphan by
        # definition (cannot happen on a real v1 file; defensive only).
        rows = conn.execute(
            f"SELECT {pk_column}, bond_id FROM {table} ORDER BY {pk_column}"  # noqa: S608
        ).fetchall()
    return [(str(r[0]), str(r[1])) for r in rows]


def _migrate_bond_1_to_2(conn: sqlite3.Connection) -> None:
    """Migrate a bond DB from schema v1 to v2: retrofit the FK schema.

    ``vows``/``hurts`` in a genuine v1 file declare no foreign key, and
    ``CREATE TABLE IF NOT EXISTS`` never alters an existing table, so
    the only way to give existing files the v2 declarations is the
    standard SQLite table rebuild: create the table anew with the FK
    schema, copy every row, drop the old table, rename, recreate the
    index. ``bond_edges`` itself is unchanged by v2 and is not rebuilt.

    Orphan policy (honesty rule, Phase A2): a legacy v1 file may hold
    vow/hurt rows whose ``bond_id`` names no edge — silently legal
    before A1. Those rows are the user's data: they are **preserved**
    verbatim and **reported** (counted and named in a warning log),
    never silently dropped. Copying them into an FK table is the
    delicate part:

    - With ``foreign_keys=ON`` and the FK ``INITIALLY DEFERRED``, the
      copy inserts would pass but the migration's COMMIT would fail,
      aborting the whole migration (and quarantining a healthy file).
    - So the rebuild runs in its own transaction with
      ``PRAGMA foreign_keys=OFF`` (the pragma is a no-op inside a
      transaction, so it is set *before* ``BEGIN``), and that
      transaction is committed *while enforcement is still off*.
      Enforcement is restored immediately afterwards, before this
      function returns, so the version stamp committed by
      ``state_io._run_migrations`` and every later store transaction
      run fully enforced.
    - Why preserved orphans do not then poison the file: SQLite checks
      a deferred FK at commit only for rows a transaction touched.
      Rows committed while enforcement was off are not re-checked by
      later, unrelated transactions (verified against SQLite 3.45) —
      a migrated file serves its legacy orphans for reading, accepts
      normal edge/vow writes, still cascades ``delete_edge``, and
      refuses any *new* orphan save at commit, exactly like a fresh
      v2 file.

    Fresh DBs: ``open_state_db`` runs this step on the 0 -> 2 chain
    for a brand-new file whose tables do not exist yet; with no child
    tables present there is nothing to rebuild and this is a no-op —
    ``_SCHEMA`` then creates the tables directly at v2.
    """
    existing = {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    child_tables = [t for t in _V2_CHILD_TABLES if t in existing]
    if not child_tables:
        return  # fresh DB (or no bond tables yet): _SCHEMA creates v2

    has_parent = "bond_edges" in existing
    orphans: dict[str, list[tuple[str, str]]] = {
        table: _orphan_rows(conn, table, _V2_CHILD_TABLES[table][0], has_parent)
        for table in child_tables
    }

    # foreign_keys is a no-op inside a transaction; the caller
    # (_run_migrations on a fresh connection) is not in one, but guard
    # anyway — if the pragma did not take, rebuilding with enforcement
    # on would break on the first legacy orphan at commit time.
    conn.execute("PRAGMA foreign_keys=OFF")
    if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 0:
        raise RuntimeError(
            "bond migration v1->v2: could not disable foreign_keys "
            "outside a transaction; refusing to rebuild"
        )
    try:
        conn.execute("BEGIN")
        try:
            for table in child_tables:
                pk_column, create_new = _V2_CHILD_TABLES[table]
                conn.execute(create_new)
                conn.execute(
                    f"INSERT INTO {table}_new ({pk_column}, bond_id, data_json) "  # noqa: S608
                    f"SELECT {pk_column}, bond_id, data_json FROM {table}"
                )
                conn.execute(f"DROP TABLE {table}")  # noqa: S608 - fixed names
                conn.execute(f"ALTER TABLE {table}_new RENAME TO {table}")  # noqa: S608
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{table}_bond ON {table}(bond_id)"  # noqa: S608
                )
        except BaseException:
            conn.rollback()
            raise
        # Commit while foreign_keys is still OFF: this is the commit
        # that carries the preserved legacy orphans into the FK
        # tables. See the docstring for why later commits stay clean.
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys=ON")

    orphan_vows = orphans.get("vows", [])
    orphan_hurts = orphans.get("hurts", [])
    if orphan_vows or orphan_hurts:
        log.warning(
            "Bond store migration v1 -> v2 preserved %d orphan vow "
            "row(s) and %d orphan hurt row(s) from the legacy v1 file "
            "(bond_id with no matching bond_edges row) — preserved and "
            "reported, never dropped. Orphan vows: %s. Orphan hurts: %s. "
            "New orphan saves are refused from v2 onward.",
            len(orphan_vows),
            len(orphan_hurts),
            orphan_vows,
            orphan_hurts,
        )
    log.info(
        "Bond store migration v1 -> v2: rebuilt %s with the "
        "foreign-key schema (%d orphan vow(s), %d orphan hurt(s) preserved)",
        ", ".join(child_tables),
        len(orphan_vows),
        len(orphan_hurts),
    )


#: Forward migrations for the bond store, in ``state_io``'s contract:
#: the key is the version being migrated *from*. ``_run_migrations``
#: looks up each step in ``range(from_version, to_version)``; steps
#: with no entry are stamp-only (that is how unstamped v0 files
#: become v1 — no DDL was ever needed for that transition).
BOND_MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    1: _migrate_bond_1_to_2,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PersistentBondStore:
    """SQLite store for BondEdge, Vow, and Hurt objects.

    Args:
        db_path: File path for the SQLite database.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        # Guarded open: a corrupt DB is quarantined (announced once) and a
        # fresh one created — the constructor never crashes on bad bytes.
        # open_verified_state_db also runs PRAGMA integrity_check, catching
        # bit-rot inside data pages that a header-only open would miss.
        conn, _recovered = open_verified_state_db(
            self._db_path,
            current_version=CURRENT_SCHEMA_VERSION,
            migrations=BOND_MIGRATIONS,
        )
        with conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        # Phase A: connections come from the one shared factory
        # (WAL + synchronous=FULL + foreign_keys + unified busy
        # timeout). This store previously ran with foreign_keys OFF
        # and no FK declarations; its connections now enforce the
        # vows/hurts -> bond_edges references declared in _SCHEMA.
        # The FKs are DEFERRABLE INITIALLY DEFERRED so delete_edge's
        # single transaction (edge, then vows, then hurts) still
        # commits cleanly — the check lands at COMMIT, when no
        # orphans remain.
        return connect_state_db(self._db_path, row_factory=True)

    # ------------------------------------------------------------------
    # BondEdge
    # ------------------------------------------------------------------

    def save_edge(self, edge: BondEdge) -> None:
        """Insert or replace a BondEdge."""
        payload = json.loads(edge.model_dump_json())
        now = _now_iso()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT created_at FROM bond_edges WHERE bond_id=?", (edge.bond_id,)
            ).fetchone()
            created_at = row["created_at"] if row else now
            conn.execute(
                "INSERT OR REPLACE INTO bond_edges "
                "(bond_id, entity_a, entity_b, domain, status, data_json, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    edge.bond_id,
                    edge.entity_a,
                    edge.entity_b,
                    edge.domain.value,
                    edge.status.value,
                    json.dumps(payload),
                    created_at,
                    now,
                ),
            )

    def load_edge(self, bond_id: str) -> BondEdge | None:
        """Return a BondEdge by ID, or None if not found."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data_json FROM bond_edges WHERE bond_id=?", (bond_id,)
            ).fetchone()
        if row is None:
            return None
        return BondEdge.model_validate(json.loads(row["data_json"]))

    def all_edges(self) -> list[BondEdge]:
        """Return all stored BondEdge records."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT data_json FROM bond_edges ORDER BY created_at"
            ).fetchall()
        return [BondEdge.model_validate(json.loads(r["data_json"])) for r in rows]

    def delete_edge(self, bond_id: str) -> bool:
        """Delete a BondEdge and its associated vows/hurts. Returns True if found."""
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM bond_edges WHERE bond_id=?", (bond_id,))
            conn.execute("DELETE FROM vows WHERE bond_id=?", (bond_id,))
            conn.execute("DELETE FROM hurts WHERE bond_id=?", (bond_id,))
        return cursor.rowcount > 0

    def edges_for_entity(self, entity_id: str) -> list[BondEdge]:
        """Return all edges where entity_id is either entity_a or entity_b."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT data_json FROM bond_edges WHERE entity_a=? OR entity_b=?",
                (entity_id, entity_id),
            ).fetchall()
        return [BondEdge.model_validate(json.loads(r["data_json"])) for r in rows]

    # ------------------------------------------------------------------
    # Vow
    # ------------------------------------------------------------------

    def save_vow(self, vow: Vow) -> None:
        """Insert or replace a Vow."""
        payload = json.loads(vow.model_dump_json())
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO vows (vow_id, bond_id, data_json) VALUES (?,?,?)",
                (vow.vow_id, vow.bond_id, json.dumps(payload)),
            )

    def load_vow(self, vow_id: str) -> Vow | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data_json FROM vows WHERE vow_id=?", (vow_id,)
            ).fetchone()
        if row is None:
            return None
        return Vow.model_validate(json.loads(row["data_json"]))

    def vows_for_bond(self, bond_id: str) -> list[Vow]:
        """Return all vows for a specific bond."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT data_json FROM vows WHERE bond_id=?", (bond_id,)
            ).fetchall()
        return [Vow.model_validate(json.loads(r["data_json"])) for r in rows]

    # ------------------------------------------------------------------
    # Hurt
    # ------------------------------------------------------------------

    def save_hurt(self, hurt: Hurt) -> None:
        """Insert or replace a Hurt."""
        payload = json.loads(hurt.model_dump_json())
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO hurts (hurt_id, bond_id, data_json) VALUES (?,?,?)",
                (hurt.hurt_id, hurt.bond_id, json.dumps(payload)),
            )

    def load_hurt(self, hurt_id: str) -> Hurt | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data_json FROM hurts WHERE hurt_id=?", (hurt_id,)
            ).fetchone()
        if row is None:
            return None
        return Hurt.model_validate(json.loads(row["data_json"]))

    def hurts_for_bond(self, bond_id: str) -> list[Hurt]:
        """Return all hurts for a specific bond."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT data_json FROM hurts WHERE bond_id=?", (bond_id,)
            ).fetchall()
        return [Hurt.model_validate(json.loads(r["data_json"])) for r in rows]

    # ------------------------------------------------------------------
    # Bulk load
    # ------------------------------------------------------------------

    def load_into_service(self, service: object) -> None:
        """Restore all edges, vows, and hurts into a BondGraphService instance.

        Args:
            service: A ``BondGraphService`` instance with ``.edges``,
                     ``.vows``, and ``.hurts`` dicts.
        """
        for edge in self.all_edges():
            service.edges[edge.bond_id] = edge  # type: ignore[attr-defined]
        with self._connect() as conn:
            for row in conn.execute("SELECT data_json FROM vows").fetchall():
                vow = Vow.model_validate(json.loads(row["data_json"]))
                service.vows[vow.vow_id] = vow  # type: ignore[attr-defined]
            for row in conn.execute("SELECT data_json FROM hurts").fetchall():
                hurt = Hurt.model_validate(json.loads(row["data_json"]))
                service.hurts[hurt.hurt_id] = hurt  # type: ignore[attr-defined]

    def count_edges(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM bond_edges").fetchone()[0]

    def count_vows(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM vows").fetchone()[0]

    def count_hurts(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM hurts").fetchone()[0]

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def integrity_check(self) -> bool:
        """Run SQLite's integrity_check pragma; True when the DB is healthy.

        Added for parity with WorldStore and PersistentMemoryStore.
        """
        with self._connect() as conn:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            return result is not None and result[0] == "ok"
