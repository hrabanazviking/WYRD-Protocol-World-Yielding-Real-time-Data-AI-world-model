"""Phase C4 tests — circuit breaker wiring in TurnLoop stage 3 + stage 2 wrap.

Before C4 the breaker existed with zero callers, stage 3 caught only
``OllamaUnavailableError`` (any other connector exception aborted the
turn), and stage 2 (prompt build) was unwrapped.  These tests pin:

- stage 3 routes through a TurnLoop-owned CircuitBreaker; ALL connector
  exceptions degrade the turn exactly as OllamaUnavailableError did
  (fallback response, ``error`` set, stage_errors recorded, history and
  later stages intact) instead of aborting;
- bounded backoff within a turn (attempt count + injected sleeper, so
  no test ever really sleeps) composing with the breaker across turns
  (one breaker verdict per turn);
- the breaker opening after threshold consecutive failed turns, fast-
  failing while open (connector provably not called), and half-open
  probes (driven by an injected fake clock on the breaker) closing on
  success and re-opening on failure;
- stage 2 degrading to the smallest honest prompt (base instructions +
  persona, no world data) when prompt assembly raises;
- healthy turns behaving exactly as before C4.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from wyrdforge.hardening.backoff import BackoffConfig
from wyrdforge.hardening.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
)
from wyrdforge.llm.ollama_connector import OllamaUnavailableError
from wyrdforge.oracle.models import WorldContextPacket
from wyrdforge.runtime.turn_loop import (
    CONNECTOR_UNAVAILABLE_RESPONSE,
    TurnLoop,
    TurnResult,
)

# ---------------------------------------------------------------------------
# Stubs (forge turn-loop pattern)
# ---------------------------------------------------------------------------


def _stub_packet() -> WorldContextPacket:
    return WorldContextPacket(
        query_timestamp=datetime.now(timezone.utc),
        world_id="stub_world",
        focus_entities=[],
        location_context=None,
        present_entities=[],
        canonical_facts={},
        active_policies=[],
        recent_observations=[],
        open_contradiction_count=0,
        formatted_for_llm="stub context",
    )


class StubOracle:
    def build_context_packet(self, **kwargs):
        return _stub_packet()


class StubEngine:
    def process_turn(self, **kwargs):
        return {
            "observations": [SimpleNamespace(record_id="obs_1")],
            "facts": [SimpleNamespace(record_id="fact_1")],
        }


class StubDetector:
    def check_and_record(self, fact_record):
        return []


class FakeClock:
    """Injectable monotonic clock for the breaker (no real waiting)."""

    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class CountingConnector:
    """Connector whose behaviour can be flipped mid-test; counts calls."""

    def __init__(self, exc: Exception | None = None, response: str = "canned reply"):
        self.exc = exc
        self.response = response
        self.calls: list[list[dict]] = []

    def chat(self, messages, **kwargs):
        self.calls.append(messages)
        if self.exc is not None:
            raise self.exc
        return self.response


class FlakyConnector:
    """Fails the first ``failures`` calls, then succeeds."""

    def __init__(self, failures: int, exc: Exception | None = None):
        self.remaining = failures
        self.exc = exc or ConnectionError("transient blip")
        self.calls = 0

    def chat(self, messages, **kwargs):
        self.calls += 1
        if self.remaining > 0:
            self.remaining -= 1
            raise self.exc
        return "recovered reply"


_ZERO_BACKOFF = BackoffConfig(max_attempts=1, base_delay=0.0, max_delay=0.0, jitter=0.0)


def _build_loop(connector, *, breaker=None, backoff=None, sleeper=None, **kwargs):
    return TurnLoop(
        StubOracle(),
        StubEngine(),
        StubDetector(),
        connector,
        circuit_breaker=breaker,
        connector_backoff=backoff if backoff is not None else _ZERO_BACKOFF,
        backoff_sleeper=sleeper if sleeper is not None else (lambda _d: None),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Stage 3 — every connector exception degrades, none aborts
# ---------------------------------------------------------------------------


def test_runtime_error_from_connector_degrades_instead_of_aborting() -> None:
    conn = CountingConnector(exc=RuntimeError("connector exploded"))
    loop = _build_loop(conn)
    result = loop.execute_turn("hello")
    assert isinstance(result, TurnResult)
    assert result.assistant_response == CONNECTOR_UNAVAILABLE_RESPONSE
    assert result.error == "connector exploded"
    assert result.stage_errors == [
        "generate_response: RuntimeError: connector exploded"
    ]
    # Later stages + history survive the degraded generation.
    assert result.written_record_ids["observations"] == ["obs_1"]
    assert loop.history_turn_count() == 1


def test_connection_error_from_connector_degrades() -> None:
    conn = CountingConnector(exc=ConnectionError("connection refused"))
    loop = _build_loop(conn)
    result = loop.execute_turn("hello")
    assert result.assistant_response == CONNECTOR_UNAVAILABLE_RESPONSE
    assert result.error == "connection refused"
    assert result.stage_errors == [
        "generate_response: ConnectionError: connection refused"
    ]


def test_ollama_unavailable_degrades_exactly_as_before_c4() -> None:
    conn = CountingConnector(exc=OllamaUnavailableError("test server down"))
    loop = _build_loop(conn)
    result = loop.execute_turn("hello")
    assert result.assistant_response == "[Ollama unavailable — cannot generate response]"
    assert result.error == "test server down"
    # C4's additive recording: the failure is now also in stage_errors.
    assert result.stage_errors == [
        "generate_response: OllamaUnavailableError: test server down"
    ]


# ---------------------------------------------------------------------------
# Bounded backoff within the turn
# ---------------------------------------------------------------------------


def test_backoff_attempt_bound_and_delays_are_exact() -> None:
    conn = CountingConnector(exc=RuntimeError("down"))
    sleeps: list[float] = []
    backoff = BackoffConfig(
        max_attempts=3, base_delay=0.5, max_delay=5.0, multiplier=2.0, jitter=0.0
    )
    breaker = CircuitBreaker(failure_threshold=5, reset_timeout=60.0, name="t")
    loop = _build_loop(conn, breaker=breaker, backoff=backoff, sleeper=sleeps.append)
    result = loop.execute_turn("hello")
    # Bounded: exactly max_attempts connector calls, max_attempts-1 sleeps
    # of the config's exact capped delays, then degradation — no abort,
    # no unbounded loop.
    assert len(conn.calls) == 3
    assert sleeps == [0.5, 1.0]
    assert result.assistant_response == CONNECTOR_UNAVAILABLE_RESPONSE
    assert len(result.stage_errors) == 1
    # One breaker verdict for the whole turn, not one per attempt.
    stats = breaker.stats()
    assert stats["total_calls"] == 1
    assert stats["total_failures"] == 1


def test_transient_failure_recovers_within_the_turn() -> None:
    conn = FlakyConnector(failures=2)
    sleeps: list[float] = []
    backoff = BackoffConfig(
        max_attempts=3, base_delay=0.25, max_delay=5.0, multiplier=2.0, jitter=0.0
    )
    breaker = CircuitBreaker(failure_threshold=3, reset_timeout=60.0, name="t")
    loop = _build_loop(conn, breaker=breaker, backoff=backoff, sleeper=sleeps.append)
    result = loop.execute_turn("hello")
    assert result.assistant_response == "recovered reply"
    assert result.error is None
    assert result.stage_errors == []
    assert conn.calls == 3
    assert sleeps == [0.25, 0.5]
    stats = breaker.stats()
    assert stats["total_successes"] == 1
    assert stats["total_failures"] == 0
    assert breaker.state is CircuitState.CLOSED


def test_permanently_down_connector_bounded_then_degrades_every_turn() -> None:
    conn = CountingConnector(exc=RuntimeError("permanently down"))
    backoff = BackoffConfig(
        max_attempts=2, base_delay=0.0, max_delay=0.0, jitter=0.0
    )
    breaker = CircuitBreaker(failure_threshold=10, reset_timeout=60.0, name="t")
    loop = _build_loop(conn, breaker=breaker, backoff=backoff)
    for _ in range(3):
        result = loop.execute_turn("hello")
        assert result.assistant_response == CONNECTOR_UNAVAILABLE_RESPONSE
    assert len(conn.calls) == 6  # 2 attempts x 3 turns — bounded throughout
    assert loop.history_turn_count() == 3


# ---------------------------------------------------------------------------
# Breaker across turns — open, fast-fail, half-open probes
# ---------------------------------------------------------------------------


def test_breaker_opens_after_threshold_turns_and_skips_connector() -> None:
    conn = CountingConnector(exc=RuntimeError("down"))
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout=60.0, name="t")
    loop = _build_loop(conn, breaker=breaker)

    loop.execute_turn("one")
    assert breaker.state is CircuitState.CLOSED
    loop.execute_turn("two")
    assert breaker.state is CircuitState.OPEN
    assert len(conn.calls) == 2

    result = loop.execute_turn("three")
    assert len(conn.calls) == 2  # fast fail: connector NOT called again
    assert result.assistant_response == CONNECTOR_UNAVAILABLE_RESPONSE
    assert result.stage_errors[0].startswith("generate_response: CircuitOpenError:")
    assert result.error is not None and "OPEN" in result.error
    assert breaker.stats()["total_rejected"] == 1
    # The fast-failed turn still completes its other stages.
    assert result.written_record_ids["observations"] == ["obs_1"]
    assert loop.history_turn_count() == 3


def test_half_open_probe_success_closes_circuit() -> None:
    clock = FakeClock()
    conn = CountingConnector(exc=RuntimeError("down"))
    breaker = CircuitBreaker(
        failure_threshold=1, reset_timeout=30.0, name="t", clock=clock
    )
    loop = _build_loop(conn, breaker=breaker)

    loop.execute_turn("one")
    assert breaker.state is CircuitState.OPEN

    blocked = loop.execute_turn("two")  # no time passed: still fast-fail
    assert len(conn.calls) == 1
    assert blocked.stage_errors[0].startswith("generate_response: CircuitOpenError:")

    clock.advance(31.0)  # recovery timeout elapsed (injected clock)
    conn.exc = None  # dependency recovered
    result = loop.execute_turn("three")
    assert result.assistant_response == "canned reply"
    assert result.stage_errors == []
    assert len(conn.calls) == 2  # exactly one probe call
    assert breaker.state is CircuitState.CLOSED


def test_half_open_probe_failure_reopens_circuit() -> None:
    clock = FakeClock()
    conn = CountingConnector(exc=RuntimeError("still down"))
    breaker = CircuitBreaker(
        failure_threshold=1, reset_timeout=30.0, name="t", clock=clock
    )
    loop = _build_loop(conn, breaker=breaker)

    loop.execute_turn("one")
    assert breaker.stats()["open_count"] == 1

    clock.advance(31.0)
    probe = loop.execute_turn("two")
    assert len(conn.calls) == 2  # the probe WAS attempted
    assert probe.assistant_response == CONNECTOR_UNAVAILABLE_RESPONSE
    assert probe.stage_errors == ["generate_response: RuntimeError: still down"]
    assert breaker.state is CircuitState.OPEN
    assert breaker.stats()["open_count"] == 2  # re-opened by the failed probe

    blocked = loop.execute_turn("three")  # open again: fast fail
    assert len(conn.calls) == 2
    assert blocked.stage_errors[0].startswith("generate_response: CircuitOpenError:")


def test_success_between_failures_resets_breaker_count() -> None:
    conn = CountingConnector(exc=RuntimeError("down"))
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout=60.0, name="t")
    loop = _build_loop(conn, breaker=breaker)

    loop.execute_turn("fail 1")
    conn.exc = None
    loop.execute_turn("ok 1")
    conn.exc = RuntimeError("down")
    loop.execute_turn("fail 2")
    conn.exc = None
    result = loop.execute_turn("ok 2")
    # Failures were never consecutive, so the circuit never opened and
    # every turn reached the connector.
    assert breaker.state is CircuitState.CLOSED
    assert len(conn.calls) == 4
    assert result.assistant_response == "canned reply"


# ---------------------------------------------------------------------------
# Healthy turns + defaults — behaviour identical to pre-C4
# ---------------------------------------------------------------------------


def test_healthy_turn_unchanged_and_breaker_records_success() -> None:
    conn = CountingConnector()
    sleeps: list[float] = []
    loop = _build_loop(conn, sleeper=sleeps.append)
    result = loop.execute_turn("hello")
    assert result.assistant_response == "canned reply"
    assert result.error is None
    assert result.stage_errors == []
    assert len(conn.calls) == 1
    assert sleeps == []  # no backoff on success
    stats = loop.circuit_breaker.stats()
    assert stats["total_successes"] == 1
    assert stats["total_failures"] == 0


def test_default_breaker_and_backoff_wiring() -> None:
    loop = TurnLoop(StubOracle(), StubEngine(), StubDetector(), CountingConnector())
    breaker = loop.circuit_breaker
    assert isinstance(breaker, CircuitBreaker)
    assert breaker.stats()["name"] == "turn-loop-connector"
    assert breaker.state is CircuitState.CLOSED
    backoff = loop.connector_backoff
    assert backoff.max_attempts == 3
    assert backoff.base_delay == 0.5
    assert backoff.max_delay == 5.0


# ---------------------------------------------------------------------------
# Stage 2 — prompt build failure degrades to the smallest honest prompt
# ---------------------------------------------------------------------------


class _ExplodingPromptBuilder:
    """PromptBuilder stand-in whose system-prompt build always raises."""

    base_instructions = "STUB BASE INSTRUCTIONS"

    def build_system_prompt(self, packet, **kwargs):
        raise RuntimeError("prompt exploded")

    def build_messages(self, system_prompt, history, user_input):
        raise AssertionError("fallback must not route through build_messages")


class _ExplodingMessagesBuilder:
    """PromptBuilder stand-in that fails only at message assembly."""

    base_instructions = "STUB BASE INSTRUCTIONS"

    def build_system_prompt(self, packet, **kwargs):
        return "assembled prompt"

    def build_messages(self, system_prompt, history, user_input):
        raise ValueError("messages exploded")


def test_stage2_system_prompt_failure_degrades_to_base_prompt() -> None:
    conn = CountingConnector()
    loop = _build_loop(conn, persona_name="Gunnar")
    loop._prompt_builder = _ExplodingPromptBuilder()
    result = loop.execute_turn("hello there")
    assert result.stage_errors == ["build_prompt: RuntimeError: prompt exploded"]
    assert result.error is None
    assert result.assistant_response == "canned reply"
    # The connector received the fallback messages: base instructions +
    # persona as system, then history, then the user input — and no
    # world-data block (assembling it is what failed).
    messages = conn.calls[0]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"].startswith("STUB BASE INSTRUCTIONS")
    assert "You are Gunnar." in messages[0]["content"]
    assert "stub context" not in messages[0]["content"]
    assert messages[-1] == {"role": "user", "content": "hello there"}
    assert loop.history_turn_count() == 1


def test_stage2_messages_failure_degrades_to_base_prompt() -> None:
    conn = CountingConnector()
    loop = _build_loop(conn)
    loop._prompt_builder = _ExplodingMessagesBuilder()
    result = loop.execute_turn("hello")
    assert result.stage_errors == ["build_prompt: ValueError: messages exploded"]
    assert result.assistant_response == "canned reply"
    messages = conn.calls[0]
    assert messages[0]["content"].startswith("STUB BASE INSTRUCTIONS")
    assert messages[-1] == {"role": "user", "content": "hello"}


def test_stage2_fallback_includes_history_snapshot() -> None:
    conn = CountingConnector()
    loop = _build_loop(conn)
    first = loop.execute_turn("first question")
    assert first.stage_errors == []
    loop._prompt_builder = _ExplodingPromptBuilder()
    result = loop.execute_turn("second question")
    assert result.stage_errors == ["build_prompt: RuntimeError: prompt exploded"]
    contents = [m["content"] for m in conn.calls[-1]]
    assert "first question" in contents
    assert "canned reply" in contents
    assert contents[-1] == "second question"
