"""Tests for PersistentBondStore — SQLite persistence of bond graph data."""
from __future__ import annotations

import tempfile

import pytest

from wyrdforge.models.bond import BondDomain, BondEdge, BondStatus, Hurt, Vow, VowState
from wyrdforge.persistence.bond_store import PersistentBondStore
from wyrdforge.services.bond_graph_service import BondGraphService


def _store() -> PersistentBondStore:
    return PersistentBondStore(tempfile.mktemp(suffix=".db"))


def _edge(bond_id: str = "bond-001") -> BondEdge:
    return BondEdge(
        bond_id=bond_id,
        entity_a="user:volmarr",
        entity_b="persona:sigrid",
        domain=BondDomain.COMPANION,
    )


def _vow(bond_id: str = "bond-001", vow_id: str = "vow-001") -> Vow:
    return Vow(
        vow_id=vow_id,
        bond_id=bond_id,
        vow_text="I will stand by you through storm and fire.",
        vow_kind="loyalty",
        created_from_record_id="rec-001",
    )


def _hurt(bond_id: str = "bond-001", hurt_id: str = "hurt-001") -> Hurt:
    return Hurt(
        hurt_id=hurt_id,
        bond_id=bond_id,
        source_event_id="evt-001",
        hurt_kind="neglect",
        severity="low",
    )


# ---------------------------------------------------------------------------
# BondEdge — save / load / all
# ---------------------------------------------------------------------------

def test_save_and_load_edge_roundtrip() -> None:
    store = _store()
    edge = _edge()
    store.save_edge(edge)
    loaded = store.load_edge(edge.bond_id)
    assert loaded is not None
    assert loaded.bond_id == edge.bond_id


def test_load_missing_edge_returns_none() -> None:
    store = _store()
    assert store.load_edge("nonexistent") is None


def test_save_edge_replaces_on_update() -> None:
    store = _store()
    edge = _edge()
    store.save_edge(edge)
    edge.status = BondStatus.ACTIVE
    store.save_edge(edge)
    loaded = store.load_edge(edge.bond_id)
    assert loaded is not None
    assert loaded.status == BondStatus.ACTIVE


def test_all_edges_returns_all() -> None:
    store = _store()
    store.save_edge(_edge("b1"))
    store.save_edge(_edge("b2"))
    assert len(store.all_edges()) == 2


def test_count_edges() -> None:
    store = _store()
    assert store.count_edges() == 0
    store.save_edge(_edge())
    assert store.count_edges() == 1


def test_delete_edge_removes_it() -> None:
    store = _store()
    store.save_edge(_edge())
    result = store.delete_edge("bond-001")
    assert result is True
    assert store.load_edge("bond-001") is None


def test_delete_missing_edge_returns_false() -> None:
    store = _store()
    assert store.delete_edge("ghost") is False


def test_edges_for_entity_finds_matches() -> None:
    store = _store()
    store.save_edge(_edge("b1"))
    results = store.edges_for_entity("user:volmarr")
    assert len(results) == 1


def test_edges_for_entity_empty_for_unknown() -> None:
    store = _store()
    store.save_edge(_edge())
    assert store.edges_for_entity("nobody") == []


# ---------------------------------------------------------------------------
# Vow
# ---------------------------------------------------------------------------

def test_save_and_load_vow_roundtrip() -> None:
    store = _store()
    vow = _vow()
    store.save_vow(vow)
    loaded = store.load_vow(vow.vow_id)
    assert loaded is not None
    assert loaded.vow_text == vow.vow_text


def test_load_missing_vow_returns_none() -> None:
    store = _store()
    assert store.load_vow("ghost") is None


def test_vows_for_bond_returns_correct() -> None:
    store = _store()
    store.save_vow(_vow(bond_id="b1", vow_id="v1"))
    store.save_vow(_vow(bond_id="b2", vow_id="v2"))
    results = store.vows_for_bond("b1")
    assert len(results) == 1
    assert results[0].vow_id == "v1"


def test_count_vows() -> None:
    store = _store()
    assert store.count_vows() == 0
    store.save_vow(_vow())
    assert store.count_vows() == 1


# ---------------------------------------------------------------------------
# Hurt
# ---------------------------------------------------------------------------

def test_save_and_load_hurt_roundtrip() -> None:
    store = _store()
    hurt = _hurt()
    store.save_hurt(hurt)
    loaded = store.load_hurt(hurt.hurt_id)
    assert loaded is not None
    assert loaded.hurt_kind == "neglect"


def test_hurts_for_bond_returns_correct() -> None:
    store = _store()
    store.save_hurt(_hurt(bond_id="b1", hurt_id="h1"))
    store.save_hurt(_hurt(bond_id="b2", hurt_id="h2"))
    results = store.hurts_for_bond("b1")
    assert len(results) == 1


def test_count_hurts() -> None:
    store = _store()
    assert store.count_hurts() == 0
    store.save_hurt(_hurt())
    assert store.count_hurts() == 1


# ---------------------------------------------------------------------------
# load_into_service
# ---------------------------------------------------------------------------

def test_load_into_service_restores_edges() -> None:
    store = _store()
    store.save_edge(_edge("bond-A"))
    store.save_edge(_edge("bond-B"))
    service = BondGraphService()
    store.load_into_service(service)
    assert "bond-A" in service.edges
    assert "bond-B" in service.edges


def test_load_into_service_restores_vows() -> None:
    store = _store()
    store.save_vow(_vow(bond_id="bond-001", vow_id="vow-X"))
    service = BondGraphService()
    store.load_into_service(service)
    assert "vow-X" in service.vows


def test_delete_edge_also_removes_associated_vows_and_hurts() -> None:
    store = _store()
    store.save_edge(_edge("bond-001"))
    store.save_vow(_vow(bond_id="bond-001"))
    store.save_hurt(_hurt(bond_id="bond-001"))
    store.delete_edge("bond-001")
    assert store.vows_for_bond("bond-001") == []
    assert store.hurts_for_bond("bond-001") == []
