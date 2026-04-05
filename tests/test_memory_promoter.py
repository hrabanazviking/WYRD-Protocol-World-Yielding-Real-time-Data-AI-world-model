"""Tests for MemoryPromoter — scoring, eligibility, promotion passes, decay."""
from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from wyrdforge.models.common import RetentionClass, WritePolicy
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.runtime.demo_seed import build_seed_fact
from wyrdforge.services.memory_promoter import MemoryPromoter


def _store() -> PersistentMemoryStore:
    return PersistentMemoryStore(tempfile.mktemp(suffix=".db"))


def _promoter(store: PersistentMemoryStore) -> MemoryPromoter:
    return MemoryPromoter(store, config_path=None)


# ---------------------------------------------------------------------------
# score_for_promotion()
# ---------------------------------------------------------------------------

def test_score_returns_float_in_range() -> None:
    store = _store()
    record = build_seed_fact()
    store.add(record)
    promoter = _promoter(store)
    score = promoter.score_for_promotion(record)
    assert 0.0 <= score <= 1.0


def test_high_confidence_raises_score() -> None:
    store = _store()
    promoter = _promoter(store)
    low = build_seed_fact()
    low.record_id = "low_conf"
    low.truth.confidence = 0.3
    high = build_seed_fact()
    high.record_id = "high_conf"
    high.truth.confidence = 0.95
    store.add(low)
    store.add(high)
    assert promoter.score_for_promotion(high) > promoter.score_for_promotion(low)


def test_access_count_raises_score() -> None:
    store = _store()
    promoter = _promoter(store)
    r1 = build_seed_fact()
    r1.record_id = "r1"
    r1.lifecycle.access_count = 0
    r2 = build_seed_fact()
    r2.record_id = "r2"
    r2.lifecycle.access_count = 5
    store.add(r1)
    store.add(r2)
    assert promoter.score_for_promotion(r2) > promoter.score_for_promotion(r1)


# ---------------------------------------------------------------------------
# is_eligible()
# ---------------------------------------------------------------------------

def test_low_confidence_not_eligible() -> None:
    store = _store()
    promoter = _promoter(store)
    record = build_seed_fact()
    record.truth.confidence = 0.3   # below threshold
    record.lifecycle.access_count = 5
    assert promoter.is_eligible(record) is False


def test_low_access_count_not_eligible() -> None:
    store = _store()
    promoter = _promoter(store)
    record = build_seed_fact()
    record.truth.confidence = 0.95
    record.lifecycle.access_count = 0   # below min
    assert promoter.is_eligible(record) is False


def test_already_canonical_not_eligible() -> None:
    store = _store()
    promoter = _promoter(store)
    record = build_seed_fact()
    record.truth.confidence = 0.95
    record.lifecycle.access_count = 5
    record.lifecycle.write_policy = WritePolicy.CANONICAL
    assert promoter.is_eligible(record) is False


def test_quarantined_not_eligible() -> None:
    store = _store()
    promoter = _promoter(store)
    record = build_seed_fact()
    record.truth.confidence = 0.95
    record.lifecycle.access_count = 5
    store.add(record)
    store.quarantine(record.record_id)
    loaded = store.get(record.record_id)
    assert loaded is not None
    assert promoter.is_eligible(loaded) is False


def test_eligible_record_passes_all_checks() -> None:
    store = _store()
    promoter = _promoter(store)
    record = build_seed_fact()
    record.truth.confidence = 0.95
    record.lifecycle.access_count = 5
    record.lifecycle.write_policy = WritePolicy.EPHEMERAL
    assert promoter.is_eligible(record) is True


# ---------------------------------------------------------------------------
# promote_if_eligible()
# ---------------------------------------------------------------------------

def test_promote_if_eligible_promotes_qualifying_record() -> None:
    store = _store()
    promoter = _promoter(store)
    record = build_seed_fact()
    record.truth.confidence = 0.95
    record.lifecycle.access_count = 10
    record.retrieval.default_priority = 0.9
    record.lifecycle.write_policy = WritePolicy.EPHEMERAL
    store.add(record)
    # Access it to set last_accessed_at
    store.get(record.record_id)
    result = promoter.promote_if_eligible(record.record_id)
    assert result is True
    updated = store.get(record.record_id)
    assert updated is not None
    assert updated.lifecycle.write_policy == WritePolicy.PROMOTABLE


def test_promote_if_eligible_skips_low_confidence() -> None:
    store = _store()
    promoter = _promoter(store)
    record = build_seed_fact()
    record.truth.confidence = 0.3
    store.add(record)
    result = promoter.promote_if_eligible(record.record_id)
    assert result is False


def test_run_promotion_pass_returns_count() -> None:
    store = _store()
    promoter = _promoter(store)
    # Add a high-quality record
    r = build_seed_fact()
    r.truth.confidence = 0.95
    r.lifecycle.access_count = 10
    r.retrieval.default_priority = 0.9
    r.lifecycle.write_policy = WritePolicy.PROMOTABLE  # makes it appear in pending
    store.add(r)
    store.get(r.record_id)  # set last_accessed_at
    count = promoter.run_promotion_pass()
    assert isinstance(count, int)
    assert count >= 0


# ---------------------------------------------------------------------------
# decay_stale_records()
# ---------------------------------------------------------------------------

def test_decay_reduces_confidence_on_stale_record() -> None:
    store = _store()
    promoter = _promoter(store)
    record = build_seed_fact()
    record.truth.confidence = 0.8
    record.lifecycle.retention_class = RetentionClass.SHORT
    # Backdate last_accessed_at to 60 days ago (beyond 30-day stale window)
    old_time = datetime.now(timezone.utc) - timedelta(days=60)
    record.lifecycle.last_accessed_at = old_time
    store.add(record)
    decayed = promoter.decay_stale_records()
    assert decayed >= 1
    updated = store.get(record.record_id)
    assert updated is not None
    assert updated.truth.confidence < 0.8


def test_decay_dry_run_does_not_write() -> None:
    store = _store()
    promoter = _promoter(store)
    record = build_seed_fact()
    record.truth.confidence = 0.8
    record.lifecycle.retention_class = RetentionClass.SHORT
    old_time = datetime.now(timezone.utc) - timedelta(days=60)
    record.lifecycle.last_accessed_at = old_time
    store.add(record)
    promoter.decay_stale_records(dry_run=True)
    loaded = store.get(record.record_id)
    assert loaded is not None
    assert loaded.truth.confidence == 0.8  # unchanged


def test_decay_skips_immutable_records() -> None:
    store = _store()
    promoter = _promoter(store)
    record = build_seed_fact()
    record.truth.confidence = 0.8
    record.lifecycle.write_policy = WritePolicy.IMMUTABLE
    record.lifecycle.retention_class = RetentionClass.SHORT
    old_time = datetime.now(timezone.utc) - timedelta(days=60)
    record.lifecycle.last_accessed_at = old_time
    store.add(record)
    decayed = promoter.decay_stale_records()
    assert decayed == 0
    loaded = store.get(record.record_id)
    assert loaded is not None
    assert loaded.truth.confidence == 0.8
