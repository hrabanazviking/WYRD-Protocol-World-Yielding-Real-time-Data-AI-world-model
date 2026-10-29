from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from wyrdforge.ecs.component import (
    deserialize_component,
    get_component_version,
    registered_types,
)
from wyrdforge.ecs.entity import Entity
from wyrdforge.ecs.world import World
from wyrdforge.hardening.state_io import connect_state_db, open_verified_state_db

log = logging.getLogger(__name__)

#: Schema version stamped as ``PRAGMA user_version`` on the world DB.
#: Bump when _SCHEMA gains a table/column, and add a forward migration.
#:
#: History:
#: - v1: worlds/entities/components (the original schema).
#: - v2 (Phase A4, load honesty): adds ``quarantined_components`` — the
#:   preservation home for component rows that fail to load (unknown
#:   type, corrupt payload, newer schema version). See
#:   :data:`WORLD_MIGRATIONS`.
CURRENT_SCHEMA_VERSION = 2

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

CREATE TABLE IF NOT EXISTS quarantined_components (
    world_id        TEXT NOT NULL,
    entity_id       TEXT NOT NULL,
    component_type  TEXT NOT NULL,
    data_json       TEXT NOT NULL,
    schema_version  TEXT,
    reason          TEXT NOT NULL,
    detail          TEXT NOT NULL DEFAULT '',
    quarantined_at  TEXT NOT NULL,
    PRIMARY KEY (world_id, entity_id, component_type),
    FOREIGN KEY (world_id) REFERENCES worlds(world_id)
);

PRAGMA journal_mode=WAL;
"""


_QUARANTINED_COMPONENTS_DDL = """
CREATE TABLE IF NOT EXISTS quarantined_components (
    world_id        TEXT NOT NULL,
    entity_id       TEXT NOT NULL,
    component_type  TEXT NOT NULL,
    data_json       TEXT NOT NULL,
    schema_version  TEXT,
    reason          TEXT NOT NULL,
    detail          TEXT NOT NULL DEFAULT '',
    quarantined_at  TEXT NOT NULL,
    PRIMARY KEY (world_id, entity_id, component_type),
    FOREIGN KEY (world_id) REFERENCES worlds(world_id)
);
"""


def _migrate_world_1_to_2(conn: sqlite3.Connection) -> None:
    """Migrate a world DB from schema v1 to v2 (Phase A4).

    Adds the ``quarantined_components`` table — the preservation home
    for component rows that cannot be loaded. No existing table is
    touched and no row is moved: a v1 file's worlds, entities, and
    components load exactly as before (pinned by
    ``tests/test_load_honesty.py``).
    """
    conn.execute(_QUARANTINED_COMPONENTS_DDL)


#: Forward migrations for the world store, keyed by the version being
#: migrated *from* (the ``state_io._run_migrations`` contract).
WORLD_MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    1: _migrate_world_1_to_2,
}


# ---------------------------------------------------------------------------
# Load honesty (Phase A4) — a load that loses a component must say so
# ---------------------------------------------------------------------------

#: A stored component claims a schema version newer than the version
#: registered for its type: this code cannot know how to read it.
REASON_VERSION_MISMATCH = "version-mismatch"
#: The stored component's type is not in the component registry.
REASON_UNKNOWN_TYPE = "unknown-type"
#: The stored payload is not valid JSON at all.
REASON_INVALID_JSON = "invalid-json"
#: The payload parses but cannot become a component (not an object,
#: missing its type field, or rejected by the component model).
REASON_CORRUPT_PAYLOAD = "corrupt-payload"


@dataclass(frozen=True)
class ComponentLoadFailure:
    """One stored component row that did not load — and was not dropped.

    The raw stored payload is preserved verbatim, both here and in the
    store's ``quarantined_components`` table, so nothing a load refused
    is ever lost silently.
    """

    entity_id: str
    component_type: str
    reason: str
    detail: str
    raw_payload: str
    stored_schema_version: str | None


@dataclass
class WorldLoadReport:
    """Structured outcome of a :meth:`WorldStore.load_with_report` call."""

    world_id: str
    loaded_components: int = 0
    failures: list[ComponentLoadFailure] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when every stored component loaded."""
        return not self.failures


def _version_key(version: str) -> tuple[int, ...] | None:
    """Parse a dotted schema version into a comparable tuple.

    Returns None for anything unparseable — an unparseable stamp is
    not, by itself, grounds to refuse a component that otherwise
    deserializes cleanly.
    """
    try:
        return tuple(int(part) for part in version.strip().split("."))
    except (ValueError, AttributeError):
        return None


