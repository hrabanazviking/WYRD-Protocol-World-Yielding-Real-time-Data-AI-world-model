from __future__ import annotations

from wyrdforge.models.bond import BondDomain, BondEdge
from wyrdforge.models.persona import PersonaMode
from wyrdforge.runtime.demo_seed import build_seed_fact
from wyrdforge.services.memory_store import InMemoryRecordStore
from wyrdforge.services.persona_compiler import PersonaCompiler


def test_memory_store_search_and_promote() -> None:
    store = InMemoryRecordStore()
    record = build_seed_fact()
    store.add(record)
    results = store.search("calm mystical guide")
    assert results
    promoted = store.promote(record.record_id)
    assert promoted.truth.approval_state == "approved"


def test_persona_compiler_builds_packet() -> None:
    record = build_seed_fact()
    bond = BondEdge(bond_id="bond-001", entity_a="user:volmarr", entity_b="persona:veyrunn", domain=BondDomain.COMPANION)
    compiler = PersonaCompiler()
    packet = compiler.compile(persona_id="persona:veyrunn", user_id="user:volmarr", mode=PersonaMode.COMPANION, records=[record], bond_edge=bond)
    assert packet.persona_id == "persona:veyrunn"
    assert packet.identity_core
    assert packet.response_guidance
