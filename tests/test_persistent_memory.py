"""Tests for PersistentMemoryStore (SQLite-backed memory)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from wyrdforge.models.common import ApprovalState, StoreName, WritePolicy
from wyrdforge.models.memory import CanonicalFactRecord, ObservationRecord
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.runtime.demo_seed import build_seed_fact


def _store() -> PersistentMemoryStore:
    return PersistentMemoryStore(tempfile.mktemp(suffix=".db"))


def _seed_fact(tenant: str = "test", system: str = "wyrd") -> CanonicalFactRecord:
    r = build_seed_fact()
    r.tenant_id = tenant
    r.system_id = system
    return r


# ---------------------------------------------------------------------------
# Add / get
# ---------------------------------------------------------------------------

def test_add_and_get_round_trip() -> None:
    store = _store()
    record = _seed_fact()
    store.add(record)
    loaded = store.get(record.record_id)
    assert loaded is not None
    assert loaded.record_id == record.record_id


def test_get_returns_correct_subtype() -> None:
    store = _store()
    record = _seed_fact()
    store.add(record)
    loaded = store.get(record.record_id)
    assert isinstance(loaded, CanonicalFactRecord)


def test_get_missing_returns_none() -> None:
    store = _store()
    assert store.get("nonexistent_id") is None


def test_get_increments_access_count() -> None:
    store = _store()
    record = _seed_fact()
    store.add(record)
    store.get(record.record_id)
    loaded = store.get(record.record_id)
    assert loaded is not None
    assert loaded.lifecycle.access_count >= 1


def test_add_replaces_existing_record() -> None:
    store = _store()
    record = _seed_fact()
    store.add(record)
    record.truth.confidence = 0.99
    store.add(record)
    loaded = store.get(record.record_id)
    assert loaded is not None
    assert loaded.truth.confidence == 0.99


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def test_delete_existing_record() -> None:
    store = _store()
    record = _seed_fact()
    store.add(record)
    result = store.delete(record.record_id)
    assert result is True
    assert store.get(record.record_id) is None


def test_delete_missing_returns_false() -> None:
    store = _store()
    assert store.delete("ghost") is False


# ---------------------------------------------------------------------------
# all() / count()
# ---------------------------------------------------------------------------

def test_all_returns_all_records() -> None:
    store = _store()
    for i in range(3):
        r = _seed_fact()
        r.record_id = f"rec_{i}"
        store.add(r)
    assert len(store.all()) == 3


def test_all_filters_by_store() -> None:
    store = _store()
    r = _seed_fact()
    store.add(r)
    mimir_records = store.all(store=StoreName.MIMIR.value)
    other_records = store.all(store=StoreName.HUGIN.value)
    assert len(mimir_records) >= 1
    assert len(other_records) == 0


def test_count() -> None:
    store = _store()
    assert store.count() == 0
    store.add(_seed_fact())
    assert store.count() == 1


def test_count_by_store() -> None:
    store = _store()
    store.add(_seed_fact())
    assert store.count(store=StoreName.MIMIR.value) == 1
    assert store.count(store=StoreName.HUGIN.value) == 0


# ---------------------------------------------------------------------------
# search()
# ---------------------------------------------------------------------------

def test_search_finds_matching_record() -> None:
    store = _store()
    record = _seed_fact()
    store.add(record)
    results = store.search("calm mystical guide")
    assert len(results) >= 1


def test_search_returns_empty_for_no_match() -> None:
    store = _store()
    store.add(_seed_fact())
    results = store.search("xyzzy_impossible_query_term_1234")
    assert results == []


def test_search_respects_limit() -> None:
    store = _store()
    for i in range(5):
        r = _seed_fact()
        r.record_id = f"rec_{i}"
        store.add(r)
    results = store.search("calm", limit=2)
    assert len(results) <= 2


def test_search_filters_by_store() -> None:
    store = _store()
    store.add(_seed_fact())
    results_mimir = store.search("calm", store=StoreName.MIMIR.value)
    results_hugin = store.search("calm", store=StoreName.HUGIN.value)
    assert len(results_mimir) >= 1
    assert len(results_hugin) == 0


# ---------------------------------------------------------------------------
# promote() / quarantine()
# ---------------------------------------------------------------------------

def test_promote_sets_approved_and_canonical() -> None:
    store = _store()
    record = _seed_fact()
    store.add(record)
    promoted = store.promote(record.record_id)
    assert promoted.truth.approval_state == ApprovalState.APPROVED
    assert promoted.lifecycle.write_policy == WritePolicy.CANONICAL


def test_quarantine_sets_quarantined_state() -> None:
    store = _store()
    record = _seed_fact()
    store.add(record)
    quarantined = store.quarantine(record.record_id)
    assert quarantined.truth.approval_state == ApprovalState.QUARANTINED
    assert quarantined.governance.allowed_for_runtime is False


def test_promote_missing_raises() -> None:
    store = _store()
    with pytest.raises(KeyError):
        store.promote("ghost")


def test_quarantine_persists_across_reload() -> None:
    store = _store()
    record = _seed_fact()
    store.add(record)
    store.quarantine(record.record_id)
    loaded = store.get(record.record_id)
    assert loaded is not None
    assert loaded.truth.approval_state == ApprovalState.QUARANTINED


# ---------------------------------------------------------------------------
# list_pending_promotion() / list_by_record_type()
# ---------------------------------------------------------------------------

def test_list_pending_promotion_finds_promotable() -> None:
    store = _store()
    record = _seed_fact()
    record.lifecycle.write_policy = WritePolicy.PROMOTABLE
    store.add(record)
    pending = store.list_pending_promotion()
    assert any(r.record_id == record.record_id for r in pending)


def test_list_by_record_type() -> None:
    store = _store()
    store.add(_seed_fact())
    facts = store.list_by_record_type("canonical_fact")
    assert len(facts) >= 1
    assert all(r.record_type == "canonical_fact" for r in facts)


def test_integrity_check_passes() -> None:
    store = _store()
    store.add(_seed_fact())
    assert store.integrity_check() is True
