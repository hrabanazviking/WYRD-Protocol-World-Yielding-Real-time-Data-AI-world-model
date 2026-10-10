"""Forge tests: prune_quarantine, read_json_state, open_verified_state_db
(Helheim Hardening, slices 4-6) for wyrdforge.hardening.state_io.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path

import pytest

from wyrdforge.hardening import state_io
from wyrdforge.hardening.state_io import (
    CorruptStateError,
    atomic_write_json,
    open_verified_state_db,
    prune_quarantine,
    read_json_state,
)


@pytest.fixture(autouse=True)
def _fresh_announce_ledger():
    state_io._reset_announced()
    yield
    state_io._reset_announced()


def _touch(path: Path, mtime: float) -> Path:
    path.write_bytes(b"quarantined bytes")
    os.utime(path, (mtime, mtime))
    return path


# ---------------------------------------------------------------------------
# prune_quarantine
# ---------------------------------------------------------------------------

def test_prune_keeps_newest_and_returns_count(tmp_path):
    qdir = tmp_path / "quarantine"
    qdir.mkdir()
    base = 1_700_000_000.0
    for i in range(15):
        _touch(qdir / f"old-{i:02d}.db", base + i)  # distinct mtimes

    pruned = prune_quarantine(qdir, keep=10)

    assert pruned == 5
    remaining = sorted(p.name for p in qdir.iterdir())
    assert remaining == [f"old-{i:02d}.db" for i in range(5, 15)]  # 10 newest


def test_prune_keep_zero_removes_everything(tmp_path):
    qdir = tmp_path / "quarantine"
    qdir.mkdir()
    for i in range(3):
        _touch(qdir / f"f{i}.db", 1_700_000_000.0 + i)
    assert prune_quarantine(qdir, keep=0) == 3
    assert list(qdir.iterdir()) == []


def test_prune_keep_larger_than_population_prunes_nothing(tmp_path):
    qdir = tmp_path / "quarantine"
    qdir.mkdir()
    for i in range(3):
        _touch(qdir / f"f{i}.db", 1_700_000_000.0 + i)
    assert prune_quarantine(qdir, keep=10) == 0
    assert len(list(qdir.iterdir())) == 3


def test_prune_negative_keep_raises(tmp_path):
    with pytest.raises(ValueError):
        prune_quarantine(tmp_path, keep=-1)


def test_prune_ignores_subdirectories_and_missing_dir(tmp_path):
    qdir = tmp_path / "quarantine"
    qdir.mkdir()
    (qdir / "subdir").mkdir()
    _touch(qdir / "a.db", 1_700_000_000.0)
    assert prune_quarantine(qdir, keep=0) == 1
    assert (qdir / "subdir").is_dir()  # subdirectories never touched
    assert prune_quarantine(tmp_path / "no-such-dir", keep=5) == 0


# ---------------------------------------------------------------------------
# read_json_state
# ---------------------------------------------------------------------------

def test_read_json_state_round_trip(tmp_path):
    path = tmp_path / "state.json"
    obj = {"entities": 3, "nested": {"a": [1, 2, 3]}}
    atomic_write_json(path, obj)
    assert read_json_state(path) == obj


def test_read_json_state_corrupt_quarantines_and_raises(tmp_path):
    path = tmp_path / "state.json"
    payload = b'{"half-written": tru'
    path.write_bytes(payload)

    with pytest.raises(CorruptStateError) as exc_info:
        read_json_state(path)
    assert exc_info.value.reason == "not-json"
    assert not path.exists()  # moved aside, not left in place
    quarantined = list((tmp_path / "quarantine").glob("state-*.json"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == payload  # bytes preserved


def test_read_json_state_validator_rejection_quarantines(tmp_path):
    path = tmp_path / "state.json"
    obj = {"version": 999}  # valid JSON, wrong content
    atomic_write_json(path, obj)

    def validator(o):
        return isinstance(o, dict) and o.get("version") == 1

    with pytest.raises(CorruptStateError) as exc_info:
        read_json_state(path, validator=validator)
    assert exc_info.value.reason == "invalid-content"
    quarantined = list((tmp_path / "quarantine").glob("state-*.json"))
    assert len(quarantined) == 1
    assert json.loads(quarantined[0].read_text(encoding="utf-8")) == obj


def test_read_json_state_validator_exception_counts_as_rejection(tmp_path):
    path = tmp_path / "state.json"
    atomic_write_json(path, {"ok": True})

    def validator(o):
        raise RuntimeError("validator blew up")

    with pytest.raises(CorruptStateError) as exc_info:
        read_json_state(path, validator=validator)
    assert exc_info.value.reason == "invalid-content"
    assert list((tmp_path / "quarantine").glob("state-*.json"))


def test_read_json_state_accepting_validator_returns_object(tmp_path):
    path = tmp_path / "state.json"
    obj = {"version": 1}
    atomic_write_json(path, obj)
    assert read_json_state(path, validator=lambda o: o.get("version") == 1) == obj
    assert not (tmp_path / "quarantine").exists()  # nothing quarantined


def test_read_json_state_missing_file_raises_not_found(tmp_path):
    # Missing is normal — the caller creates fresh state. read_json_state
    # must not mask it as corruption.
    with pytest.raises(FileNotFoundError):
        read_json_state(tmp_path / "absent.json")


# ---------------------------------------------------------------------------
# open_verified_state_db
# ---------------------------------------------------------------------------

def _build_db(path: Path, rows: int = 300) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.executemany(
        "INSERT INTO t (v) VALUES (?)", [(("x" * 200) + str(i),) for i in range(rows)]
    )
    conn.execute("PRAGMA user_version=1")
    conn.commit()
    conn.close()
    for suffix in ("-wal", "-shm"):  # keep the tamper surface to one file
        try:
            os.remove(str(path) + suffix)
        except OSError:
            pass


def _tamper_mid_file(path: Path) -> None:
    """Flip one byte inside a data page: the header still parses (so the
    guarded open succeeds) but integrity_check reports corruption."""
    data = bytearray(path.read_bytes())
    data[16394] ^= 0xFF
    path.write_bytes(bytes(data))
    # sanity: the tamper must fail integrity_check on a direct open,
    # otherwise this test would prove nothing about the verified path.
    conn = sqlite3.connect(str(path))
    try:
        rows = conn.execute("PRAGMA integrity_check").fetchall()
        problems = [r[0] for r in rows if str(r[0]).lower() != "ok"]
    except sqlite3.Error:
        problems = ["integrity_check raised"]
    finally:
        conn.close()
    assert problems, "tamper did not corrupt the DB — test setup is broken"


def test_verified_open_healthy_file_not_recovered(tmp_path):
    path = tmp_path / "healthy.db"
    conn, recovered = open_verified_state_db(path, current_version=1)
    assert recovered is False
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        conn.close()
    # second open of the now-existing healthy file: still not recovered
    conn2, recovered2 = open_verified_state_db(path, current_version=1)
    assert recovered2 is False
    conn2.close()
    assert not (tmp_path / "quarantine").exists()


def test_verified_open_tampered_file_recovers_and_preserves_bytes(tmp_path, caplog):
    path = tmp_path / "store.db"
    _build_db(path)
    _tamper_mid_file(path)

    with caplog.at_level(logging.WARNING, logger="wyrdforge.hardening.state_io"):
        conn, recovered = open_verified_state_db(path, current_version=1)

    assert recovered is True
    try:
        # fresh, usable DB at the original path
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
        conn.execute("CREATE TABLE probe (id INTEGER)")
        conn.execute("INSERT INTO probe VALUES (1)")
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM probe").fetchone()[0] == 1
    finally:
        conn.close()

    # the tampered bytes were preserved under quarantine/, not deleted
    quarantined = list((tmp_path / "quarantine").glob("store-*.db"))
    assert len(quarantined) == 1
    qconn = sqlite3.connect(str(quarantined[0]))
    try:
        qrows = qconn.execute("PRAGMA integrity_check").fetchall()
        qproblems = [r[0] for r in qrows if str(r[0]).lower() != "ok"]
    except sqlite3.Error:
        qproblems = ["integrity_check raised"]
    finally:
        qconn.close()
    assert qproblems, "quarantined file should still be the corrupt one"

    # the quarantine announcement names the integrity failure
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("integrity-failed" in r.getMessage() for r in warnings)


def test_verified_open_torn_file_still_recovers(tmp_path):
    # A file that cannot even be opened takes the open_or_quarantine path;
    # the verified wrapper must not break that older contract.
    path = tmp_path / "torn.db"
    path.write_bytes(b"\x89garbage\x00\xff" * 64)
    conn, recovered = open_verified_state_db(path, current_version=1)
    assert recovered is True
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        conn.close()
    assert list((tmp_path / "quarantine").glob("torn-*.db"))
