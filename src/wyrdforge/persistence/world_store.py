from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from wyrdforge.ecs.component import deserialize_component
from wyrdforge.ecs.entity import Entity
from wyrdforge.ecs.world import World

_SCHEMA = """
CREATE TABLE IF NOT EXISTS worlds (
    world_id    TEXT PRIMARY KEY,
    world_name  TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
    world_id    TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    tags_json   TEXT NOT NULL DEFAULT '[]',
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (world_id, entity_id),
    FOREIGN KEY (world_id) REFERENCES worlds(world_id)
);

CREATE TABLE IF NOT EXISTS components (
    world_id        TEXT NOT NULL,
    entity_id       TEXT NOT NULL,
    component_type  TEXT NOT NULL,
    data_json       TEXT NOT NULL,
    schema_version  TEXT NOT NULL DEFAULT '1.0',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    PRIMARY KEY (world_id, entity_id, component_type),
    FOREIGN KEY (world_id) REFERENCES worlds(world_id)
);

PRAGMA journal_mode=WAL;
"""


class WorldStore:
    """SQLite-backed persistence for ECS World state.

    Uses stdlib sqlite3 only — no external ORM dependencies.
    All component data is stored as JSON blobs with the full Pydantic
    model_dump() output so that deserialization is type-safe.
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
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save(self, world: World) -> None:
        """Persist all entities and components of a World to SQLite.

        Uses INSERT OR REPLACE so that re-saving updates existing rows.
        """
        with self._connect() as conn:
            # Upsert world record
            conn.execute(
                "INSERT OR REPLACE INTO worlds (world_id, world_name, created_at) VALUES (?,?,?)",
                (world.world_id, world.world_name, world.created_at.isoformat()),
            )

            # Delete stale entities/components (for entities removed since last save)
            existing_ids = {
                row[0]
                for row in conn.execute(
                    "SELECT entity_id FROM entities WHERE world_id=?", (world.world_id,)
                )
            }
            current_ids = set(world._entities.keys())
            for stale_id in existing_ids - current_ids:
                conn.execute(
                    "DELETE FROM components WHERE world_id=? AND entity_id=?",
                    (world.world_id, stale_id),
                )
                conn.execute(
                    "DELETE FROM entities WHERE world_id=? AND entity_id=?",
                    (world.world_id, stale_id),
                )

            # Upsert current entities
            for entity in world._entities.values():
                conn.execute(
                    "INSERT OR REPLACE INTO entities "
                    "(world_id, entity_id, tags_json, active, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        world.world_id,
                        entity.entity_id,
                        json.dumps(list(entity.tags)),
                        1 if entity.active else 0,
                        entity.created_at.isoformat(),
                        entity.updated_at.isoformat(),
                    ),
                )

            # Upsert current components
            for entity_id, comp_map in world._components.items():
                for comp_type, comp in comp_map.items():
                    conn.execute(
                        "INSERT OR REPLACE INTO components "
                        "(world_id, entity_id, component_type, data_json, schema_version, created_at, updated_at) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (
                            world.world_id,
                            entity_id,
                            comp_type,
                            comp.model_dump_json(),
                            comp.schema_version,
                            comp.created_at.isoformat(),
                            comp.updated_at.isoformat(),
                        ),
                    )

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load(self, world_id: str) -> World:
        """Restore a World from SQLite by world_id."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT world_id, world_name, created_at FROM worlds WHERE world_id=?",
                (world_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"World '{world_id}' not found in store at {self._db_path}")

            world = World(world_id=row["world_id"], world_name=row["world_name"])

            # Load entities
            entity_rows = conn.execute(
                "SELECT entity_id, tags_json, active, created_at, updated_at "
                "FROM entities WHERE world_id=? ORDER BY created_at",
                (world_id,),
            ).fetchall()

            for er in entity_rows:
                from datetime import datetime
                entity = Entity(
                    entity_id=er["entity_id"],
                    tags=set(json.loads(er["tags_json"])),
                    active=bool(er["active"]),
                    created_at=datetime.fromisoformat(er["created_at"]),
                    updated_at=datetime.fromisoformat(er["updated_at"]),
                )
                world._entities[entity.entity_id] = entity
                for tag in entity.tags:
                    world._tag_index[tag].add(entity.entity_id)

            # Load components
            comp_rows = conn.execute(
                "SELECT entity_id, component_type, data_json "
                "FROM components WHERE world_id=?",
                (world_id,),
            ).fetchall()

            for cr in comp_rows:
                try:
                    data = json.loads(cr["data_json"])
                    comp = deserialize_component(data)
                    eid = cr["entity_id"]
                    world._components[eid][cr["component_type"]] = comp
                    world._comp_type_index[cr["component_type"]].add(eid)
                except (KeyError, Exception):
                    # Unknown component type — skip gracefully (forward compat)
                    pass

        return world

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def list_worlds(self) -> list[str]:
        with self._connect() as conn:
            return [row[0] for row in conn.execute("SELECT world_id FROM worlds ORDER BY world_id")]

    def delete_world(self, world_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM components WHERE world_id=?", (world_id,))
            conn.execute("DELETE FROM entities WHERE world_id=?", (world_id,))
            conn.execute("DELETE FROM worlds WHERE world_id=?", (world_id,))

    def integrity_check(self) -> bool:
        with self._connect() as conn:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            return result is not None and result[0] == "ok"
