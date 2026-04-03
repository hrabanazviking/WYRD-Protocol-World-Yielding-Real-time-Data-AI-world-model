"""Tests for PromptBuilder."""
from __future__ import annotations

import tempfile

from wyrdforge.ecs.components.identity import NameComponent
from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree
from wyrdforge.llm.prompt_builder import PromptBuilder
from wyrdforge.oracle.passive_oracle import PassiveOracle
from wyrdforge.persistence.memory_store import PersistentMemoryStore


def _empty_packet():
    world = World("pw", "Prompt World")
    tree = YggdrasilTree(world)
    tree.create_zone(zone_id="z", name="Zone")
    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    oracle = PassiveOracle(world, store, yggdrasil=tree)
    return oracle.build_context_packet(focus_entity_ids=[])


# ---------------------------------------------------------------------------
# build_system_prompt
# ---------------------------------------------------------------------------

def test_build_system_prompt_returns_string() -> None:
    pb = PromptBuilder()
    packet = _empty_packet()
    result = pb.build_system_prompt(packet)
    assert isinstance(result, str)
    assert len(result) > 0


def test_build_system_prompt_contains_base_instructions() -> None:
    pb = PromptBuilder()
    packet = _empty_packet()
    result = pb.build_system_prompt(packet)
    assert "Norse" in result or "character" in result.lower()


def test_build_system_prompt_contains_world_state() -> None:
    pb = PromptBuilder()
    packet = _empty_packet()
    result = pb.build_system_prompt(packet)
    assert "WORLD STATE" in result


def test_build_system_prompt_includes_persona_name() -> None:
    pb = PromptBuilder()
    packet = _empty_packet()
    result = pb.build_system_prompt(packet, persona_name="Sigrid")
    assert "Sigrid" in result


def test_build_system_prompt_no_persona_name_no_label() -> None:
    pb = PromptBuilder()
    packet = _empty_packet()
    result = pb.build_system_prompt(packet)
    assert "You are \n" not in result


def test_build_system_prompt_includes_persona_notes() -> None:
    pb = PromptBuilder()
    packet = _empty_packet()
    result = pb.build_system_prompt(
        packet, persona_name="Gunnar", persona_notes="Hot-tempered warrior"
    )
    assert "Hot-tempered warrior" in result


def test_build_system_prompt_custom_base_instructions() -> None:
    pb = PromptBuilder(base_instructions="CUSTOM_BASE_INSTRUCTION")
    packet = _empty_packet()
    result = pb.build_system_prompt(packet)
    assert "CUSTOM_BASE_INSTRUCTION" in result


# ---------------------------------------------------------------------------
# build_messages
# ---------------------------------------------------------------------------

def test_build_messages_first_is_system() -> None:
    pb = PromptBuilder()
    messages = pb.build_messages("sys_prompt", [], "hello")
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "sys_prompt"


def test_build_messages_last_is_user() -> None:
    pb = PromptBuilder()
    messages = pb.build_messages("sys", [], "my question")
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "my question"


def test_build_messages_history_included() -> None:
    pb = PromptBuilder()
    history = [
        {"role": "user", "content": "earlier question"},
        {"role": "assistant", "content": "earlier answer"},
    ]
    messages = pb.build_messages("sys", history, "new question")
    roles = [m["role"] for m in messages]
    assert roles == ["system", "user", "assistant", "user"]


def test_build_messages_empty_history() -> None:
    pb = PromptBuilder()
    messages = pb.build_messages("sys", [], "hi")
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
