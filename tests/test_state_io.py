"""Unit tests for wyrdforge.hardening.state_io (Track 5).

Covers the helper itself: quarantine layout/naming/companions,
announce-once semantics, strict-open version handling, migration
ordering, unknown-version rejection, and the atomic JSON writer.
The store-level chaos matrix lives in test_state_chaos.py.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from pathlib import Path

import pytest

from wyrdforge.hardening import state_io
from wyrdforge.hardening.state_io import (
    CorruptStateError,
    atomic_write_json,
    open_or_quarantine,
    open_state_db,
    quarantine_file,
)


@pytest.fixture(autouse=True)
def _fresh_announce_ledger():
    state_io._reset_announced()
    yield
    state_io._reset_announced()


@pytest.fixture()
def tmp_state(tmp_path):
    return tmp_path


# ---------------------------------------------------------------------------
# quarantine_file
# ---------------------------------------------------------------------------

def test_quarantine_layout_naming_and_companions(tmp_state, caplog):
    src = tmp_state / "wyrd_hermes.db"
    payload = b"\x00\x01garbage-not-a-database\xff"
    src.write_bytes(payload)
    (tmp_state / "wyrd_hermes.db-wal").write_bytes(b"wal-bytes")
    (tmp_state / "wyrd_hermes.db-shm").write_bytes(b"shm-bytes")

    with caplog.at_level(logging.WARNING, logger="wyrdforge.hardening.state_io"):
        dest = quarantine_file(src)

    assert dest.parent == tmp_state / "quarantine"
    assert re.fullmatch(r"wyrd_hermes-\d{8}-\d{6}\.db", dest.name), dest.name
    assert dest.read_bytes() == payload  # byte-identical, nothing dropped
    assert not src.exists()
    # companions moved alongside, same naming
    assert (dest.parent / (dest.name + "-wal")).read_bytes() == b"wal-bytes"
    assert (dest.parent / (dest.name + "-shm")).read_bytes() == b"shm-bytes"
    assert not (tmp_state / "wyrd_hermes.db-wal").exists()
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "quarantined" in warnings[0].getMessage()


def test_quarantine_announces_once_per_path_per_process(tmp_state, caplog):
    src = tmp_state / "store.db"
    with caplog.at_level(logging.WARNING, logger="wyrdforge.hardening.state_io"):
        src.write_bytes(b"bad-1")
        quarantine_file(src)
        src.write_bytes(b"bad-2")
        quarantine_file(src)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    quarantined = list((tmp_state / "quarantine").glob("store-*.db"))
    assert len(quarantined) == 2  # both preserved, no overwrite


# ---------------------------------------------------------------------------
# open_state_db — strict open
# ---------------------------------------------------------------------------

def test_open_missing_creates_and_stamps(tmp_state):
    path = tmp_state / "fresh.db"
    conn = open_state_db(path, current_version=1)
    try:
        assert path.exists()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        conn.close()


def test_open_current_version_passes_through(tmp_state):
    path = tmp_state / "v1.db"
    conn = open_state_db(path, current_version=1)
    conn.close()
    conn2 = open_state_db(path, current_version=1)
    try:
        assert conn2.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        conn2.close()


def test_open_torn_raises_not_a_database(tmp_state):
    path = tmp_state / "torn.db"
    path.write_bytes(b"\x89garbage\x00\xff" * 64)
    with pytest.raises(CorruptStateError) as ei:
        open_state_db(path, current_version=1)
    assert ei.value.reason == "not-a-database"
    assert ei.value.path == path


def test_open_empty_file_treated_as_fresh(tmp_state):
    # SQLite treats a 0-byte file as a valid empty DB — same as missing.
    path = tmp_state / "empty.db"
    path.write_bytes(b"")
    conn = open_state_db(path, current_version=1)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        conn.close()


def test_open_unstamped_migrates_0_to_1(tmp_state):
    path = tmp_state / "old.db"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    # user_version reads 0 — a DB from before versioning existed.
    conn2 = open_state_db(path, current_version=1)
    try:
        assert conn2.execute("PRAGMA user_version").fetchone()[0] == 1
        # the old table survived the stamp
        assert conn2.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='t'"
        ).fetchone() is not None
    finally:
        conn2.close()


def test_migrations_run_in_order(tmp_state):
    order: list[int] = []

    def step0(conn):
        order.append(0)
        conn.execute("CREATE TABLE m0 (id INTEGER)")

    def step1(conn):
        order.append(1)
        conn.execute("CREATE TABLE m1 (id INTEGER)")

    path = tmp_state / "mig.db"
    conn = sqlite3.connect(str(path))
    conn.commit()
    conn.close()  # v0
    opened = open_state_db(
        path, current_version=2, migrations={0: step0, 1: step1}
    )
    try:
        assert order == [0, 1]
        assert opened.execute("PRAGMA user_version").fetchone()[0] == 2
    finally:
        opened.close()


def test_failing_migration_raises_unmigratable(tmp_state):
    def boom(conn):
        raise RuntimeError("ddl exploded")

    path = tmp_state / "badmig.db"
    sqlite3.connect(str(path)).close()  # v0
    with pytest.raises(CorruptStateError) as ei:
        open_state_db(path, current_version=1, migrations={0: boom})
    assert ei.value.reason == "unmigratable"


def test_open_newer_version_raises_unknown_version(tmp_state):
    path = tmp_state / "future.db"
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA user_version=999")
    conn.commit()
    conn.close()
    with pytest.raises(CorruptStateError) as ei:
        open_state_db(path, current_version=1)
    assert ei.value.reason == "unknown-version"
    assert "v999" in ei.value.detail and "v1" in ei.value.detail


# ---------------------------------------------------------------------------
# open_or_quarantine — the call-site API
# ---------------------------------------------------------------------------

def test_open_or_quarantine_recovers_from_torn(tmp_state, caplog):
    path = tmp_state / "store.db"
    payload = b"definitely not sqlite" * 32
    path.write_bytes(payload)
    with caplog.at_level(logging.WARNING, logger="wyrdforge.hardening.state_io"):
        conn, recovered = open_or_quarantine(path, current_version=1)
    assert recovered is True
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
        conn.execute("CREATE TABLE ok (id INTEGER)")
    finally:
        conn.close()
    quarantined = list((tmp_state / "quarantine").glob("store-*.db"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == payload
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1  # announce once


def test_open_or_quarantine_recovers_from_newer_version(tmp_state):
    path = tmp_state / "future.db"
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA user_version=999")
    conn.commit()
    conn.close()
    conn2, recovered = open_or_quarantine(path, current_version=1)
    assert recovered is True
    try:
        assert conn2.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        conn2.close()
    assert list((tmp_state / "quarantine").glob("future-*.db"))


def test_open_or_quarantine_healthy_path_not_recovered(tmp_state):
    path = tmp_state / "healthy.db"
    conn, recovered = open_or_quarantine(path, current_version=1)
    assert recovered is False
    conn.close()
    conn2, recovered2 = open_or_quarantine(path, current_version=1)
    assert recovered2 is False
    conn2.close()
    assert not (tmp_state / "quarantine").exists()


def test_second_corrupt_open_same_process_stays_silent(tmp_state, caplog):
    # Forge-queue precedent: the first corrupt open announces, the next
    # drain is silent about it.
    path = tmp_state / "noisy.db"
    with caplog.at_level(logging.WARNING, logger="wyrdforge.hardening.state_io"):
        path.write_bytes(b"bad")
        open_or_quarantine(path, current_version=1)[0].close()
        path.write_bytes(b"bad again")
        open_or_quarantine(path, current_version=1)[0].close()
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1


# ---------------------------------------------------------------------------
# atomic_write_json — the blessed path
# ---------------------------------------------------------------------------

def test_atomic_write_json_round_trip(tmp_state):
    path = tmp_state / "state.json"
    obj = {"entities": 3, "beliefs": ["sky is blue"]}
    atomic_write_json(path, obj)
    assert json.loads(path.read_text(encoding="utf-8")) == obj


def test_atomic_write_json_no_partial_on_midstream_failure(tmp_state, monkeypatch):
    path = tmp_state / "state.json"
    path.write_text(json.dumps({"old": True}), encoding="utf-8")

    def boom_replace(src, dst):
        raise OSError("disk exploded mid-replace")

    monkeypatch.setattr(os, "replace", boom_replace)
    with pytest.raises(OSError, match="disk exploded"):
        atomic_write_json(path, {"new": True})
    # the old file is untouched, and no temp file leaked
    assert json.loads(path.read_text(encoding="utf-8")) == {"old": True}
    assert list(tmp_state.glob("state.json.*.tmp")) == []


def test_open_state_db_directory_at_path_raises_not_crashes(tmp_state):
    """A directory where the DB should be is corruption, not a crash.

    Pins audit F2: sqlite3.connect() lives inside the guarded try, so
    the OperationalError becomes CorruptStateError('not-a-database')
    and the caller takes the quarantine path.
    """
    blocker = tmp_state / "store.db"
    blocker.mkdir()
    with pytest.raises(CorruptStateError) as exc_info:
        open_state_db(blocker, current_version=1)
    assert exc_info.value.reason == "not-a-database"
