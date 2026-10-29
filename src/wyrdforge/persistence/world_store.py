from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
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


# ---------------------------------------------------------------------------
# Incremental persistence (Phase B2) — dirty-row tracking for save()
# ---------------------------------------------------------------------------

#: Rows per batched ``executemany`` chunk inside save(). All of a
#: save's writes run under ONE savepoint inside the save's single
#: transaction (``SAVEPOINT wyrd_save``): a failure rolls back to
#: that savepoint, the exception propagates, and the outer
#: ``with conn`` block rolls the whole save back — a save is still
#: all-or-nothing, exactly like the pre-B2 full save. (Measured
#: 2026-10-29: a savepoint PER CHUNK costs ~2x the write time under
#: WAL + synchronous=FULL — 48 ms vs 22 ms for 6,000 component rows —
#: while one savepoint for the whole batch costs nothing measurable.
#: Hence one savepoint, batched executemany chunks inside it.)
_SAVE_BATCH_ROWS = 400


@dataclass(frozen=True)
class SaveReport:
    """What one :meth:`WorldStore.save_with_report` call actually did.

    The counts are the incremental-persistence evidence: at live
    rates a 1 Hz presence tick should write a handful of rows, not
    the whole world. ``full=True`` marks a forced full save (every
    current row written, sweep against the database itself).
    """

    world_id: str
    full: bool
    world_row_written: bool
    entities_written: int
    entities_deleted: int
    components_written: int
    components_deleted: int
    entities_unchanged: int
    components_unchanged: int
    elapsed_ms: float


