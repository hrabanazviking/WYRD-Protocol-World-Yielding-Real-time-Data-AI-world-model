"""Tests for TurnLoop — uses a mock connector to avoid needing Ollama."""
from __future__ import annotations

import tempfile

from wyrdforge.ecs.components.character import FactionComponent
from wyrdforge.ecs.components.identity import DescriptionComponent, NameComponent, StatusComponent
from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree
from wyrdforge.llm.ollama_connector import OllamaUnavailableError
from wyrdforge.oracle.passive_oracle import PassiveOracle
from wyrdforge.oracle.models import WorldContextPacket
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.runtime.turn_loop import TurnLoop, TurnResult
from wyrdforge.services.contradiction_detector import ContradictionDetector
from wyrdforge.services.writeback_engine import WritebackEngine


# ---------------------------------------------------------------------------
# Mock connector
# ---------------------------------------------------------------------------

class MockConnector:
    """Connector stub that returns a canned response without network calls."""

    def __init__(self, response: str = "A brave answer from the mock.") -> None:
        self.response = response
        self.calls: list[list[dict]] = []

    def chat(self, messages: list[dict], **kwargs) -> str:
        self.calls.append(messages)
        return self.response


class FailingConnector:
    """Connector stub that always raises OllamaUnavailableError."""

    def chat(self, messages: list[dict], **kwargs) -> str:
        raise OllamaUnavailableError("test server down")


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _build_world() -> tuple[World, YggdrasilTree]:
    world = World("tl_world", "TurnLoop World")
    tree = YggdrasilTree(world)
    tree.create_zone(zone_id="midgard", name="Midgard")
    tree.create_region(region_id="fjords", name="Fjords", parent_zone_id="midgard")
    tree.create_location(location_id="hall", name="Great Hall", parent_region_id="fjords")
    world.create_entity(entity_id="gunnar", tags={"character"})
    world.add_component("gunnar", NameComponent(entity_id="gunnar", name="Gunnar"))
    world.add_component("gunnar", StatusComponent(entity_id="gunnar", state="idle"))
    tree.place_entity("gunnar", location_id="hall")
    return world, tree


def _build_stack(
    connector=None,
) -> tuple[TurnLoop, PersistentMemoryStore]:
    world, tree = _build_world()
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    engine = WritebackEngine(store)
    detector = ContradictionDetector(store)
    oracle = PassiveOracle(world, store, yggdrasil=tree)
    conn = connector or MockConnector()
    loop = TurnLoop(
        oracle,
        engine,
        detector,
        conn,
        focus_entity_id="gunnar",
        location_id="hall",
        persona_name="Gunnar Ironside",
    )
    return loop, store


# ---------------------------------------------------------------------------
# execute_turn — return type and fields
# ---------------------------------------------------------------------------

def test_execute_turn_returns_turn_result() -> None:
    loop, _ = _build_stack()
    result = loop.execute_turn("Hail, Gunnar!")
    assert isinstance(result, TurnResult)


def test_execute_turn_response_populated() -> None:
    loop, _ = _build_stack(MockConnector("Hail back!"))
    result = loop.execute_turn("Hello")
    assert result.assistant_response == "Hail back!"


def test_execute_turn_user_input_preserved() -> None:
    loop, _ = _build_stack()
    result = loop.execute_turn("What is your name?")
    assert result.user_input == "What is your name?"


def test_execute_turn_context_packet_is_world_context_packet() -> None:
    loop, _ = _build_stack()
    result = loop.execute_turn("hi")
    assert isinstance(result.context_packet, WorldContextPacket)


def test_execute_turn_no_error_on_success() -> None:
    loop, _ = _build_stack()
    result = loop.execute_turn("hi")
    assert result.error is None


# ---------------------------------------------------------------------------
# Memory writes
# ---------------------------------------------------------------------------

def test_execute_turn_writes_observation() -> None:
    loop, store = _build_stack()
    loop.execute_turn("Gunnar, where are you?")
    obs = store.all(store="hugin_observation_store")
    assert len(obs) >= 1


def test_execute_turn_written_record_ids_has_observations() -> None:
    loop, _ = _build_stack()
    result = loop.execute_turn("hi")
    assert len(result.written_record_ids["observations"]) >= 1


