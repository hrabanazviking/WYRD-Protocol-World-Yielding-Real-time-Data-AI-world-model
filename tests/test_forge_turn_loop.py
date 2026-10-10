"""Forge tests — TurnLoop resilience weave (slices 6, 7, 8).

Slice 6: per-stage fault isolation — oracle (stage 1), writeback engine
         (stage 4), and contradiction detector (stage 5) each raise in turn;
         the turn must still return a TurnResult with stage_errors populated
         and the assistant response intact when the connector works.
Slice 7: input validation — TypeError for non-str, ValueError for
         empty/whitespace and over-length input.
Slice 8: observability — run_id stable per TurnLoop, turn_id unique per
         execute_turn, debug logs tagged with turn_id.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from types import SimpleNamespace

from wyrdforge.oracle.models import WorldContextPacket
from wyrdforge.runtime.turn_loop import MAX_USER_INPUT_LEN, TurnLoop, TurnResult


# ---------------------------------------------------------------------------
# Stubs
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
    def __init__(self, fail: Exception | None = None) -> None:
        self.fail = fail

    def build_context_packet(self, **kwargs):
        if self.fail is not None:
            raise self.fail
        return _stub_packet()


class StubEngine:
    def __init__(self, fail: Exception | None = None) -> None:
        self.fail = fail

    def process_turn(self, **kwargs):
        if self.fail is not None:
            raise self.fail
        return {
            "observations": [SimpleNamespace(record_id="obs_1")],
            "facts": [SimpleNamespace(record_id="fact_1")],
        }


class StubDetector:
    def __init__(self, fail: Exception | None = None) -> None:
        self.fail = fail

    def check_and_record(self, fact_record):
        if self.fail is not None:
            raise self.fail
        return []


class StubConnector:
    def __init__(self, response: str = "canned reply") -> None:
        self.response = response

    def chat(self, messages, **kwargs):
        return self.response


def _build_loop(
    oracle=None, engine=None, detector=None, connector=None,
) -> TurnLoop:
    return TurnLoop(
        oracle or StubOracle(),
        engine or StubEngine(),
        detector or StubDetector(),
        connector or StubConnector(),
    )


# ---------------------------------------------------------------------------
# Slice 6 — per-stage fault isolation
# ---------------------------------------------------------------------------

def test_oracle_failure_degrades_to_minimal_packet() -> None:
    loop = _build_loop(oracle=StubOracle(fail=RuntimeError("memory exploded")))
    result = loop.execute_turn("hello")
    assert isinstance(result, TurnResult)
    assert result.stage_errors == ["build_context_packet: RuntimeError: memory exploded"]
    # Minimal-but-valid packet: schema-valid, world identity empty.
    assert isinstance(result.context_packet, WorldContextPacket)
    assert result.context_packet.world_id is None
    assert result.context_packet.recent_observations == []
    assert "oracle stage failed" in result.context_packet.formatted_for_llm
    # The rest of the turn still works.
    assert result.assistant_response == "canned reply"
    assert result.written_record_ids["observations"] == ["obs_1"]
    assert result.error is None


def test_writeback_failure_continues_with_empty_ids() -> None:
    loop = _build_loop(engine=StubEngine(fail=RuntimeError("store down")))
    result = loop.execute_turn("hello")
    assert isinstance(result, TurnResult)
    assert result.stage_errors == ["process_turn: RuntimeError: store down"]
    assert result.written_record_ids == {"observations": [], "facts": []}
    assert result.contradictions_found == 0
    assert result.assistant_response == "canned reply"
    # History still records the turn.
    assert loop.history_turn_count() == 1


def test_detector_failure_continues_with_zero_contradictions() -> None:
    loop = _build_loop(detector=StubDetector(fail=RuntimeError("detector blew up")))
    result = loop.execute_turn("hello")
    assert isinstance(result, TurnResult)
    assert result.stage_errors == ["check_and_record: RuntimeError: detector blew up"]
    assert result.contradictions_found == 0
    # Writeback ids survive the detector failure.
    assert result.written_record_ids == {
        "observations": ["obs_1"], "facts": ["fact_1"],
    }
    assert result.assistant_response == "canned reply"


def test_all_stages_healthy_no_stage_errors() -> None:
    loop = _build_loop()
    result = loop.execute_turn("hello")
    assert result.stage_errors == []
    assert result.error is None
    assert result.assistant_response == "canned reply"


def test_multiple_stage_failures_all_recorded() -> None:
    loop = _build_loop(
        oracle=StubOracle(fail=RuntimeError("oracle down")),
        engine=StubEngine(fail=ValueError("engine down")),
    )
    result = loop.execute_turn("hello")
    assert len(result.stage_errors) == 2
    assert result.stage_errors[0].startswith("build_context_packet: RuntimeError:")
    assert result.stage_errors[1].startswith("process_turn: ValueError:")
    assert result.assistant_response == "canned reply"


# ---------------------------------------------------------------------------
# Slice 7 — input validation
# ---------------------------------------------------------------------------

def test_non_string_input_raises_type_error() -> None:
    loop = _build_loop()
    for bad in (None, 123, b"bytes", ["hello"]):
        try:
            loop.execute_turn(bad)  # type: ignore[arg-type]
        except TypeError as exc:
            assert "must be a string" in str(exc)
        else:
            raise AssertionError(f"expected TypeError for {bad!r}")


def test_empty_and_whitespace_input_raise_value_error() -> None:
    loop = _build_loop()
    for bad in ("", "   ", "\n\t  "):
        try:
            loop.execute_turn(bad)
        except ValueError as exc:
            assert "empty or whitespace" in str(exc)
        else:
            raise AssertionError(f"expected ValueError for {bad!r}")


def test_oversize_input_raises_value_error() -> None:
    loop = _build_loop()
    try:
        loop.execute_turn("x" * (MAX_USER_INPUT_LEN + 1))
    except ValueError as exc:
        assert str(MAX_USER_INPUT_LEN) in str(exc)
    else:
        raise AssertionError("expected ValueError for oversize input")


def test_max_length_input_is_accepted() -> None:
    loop = _build_loop()
    result = loop.execute_turn("x" * MAX_USER_INPUT_LEN)
    assert result.user_input == "x" * MAX_USER_INPUT_LEN
    assert result.stage_errors == []


def test_validation_happens_before_any_stage_runs() -> None:
    # The oracle must never see invalid input.
    oracle = StubOracle()
    loop = _build_loop(oracle=oracle)
    calls = []
    orig = oracle.build_context_packet
    oracle.build_context_packet = lambda **kw: calls.append(kw) or orig(**kw)
    try:
        loop.execute_turn("")
    except ValueError:
        pass
    assert calls == []


# ---------------------------------------------------------------------------
# Slice 8 — observability
# ---------------------------------------------------------------------------

def test_two_turns_have_distinct_turn_ids() -> None:
    loop = _build_loop()
    first = loop.execute_turn("one")
    second = loop.execute_turn("two")
    assert first.turn_id != second.turn_id
    assert len(first.turn_id) == 32
    assert len(second.turn_id) == 32


def test_turn_result_run_id_matches_loop_run_id() -> None:
    loop = _build_loop()
    result = loop.execute_turn("hello")
    assert result.run_id == loop.run_id
    assert len(loop.run_id) == 32
    assert all(c in "0123456789abcdef" for c in loop.run_id)


def test_run_id_stable_across_turns() -> None:
    loop = _build_loop()
    first = loop.execute_turn("one")
    second = loop.execute_turn("two")
    assert first.run_id == second.run_id == loop.run_id


def test_distinct_loops_have_distinct_run_ids() -> None:
    assert _build_loop().run_id != _build_loop().run_id


def test_stage_debug_logs_tagged_with_turn_id(caplog) -> None:
    loop = _build_loop()
    with caplog.at_level(logging.DEBUG, logger="wyrdforge.runtime.turn_loop"):
        result = loop.execute_turn("hello")
    tagged = f"[turn_id={result.turn_id}]"
    assert tagged in caplog.text
    # All six stage boundaries emit.
    assert caplog.text.count(tagged) >= 6
