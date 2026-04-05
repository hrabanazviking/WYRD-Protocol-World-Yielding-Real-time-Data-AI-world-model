"""Turn loop — orchestrates a single conversation turn through the WYRD stack.

Execution order per turn:
    1. Query PassiveOracle → WorldContextPacket
    2. Build system prompt + messages via PromptBuilder
    3. Generate response via OllamaConnector
    4. Write observation (+ optional facts) to memory via WritebackEngine
    5. Run ContradictionDetector on any new facts
    6. Append to conversation history
    7. Return TurnResult

The loop is intentionally stateless between turns except for conversation
history (which is bounded by ``history_limit``).
"""
from __future__ import annotations

from wyrdforge.llm.ollama_connector import OllamaConnector, OllamaUnavailableError
from wyrdforge.llm.prompt_builder import PromptBuilder
from wyrdforge.models.common import StrictModel
from wyrdforge.oracle.models import WorldContextPacket
from wyrdforge.oracle.passive_oracle import PassiveOracle
from wyrdforge.services.contradiction_detector import ContradictionDetector
from wyrdforge.services.writeback_engine import WritebackEngine


class TurnResult(StrictModel):
    """Result of a single turn execution."""

    user_input: str
    assistant_response: str
    context_packet: WorldContextPacket
    written_record_ids: dict[str, list[str]]   # {"observations": [...], "facts": [...]}
    contradictions_found: int
    error: str | None = None


class TurnLoop:
    """Orchestrates conversation turns through the full WYRD stack.

    Args:
        oracle:           PassiveOracle for world state queries.
        engine:           WritebackEngine to persist turn observations and facts.
        detector:         ContradictionDetector to check new facts.
        connector:        OllamaConnector (or any object with a ``chat()`` method).
        focus_entity_id:  Entity ID to centre context packets around.
        location_id:      Default location for context packets.
        persona_name:     Character name injected into system prompt.
        persona_notes:    Extra character flavour text for system prompt.
        history_limit:    Max number of prior *turn-pairs* kept in memory.
    """

    def __init__(
        self,
        oracle: PassiveOracle,
        engine: WritebackEngine,
        detector: ContradictionDetector,
        connector: OllamaConnector,
        *,
        focus_entity_id: str = "",
        location_id: str | None = None,
        persona_name: str = "",
        persona_notes: str = "",
        history_limit: int = 10,
    ) -> None:
        self._oracle = oracle
        self._engine = engine
        self._detector = detector
        self._connector = connector
        self._focus_entity_id = focus_entity_id
        self._location_id = location_id
        self._persona_name = persona_name
        self._persona_notes = persona_notes
        self._history_limit = history_limit
        self._prompt_builder = PromptBuilder()
        self._history: list[dict[str, str]] = []

    # ------------------------------------------------------------------
    # Main API
    # ------------------------------------------------------------------

    def execute_turn(
        self,
        user_input: str,
        *,
        location_id: str | None = None,
        extra_facts: list[dict] | None = None,
    ) -> TurnResult:
        """Execute one conversation turn.

        Args:
            user_input:  The user's message text.
            location_id: Override the default location for this turn.
            extra_facts: Optional pre-parsed facts to write to MIMIR alongside
                         the observation.  Each dict must have:
                         ``{fact_subject_id, fact_key, fact_value, confidence?, domain?}``

        Returns:
            TurnResult with response, written record IDs, and contradiction count.
        """
        effective_loc = location_id or self._location_id

        # 1. Build world context
        focus_ids = [self._focus_entity_id] if self._focus_entity_id else []
        packet = self._oracle.build_context_packet(
            focus_entity_ids=focus_ids,
            location_id=effective_loc,
        )

        # 2. Build prompt + messages
        system_prompt = self._prompt_builder.build_system_prompt(
            packet,
            persona_name=self._persona_name,
            persona_notes=self._persona_notes,
        )
        trimmed_history = self._history[-(self._history_limit * 2):]
        messages = self._prompt_builder.build_messages(
            system_prompt, trimmed_history, user_input
        )

        # 3. Generate
        error: str | None = None
        try:
            response_text = self._connector.chat(messages)
        except OllamaUnavailableError as exc:
            response_text = "[Ollama unavailable — cannot generate response]"
            error = str(exc)

        # 4. Write to memory
        written = self._engine.process_turn(
            user_input=user_input,
            response_text=response_text,
            place_id=effective_loc,
            facts=extra_facts or [],
        )

        # 5. Check facts for contradictions
        contradictions_found = 0
        for fact_record in written.get("facts", []):
            found = self._detector.check_and_record(fact_record)
            contradictions_found += len(found)

        # 6. Append to history
        self._history.append({"role": "user", "content": user_input})
        self._history.append({"role": "assistant", "content": response_text})

        written_ids: dict[str, list[str]] = {
            "observations": [r.record_id for r in written.get("observations", [])],
            "facts": [r.record_id for r in written.get("facts", [])],
        }

        return TurnResult(
            user_input=user_input,
            assistant_response=response_text,
            context_packet=packet,
            written_record_ids=written_ids,
            contradictions_found=contradictions_found,
            error=error,
        )

    # ------------------------------------------------------------------
    # History management
    # ------------------------------------------------------------------

    def clear_history(self) -> None:
        """Wipe the in-memory conversation history."""
        self._history.clear()

    def get_history(self) -> list[dict[str, str]]:
        """Return a copy of the current conversation history."""
        return list(self._history)

    def history_turn_count(self) -> int:
        """Number of complete user/assistant turn-pairs in history."""
        return len(self._history) // 2
