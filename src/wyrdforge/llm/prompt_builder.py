"""Prompt builder — injects world context into LLM message payloads.

Takes a WorldContextPacket from the PassiveOracle and turns it into a
system prompt + properly structured messages list for the Ollama connector.
"""
from __future__ import annotations

from wyrdforge.oracle.models import WorldContextPacket

_DEFAULT_BASE = (
    "You are a character in a Norse-inspired story world. "
    "Stay in character and answer based solely on the world state provided. "
    "Do not invent facts, locations, or events not present in the context. "
    "Speak in first person unless narrating."
)


class PromptBuilder:
    """Builds structured prompts with Wyrd world-context injection.

    Args:
        base_instructions: Override the default system instructions.
    """

    def __init__(self, *, base_instructions: str = "") -> None:
        self._base = base_instructions or _DEFAULT_BASE

    def build_system_prompt(
        self,
        packet: WorldContextPacket,
        *,
        persona_name: str = "",
        persona_notes: str = "",
    ) -> str:
        """Assemble a system prompt from a WorldContextPacket.

        Args:
            packet:        World context from PassiveOracle.
            persona_name:  Name of the active character/persona.
            persona_notes: Optional character flavour text injected after name.

        Returns:
            A single string suitable for the ``system`` role message.
        """
        parts: list[str] = [self._base]

        if persona_name:
            parts.append(f"\nYou are {persona_name}.")
        if persona_notes:
            parts.append(f"Character notes: {persona_notes}")

        parts.append("\n" + packet.formatted_for_llm)
        return "\n".join(parts)

    def build_messages(
        self,
        system_prompt: str,
        history: list[dict[str, str]],
        user_input: str,
    ) -> list[dict[str, str]]:
        """Build the full messages list for a chat request.

        Args:
            system_prompt: The rendered system prompt string.
            history:       Prior turns as ``[{"role": ..., "content": ...}]``.
            user_input:    The new user message.

        Returns:
            Messages list with system first, then history, then new user turn.
        """
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_input})
        return messages