def test_execute_turn_with_extra_facts_writes_facts() -> None:
    loop, store = _build_stack()
    loop.execute_turn(
        "Gunnar just arrived",
        extra_facts=[
            {"fact_subject_id": "gunnar", "fact_key": "mood", "fact_value": "alert", "confidence": 0.9}
        ],
    )
    facts = store.all(store="mimir_canonical_store")
    assert len(facts) >= 1


def test_execute_turn_with_contradicting_facts_counts_contradictions() -> None:
    loop, store = _build_stack()
    # First fact
    loop.execute_turn(
        "status check",
        extra_facts=[{"fact_subject_id": "gunnar", "fact_key": "status", "fact_value": "alive", "confidence": 0.8}],
    )
    # Contradicting fact — different value, higher confidence
    result = loop.execute_turn(
        "another check",
        extra_facts=[{"fact_subject_id": "gunnar", "fact_key": "status", "fact_value": "wounded", "confidence": 0.95}],
    )
    assert result.contradictions_found >= 1


# ---------------------------------------------------------------------------
# Connector call structure
# ---------------------------------------------------------------------------

def test_execute_turn_connector_receives_messages_list() -> None:
    conn = MockConnector()
    loop, _ = _build_stack(conn)
    loop.execute_turn("Hello there")
    assert len(conn.calls) == 1
    messages = conn.calls[0]
    assert isinstance(messages, list)
    assert len(messages) >= 2  # at least system + user


def test_execute_turn_messages_start_with_system() -> None:
    conn = MockConnector()
    loop, _ = _build_stack(conn)
    loop.execute_turn("Hello")
    messages = conn.calls[0]
    assert messages[0]["role"] == "system"


def test_execute_turn_messages_end_with_user() -> None:
    conn = MockConnector()
    loop, _ = _build_stack(conn)
    loop.execute_turn("What do you seek?")
    messages = conn.calls[0]
    assert messages[-1]["role"] == "user"
    assert "What do you seek?" in messages[-1]["content"]


def test_execute_turn_system_prompt_contains_world_state() -> None:
    conn = MockConnector()
    loop, _ = _build_stack(conn)
    loop.execute_turn("hi")
    system_content = conn.calls[0][0]["content"]
    assert "WORLD STATE" in system_content


def test_execute_turn_system_prompt_contains_persona_name() -> None:
    conn = MockConnector()
    loop, _ = _build_stack(conn)
    loop.execute_turn("hi")
    system_content = conn.calls[0][0]["content"]
    assert "Gunnar Ironside" in system_content


# ---------------------------------------------------------------------------
# Unavailable connector
# ---------------------------------------------------------------------------

def test_execute_turn_handles_ollama_unavailable() -> None:
    loop, _ = _build_stack(FailingConnector())
    result = loop.execute_turn("Hello")
    assert "unavailable" in result.assistant_response.lower()
    assert result.error is not None


def test_execute_turn_still_writes_observation_when_ollama_down() -> None:
    loop, store = _build_stack(FailingConnector())
    loop.execute_turn("Hello")
    obs = store.all(store="hugin_observation_store")
    assert len(obs) >= 1


# ---------------------------------------------------------------------------
# History management
# ---------------------------------------------------------------------------

def test_history_grows_with_each_turn() -> None:
    loop, _ = _build_stack()
    loop.execute_turn("turn one")
    loop.execute_turn("turn two")
    assert loop.history_turn_count() == 2


def test_clear_history_resets_count() -> None:
    loop, _ = _build_stack()
    loop.execute_turn("turn one")
    loop.clear_history()
    assert loop.history_turn_count() == 0


def test_history_contains_correct_roles() -> None:
    loop, _ = _build_stack()
    loop.execute_turn("a question")
    history = loop.get_history()
    roles = [m["role"] for m in history]
    assert "user" in roles
    assert "assistant" in roles


def test_second_turn_messages_include_history() -> None:
    conn = MockConnector()
    loop, _ = _build_stack(conn)
    loop.execute_turn("first message")
    loop.execute_turn("second message")
    # Second call's messages should include prior user + assistant
    second_messages = conn.calls[1]
    roles = [m["role"] for m in second_messages]
    assert roles.count("user") >= 2  # prior + current


def test_location_id_override_per_turn() -> None:
    conn = MockConnector()
    loop, _ = _build_stack(conn)
    result = loop.execute_turn("hello", location_id="hall")
    assert result.context_packet.location_context is not None
