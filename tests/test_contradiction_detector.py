"""Tests for ContradictionDetector."""
from __future__ import annotations

import tempfile

import pytest

from wyrdforge.models.common import ApprovalState, WritePolicy
from wyrdforge.models.memory import CanonicalFactRecord, ContradictionRecord
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.runtime.demo_seed import build_seed_fact
from wyrdforge.services.contradiction_detector import ContradictionDetector
from wyrdforge.services.writeback_engine import WritebackEngine


def _setup() -> tuple[PersistentMemoryStore, WritebackEngine, ContradictionDetector]:
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    engine = WritebackEngine(store)
    detector = ContradictionDetector(store)
    return store, engine, detector


# ---------------------------------------------------------------------------
# No conflict cases
# ---------------------------------------------------------------------------

def test_no_conflict_for_first_fact() -> None:
    store, engine, detector = _setup()
    fact = engine.write_canonical_fact(
        fact_subject_id="gunnar",
        fact_key="location",
        fact_value="mead_hall",
    )
    contradictions = detector.check_and_record(fact)
    assert contradictions == []


def test_no_conflict_for_same_value() -> None:
    store, engine, detector = _setup()
    f1 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="faction", fact_value="thornholt"
    )
    store.promote(f1.record_id)
    f2 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="faction", fact_value="thornholt"
    )
    contradictions = detector.check_and_record(f2)
    assert contradictions == []


def test_no_conflict_for_different_keys() -> None:
    store, engine, detector = _setup()
    f1 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="location", fact_value="hall"
    )
    f2 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="faction", fact_value="thornholt"
    )
    contradictions = detector.check_and_record(f2)
    assert contradictions == []


def test_no_conflict_for_different_subjects() -> None:
    store, engine, detector = _setup()
    f1 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="location", fact_value="hall"
    )
    f2 = engine.write_canonical_fact(
        fact_subject_id="sigrid", fact_key="location", fact_value="docks"
    )
    contradictions = detector.check_and_record(f2)
    assert contradictions == []


# ---------------------------------------------------------------------------
# Conflict cases
# ---------------------------------------------------------------------------

def test_conflict_creates_contradiction_record() -> None:
    store, engine, detector = _setup()
    f1 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="location", fact_value="mead_hall",
        confidence=0.8,
    )
    f2 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="location", fact_value="docks",
        confidence=0.9,
    )
    contradictions = detector.check_and_record(f2)
    assert len(contradictions) == 1
    assert isinstance(contradictions[0], ContradictionRecord)


def test_contradiction_record_references_both_facts() -> None:
    store, engine, detector = _setup()
    f1 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="location", fact_value="hall", confidence=0.8
    )
    f2 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="location", fact_value="forge", confidence=0.9
    )
    contradictions = detector.check_and_record(f2)
    payload = contradictions[0].content.structured_payload
    assert payload.claim_a_record_id in (f1.record_id, f2.record_id)
    assert payload.claim_b_record_id in (f1.record_id, f2.record_id)


def test_conflict_quarantines_weaker_record() -> None:
    store, engine, detector = _setup()
    f1 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="location", fact_value="hall", confidence=0.6
    )
    f2 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="location", fact_value="forge", confidence=0.9
    )
    detector.check_and_record(f2)
    # f1 is weaker (confidence 0.6 vs 0.9) — should be quarantined
    loaded_f1 = store.get(f1.record_id)
    assert loaded_f1 is not None
    assert loaded_f1.truth.approval_state == ApprovalState.QUARANTINED


def test_contradiction_persists_to_store() -> None:
    store, engine, detector = _setup()
    f1 = engine.write_canonical_fact(
        fact_subject_id="sigrid", fact_key="role", fact_value="warrior", confidence=0.7
    )
    f2 = engine.write_canonical_fact(
        fact_subject_id="sigrid", fact_key="role", fact_value="volva", confidence=0.9
    )
    detector.check_and_record(f2)
    open_c = detector.find_open_contradictions()
    assert len(open_c) >= 1


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def test_resolve_marks_contradiction_resolved() -> None:
    store, engine, detector = _setup()
    f1 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="status", fact_value="alive", confidence=0.7
    )
    f2 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="status", fact_value="wounded", confidence=0.9
    )
    contradictions = detector.check_and_record(f2)
    c_id = contradictions[0].record_id
    result = detector.resolve(c_id, preferred_record_id=f2.record_id)
    assert result is True
    # After resolution, no more open contradictions for this pair
    open_c = detector.find_open_contradictions()
    assert not any(c.record_id == c_id for c in open_c)


def test_resolve_promotes_preferred_record() -> None:
    store, engine, detector = _setup()
    f1 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="weapon", fact_value="axe", confidence=0.7
    )
    f2 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="weapon", fact_value="sword", confidence=0.9
    )
    contradictions = detector.check_and_record(f2)
    detector.resolve(contradictions[0].record_id, preferred_record_id=f2.record_id)
    loaded = store.get(f2.record_id)
    assert loaded is not None
    assert loaded.truth.approval_state == ApprovalState.APPROVED
