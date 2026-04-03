"""SQLite persistence for BondEdge, Vow, and Hurt records.

BondGraphService is intentionally kept in-memory (fast, stateful).
PersistentBondStore is the durability layer: call it after every
mutating BondGraphService operation to keep disk in sync, and call
``load_into_service()`` on startup to restore prior state.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from wyrdforge.models.bond import BondEdge, Hurt, Vow

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
    bond_id     TEXT NOT NULL,
    data_json   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hurts (
    hurt_id     TEXT PRIMARY KEY,
    bond_id     TEXT NOT NULL,
    data_json   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_vows_bond   ON vows(bond_id);
CREATE INDEX IF NOT EXISTS idx_hurts_bond  ON hurts(bond_id);
"""


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
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

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
