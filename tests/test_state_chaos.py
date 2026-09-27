"""Chaos-test matrix for Track 5 (corrupt-state detection and repair).

Temp dirs only — never live ~/.hermes/state/. Every cell asserts the
behavior documented in docs/state-files.md: every case degrades or
heals, and 0 cases crash the runner.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone

import pytest

from wyrdforge.bridges import verdandi_bridge as vb
from wyrdforge.hardening import state_io
from wyrdforge.persistence.bond_store import PersistentBondStore
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.persistence.world_store import WorldStore


@pytest.fixture(autouse=True)
def _fresh_announce_ledger():
    state_io._reset_announced()
    yield
    state_io._reset_announced()


# ---------------------------------------------------------------------------
# Store matrix — parametrized over the three stores
# ---------------------------------------------------------------------------

_STORES = [
    ("world", WorldStore, lambda s: s.list_worlds()),
    ("memory", PersistentMemoryStore, lambda s: s.count()),
    ("bond", PersistentBondStore, lambda s: s.count_edges()),
]


def _torn_bytes() -> bytes:
    return b"\x89SQL-not-really\x00\xff torn-bytes" * 64


@pytest.mark.parametrize("name,cls,probe", _STORES,
                         ids=[n for n, _, _ in _STORES])
def test_store_missing_file_is_fresh(tmp_path, caplog, name, cls, probe):
    path = tmp_path / f"{name}.db"
    with caplog.at_level(logging.WARNING, logger="wyrdforge.hardening.state_io"):
        store = cls(path)
    assert probe(store) in ([], 0)  # fresh and usable
    assert path.exists()
    # missing is normal — info at most, never a warning
    assert not [r for r in caplog.records
                if r.levelno >= logging.WARNING]


@pytest.mark.parametrize("name,cls,probe", _STORES,
                         ids=[n for n, _, _ in _STORES])
def test_store_empty_file_is_fresh(tmp_path, name, cls, probe):
    path = tmp_path / f"{name}.db"
    path.write_bytes(b"")
    store = cls(path)  # 0-byte file: SQLite-valid empty DB
    assert probe(store) in ([], 0)


@pytest.mark.parametrize("name,cls,probe", _STORES,
                         ids=[n for n, _, _ in _STORES])
def test_store_torn_file_quarantines_and_heals(tmp_path, caplog, name, cls, probe):
    path = tmp_path / f"{name}.db"
    payload = _torn_bytes()
    path.write_bytes(payload)
    with caplog.at_level(logging.WARNING, logger="wyrdforge.hardening.state_io"):
        store = cls(path)  # must not raise
    assert probe(store) in ([], 0)  # fresh DB, run continues
    quarantined = list((tmp_path / "quarantine").glob(f"{name}-*.db"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == payload  # nothing silently dropped
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1  # announced exactly once
    assert "quarantined" in warnings[0].getMessage()


@pytest.mark.parametrize("name,cls,probe", _STORES,
                         ids=[n for n, _, _ in _STORES])
def test_store_newer_schema_quarantines_with_version_named(
        tmp_path, caplog, name, cls, probe):
    path = tmp_path / f"{name}.db"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE legacy (id INTEGER)")
    conn.execute("PRAGMA user_version=999")
    conn.commit()
    conn.close()
    with caplog.at_level(logging.WARNING, logger="wyrdforge.hardening.state_io"):
        store = cls(path)  # must not raise, must not misread
    assert probe(store) in ([], 0)  # fresh DB, never the v999 data
    quarantined = list((tmp_path / "quarantine").glob(f"{name}-*.db"))
    assert len(quarantined) == 1
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "v999" in warnings[0].getMessage()


@pytest.mark.parametrize("name,cls,probe", _STORES,
                         ids=[n for n, _, _ in _STORES])
def test_store_unstamped_db_migrates_to_v1(tmp_path, name, cls, probe):
    # A DB created before versioning existed reads as v0 and is stamped.
    path = tmp_path / f"{name}.db"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE legacy (id INTEGER)")
    conn.commit()
    conn.close()
    store = cls(path)
    assert probe(store) in ([], 0)
    check = sqlite3.connect(str(path))
    try:
        assert check.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        check.close()


# ---------------------------------------------------------------------------
# Reader matrix — graceful degradation, now announced
# ---------------------------------------------------------------------------

def test_hub_state_missing_empty_garbage(tmp_path):
    state_dir = tmp_path / "state"
    assert vb._read_hub_liveness(str(state_dir)) == ("warn", None)
    hub_dir = state_dir / "heilsiðr"
    hub_dir.mkdir(parents=True)
    (hub_dir / "hub.state").write_text("", encoding="utf-8")
    assert vb._read_hub_liveness(str(state_dir)) == ("warn", None)
    (hub_dir / "hub.state").write_text("nonsense-token", encoding="utf-8")
    status, raw = vb._read_hub_liveness(str(state_dir))
    assert status == "warn"  # unknown token degrades, never crashes


def test_queue_depth_counts_torn_files(tmp_path):
    qdir = tmp_path / "queue"
    qdir.mkdir()
    (qdir / "good1.json").write_text(json.dumps({"status": "queued"}))
    (qdir / "good2.json").write_text(json.dumps({"status": "running"}))
    (qdir / "done.json").write_text(json.dumps({"status": "done"}))  # wrong shape
    (qdir / "torn.json").write_text("{not json")
    (qdir / "notes.txt").write_text("ignored")
    depth, torn = vb._read_forge_queue_depth(str(qdir))
    assert depth == 2  # degrade unchanged: only queued/running count
    assert torn == 2    # announced: torn + wrong-shape are now facts


def test_queue_depth_unreadable_dir(tmp_path):
    depth, torn = vb._read_forge_queue_depth(str(tmp_path / "nope"))
    assert (depth, torn) == (None, None)


def test_feed_rate_skips_and_counts_torn_lines(tmp_path):
    feed = tmp_path / "nerve_feed.jsonl"
    now_ts = datetime.now(timezone.utc).timestamp()
    lines = [
        json.dumps({"_ts": now_ts - 60, "type": "utterance"}),
        "{torn line",
        json.dumps({"type": "no-ts-here"}),  # valid JSON, no _ts
        "",
        json.dumps({"_ts": now_ts - 120, "type": "emote"}),
    ]
    feed.write_text("\n".join(lines), encoding="utf-8")
    rate, status, torn = vb._read_nerve_feed_rate(str(feed), now_ts)
    assert rate == pytest.approx(2 / 5.0)  # good lines still counted
    assert torn == 2
    assert status == "ok"


def test_feed_rate_missing_file(tmp_path):
    rate, status, torn = vb._read_nerve_feed_rate(
        str(tmp_path / "missing.jsonl"), 1_700_000_000.0)
    assert rate is None and status == "warn" and torn is None


def test_memory_md_missing_and_empty(tmp_path):
    assert list(vb._bullet_lines(str(tmp_path / "nope.md"))) == []
    empty = tmp_path / "empty.md"
    empty.write_text("", encoding="utf-8")
    assert list(vb._bullet_lines(str(empty))) == []


def test_person_page_malformed_frontmatter_skipped(tmp_path):
    page = tmp_path / "runa.md"
    page.write_text("---\nthis is not a summary line\n---\n", encoding="utf-8")
    at = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    assert vb._parse_person_page(str(page), "runa", at=at) == []


def test_sample_senses_carries_torn_counters(tmp_path):
    qdir = tmp_path / "queue"
    qdir.mkdir()
    (qdir / "torn.json").write_text("{broken", encoding="utf-8")
    feed = tmp_path / "feed.jsonl"
    now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    feed.write_text("{broken\n", encoding="utf-8")
    readings = vb.sample_senses(
        state_dir=str(tmp_path), feed_path=str(feed),
        queue_dir=str(qdir), meminfo_path="/nonexistent", now=now)
    by_metric = {r.metric: r for r in readings}
    assert by_metric["forge_queue_torn_jobs"].value == 1
    assert by_metric["nerve_feed_torn_lines"].value == 1
    # existing senses keep their behavior
    assert by_metric["forge_queue_depth"].value == 0
    assert by_metric["hub_liveness"].status == "warn"
