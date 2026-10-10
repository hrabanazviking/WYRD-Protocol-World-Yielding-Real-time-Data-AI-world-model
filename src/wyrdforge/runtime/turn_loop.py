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

Helheim Hardening (resilience weave): each stage that can fail
independently — oracle (1), writeback engine (4), contradiction detector
(5) — is wrapped in its own try/except so one failing stage degrades the
turn instead of aborting it.  Stage failures are recorded on
``TurnResult.stage_errors`` as ``"stage_name: ExceptionType: message"``.
The connector (3) already had its own degradation path and is unchanged.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from pydantic import Field

from wyrdforge.llm.ollama_connector import OllamaConnector, OllamaUnavailableError
from wyrdforge.llm.prompt_builder import PromptBuilder
from wyrdforge.models.common import StrictModel
from wyrdforge.oracle.models import WorldContextPacket
from wyrdforge.oracle.passive_oracle import PassiveOracle
from wyrdforge.services.contradiction_detector import ContradictionDetector
from wyrdforge.services.writeback_engine import WritebackEngine

logger = logging.getLogger(__name__)

#: Maximum accepted user_input length (characters).  Guards the prompt
#: builder and the observation writer against pathological input.
MAX_USER_INPUT_LEN = 20000


class TurnResult(StrictModel):
    """Result of a single turn execution."""

    user_input: str
    assistant_response: str
    context_packet: WorldContextPacket
    written_record_ids: dict[str, list[str]]   # {"observations": [...], "facts": [...]}
    contradictions_found: int
    error: str | None = None
    # Resilience weave: per-stage failures, "stage_name: ExceptionType: message".
    stage_errors: list[str] = Field(default_factory=list)
    # Observability: run_id is shared by every turn of this TurnLoop;
    # turn_id is unique per execute_turn call.
    run_id: str
    turn_id: str


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
        # Observability: one stable identity for the life of this loop.
        self.run_id = uuid.uuid4().hex

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

        Raises:
            TypeError:  If ``user_input`` is not a string.
            ValueError: If ``user_input`` is empty/whitespace-only or longer
                        than ``MAX_USER_INPUT_LEN`` characters.
        """
        # Input validation — fail fast before any stage runs.
        if not isinstance(user_input, str):
            raise TypeError(
                f"user_input must be a string, got {type(user_input).__name__}"
            )
        if not user_input.strip():
            raise ValueError("user_input must not be empty or whitespace-only")
        if len(user_input) > MAX_USER_INPUT_LEN:
            raise ValueError(
                f"user_input exceeds maximum length of {MAX_USER_INPUT_LEN} "
                f"characters (got {len(user_input)})"
            )

        turn_id = uuid.uuid4().hex
        stage_errors: list[str] = []
        effective_loc = location_id or self._location_id

        # 1. Build world context — degrade to a minimal-but-valid packet on
        #    oracle failure so the turn can still proceed on ECS-less context.
        logger.debug("[turn_id=%s] stage 1: building context packet", turn_id)
        focus_ids = [self._focus_entity_id] if self._focus_entity_id else []
        try:
            packet = self._oracle.build_context_packet(
                focus_entity_ids=focus_ids,
                location_id=effective_loc,
            )
        except Exception as exc:  # noqa: BLE001 — resilience: isolate stage 1
            logger.warning(
                "[turn_id=%s] oracle stage failed (%s: %s) — degrading to "
                "minimal context packet",
                turn_id, type(exc).__name__, exc,
            )
            stage_errors.append(
                f"build_context_packet: {type(exc).__name__}: {exc}"
            )
            packet = self._degraded_packet()
        logger.debug("[turn_id=%s] stage 1: context packet ready", turn_id)

        # 2. Build prompt + messages
        logger.debug("[turn_id=%s] stage 2: building prompt", turn_id)
        system_prompt = self._prompt_builder.build_system_prompt(
            packet,
            persona_name=self._persona_name,
            persona_notes=self._persona_notes,
        )
        trimmed_history = self._history[-(self._history_limit * 2):]
        messages = self._prompt_builder.build_messages(
            system_prompt, trimmed_history, user_input
        )
        logger.debug("[turn_id=%s] stage 2: prompt ready", turn_id)

        # 3. Generate
        logger.debug("[turn_id=%s] stage 3: generating response", turn_id)
        error: str | None = None
        try:
            response_text = self._connector.chat(messages)
        except OllamaUnavailableError as exc:
            response_text = "[Ollama unavailable — cannot generate response]"
            error = str(exc)
        logger.debug("[turn_id=%s] stage 3: response ready", turn_id)

        # 4. Write to memory — on failure continue with empty record ids;
        #    the detector stage then naturally sees zero facts.
        logger.debug("[turn_id=%s] stage 4: writing turn to memory", turn_id)
        written_ids: dict[str, list[str]] = {"observations": [], "facts": []}
        fact_records: list = []
        try:
            written = self._engine.process_turn(
                user_input=user_input,
                response_text=response_text,
                place_id=effective_loc,
                facts=extra_facts or [],
            )
            written_ids = {
                "observations": [r.record_id for r in written.get("observations", [])],
                "facts": [r.record_id for r in written.get("facts", [])],
            }
            fact_records = written.get("facts", [])
        except Exception as exc:  # noqa: BLE001 — resilience: isolate stage 4
            logger.warning(
                "[turn_id=%s] writeback stage failed (%s: %s) — continuing "
                "turn with empty record ids",
                turn_id, type(exc).__name__, exc,
            )
            stage_errors.append(f"process_turn: {type(exc).__name__}: {exc}")
        logger.debug("[turn_id=%s] stage 4: writeback done", turn_id)

        # 5. Check facts for contradictions — on failure record zero
        #    contradictions and continue; history and response are intact.
        logger.debug("[turn_id=%s] stage 5: checking contradictions", turn_id)
        contradictions_found = 0
        try:
            for fact_record in fact_records:
                found = self._detector.check_and_record(fact_record)
                contradictions_found += len(found)
        except Exception as exc:  # noqa: BLE001 — resilience: isolate stage 5
            logger.warning(
                "[turn_id=%s] detector stage failed (%s: %s) — continuing "
                "turn with zero contradictions",
                turn_id, type(exc).__name__, exc,
            )
            stage_errors.append(f"check_and_record: {type(exc).__name__}: {exc}")
            contradictions_found = 0
        logger.debug("[turn_id=%s] stage 5: contradiction check done", turn_id)

        # 6. Append to history
        logger.debug("[turn_id=%s] stage 6: appending history", turn_id)
        self._history.append({"role": "user", "content": user_input})
        self._history.append({"role": "assistant", "content": response_text})
        logger.debug("[turn_id=%s] stage 6: turn complete", turn_id)

        return TurnResult(
            user_input=user_input,
            assistant_response=response_text,
            context_packet=packet,
            written_record_ids=written_ids,
            contradictions_found=contradictions_found,
            error=error,
            stage_errors=stage_errors,
            run_id=self.run_id,
            turn_id=turn_id,
        )

    # ------------------------------------------------------------------
    # Degraded packet
    # ------------------------------------------------------------------

    @staticmethod
    def _degraded_packet() -> WorldContextPacket:
        """Build a minimal-but-valid WorldContextPacket.

        Used when the oracle stage fails: no memory content and no world
        identity are required for a valid packet — every field except
        ``query_timestamp`` and ``formatted_for_llm`` can honestly be empty,
        and ``world_id`` is nullable in the schema.  The rendered text notes
        the degradation so the LLM does not hallucinate missing context.
        """
        return WorldContextPacket(
            query_timestamp=datetime.now(timezone.utc),
            world_id=None,
            focus_entities=[],
            location_context=None,
            present_entities=[],
            canonical_facts={},
            active_policies=[],
            recent_observations=[],
            open_contradiction_count=0,
            formatted_for_llm=(
                "=== WORLD STATE ===\n"
                "(context unavailable — oracle stage failed; answer from "
                "persona and conversation history only)"
            ),
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
