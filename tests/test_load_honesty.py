"""Phase A4 — load honesty pinning tests.

Before A4, ``WorldStore.load()`` swallowed every component error
(``except (KeyError, Exception): pass``): a corrupt or unknown-type
component vanished silently on load. These tests pin the new contract:

(a) an unknown-type component is reported and its raw payload preserved;
(b) a corrupt component payload is reported and preserved, while the
    healthy components still load;
(c) a pre-A4-format saved world (schema v1, no quarantine table) loads
    with identical state;
(d) the happy path is behaviour-identical — same entities/components,
    an empty report, nothing quarantined.

Plus: the versioned component registry, the version-mismatch refusal,
and the world-store v1 -> v2 migration that adds the quarantine table.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

import pytest

import wyrdforge.ecs.components.character  # noqa: F401
import wyrdforge.ecs.components.identity   # noqa: F401
import wyrdforge.ecs.components.spatial    # noqa: F401

from wyrdforge.ecs.component import (
    get_component_version,
    registered_component_versions,
)
from wyrdforge.ecs.components.character import HealthComponent
from wyrdforge.ecs.components.identity import NameComponent
from wyrdforge.ecs.world import World
from wyrdforge.persistence import world_store as ws_mod
from wyrdforge.persistence.world_store import (
    REASON_CORRUPT_PAYLOAD,
    REASON_INVALID_JSON,
    REASON_UNKNOWN_TYPE,
    REASON_VERSION_MISMATCH,
    WorldStore,
)

_TS = "2026-10-29T00:00:00+00:00"


def _saved_store(tmp_path: Path) -> tuple[WorldStore, Path]:
    """A store holding one world: gunnar with name + health components."""
    path = tmp_path / "world.db"
    store = WorldStore(path)
    world = World(world_id="w", world_name="Honesty World")
    world.create_entity(entity_id="gunnar", tags={"npc"})
    world.add_component("gunnar", NameComponent(entity_id="gunnar", name="Gunnar"))
    world.add_component("gunnar", HealthComponent(entity_id="gunnar", hp=80.0))
    store.save(world)
    return store, path


def _insert_raw_component(
    path: Path,
    *,
    entity_id: str,
    component_type: str,
    data_json: str,
    schema_version: str = "1.0",
) -> None:
    conn = sqlite3.connect(str(path))
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO components "
            "(world_id, entity_id, component_type, data_json, schema_version, "
            "created_at, updated_at) VALUES ('w',?,?,?,?,?,?)",
            (entity_id, component_type, data_json, schema_version, _TS, _TS),
        )
    conn.close()


# ---------------------------------------------------------------------------
# (a) Unknown component type — reported + preserved, never vanished
# ---------------------------------------------------------------------------

def test_unknown_type_component_is_reported_and_preserved(tmp_path: Path) -> None:
    store, path = _saved_store(tmp_path)
    raw = json.dumps({"component_type": "star_chart", "entity_id": "gunnar", "omen": "red moon"})
    _insert_raw_component(path, entity_id="gunnar", component_type="star_chart", data_json=raw)

    loaded, report = store.load_with_report("w")

    assert not report.ok
    assert report.loaded_components == 2  # name + health still loaded
    assert len(report.failures) == 1
    failure = report.failures[0]
    assert failure.entity_id == "gunnar"
    assert failure.component_type == "star_chart"
    assert failure.reason == REASON_UNKNOWN_TYPE
    assert failure.raw_payload == raw

    # The healthy world is intact.
    name = loaded.get_component("gunnar", "name")
    assert isinstance(name, NameComponent)
    assert name.name == "Gunnar"

    # The raw payload is preserved in the store's quarantine table…
    quarantined = store.quarantined_components("w")
    assert len(quarantined) == 1
    entry = quarantined[0]
    assert entry["component_type"] == "star_chart"
    assert entry["data_json"] == raw
    assert entry["reason"] == REASON_UNKNOWN_TYPE

    # …and the original row in `components` is untouched.
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute(
            "SELECT data_json FROM components WHERE component_type='star_chart'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None and row[0] == raw


def test_unknown_type_is_logged_at_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    store, path = _saved_store(tmp_path)
    _insert_raw_component(
        path, entity_id="gunnar", component_type="star_chart",
        data_json='{"component_type": "star_chart", "entity_id": "gunnar"}',
    )
    with caplog.at_level(logging.WARNING, logger="wyrdforge.persistence.world_store"):
        store.load("w")
    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("star_chart" in m and REASON_UNKNOWN_TYPE in m for m in messages)
    # Plain load() quarantines too — the report surface is additive,
    # the honesty is not optional.
    assert len(store.quarantined_components("w")) == 1


# ---------------------------------------------------------------------------
# (b) Corrupt payloads — reported + preserved, healthy components load
# ---------------------------------------------------------------------------

def test_invalid_json_payload_is_reported_and_preserved(tmp_path: Path) -> None:
    store, path = _saved_store(tmp_path)
    raw = '{"component_type": "health", "hp": '  # torn write
    _insert_raw_component(path, entity_id="gunnar", component_type="health", data_json=raw)

    loaded, report = store.load_with_report("w")

    assert report.loaded_components == 1  # name only
    assert len(report.failures) == 1
    assert report.failures[0].reason == REASON_INVALID_JSON
    assert report.failures[0].raw_payload == raw
    assert loaded.get_component("gunnar", "health") is None
    assert isinstance(loaded.get_component("gunnar", "name"), NameComponent)
    quarantined = store.quarantined_components("w")
    assert len(quarantined) == 1
    assert quarantined[0]["data_json"] == raw


def test_model_rejected_payload_is_reported_and_preserved(tmp_path: Path) -> None:
    store, path = _saved_store(tmp_path)
    bad = HealthComponent(entity_id="gunnar", hp=80.0).model_dump(mode="json")
    bad["hp"] = "not-a-number"
    raw = json.dumps(bad)
    _insert_raw_component(path, entity_id="gunnar", component_type="health", data_json=raw)

    loaded, report = store.load_with_report("w")

    assert report.loaded_components == 1
    assert len(report.failures) == 1
    assert report.failures[0].reason == REASON_CORRUPT_PAYLOAD
    assert report.failures[0].raw_payload == raw
    assert loaded.get_component("gunnar", "health") is None
    assert isinstance(loaded.get_component("gunnar", "name"), NameComponent)
    assert store.quarantined_components("w")[0]["data_json"] == raw


def test_newer_schema_version_is_refused_and_preserved(tmp_path: Path) -> None:
    store, path = _saved_store(tmp_path)
    good = HealthComponent(entity_id="gunnar", hp=80.0).model_dump_json()
    _insert_raw_component(
        path, entity_id="gunnar", component_type="health",
        data_json=good, schema_version="99.0",
    )

    loaded, report = store.load_with_report("w")

    assert report.loaded_components == 1
    assert len(report.failures) == 1
    failure = report.failures[0]
    assert failure.reason == REASON_VERSION_MISMATCH
    assert failure.stored_schema_version == "99.0"
    assert loaded.get_component("gunnar", "health") is None
    assert store.quarantined_components("w")[0]["reason"] == REASON_VERSION_MISMATCH


# ---------------------------------------------------------------------------
# (c) Pre-A4 saved worlds (schema v1) load with identical state
# ---------------------------------------------------------------------------

_PRE_A4_SCHEMA = """
CREATE TABLE worlds (
    world_id    TEXT PRIMARY KEY,
    world_name  TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE TABLE entities (
    world_id    TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    tags_json   TEXT NOT NULL DEFAULT '[]',
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (world_id, entity_id),
    FOREIGN KEY (world_id) REFERENCES worlds(world_id)
);
CREATE TABLE components (
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
PRAGMA user_version=1;
"""


def _write_pre_a4_db(path: Path) -> None:
    """A genuine pre-A4 file: v1 schema, rows exactly as pre-A4 save() wrote."""
    conn = sqlite3.connect(str(path))
    with conn:
        conn.executescript(_PRE_A4_SCHEMA)
        conn.execute(
            "INSERT INTO worlds VALUES ('w', 'Honesty World', ?)", (_TS,)
        )
        conn.execute(
            "INSERT INTO entities VALUES ('w', 'gunnar', '[\"npc\"]', 1, ?, ?)",
            (_TS, _TS),
        )
        for comp in (
            NameComponent(entity_id="gunnar", name="Gunnar"),
            HealthComponent(entity_id="gunnar", hp=80.0),
        ):
            conn.execute(
                "INSERT INTO components VALUES ('w', 'gunnar', ?, ?, ?, ?, ?)",
                (
                    comp.component_type,
                    comp.model_dump_json(),
                    comp.schema_version,
                    _TS,
                    _TS,
                ),
            )
    conn.close()


def test_pre_a4_world_loads_with_identical_state(tmp_path: Path) -> None:
    path = tmp_path / "legacy_world.db"
    _write_pre_a4_db(path)

    store = WorldStore(path)  # opening migrates v1 -> v2

    conn = sqlite3.connect(str(path))
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        conn.close()
    assert "quarantined_components" in tables

    loaded, report = store.load_with_report("w")
    assert report.ok
    assert report.failures == []
    assert report.loaded_components == 2
    assert loaded.world_name == "Honesty World"
    gunnar = loaded.get_entity("gunnar")
    assert gunnar is not None and gunnar.has_tag("npc")
    name = loaded.get_component("gunnar", "name")
    assert isinstance(name, NameComponent) and name.name == "Gunnar"
    health = loaded.get_component("gunnar", "health")
    assert isinstance(health, HealthComponent) and health.hp == 80.0
    assert store.quarantined_components() == []


def test_world_migration_step_is_exercised_and_not_repeated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "legacy_world.db"
    _write_pre_a4_db(path)

    calls: list[int] = []
    real = ws_mod.WORLD_MIGRATIONS[1]

    def spy(conn: sqlite3.Connection) -> None:
        calls.append(1)
        real(conn)

    monkeypatch.setitem(ws_mod.WORLD_MIGRATIONS, 1, spy)
    WorldStore(path)
    assert calls == [1]
    WorldStore(path)  # already v2 — the step must not run again
    assert calls == [1]


# ---------------------------------------------------------------------------
# (d) Happy path — behaviour-identical, no spurious reports
# ---------------------------------------------------------------------------

def test_happy_path_load_reports_nothing(tmp_path: Path) -> None:
    store, _ = _saved_store(tmp_path)

    loaded, report = store.load_with_report("w")

    assert report.ok
    assert report.failures == []
    assert report.loaded_components == 2
    assert store.quarantined_components() == []
    assert loaded.entity_count() == 1
    health = loaded.get_component("gunnar", "health")
    assert isinstance(health, HealthComponent) and health.hp == 80.0

    # load() returns exactly the same world as before A4.
    plain = store.load("w")
    assert plain.get_component("gunnar", "name").name == "Gunnar"  # type: ignore[union-attr]
    assert store.quarantined_components() == []


# ---------------------------------------------------------------------------
# Component registry with versions
# ---------------------------------------------------------------------------

def test_registry_carries_component_versions() -> None:
    versions = registered_component_versions()
    assert versions["health"] == "1.0"
    assert versions["name"] == "1.0"
    assert get_component_version("health") == "1.0"
    with pytest.raises(KeyError):
        get_component_version("no_such_type")
