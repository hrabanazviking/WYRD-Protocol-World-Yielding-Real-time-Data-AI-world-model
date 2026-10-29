"""Phase C1 — per-subject purge verification tests.

Roadmap §9 C1 (Heimdall launch gate): a subject can demand to be
forgotten, and the engine must actually forget — across all three
truth stores plus the durable journal — leaving only a hash-only
tombstone. Before C1 only per-record deletes existed.

These tests pin the contract specified in
``persistence/purge.py``'s module docstring:

(a) absence proven everywhere after a full purge: memory records
    (incl. the FTS5 index and the store/Oracle read surfaces), the
    bond graph (edges + cascaded vows/hurts), the world store
    (entities by id AND by PersonaRef, across every world in the
    file, components, A4-quarantined payloads, world load), and the
    journal (entries + persisted dead letters, snapshot
    reconstruction);
(b) the surgical boundary: other subjects are byte-identical after
    the purge — free-text mentions of the purged subject in another
    subject's records/components/facts/journal text are NOT deleted
    or rewritten. The one structural exception is
    ``ContainerComponent.children`` (containment state): purged ids
    are scrubbed from surviving containers;
(c) shared records (an observation listing the subject among its
    participants) are deleted whole;
(d) the tombstone holds the subject id's SHA-256 hash and counts
    only — no id, no content;
(e) idempotency: a re-purge reports zeros, completes, and still
    tombstones; purging a subject that never existed is a clean
    no-op with a tombstone;
(f) failure honesty: a store that raises is named in the report,
    the remaining stores are still purged, ``complete`` is False,
    and the tombstone records the failure — a half-purge never
    claims success;
(g) partial scope: stores not handed in are reported
    ``not-in-scope`` and left untouched;
(h) an empty subject id is refused (an unscoped purge is a wipe).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

import wyrdforge.ecs.components.character  # noqa: F401  (registry)
import wyrdforge.ecs.components.identity  # noqa: F401
import wyrdforge.ecs.components.spatial  # noqa: F401

from wyrdforge.ecs.components.character import HealthComponent, PersonaRefComponent
from wyrdforge.ecs.components.identity import DescriptionComponent, NameComponent
from wyrdforge.ecs.components.spatial import ContainerComponent
from wyrdforge.ecs.world import World
from wyrdforge.models.bond import BondDomain, BondEdge, Hurt, Vow
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
    CanonicalFactContent,
    CanonicalFactPayload,
    CanonicalFactRecord,
    ObservationContent,
    ObservationKind,
    ObservationPayload,
    ObservationRecord,
)
from wyrdforge.oracle.passive_oracle import PassiveOracle
from wyrdforge.persistence.bond_store import PersistentBondStore
from wyrdforge.persistence.event_journal import EventJournal
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.persistence.purge import (
    STATUS_FAILED,
    STATUS_NOT_IN_SCOPE,
    STATUS_PURGED,
    PurgeTombstoneStore,
    purge_subject,
    subject_id_hash,
)
from wyrdforge.persistence.world_store import WorldStore
from wyrdforge.runtime.events import EventEnvelope

SUBJECT = "resident:alice"
OTHER = "resident:bob"
THIRD = "resident:carol"

WORLD_A = "purge_world_a"
WORLD_B = "purge_world_b"


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _obs(
    record_id: str,
    *,
    primary: tuple[str, ...] = (),
    secondary: tuple[str, ...] = (),
    participants: tuple[str, ...] = (),
    summary: str = "",
    title: str = "",
    tags: tuple[str, ...] = (),
) -> ObservationRecord:
    now = _now()
    return ObservationRecord(
        record_id=record_id,
        tenant_id="test",
        system_id="wyrd",
        entity_scope=EntityScope(
            primary_subjects=list(primary), secondary_subjects=list(secondary)
        ),
        content=ObservationContent(
            title=title or record_id,
            summary=summary,
            structured_payload=ObservationPayload(
                observation_kind=ObservationKind.UTTERANCE,
                participants=list(participants),
                observed_at=now,
            ),
        ),
        truth=TruthMeta(confidence=0.8),
        provenance=Provenance(
            source_type="test",
            source_ref="test://purge",
            extracted_at=now,
            extracted_by="purge-test",
        ),
        lifecycle=Lifecycle(
            write_policy=WritePolicy.EPHEMERAL, retention_class=RetentionClass.SHORT
        ),
        retrieval=RetrievalMeta(lexical_terms=list(tags), default_priority=0.5),
        governance=Governance(),
        audit=Audit(
            created_at=now,
            updated_at=now,
            created_by_agent="purge-test",
            updated_by_agent="purge-test",
        ),
    )


def _fact(
    record_id: str, *, subject_id: str, key: str, value: str
) -> CanonicalFactRecord:
    now = _now()
    return CanonicalFactRecord(
        record_id=record_id,
        tenant_id="test",
        system_id="wyrd",
        entity_scope=EntityScope(primary_subjects=[subject_id]),
        content=CanonicalFactContent(
            title=f"{subject_id}.{key}",
            summary=f"{subject_id}: {key} is {value}",
            structured_payload=CanonicalFactPayload(
                fact_subject_id=subject_id, fact_key=key, fact_value=value
            ),
        ),
        truth=TruthMeta(confidence=0.9),
        provenance=Provenance(
            source_type="test",
            source_ref="test://purge",
            extracted_at=now,
            extracted_by="purge-test",
        ),
        lifecycle=Lifecycle(
            write_policy=WritePolicy.EPHEMERAL, retention_class=RetentionClass.LONG
        ),
        retrieval=RetrievalMeta(lexical_terms=[], default_priority=0.6),
        governance=Governance(),
        audit=Audit(
            created_at=now,
            updated_at=now,
            created_by_agent="purge-test",
            updated_by_agent="purge-test",
        ),
    )


def _envelope_summary(payload: dict, *, source: str = "sl-bridge", seq: int = 1) -> str:
    envelope = {
        "topic": "sl.chat",
        "payload": payload,
        "source": source,
        "seq": seq,
        "issued_at": "2026-10-29T00:00:00+00:00",
        "turn_id": None,
    }
    return json.dumps(envelope, sort_keys=True)


# ---------------------------------------------------------------------------
# Seeding — one subject + others, across every store
# ---------------------------------------------------------------------------

#: Memory record ids belonging to the subject (must all vanish).
MEMORY_SUBJECT_IDS = {
    "obs_primary",
    "obs_secondary",
    "obs_shared_participant",
    "fact_subject",
    "obs_replay_subject",
}
#: Memory record ids belonging to others (must survive byte-identical,
#: including the ones whose free text merely mentions the subject).
MEMORY_SURVIVOR_IDS = {
    "obs_other",
    "obs_mention_only",
    "fact_other",
    "fact_value_mentions_subject",
    "obs_replay_other",
    "obs_replay_mention_only",
}


def _seed_memory(store: PersistentMemoryStore) -> None:
    store.add(_obs("obs_primary", primary=(SUBJECT,), title="zqxsubjectword primary"))
    store.add(_obs("obs_secondary", secondary=(SUBJECT,)))
    # Shared observation: the subject is one participant among two —
    # deleted whole, not redacted.
    store.add(_obs("obs_shared_participant", participants=(SUBJECT, OTHER)))
    store.add(_fact("fact_subject", subject_id=SUBJECT, key="temperament", value="calm"))
    # ReplayPersistenceBridge-derived copy: no scope, no participants —
    # only its verbatim envelope names the subject.
    store.add(
        _obs(
            "obs_replay_subject",
            summary=_envelope_summary({"speaker_id": SUBJECT, "text": "hello"}),
            tags=("replay-persistence",),
        )
    )
    # --- survivors ---
    store.add(
        _obs(
            "obs_other",
            primary=(OTHER,),
            participants=(OTHER,),
            title="zqxotherword other",
            summary=f"{OTHER} was here; {SUBJECT} was mentioned in passing",
        )
    )
    store.add(
        _obs(
            "obs_mention_only",
            primary=(OTHER,),
            participants=(OTHER,),
            summary=f"{SUBJECT} stopped by the hall",
        )
    )
    store.add(_fact("fact_other", subject_id=OTHER, key="temperament", value="bold"))
    # The fact VALUE is the subject's id as free text — the fact is
    # still OTHER's (its fact_subject_id is OTHER) and must survive.
    store.add(
        _fact("fact_value_mentions_subject", subject_id=OTHER, key="friend", value=SUBJECT)
    )
    store.add(
        _obs(
            "obs_replay_other",
            summary=_envelope_summary({"speaker_id": OTHER, "text": "hi"}, seq=2),
            tags=("replay-persistence",),
        )
    )
    store.add(
        _obs(
            "obs_replay_mention_only",
            summary=_envelope_summary(
                {"speaker_id": OTHER, "text": f"hi {SUBJECT}"}, seq=3
            ),
            tags=("replay-persistence",),
        )
    )


def _seed_bonds(store: PersistentBondStore) -> None:
    store.save_edge(
        BondEdge(bond_id="bond_alice_bob", entity_a=SUBJECT, entity_b=OTHER,
                 domain=BondDomain.FRIENDSHIP)
    )
    store.save_vow(
        Vow(vow_id="vow_alice_bob", bond_id="bond_alice_bob",
            vow_text="stand by you", vow_kind="loyalty",
            created_from_record_id="rec-1")
    )
    store.save_hurt(
        Hurt(hurt_id="hurt_alice_bob", bond_id="bond_alice_bob",
             source_event_id="evt-1", hurt_kind="neglect", severity="low")
    )
    store.save_edge(
        BondEdge(bond_id="bond_bob_carol", entity_a=OTHER, entity_b=THIRD,
                 domain=BondDomain.FRIENDSHIP)
    )
    store.save_vow(
        Vow(vow_id="vow_bob_carol", bond_id="bond_bob_carol",
            vow_text=f"a vow mentioning {SUBJECT} in free text",
            vow_kind="loyalty", created_from_record_id="rec-2")
    )
    store.save_edge(
        BondEdge(bond_id="bond_carol_dave", entity_a=THIRD, entity_b="resident:dave",
                 domain=BondDomain.FRIENDSHIP)
    )


def _seed_worlds(store: WorldStore, db_path: Path) -> None:
    world_a = World(world_id=WORLD_A, world_name="Purge World A")
    # The hall survives; its children lose the two purged ids.
    world_a.create_entity(entity_id="hall")
    world_a.add_component(
        "hall",
        ContainerComponent(
            entity_id="hall", children=[SUBJECT, "ent_alice", "ent_bob"]
        ),
    )
    # An entity that IS the subject (entity_id == subject id).
    world_a.create_entity(entity_id=SUBJECT)
    world_a.add_component(SUBJECT, NameComponent(entity_id=SUBJECT, name="Alice"))
    world_a.add_component(SUBJECT, HealthComponent(entity_id=SUBJECT, hp=90.0))
    # An entity linked to the subject by PersonaRef.
    world_a.create_entity(entity_id="ent_alice")
    world_a.add_component(
        "ent_alice", PersonaRefComponent(entity_id="ent_alice", persona_id=SUBJECT)
    )
    world_a.add_component(
        "ent_alice", NameComponent(entity_id="ent_alice", name="Alice Avatar")
    )
    # Survivors — one carries the subject's id as free text only.
    world_a.create_entity(entity_id="ent_bob")
    world_a.add_component(
        "ent_bob", PersonaRefComponent(entity_id="ent_bob", persona_id=OTHER)
    )
    world_a.add_component(
        "ent_bob", NameComponent(entity_id="ent_bob", name=f"Bob, friend of {SUBJECT}")
    )
    world_a.create_entity(entity_id="ent_carol")
    world_a.add_component(
        "ent_carol",
        DescriptionComponent(
            entity_id="ent_carol", long_desc=f"Carol once met {SUBJECT} at the hall"
        ),
    )
    store.save(world_a)

    world_b = World(world_id=WORLD_B, world_name="Purge World B")
    world_b.create_entity(entity_id="ent_alice2")
    world_b.add_component(
        "ent_alice2", PersonaRefComponent(entity_id="ent_alice2", persona_id=SUBJECT)
    )
    world_b.create_entity(entity_id="ent_dave")
    world_b.add_component(
        "ent_dave", NameComponent(entity_id="ent_dave", name="Dave")
    )
    store.save(world_b)

    # A4-quarantined payloads: the subject's must be DESTROYED by
    # purge; the other subject's must be preserved.
    stamp = _now().isoformat()
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO quarantined_components (world_id, entity_id, "
            "component_type, data_json, schema_version, reason, detail, "
            "quarantined_at) VALUES (?,?,?,?,?,?,?,?)",
            (WORLD_A, "ent_alice", "mystery", '{"secret": "alice payload"}',
             "1.0", "unknown-type", "test fixture", stamp),
        )
        conn.execute(
            "INSERT INTO quarantined_components (world_id, entity_id, "
            "component_type, data_json, schema_version, reason, detail, "
            "quarantined_at) VALUES (?,?,?,?,?,?,?,?)",
            (WORLD_A, "ent_bob", "mystery", '{"secret": "bob payload"}',
             "1.0", "unknown-type", "test fixture", stamp),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_journal(journal: EventJournal) -> None:
    journal.append(
        EventEnvelope(topic="sl.chat", payload={"speaker_id": SUBJECT, "text": "hello"},
                      source="sl-bridge", seq=1)
    )
    journal.append(
        EventEnvelope(topic="sl.presence", payload={"state": "arrived"},
                      source=SUBJECT, seq=2)
    )
    journal.append(
        EventEnvelope(topic="sl.chat", payload={"speaker_id": OTHER, "text": "hi"},
                      source="sl-bridge", seq=3)
    )
    # Free-text mention inside another subject's utterance — survives.
    journal.append(
        EventEnvelope(
            topic="sl.chat",
            payload={"speaker_id": OTHER, "text": f"{SUBJECT} was here"},
            source="sl-bridge", seq=4,
        )
    )
    journal.record_dead_letter(
        {"seq": 10, "topic": "sl.chat", "subscriber": "sub1",
         "error_type": "RuntimeError",
         "message": f"delivery failed for {SUBJECT}", "timestamp": "t1"}
    )
    journal.record_dead_letter(
        {"seq": 11, "topic": "sl.chat", "subscriber": "sub1",
         "error_type": "RuntimeError",
         "message": f"delivery failed for {OTHER}", "timestamp": "t2"}
    )


class _Seeded:
    def __init__(self, tmp_path: Path) -> None:
        self.memory_path = tmp_path / "memory.db"
        self.bond_path = tmp_path / "bond.db"
        self.world_path = tmp_path / "world.db"
        self.journal_path = tmp_path / "journal.db"
        self.memory = PersistentMemoryStore(self.memory_path)
        self.bonds = PersistentBondStore(self.bond_path)
        self.worlds = WorldStore(self.world_path)
        self.journal = EventJournal(self.journal_path)
        self.tombstones = PurgeTombstoneStore(tmp_path / "tombstones.db")
        _seed_memory(self.memory)
        _seed_bonds(self.bonds)
        _seed_worlds(self.worlds, self.world_path)
        _seed_journal(self.journal)

    def purge(self, **overrides):
        kwargs = dict(
            tombstones=self.tombstones,
            world_store=self.worlds,
            memory_store=self.memory,
            bond_store=self.bonds,
            journal=self.journal,
        )
        kwargs.update(overrides)
        return purge_subject(SUBJECT, **kwargs)


@pytest.fixture()
def seeded(tmp_path: Path) -> _Seeded:
    return _Seeded(tmp_path)


def _raw_rows(db_path: Path, sql: str, params: tuple = ()) -> list[tuple]:
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _memory_bytes(seeded: _Seeded) -> dict[str, str]:
    return {
        rid: blob
        for rid, blob in _raw_rows(
            seeded.memory_path, "SELECT record_id, data_json FROM memory_records"
        )
    }


# ---------------------------------------------------------------------------
# (a) Absence everywhere
# ---------------------------------------------------------------------------


def test_full_purge_report_counts(seeded: _Seeded) -> None:
    report = seeded.purge()
    assert report.complete is True
    assert report.store_status == {
        "world": STATUS_PURGED,
        "memory": STATUS_PURGED,
        "bond": STATUS_PURGED,
        "journal": STATUS_PURGED,
    }
    assert report.failures == ()
    assert report.memory_records_removed == len(MEMORY_SUBJECT_IDS)
    assert report.bond_edges_removed == 1
    assert report.bond_vows_removed == 1
    assert report.bond_hurts_removed == 1
    # world A: the id-entity + the PersonaRef entity; world B: one more.
    assert report.world_entities_removed == 3
    # A: 2 (subject) + 2 (ent_alice); B: 1 (ent_alice2).
    assert report.world_components_removed == 5
    assert report.world_quarantined_removed == 1
    assert report.container_references_removed == 2
    assert report.journal_entries_removed == 2
    assert report.dead_letters_removed == 1
    assert report.subject_id_hash == subject_id_hash(SUBJECT)


def test_memory_absence_including_fts_and_oracle(seeded: _Seeded) -> None:
    seeded.purge()
    for rid in MEMORY_SUBJECT_IDS:
        assert seeded.memory.get(rid) is None
    remaining = {r.record_id for r in seeded.memory.all()}
    assert remaining == MEMORY_SURVIVOR_IDS
    # FTS index: the subject's unique term finds nothing; the other
    # subject's unique term still finds its record.
    assert seeded.memory.search("zqxsubjectword") == []
    assert [r.record_id for r in seeded.memory.search("zqxotherword")] == ["obs_other"]
    assert seeded.memory.find_canonical_facts(SUBJECT, "temperament") == []
    # Oracle read surface agrees.
    world = seeded.worlds.load(WORLD_A)
    oracle = PassiveOracle(world=world, memory_store=seeded.memory)
    assert oracle.get_facts(SUBJECT) == []
    assert len(oracle.get_facts(OTHER)) == 2


def test_bond_absence(seeded: _Seeded) -> None:
    seeded.purge()
    assert seeded.bonds.edges_for_entity(SUBJECT) == []
    assert seeded.bonds.load_edge("bond_alice_bob") is None
    assert seeded.bonds.vows_for_bond("bond_alice_bob") == []
    assert seeded.bonds.hurts_for_bond("bond_alice_bob") == []
    assert seeded.bonds.count_edges() == 2
    assert seeded.bonds.count_vows() == 1
    assert seeded.bonds.count_hurts() == 0


def test_world_absence_across_worlds_and_quarantine(seeded: _Seeded) -> None:
    seeded.purge()
    world_a = seeded.worlds.load(WORLD_A)
    assert world_a.get_entity(SUBJECT) is None
    assert world_a.get_entity("ent_alice") is None
    assert world_a.get_entity("ent_bob") is not None
    assert world_a.get_entity("ent_carol") is not None
    world_b = seeded.worlds.load(WORLD_B)
    assert world_b.get_entity("ent_alice2") is None
    assert world_b.get_entity("ent_dave") is not None
    # Raw tables hold no trace of the purged entities.
    assert _raw_rows(
        seeded.world_path,
        "SELECT COUNT(*) FROM entities WHERE entity_id IN (?,?,?)",
        (SUBJECT, "ent_alice", "ent_alice2"),
    ) == [(0,)]
    assert _raw_rows(
        seeded.world_path,
        "SELECT COUNT(*) FROM components WHERE entity_id IN (?,?,?)",
        (SUBJECT, "ent_alice", "ent_alice2"),
    ) == [(0,)]
    # Quarantine: the subject's payload destroyed, the other's kept.
    quarantined = seeded.worlds.quarantined_components()
    assert [(q["entity_id"]) for q in quarantined] == ["ent_bob"]


def test_container_children_scrubbed_others_kept(seeded: _Seeded) -> None:
    seeded.purge()
    world_a = seeded.worlds.load(WORLD_A)
    container = world_a.get_component("hall", "container")
    assert isinstance(container, ContainerComponent)
    assert container.children == ["ent_bob"]


def test_journal_absence_and_reconstruction(seeded: _Seeded) -> None:
    seeded.purge()
    entries = seeded.journal.entries()
    assert len(entries) == 2
    assert [e.bus_seq for e in entries] == [3, 4]
    snapshot = seeded.journal.reconstruct_snapshot()
    assert len(snapshot.entries) == 2
    letters = seeded.journal.dead_letters()
    assert len(letters) == 1
    assert OTHER in letters[0]["message"]


# ---------------------------------------------------------------------------
# (b) The surgical boundary — other subjects byte-identical
# ---------------------------------------------------------------------------


def test_other_subjects_byte_identical(seeded: _Seeded) -> None:
    mem_before = _memory_bytes(seeded)
    bond_before = {
        key: blob
        for key, blob in _raw_rows(
            seeded.bond_path,
            "SELECT bond_id, data_json FROM bond_edges",
        )
    }
    vow_before = _raw_rows(
        seeded.bond_path, "SELECT data_json FROM vows WHERE bond_id='bond_bob_carol'"
    )
    world_comp_before = {
        (w, e, t): blob
        for w, e, t, blob in _raw_rows(
            seeded.world_path,
            "SELECT world_id, entity_id, component_type, data_json FROM components",
        )
        if e in ("ent_bob", "ent_carol", "ent_dave")
    }
    seeded.purge()
    mem_after = _memory_bytes(seeded)
    for rid in MEMORY_SURVIVOR_IDS:
        assert mem_after[rid] == mem_before[rid]
    bond_after = dict(
        _raw_rows(seeded.bond_path, "SELECT bond_id, data_json FROM bond_edges")
    )
    assert bond_after["bond_bob_carol"] == bond_before["bond_bob_carol"]
    assert bond_after["bond_carol_dave"] == bond_before["bond_carol_dave"]
    assert _raw_rows(
        seeded.bond_path, "SELECT data_json FROM vows WHERE bond_id='bond_bob_carol'"
    ) == vow_before
    world_comp_after = {
        (w, e, t): blob
        for w, e, t, blob in _raw_rows(
            seeded.world_path,
            "SELECT world_id, entity_id, component_type, data_json FROM components",
        )
        if e in ("ent_bob", "ent_carol", "ent_dave")
    }
    assert world_comp_after == world_comp_before


# ---------------------------------------------------------------------------
# (d) Tombstone — hash only, no content
# ---------------------------------------------------------------------------


def test_tombstone_hash_only_no_content(seeded: _Seeded) -> None:
    report = seeded.purge()
    stones = seeded.tombstones.for_subject(SUBJECT)
    assert len(stones) == 1
    stone = stones[0]
    assert stone.tombstone_id == report.tombstone_id
    assert stone.subject_id_hash == hashlib.sha256(SUBJECT.encode()).hexdigest()
    assert stone.scope["complete"] is True
    assert stone.scope["counts"]["memory_records_removed"] == len(MEMORY_SUBJECT_IDS)
    # No plaintext id and no content anywhere in the tombstone row.
    rows = _raw_rows(
        seeded.tombstones.db_path,
        "SELECT tombstone_id, subject_id_hash, purged_at, scope_json "
        "FROM purge_tombstones",
    )
    assert len(rows) == 1
    for field in rows[0]:
        assert SUBJECT not in str(field)
        assert "hello" not in str(field)


# ---------------------------------------------------------------------------
# (e) Idempotency + never-existed subject
# ---------------------------------------------------------------------------


def test_repurge_is_idempotent_zero_counts(seeded: _Seeded) -> None:
    first = seeded.purge()
    assert first.complete is True
    second = seeded.purge()
    assert second.complete is True
    assert second.memory_records_removed == 0
    assert second.bond_edges_removed == 0
    assert second.world_entities_removed == 0
    assert second.world_components_removed == 0
    assert second.world_quarantined_removed == 0
    assert second.container_references_removed == 0
    assert second.journal_entries_removed == 0
    assert second.dead_letters_removed == 0
    # Each call appends its own tombstone.
    assert len(seeded.tombstones.for_subject(SUBJECT)) == 2


def test_purge_subject_that_never_existed(tmp_path: Path) -> None:
    seeded = _Seeded(tmp_path)
    report = purge_subject(
        "resident:nobody",
        tombstones=seeded.tombstones,
        world_store=seeded.worlds,
        memory_store=seeded.memory,
        bond_store=seeded.bonds,
        journal=seeded.journal,
    )
    assert report.complete is True
    assert report.memory_records_removed == 0
    assert report.world_entities_removed == 0
    assert len(seeded.tombstones.for_subject("resident:nobody")) == 1
    # Nothing else was touched.
    assert seeded.memory.count() == len(MEMORY_SUBJECT_IDS) + len(MEMORY_SURVIVOR_IDS)


# ---------------------------------------------------------------------------
# (f) Failure honesty + (g) partial scope + (h) empty id refused
# ---------------------------------------------------------------------------


class _ExplodingWorldStore:
    def purge_subject(self, subject_id: str) -> dict:
        raise RuntimeError("world file on fire")


def test_store_failure_is_honest_and_purge_continues(seeded: _Seeded) -> None:
    report = seeded.purge(world_store=_ExplodingWorldStore())
    assert report.complete is False
    assert report.store_status["world"] == STATUS_FAILED
    assert report.store_status["memory"] == STATUS_PURGED
    assert report.store_status["bond"] == STATUS_PURGED
    assert report.store_status["journal"] == STATUS_PURGED
    assert len(report.failures) == 1
    assert report.failures[0].store == "world"
    assert report.failures[0].error_type == "RuntimeError"
    # The other stores really were purged despite the failure.
    assert seeded.memory.get("obs_primary") is None
    assert seeded.bonds.load_edge("bond_alice_bob") is None
    # The world store really was not.
    assert seeded.worlds.load(WORLD_A).get_entity("ent_alice") is not None
    # The tombstone records the failure honestly.
    stone = seeded.tombstones.for_subject(SUBJECT)[0]
    assert stone.scope["complete"] is False
    assert stone.scope["failures"][0]["store"] == "world"


def test_partial_scope_reports_not_in_scope(seeded: _Seeded) -> None:
    report = purge_subject(
        SUBJECT, tombstones=seeded.tombstones, memory_store=seeded.memory
    )
    assert report.complete is True
    assert report.store_status == {
        "world": STATUS_NOT_IN_SCOPE,
        "memory": STATUS_PURGED,
        "bond": STATUS_NOT_IN_SCOPE,
        "journal": STATUS_NOT_IN_SCOPE,
    }
    assert report.memory_records_removed == len(MEMORY_SUBJECT_IDS)
    # Untouched stores keep the subject.
    assert seeded.bonds.load_edge("bond_alice_bob") is not None
    assert seeded.worlds.load(WORLD_A).get_entity("ent_alice") is not None
    assert seeded.journal.count() == 4


def test_empty_subject_id_refused(seeded: _Seeded) -> None:
    with pytest.raises(ValueError):
        purge_subject("", tombstones=seeded.tombstones, memory_store=seeded.memory)
    assert seeded.tombstones.all() == []


# ---------------------------------------------------------------------------
# Store-level pins (direct purge_subject on each store)
# ---------------------------------------------------------------------------


def test_store_level_purges_and_idempotency(seeded: _Seeded) -> None:
    removed = seeded.memory.purge_subject(SUBJECT)
    assert set(removed) == MEMORY_SUBJECT_IDS
    assert seeded.memory.purge_subject(SUBJECT) == []

    assert seeded.bonds.purge_subject(SUBJECT) == {"edges": 1, "vows": 1, "hurts": 1}
    assert seeded.bonds.purge_subject(SUBJECT) == {"edges": 0, "vows": 0, "hurts": 0}

    world_result = seeded.worlds.purge_subject(SUBJECT)
    assert world_result == {
        "entities": 3,
        "components": 5,
        "quarantined_components": 1,
        "container_references_removed": 2,
    }
    assert seeded.worlds.purge_subject(SUBJECT) == {
        "entities": 0,
        "components": 0,
        "quarantined_components": 0,
        "container_references_removed": 0,
    }

    assert seeded.journal.purge_subject(SUBJECT) == {"entries": 2, "dead_letters": 1}
    assert seeded.journal.purge_subject(SUBJECT) == {"entries": 0, "dead_letters": 0}


def test_world_save_after_purge_does_not_resurrect(seeded: _Seeded) -> None:
    seeded.purge()
    # Load (post-purge state), mutate a survivor, save through the
    # same store instance: the purge must not be undone by the B2
    # incremental baseline the instance held from before the purge.
    world_a = seeded.worlds.load(WORLD_A)
    name = world_a.get_component("ent_bob", "name")
    assert isinstance(name, NameComponent)
    name.name = "Bob Renamed"
    seeded.worlds.save(world_a)
    reloaded = seeded.worlds.load(WORLD_A)
    assert reloaded.get_entity("ent_alice") is None
    assert reloaded.get_entity(SUBJECT) is None
    bob = reloaded.get_component("ent_bob", "name")
    assert isinstance(bob, NameComponent)
    assert bob.name == "Bob Renamed"
    container = reloaded.get_component("hall", "container")
    assert isinstance(container, ContainerComponent)
    assert container.children == ["ent_bob"]