def _is_newer_version(stored: str, current: str) -> bool:
    stored_key = _version_key(stored)
    current_key = _version_key(current)
    if stored_key is None or current_key is None:
        return False
    width = max(len(stored_key), len(current_key))
    stored_key += (0,) * (width - len(stored_key))
    current_key += (0,) * (width - len(current_key))
    return stored_key > current_key


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
        # Guarded open: a corrupt DB is quarantined (announced once) and a
        # fresh one created — the constructor never crashes on bad bytes.
        # open_verified_state_db also runs PRAGMA integrity_check, catching
        # bit-rot inside data pages that a header-only open would miss.
        conn, _recovered = open_verified_state_db(
            self._db_path,
            current_version=CURRENT_SCHEMA_VERSION,
            migrations=WORLD_MIGRATIONS,
        )
        with conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        # Phase A: connections come from the one shared factory
        # (WAL + synchronous=FULL + foreign_keys + unified busy
        # timeout). Previously hand-rolled per store, and drifted.
        return connect_state_db(self._db_path, row_factory=True)

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
        """Restore a World from SQLite by world_id.

        Load honesty (Phase A4): a stored component that cannot be
        loaded — unknown type, corrupt payload, or a schema version
        newer than the registered one — is **never silently skipped**
        (the pre-A4 behaviour). It is logged at warning, preserved
        verbatim in the ``quarantined_components`` table, and reported
        by :meth:`load_with_report`. This method keeps its historical
        signature and return; callers that need the per-component
        outcome should use :meth:`load_with_report`.
        """
        world, _report = self.load_with_report(world_id)
        return world

    def load_with_report(self, world_id: str) -> tuple[World, WorldLoadReport]:
        """Restore a World and report every component that did not load.

        Healthy components load exactly as they always have. Each
        failing row is classified (``unknown-type`` / ``invalid-json``
        / ``corrupt-payload`` / ``version-mismatch``), logged at
        warning, copied verbatim into ``quarantined_components``
        (the original row in ``components`` is left untouched), and
        returned in the report — a load loses nothing silently.
        """
        report = WorldLoadReport(world_id=world_id)
        known_types = set(registered_types())
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

            # Load components — honestly (Phase A4).
            comp_rows = conn.execute(
                "SELECT entity_id, component_type, data_json, schema_version "
                "FROM components WHERE world_id=?",
                (world_id,),
            ).fetchall()

            for cr in comp_rows:
                failure = self._load_one_component(world, cr, known_types)
                if failure is None:
                    report.loaded_components += 1
                else:
                    report.failures.append(failure)

            # Preserve every refused payload verbatim, in the same
            # transaction as the load's connection block.
            if report.failures:
                stamp = datetime.now(timezone.utc).isoformat()
                for failure in report.failures:
                    conn.execute(
                        "INSERT OR REPLACE INTO quarantined_components "
                        "(world_id, entity_id, component_type, data_json, "
                        "schema_version, reason, detail, quarantined_at) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        (
                            world_id,
                            failure.entity_id,
                            failure.component_type,
                            failure.raw_payload,
                            failure.stored_schema_version,
                            failure.reason,
                            failure.detail,
                            stamp,
                        ),
                    )
                log.warning(
                    "WorldStore.load(%s): %d of %d component(s) did not load "
                    "and were quarantined with their raw payloads preserved: %s",
                    world_id,
                    len(report.failures),
                    len(comp_rows),
                    ", ".join(
                        f"{f.entity_id}/{f.component_type} ({f.reason})"
                        for f in report.failures
                    ),
                )

        return world, report

    def _load_one_component(
        self,
        world: World,
        cr: sqlite3.Row,
        known_types: set[str],
    ) -> ComponentLoadFailure | None:
        """Load one stored component row into ``world``.

        Returns None on success; on any failure returns the classified
        :class:`ComponentLoadFailure` (and logs it at warning) instead
        of raising or silently skipping.
        """
        eid = cr["entity_id"]
        comp_type = cr["component_type"]
        raw = cr["data_json"]
        stored_version = cr["schema_version"]

        def fail(reason: str, detail: str) -> ComponentLoadFailure:
            log.warning(
                "WorldStore.load: component %s/%s did not load (%s): %s",
                eid,
                comp_type,
                reason,
                detail,
            )
            return ComponentLoadFailure(
                entity_id=eid,
                component_type=comp_type,
                reason=reason,
                detail=detail,
                raw_payload=raw,
                stored_schema_version=stored_version,
            )

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            return fail(REASON_INVALID_JSON, f"stored payload is not valid JSON: {exc}")
        if not isinstance(data, dict):
            return fail(
                REASON_CORRUPT_PAYLOAD,
                f"stored payload is a {type(data).__name__}, not a component object",
            )
        if comp_type not in known_types:
            return fail(
                REASON_UNKNOWN_TYPE,
                f"no component registered for type '{comp_type}'",
            )
        if stored_version is not None and _is_newer_version(
            str(stored_version), get_component_version(comp_type)
        ):
            return fail(
                REASON_VERSION_MISMATCH,
                f"stored schema_version {stored_version} is newer than the "
                f"registered version {get_component_version(comp_type)} "
                f"for type '{comp_type}'",
            )
        try:
            comp = deserialize_component(data)
        except KeyError as exc:
            # The payload's own component_type field names a type the
            # registry does not know (or disagrees with the row's).
            return fail(REASON_UNKNOWN_TYPE, f"unregistered component type: {exc}")
        except Exception as exc:
            return fail(
                REASON_CORRUPT_PAYLOAD,
                f"payload rejected by {comp_type}: {type(exc).__name__}: {exc}",
            )
        world._components[eid][comp_type] = comp
        world._comp_type_index[comp_type].add(eid)
        return None

    def quarantined_components(self, world_id: str | None = None) -> list[dict]:
        """Return component payloads preserved by load honesty (Phase A4).

        Each entry carries the row's identity, its verbatim raw
        ``data_json``, the stored ``schema_version``, and the
        ``reason``/``detail`` the load refused it for. With
        ``world_id=None`` every quarantined row in the store is
        returned.
        """
        with self._connect() as conn:
            if world_id is None:
                rows = conn.execute(
                    "SELECT world_id, entity_id, component_type, data_json, "
                    "schema_version, reason, detail, quarantined_at "
                    "FROM quarantined_components ORDER BY world_id, entity_id, component_type"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT world_id, entity_id, component_type, data_json, "
                    "schema_version, reason, detail, quarantined_at "
                    "FROM quarantined_components WHERE world_id=? "
                    "ORDER BY entity_id, component_type",
                    (world_id,),
                ).fetchall()
        return [dict(row) for row in rows]

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
