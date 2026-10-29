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
independently — oracle (1), prompt build (2), connector (3), writeback
engine (4), contradiction detector (5) — is wrapped in its own try/except
so one failing stage degrades the turn instead of aborting it.  Stage
failures are recorded on ``TurnResult.stage_errors`` as
``"stage_name: ExceptionType: message"``.

Phase C4 (circuit breaker wiring): stage 3 no longer catches only
``OllamaUnavailableError``.  The connector call runs through a
:class:`~wyrdforge.hardening.circuit_breaker.CircuitBreaker` owned by
the loop, with a bounded backoff retry *within* the turn (the breaker
sees one verdict per turn: success, or failure after the bounded
attempts are exhausted).  ANY connector exception therefore degrades
the turn exactly as ``OllamaUnavailableError`` always did — fallback
response, ``TurnResult.error`` set, history and later stages intact —
instead of aborting it, and while the circuit is OPEN stage 3 fails
fast (no connector call attempted) until the breaker's half-open
probe is allowed.  Stage 2 is wrapped the same way: a prompt-build
failure degrades to the smallest honest prompt (base instructions +
persona, no world data) and the turn continues.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

from pydantic import Field

from wyrdforge.hardening.backoff import BackoffConfig
from wyrdforge.hardening.circuit_breaker import CircuitBreaker, CircuitOpenError
from wyrdforge.llm.ollama_connector import OllamaConnector
from wyrdforge.llm.prompt_builder import PromptBuilder
from wyrdforge.models.common import StrictModel
from wyrdforge.oracle.models import WorldContextPacket
from wyrdforge.oracle.passive_oracle import PassiveOracle
from wyrdforge.services.contradiction_detector import ContradictionDetector
from wyrdforge.services.writeback_engine import WritebackEngine

if TYPE_CHECKING:
    from wyrdforge.runtime.events import EventBus

logger = logging.getLogger(__name__)

#: Topics emitted by TurnLoop when wired to an EventBus (opt-in via ``bus=``).
_TURN_TOPICS = ("turn.started", "turn.completed")


def _register_turn_topics(bus: "EventBus") -> None:
    """Register the turn.* topics once; tolerate double registration."""
    for topic in _TURN_TOPICS:
        try:
            bus.register_topic(topic)
        except ValueError:
            pass  # already registered — another producer got here first

#: Maximum accepted user_input length (characters).  Guards the prompt
#: builder and the observation writer against pathological input.
MAX_USER_INPUT_LEN = 20000

#: Fallback assistant response when stage 3 cannot generate one
#: (Phase C4: used for EVERY connector failure and for open-circuit
#: fast-fails — the exact degradation ``OllamaUnavailableError``
#: produced before C4).
CONNECTOR_UNAVAILABLE_RESPONSE = "[Ollama unavailable — cannot generate response]"

