"""Phase D3 — salience & filtered recall pinning tests.

Design under test (roadmap §5.3, ``oracle/salience.py`` +
``PassiveOracle.recent_observations`` / ``recall_by_salience``):

* Doc 04's ask: recent observations filtered by place and/or kind,
  newest first, with a limit — an empty filter result is empty,
  never a fallback to the unfiltered set.
* Salience = 0.45*recency + 0.30*bond + 0.25*novelty, every factor
  in [0, 1] and carried on the result next to the score — the
  ranking is transparent, never an opaque rank. Recency decays
  exponentially at an INJECTED ``now`` (no hidden wall clock);
  bond is ``BondEdge.closeness_index()`` toward the focus entity
  (neutral 0.5 when unknown — no bond service, no focus, or no
  edge); novelty is derived from the record history itself
  (1/(1 + earlier same-(kind, place) count)).
* Ordering is total and deterministic: score desc, observed_at
  desc, record_id asc. The writer-asserted
  ``ObservationPayload.salience`` field plays no part.
* Opt-in only: the unranked query stays newest-first and the
  context packet's default observation order is byte the pre-D3
  behaviour; salience ordering enters the packet only via
  ``rank_by_salience=True``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from wyrdforge.ecs.world import World
from wyrdforge.models.bond import BondDomain, BondEdge, BondVector
from wyrdforge.models.common import (
    Audit,
    EntityScope,
    Governance,
    Lifecycle,
    Provenance,
    RetrievalMeta,
    RetentionClass,
    TruthMeta,
    WritePolicy,
)
from wyrdforge.models.memory import (
    ObservationContent,
    ObservationKind,
    ObservationPayload,
    ObservationRecord,
)
from wyrdforge.oracle import PassiveOracle
from wyrdforge.oracle.salience import (
    NEUTRAL_BOND_STRENGTH,
    WEIGHT_BOND,
    WEIGHT_NOVELTY,
    WEIGHT_RECENCY,
)
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.services.bond_graph_service import BondGraphService

UTC = timezone.utc
T0 = datetime(2026, 10, 29, 12, 0, 0, tzinfo=UTC)


def _obs(
    record_id: str,
    *,
    kind: ObservationKind = ObservationKind.UTTERANCE,
    at: datetime = T0,
    place: str | None = "hall",
    speaker: str | None = None,
    participants: list[str] | None = None,
) -> ObservationRecord:
    return ObservationRecord(
        record_id=record_id,
        tenant_id="test",
        system_id="wyrd",
        entity_scope=EntityScope(),
        content=ObservationContent(
            title=record_id,
            summary=f"summary of {record_id}",
            structured_payload=ObservationPayload(
                observation_kind=kind,
                speaker_id=speaker,
                participants=participants or [],
                observed_at=at,
                place_id=place,
            ),
        ),
        truth=TruthMeta(confidence=0.8),
        provenance=Provenance(
            source_type="test",
            source_ref="test://salience",
            extracted_at=at,
            extracted_by="salience-test",
        ),
        lifecycle=Lifecycle(
            write_policy=WritePolicy.EPHEMERAL, retention_class=RetentionClass.SHORT
        ),
        retrieval=RetrievalMeta(lexical_terms=[record_id], default_priority=0.5),
        governance=Governance(),
        audit=Audit(
            created_at=at,
            updated_at=at,
            created_by_agent="salience-test",
            updated_by_agent="salience-test",
        ),
    )


def _store(tmp_path, records: list[ObservationRecord]) -> PersistentMemoryStore:
    store = PersistentMemoryStore(tmp_path / "memory.db")
    for record in records:
        store.add(record)
    return store


def _oracle(store: PersistentMemoryStore, bonds: BondGraphService | None = None) -> PassiveOracle:
    return PassiveOracle(World("w"), store, bond_service=bonds)


def _bond(focus: str, other: str, strength: float, *, bond_id: str = "b1") -> BondEdge:
    return BondEdge(
        bond_id=bond_id,
        entity_a=focus,
        entity_b=other,
        domain=BondDomain.FRIENDSHIP,
        vector=BondVector(
            trust=strength, warmth=strength,
            familiarity=strength, vulnerability=strength,
        ),
    )


# ---------------------------------------------------------------------------
# Query 24: place/kind-filtered recent observations
# ---------------------------------------------------------------------------


class TestRecentObservations:
    def test_place_filter_newest_first(self, tmp_path):
        store = _store(tmp_path, [
            _obs("obs_old", at=T0),
            _obs("obs_docks", at=T0 + timedelta(hours=2), place="docks"),
            _obs("obs_new", at=T0 + timedelta(hours=1)),
        ])
        result = _oracle(store).recent_observations(place_id="hall")
        assert [r.record_id for r in result] == ["obs_new", "obs_old"]

    def test_kind_filter_enum_and_string(self, tmp_path):
        store = _store(tmp_path, [
            _obs("obs_chat", kind=ObservationKind.UTTERANCE, at=T0),
            _obs("obs_event", kind=ObservationKind.WORLD_EVENT, at=T0 + timedelta(hours=1)),
        ])
        oracle = _oracle(store)
        by_enum = oracle.recent_observations(kind=ObservationKind.UTTERANCE)
        by_string = oracle.recent_observations(kind="utterance")
        assert [r.record_id for r in by_enum] == ["obs_chat"]
        assert [r.record_id for r in by_string] == ["obs_chat"]

    def test_combined_filters_and_limit(self, tmp_path):
        store = _store(tmp_path, [
            _obs("obs_1", at=T0),
            _obs("obs_2", at=T0 + timedelta(hours=1)),
            _obs("obs_3", at=T0 + timedelta(hours=2)),
            _obs("obs_other_kind", kind=ObservationKind.ACTION, at=T0 + timedelta(hours=3)),
            _obs("obs_other_place", place="docks", at=T0 + timedelta(hours=4)),
        ])
        result = _oracle(store).recent_observations(
            place_id="hall", kind=ObservationKind.UTTERANCE, limit=2
        )
        assert [r.record_id for r in result] == ["obs_3", "obs_2"]

    def test_empty_result_is_empty_not_unfiltered(self, tmp_path):
        store = _store(tmp_path, [_obs("obs_1")])
        oracle = _oracle(store)
        assert oracle.recent_observations(place_id="nowhere") == []
        assert oracle.recent_observations(kind=ObservationKind.SENSATION) == []
        assert oracle.recent_observations(limit=0) == []

    def test_ties_break_by_record_id(self, tmp_path):
        store = _store(tmp_path, [_obs("obs_b"), _obs("obs_a")])  # same instant
        result = _oracle(store).recent_observations()
        assert [r.record_id for r in result] == ["obs_a", "obs_b"]

    def test_unfiltered_is_global_newest_first(self, tmp_path):
        store = _store(tmp_path, [
            _obs("obs_mid", at=T0 + timedelta(hours=1), place="docks"),
            _obs("obs_old", at=T0),
            _obs("obs_new", at=T0 + timedelta(hours=2), kind=ObservationKind.ACTION),
        ])
        result = _oracle(store).recent_observations()
        assert [r.record_id for r in result] == ["obs_new", "obs_mid", "obs_old"]

    def test_invalid_arguments_raise(self, tmp_path):
        oracle = _oracle(_store(tmp_path, [_obs("obs_1")]))
        with pytest.raises(ValueError):
            oracle.recent_observations(limit=-1)
        with pytest.raises(ValueError):
            oracle.recent_observations(kind="not-a-kind")


# ---------------------------------------------------------------------------
# BondGraphService.strength_between (the additive bond read)
# ---------------------------------------------------------------------------


class TestStrengthBetween:
    def test_both_directions_and_closeness_value(self):
        service = BondGraphService()
        service.add_edge(_bond("yrsa", "sigrid", 0.9))
        assert service.strength_between("yrsa", "sigrid") == 0.9
        assert service.strength_between("sigrid", "yrsa") == 0.9

    def test_strongest_edge_wins_across_domains(self):
        service = BondGraphService()
        service.add_edge(_bond("yrsa", "sigrid", 0.4, bond_id="b1"))
        service.add_edge(_bond("sigrid", "yrsa", 0.8, bond_id="b2"))
        assert service.strength_between("yrsa", "sigrid") == 0.8

    def test_strangers_and_self_have_no_strength(self):
        service = BondGraphService()
        service.add_edge(_bond("yrsa", "sigrid", 0.9))
        assert service.strength_between("yrsa", "stranger") is None
        assert service.strength_between("yrsa", "yrsa") is None


# ---------------------------------------------------------------------------
# Query 25: salience-ranked recall — one factor isolated at a time
# ---------------------------------------------------------------------------


class TestSalienceFactors:
    def test_recency_effect_isolated(self, tmp_path):
        # Distinct (kind, place) classes → novelty 1.0 for both; no
        # bonds → neutral. Only the timestamps differ.
        store = _store(tmp_path, [
            _obs("obs_fresh", place="hall", at=T0),
            _obs("obs_day_old", place="docks", at=T0 - timedelta(hours=24)),
        ])
        results = _oracle(store).recall_by_salience(now=T0)
        assert [r.record_id for r in results] == ["obs_fresh", "obs_day_old"]
        fresh, old = results
        assert fresh.recency == 1.0 and old.recency == 0.5  # one half-life
        assert fresh.novelty == old.novelty == 1.0
        assert fresh.bond_strength == old.bond_strength == NEUTRAL_BOND_STRENGTH
        assert fresh.score == pytest.approx(0.45 * 1.0 + 0.30 * 0.5 + 0.25 * 1.0)
        assert old.score == pytest.approx(0.45 * 0.5 + 0.30 * 0.5 + 0.25 * 1.0)

    def test_bond_effect_isolated(self, tmp_path):
        bonds = BondGraphService()
        bonds.add_edge(_bond("yrsa", "sigrid", 0.9))
        store = _store(tmp_path, [
            _obs("obs_friend", place="hall", speaker="sigrid", at=T0),
            _obs("obs_stranger", place="docks", speaker="stranger", at=T0),
        ])
        results = _oracle(store, bonds).recall_by_salience(focus_entity_id="yrsa", now=T0)
        assert [r.record_id for r in results] == ["obs_friend", "obs_stranger"]
        assert results[0].bond_strength == 0.9
        assert results[1].bond_strength == NEUTRAL_BOND_STRENGTH
        assert results[0].recency == results[1].recency == 1.0
        assert results[0].novelty == results[1].novelty == 1.0

    def test_weak_bond_ranks_below_neutral_stranger(self, tmp_path):
        bonds = BondGraphService()
        bonds.add_edge(_bond("yrsa", "cold", 0.1))
        store = _store(tmp_path, [
            _obs("obs_cold", place="hall", speaker="cold", at=T0),
            _obs("obs_stranger", place="docks", speaker="stranger", at=T0),
        ])
        results = _oracle(store, bonds).recall_by_salience(focus_entity_id="yrsa", now=T0)
        assert [r.record_id for r in results] == ["obs_stranger", "obs_cold"]
        assert results[1].bond_strength == 0.1

    def test_bond_via_participants_not_only_speaker(self, tmp_path):
        bonds = BondGraphService()
        bonds.add_edge(_bond("yrsa", "sigrid", 0.9))
        store = _store(tmp_path, [
            _obs("obs_group", participants=["stranger", "sigrid"], at=T0),
        ])
        results = _oracle(store, bonds).recall_by_salience(focus_entity_id="yrsa", now=T0)
        assert results[0].bond_strength == 0.9

    def test_no_bond_service_or_no_focus_is_neutral(self, tmp_path):
        bonds = BondGraphService()
        bonds.add_edge(_bond("yrsa", "sigrid", 0.9))
        store = _store(tmp_path, [_obs("obs_1", speaker="sigrid", at=T0)])
        no_service = _oracle(store).recall_by_salience(focus_entity_id="yrsa", now=T0)
        no_focus = _oracle(store, bonds).recall_by_salience(now=T0)
        assert no_service[0].bond_strength == NEUTRAL_BOND_STRENGTH
        assert no_focus[0].bond_strength == NEUTRAL_BOND_STRENGTH

    def test_self_only_observation_is_neutral(self, tmp_path):
        bonds = BondGraphService()
        bonds.add_edge(_bond("yrsa", "sigrid", 0.9))
        store = _store(tmp_path, [_obs("obs_self", speaker="yrsa", at=T0)])
        results = _oracle(store, bonds).recall_by_salience(focus_entity_id="yrsa", now=T0)
        assert results[0].bond_strength == NEUTRAL_BOND_STRENGTH

    def test_novelty_factors_from_history(self, tmp_path):
        # Same (kind, place) repeated over time: novelty decays as
        # 1/(1+priors) — read off the factors directly.
        store = _store(tmp_path, [
            _obs("obs_first", at=T0),
            _obs("obs_second", at=T0 + timedelta(hours=1)),
            _obs("obs_third", at=T0 + timedelta(hours=2)),
            _obs("obs_elsewhere", place="docks", at=T0 + timedelta(hours=2)),
        ])
        results = _oracle(store).recall_by_salience(now=T0 + timedelta(hours=2))
        by_id = {r.record_id: r for r in results}
        assert by_id["obs_first"].novelty == 1.0
        assert by_id["obs_second"].novelty == 0.5
        assert by_id["obs_third"].novelty == pytest.approx(1 / 3, abs=1e-6)
        assert by_id["obs_elsewhere"].novelty == 1.0  # its own (kind, place) class

    def test_novelty_effect_isolated_in_order(self, tmp_path):
        # Same instant, same kind/place → recency and bond identical;
        # only novelty separates them, in (observed_at, record_id)
        # history order.
        store = _store(tmp_path, [_obs("obs_c"), _obs("obs_a"), _obs("obs_b")])
        results = _oracle(store).recall_by_salience(now=T0)
        assert [r.record_id for r in results] == ["obs_a", "obs_b", "obs_c"]
        assert [r.novelty for r in results] == [1.0, 0.5, pytest.approx(1 / 3, abs=1e-6)]

    def test_future_observation_recency_clamps_to_fresh(self, tmp_path):
        store = _store(tmp_path, [_obs("obs_future", at=T0 + timedelta(hours=3))])
        results = _oracle(store).recall_by_salience(now=T0)
        assert results[0].recency == 1.0


class TestSalienceOrdering:
    def test_score_is_transparent_weighted_sum(self, tmp_path):
        assert WEIGHT_RECENCY + WEIGHT_BOND + WEIGHT_NOVELTY == pytest.approx(1.0)
        bonds = BondGraphService()
        bonds.add_edge(_bond("yrsa", "sigrid", 0.9))
        store = _store(tmp_path, [
            _obs("obs_1", speaker="sigrid", at=T0 - timedelta(hours=5)),
            _obs("obs_2", speaker="sigrid", at=T0 - timedelta(hours=4)),
            _obs("obs_3", place="docks", at=T0),
        ])
        for r in _oracle(store, bonds).recall_by_salience(focus_entity_id="yrsa", now=T0):
            assert r.score == pytest.approx(
                WEIGHT_RECENCY * r.recency
                + WEIGHT_BOND * r.bond_strength
                + WEIGHT_NOVELTY * r.novelty
            )
            assert 0.0 <= r.score <= 1.0
            # The result carries its full provenance for the ranking.
            assert r.kind == "utterance"
        by_id = {
            r.record_id: r
            for r in _oracle(store, bonds).recall_by_salience(focus_entity_id="yrsa", now=T0)
        }
        assert by_id["obs_1"].speaker_id == "sigrid" and by_id["obs_1"].place_id == "hall"
        assert by_id["obs_3"].speaker_id is None and by_id["obs_3"].place_id == "docks"

    def test_deterministic_tiebreak_and_reproducibility(self, tmp_path):
        # Identical factors (same instant, both first of their class,
        # no bonds) → identical scores → record_id decides, and a
        # repeat query reproduces the order exactly.
        store = _store(tmp_path, [
            _obs("obs_z", place="hall", at=T0),
            _obs("obs_a", place="docks", at=T0),
        ])
        oracle = _oracle(store)
        first = oracle.recall_by_salience(now=T0)
        second = oracle.recall_by_salience(now=T0)
        assert first[0].score == first[1].score
        assert [r.record_id for r in first] == ["obs_a", "obs_z"]
        assert [r.record_id for r in second] == ["obs_a", "obs_z"]

    def test_ranked_filters_and_limit(self, tmp_path):
        store = _store(tmp_path, [
            _obs("obs_hall_old", place="hall", at=T0),
            _obs("obs_hall_new", place="hall", at=T0 + timedelta(hours=1)),
            _obs("obs_docks", place="docks", at=T0 + timedelta(hours=2)),
            _obs("obs_event", kind=ObservationKind.WORLD_EVENT, place="hall",
                 at=T0 + timedelta(hours=3)),
        ])
        oracle = _oracle(store)
        hall = oracle.recall_by_salience(place_id="hall", now=T0 + timedelta(hours=3))
        assert {r.record_id for r in hall} == {"obs_hall_old", "obs_hall_new", "obs_event"}
        assert all(r.place_id == "hall" for r in hall)
        top1 = oracle.recall_by_salience(now=T0 + timedelta(hours=3), limit=1)
        assert len(top1) == 1 and top1[0].score >= hall[-1].score
        assert oracle.recall_by_salience(place_id="nowhere", now=T0) == []

    def test_ranked_invalid_arguments_raise(self, tmp_path):
        oracle = _oracle(_store(tmp_path, [_obs("obs_1")]))
        with pytest.raises(ValueError):
            oracle.recall_by_salience(limit=-1)
        with pytest.raises(ValueError):
            oracle.recall_by_salience(half_life_hours=0)
        with pytest.raises(ValueError):
            oracle.recall_by_salience(kind="not-a-kind")

    def test_ranking_ignores_writer_asserted_salience(self, tmp_path):
        # A record whose payload CLAIMS salience 1.0 but is old and
        # repetitive must not outrank a fresh first-of-its-kind one.
        loud = _obs("obs_loud", place="hall", at=T0 - timedelta(hours=48))
        loud.content.structured_payload.salience = 1.0
        store = _store(tmp_path, [
            _obs("obs_repeat_1", place="hall", at=T0 - timedelta(hours=49)),
            _obs("obs_repeat_2", place="hall", at=T0 - timedelta(hours=48, minutes=30)),
            loud,
            _obs("obs_fresh", place="docks", at=T0),
        ])
        results = _oracle(store).recall_by_salience(now=T0)
        assert results[0].record_id == "obs_fresh"
        loud_result = next(r for r in results if r.record_id == "obs_loud")
        assert loud_result.novelty == pytest.approx(1 / 3, abs=1e-6)  # third at hall


# ---------------------------------------------------------------------------
# Opt-in nature: defaults unchanged, packet ranking only on request
# ---------------------------------------------------------------------------


class TestOptIn:
    def _packet_store(self, tmp_path) -> PersistentMemoryStore:
        # obs_salient: a world_event at the docks an hour before the
        # query — first of its class (novelty 1.0), still recent.
        # obs_mundane: the third hall utterance, newest but routine.
        return _store(tmp_path, [
            _obs("obs_hall_1", at=T0 - timedelta(hours=3)),
            _obs("obs_hall_2", at=T0 - timedelta(hours=2)),
            _obs("obs_salient", kind=ObservationKind.WORLD_EVENT, place="docks",
                 at=T0 - timedelta(hours=1)),
            _obs("obs_mundane", at=T0),
        ])

    def test_unranked_query_ignores_salience(self, tmp_path):
        oracle = _oracle(self._packet_store(tmp_path))
        result = oracle.recent_observations()
        assert result[0].record_id == "obs_mundane"  # newest wins, unranked

    def test_packet_default_order_unchanged(self, tmp_path):
        oracle = _oracle(self._packet_store(tmp_path))
        packet = oracle.build_context_packet(focus_entity_ids=[], max_observations=10)
        assert packet.recent_observations[0].record_id == "obs_mundane"

    def test_packet_ranked_only_on_opt_in(self, tmp_path):
        oracle = _oracle(self._packet_store(tmp_path))
        packet = oracle.build_context_packet(
            focus_entity_ids=[], max_observations=10,
            rank_by_salience=True, salience_now=T0,
        )
        assert packet.recent_observations[0].record_id == "obs_salient"
        ranked = oracle.recall_by_salience(now=T0, limit=10)
        assert [o.record_id for o in packet.recent_observations] == [
            r.record_id for r in ranked
        ]


# ---------------------------------------------------------------------------
# Persistence-backed recall: a reopened store ranks identically
# ---------------------------------------------------------------------------


class TestPersistenceBacked:
    def test_reopened_store_ranks_identically(self, tmp_path):
        bonds = BondGraphService()
        bonds.add_edge(_bond("yrsa", "sigrid", 0.9))
        db = tmp_path / "memory.db"
        store = PersistentMemoryStore(db)
        for record in [
            _obs("obs_1", speaker="sigrid", at=T0 - timedelta(hours=2)),
            _obs("obs_2", speaker="sigrid", at=T0 - timedelta(hours=1)),
            _obs("obs_3", place="docks", at=T0),
        ]:
            store.add(record)
        before = _oracle(store, bonds).recall_by_salience(focus_entity_id="yrsa", now=T0)
        store.close()

        reopened = PersistentMemoryStore(db)
        oracle = _oracle(reopened, bonds)
        after = oracle.recall_by_salience(focus_entity_id="yrsa", now=T0)
        assert [r.record_id for r in after] == [r.record_id for r in before]
        assert [r.score for r in after] == [r.score for r in before]
        assert [r.record_id for r in oracle.recent_observations(place_id="hall")] == [
            "obs_2", "obs_1"
        ]
