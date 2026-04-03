"""Tests for MemoryToRAGAdapter — MemoryRecord → RetrievalItem conversion."""
from __future__ import annotations

import tempfile

from wyrdforge.models.micro_rag import RetrievalItem
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.services.memory_to_rag import MemoryToRAGAdapter
from wyrdforge.services.writeback_engine import WritebackEngine


def _setup() -> tuple[PersistentMemoryStore, WritebackEngine, MemoryToRAGAdapter]:
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    engine = WritebackEngine(store)
    adapter = MemoryToRAGAdapter(store)
    return store, engine, adapter


# ---------------------------------------------------------------------------
# get_candidates_by_family
# ---------------------------------------------------------------------------

def test_returns_dict_with_expected_keys() -> None:
    store, engine, adapter = _setup()
    engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="status", fact_value="alive"
    )
    result = adapter.get_candidates_by_family()
    assert isinstance(result, dict)


def test_canonical_family_populated_from_facts() -> None:
    store, engine, adapter = _setup()
    engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="status", fact_value="alive"
    )
    result = adapter.get_candidates_by_family()
    assert "canonical" in result
    assert len(result["canonical"]) >= 1


def test_canonical_items_are_retrieval_items() -> None:
    store, engine, adapter = _setup()
    engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="weapon", fact_value="axe"
    )
    result = adapter.get_candidates_by_family()
    assert all(isinstance(item, RetrievalItem) for item in result["canonical"])


def test_canonical_item_text_contains_fact_info() -> None:
    store, engine, adapter = _setup()
    engine.write_canonical_fact(
        fact_subject_id="sigrid", fact_key="role", fact_value="völva"
    )
    result = adapter.get_candidates_by_family()
    texts = [item.text for item in result["canonical"]]
    assert any("völva" in t for t in texts)


def test_subject_id_filter_restricts_canonical() -> None:
    store, engine, adapter = _setup()
    engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="status", fact_value="alive"
    )
    engine.write_canonical_fact(
        fact_subject_id="sigrid", fact_key="role", fact_value="völva"
    )
    result = adapter.get_candidates_by_family(subject_ids=["gunnar"])
    if "canonical" in result:
        for item in result["canonical"]:
            assert "gunnar" in item.text


def test_quarantined_facts_excluded() -> None:
    store, engine, adapter = _setup()
    r = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="secret", fact_value="hidden", confidence=0.9
    )
    store.quarantine(r.record_id)
    result = adapter.get_candidates_by_family()
    texts = [item.text for item in result.get("canonical", [])]
    assert not any("hidden" in t for t in texts)


def test_recent_family_populated_from_observations() -> None:
    store, engine, adapter = _setup()
    engine.write_observation(title="Gunnar enters", summary="He walked in.")
    result = adapter.get_candidates_by_family()
    assert "recent" in result
    assert len(result["recent"]) >= 1


def test_recent_item_text_contains_summary() -> None:
    store, engine, adapter = _setup()
    engine.write_observation(title="Test obs", summary="Something notable occurred.")
    result = adapter.get_candidates_by_family()
    texts = [item.text for item in result.get("recent", [])]
    assert any("Something notable" in t for t in texts)


def test_bond_excerpt_lines_become_bond_family() -> None:
    _, _, adapter = _setup()
    result = adapter.get_candidates_by_family(
        bond_excerpt_lines=["domain=companion", "status=active", "closeness_index=0.75"]
    )
    assert "bond" in result
    assert len(result["bond"]) == 3


def test_bond_family_items_have_correct_type() -> None:
    _, _, adapter = _setup()
    result = adapter.get_candidates_by_family(bond_excerpt_lines=["domain=companion"])
    for item in result["bond"]:
        assert item.item_type == "bond"


def test_empty_store_returns_empty_families() -> None:
    _, _, adapter = _setup()
    result = adapter.get_candidates_by_family()
    for family_items in result.values():
        assert len(family_items) == 0


# ---------------------------------------------------------------------------
# record_to_item
# ---------------------------------------------------------------------------

def test_record_to_item_canonical() -> None:
    store, engine, adapter = _setup()
    r = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="age", fact_value="35"
    )
    item = adapter.record_to_item(r)
    assert isinstance(item, RetrievalItem)
    assert item.item_type == "canonical_fact"
    assert "gunnar" in item.text


def test_record_to_item_observation() -> None:
    store, engine, adapter = _setup()
    r = engine.write_observation(title="Event", summary="Something happened here.")
    item = adapter.record_to_item(r)
    assert item.item_type == "observation"
    assert "Something happened" in item.text


def test_record_to_item_has_positive_token_cost() -> None:
    store, engine, adapter = _setup()
    r = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="status", fact_value="alive"
    )
    item = adapter.record_to_item(r)
    assert item.token_cost > 0