@dataclass
class _PersistedState:
    """One store instance's record of what it last persisted.

    The baseline a save diffs against. Fingerprints are the exact
    persisted row tuples (minus ``world_id``) — for components that
    includes the verbatim ``model_dump_json()`` payload, so ANY
    change to a component's serialized form marks its row dirty,
    including in-place field mutation that never passes through a
    World method (``HealthComponent.take_damage()``,
    ``ContainerComponent.add_child()``, direct field assignment,
    ``touch()``). See :meth:`WorldStore.save_with_report`.

    ``pinned_components`` are component keys whose stored rows this
    baseline must never sweep: rows a load refused and quarantined
    (Phase A4 — the original row is preserved by design). A pin is
    dropped when its entity is deleted (the stale-entity sweep has
    always removed every component of a deleted entity).
    """

    world_row: tuple | None = None
    entities: dict[str, tuple] = field(default_factory=dict)
    components: dict[tuple[str, str], tuple] = field(default_factory=dict)
    pinned_components: set[tuple[str, str]] = field(default_factory=set)


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
        # Phase B2: incremental-save baselines, one per world_id, plus
        # the lock serialising this instance's saves (the EventBus /
        # World RLock house pattern). The baseline is only ever a
        # write-skipping oracle: it is seeded from this store's own
        # saves, from a load's rows, or from the database itself —
        # never assumed. See save_with_report().
        self._save_lock = threading.RLock()
        self._persisted: dict[str, _PersistedState] = {}
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

    # -- Snapshot (shared by save and by load's baseline seeding) --

    @staticmethod
    def _snapshot_world(
        world: World,
    ) -> tuple[tuple, list[tuple], list[tuple]]:
        """Serialise a world into persisted-row tuples, under its lock.

        Phase B1 discipline, unchanged: every row (entity rows,
        component JSON, id set) is materialised while ``world.lock``
        is held, because the live Entity/Component objects can be
        mutated by other threads; database I/O then runs outside the
        lock. Phase B2 change: entity ``tags_json`` is serialised
        sorted, so a row's bytes are a deterministic function of its
        content (a set's iteration order otherwise makes identical
        tag sets serialise differently between saves, defeating the
        fingerprint diff — and stores nondeterministic bytes).
        """
        with world.lock:
            world_row = (world.world_id, world.world_name, world.created_at.isoformat())
            entity_rows = [
                (
                    world.world_id,
                    entity.entity_id,
                    json.dumps(sorted(entity.tags)),
                    1 if entity.active else 0,
                    entity.created_at.isoformat(),
                    entity.updated_at.isoformat(),
                )
                for entity in world._entities.values()
            ]
            component_rows = [
                (
                    world.world_id,
                    entity_id,
                    comp_type,
                    comp.model_dump_json(),
                    comp.schema_version,
                    comp.created_at.isoformat(),
                    comp.updated_at.isoformat(),
                )
                for entity_id, comp_map in world._components.items()
                for comp_type, comp in comp_map.items()
            ]
        return world_row, entity_rows, component_rows

    @staticmethod
    def _state_from_rows(
        world_row: tuple | None,
        entity_rows: list[tuple],
        component_rows: list[tuple],
    ) -> _PersistedState:
        """Build a persisted-state baseline from full row tuples."""
        return _PersistedState(
            world_row=world_row,
            entities={row[1]: row[1:] for row in entity_rows},
            components={(row[1], row[2]): row[1:] for row in component_rows},
        )

    def _seed_state_from_db(self, conn: sqlite3.Connection, world_id: str) -> _PersistedState:
        """Read the database's own rows for ``world_id`` as a baseline.

        Used when this store instance has no baseline for the world
        (first save through this instance — e.g. after a process
        restart): the diff then runs against what the file actually
        holds, not against an assumed-empty world, so a fresh store
        instance still saves incrementally and still sweeps stale
        rows. Component rows a previous load quarantined (present in
        ``quarantined_components``) are pinned, never swept.
        """
        wrow = conn.execute(
            "SELECT world_id, world_name, created_at FROM worlds WHERE world_id=?",
            (world_id,),
        ).fetchone()
        entity_rows = [
            tuple(row)
            for row in conn.execute(
                "SELECT world_id, entity_id, tags_json, active, created_at, updated_at "
                "FROM entities WHERE world_id=?",
                (world_id,),
            )
        ]
        component_rows = [
            tuple(row)
            for row in conn.execute(
                "SELECT world_id, entity_id, component_type, data_json, schema_version, "
                "created_at, updated_at FROM components WHERE world_id=?",
                (world_id,),
            )
        ]
        state = self._state_from_rows(
            tuple(wrow) if wrow is not None else None, entity_rows, component_rows
        )
        state.pinned_components = {
            (row[0], row[1])
            for row in conn.execute(
                "SELECT entity_id, component_type FROM quarantined_components "
                "WHERE world_id=?",
                (world_id,),
            )
        } & set(state.components)
        return state

    @staticmethod
    def _executemany_batched(
        conn: sqlite3.Connection, sql: str, rows: list[tuple]
    ) -> None:
        """Run ``executemany`` in chunks of ``_SAVE_BATCH_ROWS``.

        Chunking only — the savepoint discipline lives in
        :meth:`save_with_report`, which wraps all of a save's writes
        in one SAVEPOINT inside the save's transaction.
        """
        for start in range(0, len(rows), _SAVE_BATCH_ROWS):
            conn.executemany(sql, rows[start : start + _SAVE_BATCH_ROWS])

    def save(self, world: World, *, full: bool = False) -> None:
        """Persist a World to SQLite — incrementally by default (B2).

        Only rows whose serialized content changed since this store
        last persisted the world are upserted; rows for deleted
        entities/components are swept. ``full=True`` forces the
        pre-B2 behaviour as a fallback: every current row is written
        and the sweep runs against the database itself. The
        historical signature and ``None`` return are unchanged;
        callers that want the evidence use :meth:`save_with_report`.
        """
        self.save_with_report(world, full=full)

    def save_with_report(self, world: World, *, full: bool = False) -> SaveReport:
        """Persist a World and report exactly what was written.

        Dirty tracking (Phase B2) — design and honest coverage:

        * The world is snapshotted under ``world.lock`` exactly as
          B1 built it (see :meth:`_snapshot_world`); each snapshot
          row is then compared, byte for byte, against the baseline
          of what this store last persisted for the world. A row
          whose bytes differ — or that is new — is dirty and is
          upserted; a baseline key absent from the snapshot is a
          deletion and is swept; identical rows are not written.
        * Because the fingerprint IS the serialized row, detection
          covers every mutation path that changes persisted content:
          World create/remove, component add/replace/remove,
          tag/untag, Yggdrasil placement (which replaces the spatial
          component and mutates container components in place),
          direct entity changes (``deactivate()``), AND direct
          component field mutation (``take_damage()``, field
          assignment, ``touch()``, list mutation inside a component).
          What it does NOT do is skip serializing unchanged rows:
          detection happens at the snapshot surface B1 built, so a
          save's CPU cost still scales with world size while its
          database write cost scales with the change set. A mutation
          that changes no persisted byte (e.g. setting a field to the
          value it already holds) is correctly not written.
        * The baseline comes only from evidence: this instance's own
          last successful save, a load through this instance (the
          loaded rows), or — on a cold cache — the database's own
          current rows. It is updated ONLY after the save's
          transaction commits, so a failed save leaves every pending
          change dirty for the next one. The one assumption is the
          store's long-standing one: a WorldStore instance is the
          writer for its file. If another writer may have changed
          the file behind this instance's back, call ``save(...,
          full=True)`` — it re-reads the database and cannot skip a
          needed write. When in doubt, the code falls back the same
          way: any baseline doubt means full, never silent loss.
        * Sweep semantics: the pre-B2 stale-entity sweep is preserved
          exactly (a deleted entity's row and all its component rows
          are deleted) and extended to components of live entities —
          pre-B2, a component removed via ``remove_component`` was
          never deleted from the store and RESURRECTED on the next
          load (verified 2026-10-29 against the B1 tree); B2 sweeps
          it, in incremental and full saves alike. One preservation
          exception: component rows a load quarantined (Phase A4)
          are pinned and never swept while their entity lives — A4's
          doctrine is that the original row stays untouched; the pin
          drops when the entity itself is deleted.

        Writes run as batched ``executemany`` chunks
        (:meth:`_executemany_batched`) under one SAVEPOINT inside the
        save's single transaction — a save remains all-or-nothing.
        This instance's
        saves are serialised on ``_save_lock`` so two threads saving
        through one store cannot interleave diff and commit; the
        world lock is held only for the snapshot, never across I/O.
        """
        started = time.perf_counter()
        with self._save_lock:
            world_row, entity_rows, component_rows = self._snapshot_world(world)
            current = self._state_from_rows(world_row, entity_rows, component_rows)

            baseline = None if full else self._persisted.get(world.world_id)
            diff: tuple | None = None
            if baseline is not None:
                diff = self._diff_against_baseline(
                    baseline, current, entity_rows, component_rows, world_row, full=False
                )
                if not diff[4] and not diff[0] and not diff[1] and not diff[2] and not diff[3]:
                    # Fast path: the cached baseline proves nothing
                    # changed — no connection, no transaction, no
                    # commit sync. The baseline already equals the
                    # current snapshot, so it stays as it is.
                    return SaveReport(
                        world_id=world.world_id,
                        full=False,
                        world_row_written=False,
                        entities_written=0,
                        entities_deleted=0,
                        components_written=0,
                        components_deleted=0,
                        entities_unchanged=len(entity_rows),
                        components_unchanged=len(component_rows),
                        elapsed_ms=(time.perf_counter() - started) * 1e3,
                    )

            with self._connect() as conn:
                if baseline is None:
                    # Cold cache (or a forced full save): the baseline
                    # is the database's own current rows — evidence,
                    # never an assumption.
                    baseline = self._seed_state_from_db(conn, world.world_id)
                    diff = self._diff_against_baseline(
                        baseline, current, entity_rows, component_rows, world_row, full=full
                    )
                assert diff is not None and baseline is not None
                (
                    entities_to_write,
                    components_to_write,
                    stale_entity_ids,
                    components_to_delete,
                    world_row_written,
                ) = diff

                # All writes under one savepoint (batched savepoint
                # discipline): any failure rolls back to it, the
                # exception propagates, and the outer ``with conn``
                # block rolls the whole save back.
                conn.execute("SAVEPOINT wyrd_save")
                try:
                    if world_row_written:
                        conn.execute(
                            "INSERT OR REPLACE INTO worlds (world_id, world_name, created_at) VALUES (?,?,?)",
                            world_row,
                        )
                    if components_to_delete:
                        self._executemany_batched(
                            conn,
                            "DELETE FROM components WHERE world_id=? AND entity_id=? AND component_type=?",
                            [
                                (world.world_id, eid, ctype)
                                for eid, ctype in components_to_delete
                            ],
                        )
                    if stale_entity_ids:
                        self._executemany_batched(
                            conn,
                            "DELETE FROM entities WHERE world_id=? AND entity_id=?",
                            [(world.world_id, eid) for eid in stale_entity_ids],
                        )
                    if entities_to_write:
                        self._executemany_batched(
                            conn,
                            "INSERT OR REPLACE INTO entities "
                            "(world_id, entity_id, tags_json, active, created_at, updated_at) "
                            "VALUES (?,?,?,?,?,?)",
                            entities_to_write,
                        )
                    if components_to_write:
                        self._executemany_batched(
                            conn,
                            "INSERT OR REPLACE INTO components "
                            "(world_id, entity_id, component_type, data_json, schema_version, created_at, updated_at) "
                            "VALUES (?,?,?,?,?,?,?)",
                            components_to_write,
                        )
                except Exception:
                    conn.execute("ROLLBACK TO SAVEPOINT wyrd_save")
                    conn.execute("RELEASE SAVEPOINT wyrd_save")
                    raise
                conn.execute("RELEASE SAVEPOINT wyrd_save")
            # The transaction committed (the ``with conn`` block above
            # is the commit boundary): the current snapshot becomes
            # the baseline. On any exception this line is never
            # reached and every pending change stays dirty.
            current.pinned_components = {
                key
                for key in baseline.pinned_components
                if key[0] in current.entities and key not in current.components
            }
            self._persisted[world.world_id] = current

        return SaveReport(
            world_id=world.world_id,
            full=full,
            world_row_written=world_row_written,
            entities_written=len(entities_to_write),
            entities_deleted=len(stale_entity_ids),
            components_written=len(components_to_write),
            components_deleted=len(components_to_delete),
            entities_unchanged=len(entity_rows) - len(entities_to_write) if not full else 0,
            components_unchanged=len(component_rows) - len(components_to_write) if not full else 0,
            elapsed_ms=(time.perf_counter() - started) * 1e3,
        )

    @staticmethod
    def _diff_against_baseline(
        baseline: _PersistedState,
        current: _PersistedState,
        entity_rows: list[tuple],
        component_rows: list[tuple],
        world_row: tuple,
        *,
        full: bool,
    ) -> tuple[list[tuple], list[tuple], list[str], list[tuple[str, str]], bool]:
        """Diff a snapshot against a persisted baseline.

        Returns ``(entities_to_write, components_to_write,
        stale_entity_ids, components_to_delete, world_row_written)``.
        Components to sweep are baseline keys the world no longer
        holds — except pinned (quarantined) rows of entities that
        still live; components of deleted entities are always swept
        (the pre-B2 stale-entity sweep semantics).
        """
        if full:
            entities_to_write = entity_rows
            components_to_write = component_rows
        else:
            entities_to_write = [
                row for row in entity_rows if baseline.entities.get(row[1]) != row[1:]
            ]
            components_to_write = [
                row
                for row in component_rows
                if baseline.components.get((row[1], row[2])) != row[1:]
            ]
        stale_entity_ids = sorted(set(baseline.entities) - set(current.entities))
        stale_entity_set = set(stale_entity_ids)
        components_to_delete = sorted(
            key
            for key in set(baseline.components) - set(current.components)
            if key[0] in stale_entity_set or key not in baseline.pinned_components
        )
        world_row_written = full or baseline.world_row != world_row
        return (
            entities_to_write,
            components_to_write,
            stale_entity_ids,
            components_to_delete,
            world_row_written,
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

            # Load entities. The World under construction is not yet
            # shared with any other thread, so the direct internal
            # writes below need no lock (Phase B1 note); once load
            # returns and the caller publishes the World, all access
            # goes through World's locked methods.
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
                "SELECT entity_id, component_type, data_json, schema_version, "
                "created_at, updated_at "
                "FROM components WHERE world_id=?",
                (world_id,),
            ).fetchall()

            pinned_rows: dict[tuple[str, str], tuple] = {}
            for cr in comp_rows:
                failure = self._load_one_component(world, cr, known_types)
                if failure is None:
                    report.loaded_components += 1
                else:
                    report.failures.append(failure)
                    # The refused row's own tuple, in snapshot-row
                    # shape: the B2 baseline carries it as a pinned
                    # entry (see the seeding below).
                    pinned_rows[(cr["entity_id"], cr["component_type"])] = (
                        cr["entity_id"],
                        cr["component_type"],
                        cr["data_json"],
                        cr["schema_version"],
                        cr["created_at"],
                        cr["updated_at"],
                    )

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

        # Phase B2: seed this store's incremental baseline from the
        # world just loaded — its rows are what the database holds,
        # so a first save after a load writes only what changed since
        # the load. Components this load refused are pinned: their
        # original rows stay untouched and are never swept while
        # their entity lives (Phase A4 preservation).
        with self._save_lock:
            seed_row, seed_entities, seed_components = self._snapshot_world(world)
            seeded = self._state_from_rows(seed_row, seed_entities, seed_components)
            # Pinned entries join the baseline's component map with
            # their stored rows, so the sweep logic can see them:
            # pinned + entity alive -> never swept; pinned + entity
            # deleted -> swept with the entity, as always.
            seeded.components.update(pinned_rows)
            seeded.pinned_components = set(pinned_rows)
            self._persisted[world_id] = seeded

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
    # Per-subject purge (Phase C1)
    # ------------------------------------------------------------------

    def purge_subject(self, subject_id: str) -> dict:
        """Erase every entity that *is* *subject_id*, in every world.

        An entity is the subject when its ``entity_id`` equals the
        subject id, or it carries a ``PersonaRefComponent``
        (component type ``persona_ref``) whose ``persona_id`` equals
        the subject id. For each such entity, in ONE transaction:

        - all of its rows in ``components`` are deleted;
        - its row in ``entities`` is deleted;
        - its rows in ``quarantined_components`` (Phase A4 payloads
          preserved on refused loads) are DESTROYED — purge is the
          one act that overrides the quarantine doctrine, on the
          subject's own demand (see ``persistence/purge.py``).

        One structural exception to the mention rule:
        ``ContainerComponent.children`` is containment state, not a
        mention — a purged entity's id is scrubbed from the
        ``children`` list of every SURVIVING container in the same
        world (the row's ``data_json`` is rewritten with the scrubbed
        list; nothing else in the payload changes). Every other
        component of every other entity is left byte-identical —
        including free text that merely mentions the subject.

        This instance's incremental-save baselines (Phase B2) are
        dropped afterwards: the file changed behind them, so the
        next save re-seeds its baseline from the database itself.

        Returns ``{"entities": n, "components": n,
        "quarantined_components": n,
        "container_references_removed": n}`` — removals performed by
        THIS call (a re-purge reports zeros).
        """
        entities_removed = 0
        components_removed = 0
        quarantined_removed = 0
        references_removed = 0
        with self._save_lock:
            with self._connect() as conn:
                # Identify the subject's entities, per world.
                purged: dict[str, set[str]] = {}
                for row in conn.execute(
                    "SELECT world_id, entity_id FROM entities"
                ).fetchall():
                    if row["entity_id"] == subject_id:
                        purged.setdefault(row["world_id"], set()).add(
                            row["entity_id"]
                        )
                for row in conn.execute(
                    "SELECT world_id, entity_id, data_json FROM components "
                    "WHERE component_type='persona_ref'"
                ).fetchall():
                    try:
                        data = json.loads(row["data_json"])
                    except (ValueError, TypeError):
                        continue  # cannot prove it names the subject
                    if isinstance(data, dict) and data.get("persona_id") == subject_id:
                        purged.setdefault(row["world_id"], set()).add(
                            row["entity_id"]
                        )
                if purged:
                    for world_id, entity_ids in purged.items():
                        ids = sorted(entity_ids)
                        placeholders = ",".join("?" * len(ids))
                        components_removed += conn.execute(
                            "SELECT COUNT(*) FROM components "
                            f"WHERE world_id=? AND entity_id IN ({placeholders})",  # noqa: S608 - placeholders only
                            [world_id, *ids],
                        ).fetchone()[0]
                        quarantined_removed += conn.execute(
                            "SELECT COUNT(*) FROM quarantined_components "
                            f"WHERE world_id=? AND entity_id IN ({placeholders})",  # noqa: S608 - placeholders only
                            [world_id, *ids],
                        ).fetchone()[0]
                        conn.execute(
                            "DELETE FROM components "
                            f"WHERE world_id=? AND entity_id IN ({placeholders})",  # noqa: S608 - placeholders only
                            [world_id, *ids],
                        )
                        conn.execute(
                            "DELETE FROM quarantined_components "
                            f"WHERE world_id=? AND entity_id IN ({placeholders})",  # noqa: S608 - placeholders only
                            [world_id, *ids],
                        )
                        cursor = conn.execute(
                            "DELETE FROM entities "
                            f"WHERE world_id=? AND entity_id IN ({placeholders})",  # noqa: S608 - placeholders only
                            [world_id, *ids],
                        )
                        entities_removed += cursor.rowcount
                    # Scrub containment state: surviving containers in
                    # each affected world lose the purged ids.
                    stamp = datetime.now(timezone.utc).isoformat()
                    for world_id, entity_ids in purged.items():
                        container_rows = conn.execute(
                            "SELECT entity_id, data_json FROM components "
                            "WHERE world_id=? AND component_type='container'",
                            (world_id,),
                        ).fetchall()
                        for crow in container_rows:
                            if crow["entity_id"] in entity_ids:
                                continue  # purged itself; already deleted
                            try:
                                data = json.loads(crow["data_json"])
                            except (ValueError, TypeError):
                                continue
                            if not isinstance(data, dict):
                                continue
                            children = data.get("children")
                            if not isinstance(children, list):
                                continue
                            kept = [c for c in children if c not in entity_ids]
                            removed_here = len(children) - len(kept)
                            if not removed_here:
                                continue
                            data["children"] = kept
                            if "updated_at" in data:
                                data["updated_at"] = stamp
                            conn.execute(
                                "UPDATE components SET data_json=?, updated_at=? "
                                "WHERE world_id=? AND entity_id=? "
                                "AND component_type='container'",
                                (
                                    json.dumps(data),
                                    stamp,
                                    world_id,
                                    crow["entity_id"],
                                ),
                            )
                            references_removed += removed_here
            # The file changed behind this instance's B2 baselines;
            # drop them so the next save re-seeds from the database.
            self._persisted.clear()
        return {
            "entities": entities_removed,
            "components": components_removed,
            "quarantined_components": quarantined_removed,
            "container_references_removed": references_removed,
        }

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
        with self._save_lock:
            self._persisted.pop(world_id, None)

    def integrity_check(self) -> bool:
        with self._connect() as conn:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            return result is not None and result[0] == "ok"