#: Phase C4 defaults, sized for a flaky local model provider: the
#: breaker opens after 3 consecutive failed *turns* and allows a
#: half-open probe after 30 s; within a turn the connector is tried
#: at most 3 times with backoff delays of ~0.5 s then ~1.0 s, capped
#: at 5 s (never the unbounded stall a turn loop must not risk).
_DEFAULT_CONNECTOR_BACKOFF = BackoffConfig(
    max_attempts=3, base_delay=0.5, max_delay=5.0, multiplier=2.0, jitter=0.25
)


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
        speaker_id:       Phase C3 — the identity the turn's
                          ``user_input`` is attributed to in memory.
                          ``execute_turn``'s contract is that its input
                          is the interlocutor's utterance, so the
                          default is the generic role id ``"user"``;
                          bridges that know their player pass the real
                          id (PythonRPGBridge passes ``"player"``,
                          matching its CharacterContext user_id), and a
                          single turn may override via
                          ``execute_turn(..., speaker_id=...)``.
        circuit_breaker:  Phase C4 — the breaker guarding stage 3's
                          connector call, shared across this loop's
                          turns.  Injectable; the default opens after
                          3 consecutive failed turns and half-opens
                          after 30 s (one probe).
        connector_backoff: Phase C4 — bounded retry policy *within* a
                          turn (default: 3 attempts, ~0.5 s / ~1.0 s
                          delays capped at 5 s).  Tests pass a
                          zero-delay config so no test sleeps.
        backoff_sleeper:  Phase C4 — the sleep function used between
                          backoff attempts (default ``time.sleep``);
                          injectable so tests can record delays
                          instead of waiting (the B5 injectable-source
                          precedent).
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
        speaker_id: str = "user",
        bus: "EventBus | None" = None,
        circuit_breaker: CircuitBreaker | None = None,
        connector_backoff: BackoffConfig | None = None,
        backoff_sleeper: Callable[[float], None] | None = None,
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
        self._speaker_id = speaker_id
        self._prompt_builder = PromptBuilder()
        # Phase C4: stage-3 resilience — one breaker per loop (hence
        # per persona behind the bridges), plus the bounded in-turn
        # retry policy and its injectable sleeper.
        self._circuit_breaker = circuit_breaker or CircuitBreaker(
            failure_threshold=3,
            reset_timeout=30.0,
            half_open_probes=1,
            name="turn-loop-connector",
        )
        self._connector_backoff = connector_backoff or _DEFAULT_CONNECTOR_BACKOFF
        self._backoff_sleeper = backoff_sleeper or time.sleep
        # Phase B1: one TurnLoop is shared by every request thread of
        # its persona behind the threading HTTP server, so the history
        # list is guarded state. _history_lock makes the user+assistant
        # append pair atomic (two turns can never interleave into
        # user/user/assistant/assistant), makes the prompt-build read a
        # consistent snapshot, and serialises clear/get/count. Turns
        # themselves are NOT serialised — the connector call stays
        # outside any lock; only the shared list is guarded.
        self._history_lock = threading.RLock()
        self._history: list[dict[str, str]] = []
        # Observability: one stable identity for the life of this loop.
        self.run_id = uuid.uuid4().hex
        # Opt-in inner-communications wiring: bus=None preserves the exact
        # historical behavior; a bus wires turn events into the EventBus.
        self._bus = bus
        if self._bus is not None:
            _register_turn_topics(self._bus)

    # ------------------------------------------------------------------
    # Phase C4 — stage-3 resilience surface
    # ------------------------------------------------------------------

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        """The breaker guarding this loop's connector (Phase C4).

        Exposed so operators and tests can read ``stats()`` / ``state``
        and call ``reset()``; the loop itself only calls ``call()``.
        """
        return self._circuit_breaker

    @property
    def connector_backoff(self) -> BackoffConfig:
        """The bounded in-turn retry policy for the connector (Phase C4)."""
        return self._connector_backoff

    def _call_connector_with_backoff(self, messages: list[dict[str, str]]) -> str:
        """One breaker-visible connector call: bounded retries within the turn.

        Every connector exception is treated as potentially transient
        for the bounded attempts (the breaker, not this loop, decides
        across turns whether the dependency is down).  After the final
        attempt the last exception propagates to the breaker, which
        counts the turn as one failure.  The attempt count is the
        config's ``max_attempts`` — bounded by construction, never an
        unbounded loop.
        """
        cfg = self._connector_backoff
        last_exc: Exception | None = None
        for attempt in range(cfg.max_attempts):
            try:
                return self._connector.chat(messages)
            except Exception as exc:  # noqa: BLE001 — any connector error may be transient
                last_exc = exc
                if attempt < cfg.max_attempts - 1:
                    self._backoff_sleeper(cfg.delay_for(attempt))
        assert last_exc is not None  # max_attempts >= 1 is config-validated
        raise last_exc

    def _fallback_system_prompt(self) -> str:
        """The smallest honest system prompt (Phase C4 stage-2 fallback).

        Base instructions + persona only — no world data block, since
        assembling that block is what failed.  Mirrors the persona
        handling of ``PromptBuilder.build_system_prompt``.
        """
        base = getattr(self._prompt_builder, "base_instructions", None)
        if not base:
            base = getattr(self._prompt_builder, "_base", None) or (
                "You are a character in a Norse-inspired story world. "
                "Stay in character and answer based solely on the world "
                "state provided."
            )
        parts: list[str] = [base]
        if self._persona_name:
            parts.append(f"\nYou are {self._persona_name}.")
        if self._persona_notes:
            parts.append(f"Character notes: {self._persona_notes}")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Main API
    # ------------------------------------------------------------------

    def execute_turn(
        self,
        user_input: str,
        *,
        location_id: str | None = None,
        extra_facts: list[dict] | None = None,
        speaker_id: str | None = None,
    ) -> TurnResult:
        """Execute one conversation turn.

        Args:
            user_input:  The user's message text.
            location_id: Override the default location for this turn.
            extra_facts: Optional pre-parsed facts to write to MIMIR alongside
                         the observation.  Each dict must have:
                         ``{fact_subject_id, fact_key, fact_value, confidence?, domain?}``
            speaker_id:  Per-turn override of the loop's speaker
                         attribution (Phase C3); defaults to the
                         loop's ``speaker_id``.

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

        # Wired event: announce the turn before the oracle stage runs.
        self._emit(
            "turn.started",
            {"turn_id": turn_id, "run_id": self.run_id, "input_len": len(user_input)},
            turn_id=turn_id,
        )

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

        # 2. Build prompt + messages — degrade to the smallest honest
        #    prompt on failure (Phase C4, following stage 1's precedent):
        #    base instructions + persona as the system prompt, the history
        #    snapshot and the user's input assembled directly, and the
        #    turn continues to the connector.
        logger.debug("[turn_id=%s] stage 2: building prompt", turn_id)
        with self._history_lock:
            trimmed_history = self._history[-(self._history_limit * 2):]
        try:
            system_prompt = self._prompt_builder.build_system_prompt(
                packet,
                persona_name=self._persona_name,
                persona_notes=self._persona_notes,
            )
            messages = self._prompt_builder.build_messages(
                system_prompt, trimmed_history, user_input
            )
        except Exception as exc:  # noqa: BLE001 — resilience: isolate stage 2
            logger.warning(
                "[turn_id=%s] prompt stage failed (%s: %s) — degrading to "
                "base-instructions prompt",
                turn_id, type(exc).__name__, exc,
            )
            stage_errors.append(f"build_prompt: {type(exc).__name__}: {exc}")
            system_prompt = self._fallback_system_prompt()
            messages = [
                {"role": "system", "content": system_prompt},
                *trimmed_history,
                {"role": "user", "content": user_input},
            ]
        logger.debug("[turn_id=%s] stage 2: prompt ready", turn_id)

        # 3. Generate — through the circuit breaker with bounded in-turn
        #    backoff (Phase C4).  ANY connector exception degrades the
        #    turn exactly as OllamaUnavailableError did before C4; an
        #    open circuit fails fast without calling the connector.
        logger.debug("[turn_id=%s] stage 3: generating response", turn_id)
        error: str | None = None
        try:
            response_text = self._circuit_breaker.call(
                self._call_connector_with_backoff, messages
            )
        except CircuitOpenError as exc:
            logger.warning(
                "[turn_id=%s] connector circuit open (%s) — failing fast, "
                "connector not called",
                turn_id, exc,
            )
            stage_errors.append(
                f"generate_response: {type(exc).__name__}: {exc}"
            )
            response_text = CONNECTOR_UNAVAILABLE_RESPONSE
            error = str(exc)
        except Exception as exc:  # noqa: BLE001 — resilience: isolate stage 3
            logger.warning(
                "[turn_id=%s] connector stage failed after bounded retries "
                "(%s: %s) — degrading response",
                turn_id, type(exc).__name__, exc,
            )
            stage_errors.append(
                f"generate_response: {type(exc).__name__}: {exc}"
            )
            response_text = CONNECTOR_UNAVAILABLE_RESPONSE
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
                speaker_id=speaker_id or self._speaker_id,
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

        # 6. Append to history — the pair lands atomically (Phase B1):
        #    a concurrent turn's pair can never interleave into this one.
        logger.debug("[turn_id=%s] stage 6: appending history", turn_id)
        with self._history_lock:
            self._history.append({"role": "user", "content": user_input})
            self._history.append({"role": "assistant", "content": response_text})
        logger.debug("[turn_id=%s] stage 6: turn complete", turn_id)

        result = TurnResult(
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

        # Wired event: always announce completion — even when stages
        # degraded.  The turn itself must never be aborted by bus trouble.
        self._emit(
            "turn.completed",
            {
                "turn_id": turn_id,
                "run_id": self.run_id,
                "contradictions_found": contradictions_found,
                "stage_errors": list(stage_errors),
                "degraded": bool(stage_errors or error),
            },
            turn_id=turn_id,
        )
        return result

    # ------------------------------------------------------------------
    # Bus wiring helper
    # ------------------------------------------------------------------

    def _emit(self, topic: str, payload: dict, *, turn_id: str | None = None) -> None:
        """Publish an event envelope; never disturb turn execution.

        No-op when this TurnLoop is not bus-wired.  Bus errors are
        swallowed here — the contract is that the turn completes
        regardless of bus health.
        """
        bus = getattr(self, "_bus", None)
        if bus is None:
            return
        try:
            bus.publish(topic, payload, source="runtime.turn_loop", turn_id=turn_id)
        except Exception:
            pass

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
        with self._history_lock:
            self._history.clear()

    def get_history(self) -> list[dict[str, str]]:
        """Return a copy of the current conversation history."""
        with self._history_lock:
            return list(self._history)

    def history_turn_count(self) -> int:
        """Number of complete user/assistant turn-pairs in history."""
        with self._history_lock:
            return len(self._history) // 2
