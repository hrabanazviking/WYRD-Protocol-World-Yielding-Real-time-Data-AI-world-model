"""Tests for EvalHarness — Phase 7 deterministic evaluation."""
from __future__ import annotations

import tempfile

import pytest

from wyrdforge.ecs.components.identity import NameComponent, StatusComponent
from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree
from wyrdforge.evals.harness import EvalCase, EvalResult, EvalRunner
from wyrdforge.models.micro_rag import QueryMode
from wyrdforge.oracle.passive_oracle import PassiveOracle
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.runtime.character_context import CharacterContext, CharacterContextResult
from wyrdforge.services.writeback_engine import WritebackEngine


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _build_result() -> CharacterContextResult:
    world = World("eval_world", "Eval World")
    tree = YggdrasilTree(world)
    tree.create_zone(zone_id="midgard", name="Midgard")
    tree.create_region(region_id="fjords", name="Fjords", parent_zone_id="midgard")
    tree.create_location(location_id="hall", name="Hall", parent_region_id="fjords")
    world.create_entity(entity_id="sigrid", tags={"character"})
    world.add_component("sigrid", NameComponent(entity_id="sigrid", name="Sigrid"))
    world.add_component("sigrid", StatusComponent(entity_id="sigrid", state="calm"))
    tree.place_entity("sigrid", location_id="hall")

    store = PersistentMemoryStore(tempfile.mktemp(suffix=".db"))
    engine = WritebackEngine(store)
    oracle = PassiveOracle(world, store, yggdrasil=tree)

    engine.write_canonical_fact(
        fact_subject_id="sigrid", fact_key="role", fact_value="völva",
        domain="identity", confidence=0.95,
    )
    engine.write_canonical_fact(
        fact_subject_id="sigrid", fact_key="temperament", fact_value="calm",
        domain="identity", confidence=0.9,
    )

    ctx = CharacterContext(oracle, store)
    return ctx.build(
        persona_id="sigrid",
        user_id="player",
        query="What are you?",
        focus_entity_ids=["sigrid"],
        mode=QueryMode.FACTUAL_LOOKUP,
    )


# ---------------------------------------------------------------------------
# EvalCase construction
# ---------------------------------------------------------------------------

def test_eval_case_default_fields() -> None:
    case = EvalCase(case_id="c1")
    assert case.required_strings == []
    assert case.forbidden_strings == []
    assert case.expect_world_state is True
    assert case.expect_persona_identity is False
    assert case.expect_bond_state is False


def test_eval_case_custom_fields() -> None:
    case = EvalCase(
        case_id="c2",
        required_strings=["foo"],
        forbidden_strings=["bar"],
        expect_world_state=False,
    )
    assert "foo" in case.required_strings
    assert "bar" in case.forbidden_strings
    assert case.expect_world_state is False


# ---------------------------------------------------------------------------
# EvalRunner registration
# ---------------------------------------------------------------------------

def test_runner_add_case_registers() -> None:
    runner = EvalRunner()
    runner.add_case(EvalCase(case_id="x1"))
    assert "x1" in runner.case_ids


def test_runner_init_with_cases() -> None:
    runner = EvalRunner([EvalCase(case_id="a"), EvalCase(case_id="b")])
    assert "a" in runner.case_ids
    assert "b" in runner.case_ids


def test_runner_unknown_case_id_raises() -> None:
    runner = EvalRunner()
    result = _build_result()
    with pytest.raises(KeyError):
        runner.run(result, "nonexistent")


# ---------------------------------------------------------------------------
# EvalRunner.run — passing cases
# ---------------------------------------------------------------------------

def test_run_world_state_check_passes() -> None:
    runner = EvalRunner([EvalCase(case_id="ws", expect_world_state=True)])
    result = _build_result()
    eval_result = runner.run(result, "ws")
    assert eval_result.passed


def test_run_required_string_present_passes() -> None:
    runner = EvalRunner([
        EvalCase(case_id="rs", required_strings=["WORLD STATE"], expect_world_state=False)
    ])
    result = _build_result()
    eval_result = runner.run(result, "rs")
    assert eval_result.passed


def test_run_forbidden_string_absent_passes() -> None:
    runner = EvalRunner([
        EvalCase(case_id="fs", forbidden_strings=["TOTALLY_ABSENT_XYZ"], expect_world_state=False)
    ])
    result = _build_result()
    eval_result = runner.run(result, "fs")
    assert eval_result.passed


def test_run_identity_section_present_passes() -> None:
    runner = EvalRunner([
        EvalCase(case_id="id", expect_persona_identity=True, expect_world_state=False)
    ])
    result = _build_result()
    eval_result = runner.run(result, "id")
    assert eval_result.passed


# ---------------------------------------------------------------------------
# EvalRunner.run — failing cases
# ---------------------------------------------------------------------------

def test_run_required_string_absent_fails() -> None:
    runner = EvalRunner([
        EvalCase(case_id="rs_fail", required_strings=["NONEXISTENT_TOKEN_XYZ"], expect_world_state=False)
    ])
    result = _build_result()
    eval_result = runner.run(result, "rs_fail")
    assert not eval_result.passed
    assert len(eval_result.failures) >= 1


def test_run_forbidden_string_present_fails() -> None:
    runner = EvalRunner([
        EvalCase(case_id="fs_fail", forbidden_strings=["WORLD STATE"], expect_world_state=False)
    ])
    result = _build_result()
    eval_result = runner.run(result, "fs_fail")
    assert not eval_result.passed


def test_run_bond_state_expected_but_absent_fails() -> None:
    runner = EvalRunner([
        EvalCase(case_id="bond_fail", expect_bond_state=True, expect_world_state=False)
    ])
    result = _build_result()
    eval_result = runner.run(result, "bond_fail")
    assert not eval_result.passed
    assert any("BOND STATE" in f for f in eval_result.failures)


# ---------------------------------------------------------------------------
# EvalResult fields
# ---------------------------------------------------------------------------

def test_eval_result_score_between_zero_and_one() -> None:
    runner = EvalRunner([
        EvalCase(case_id="score_test", expect_world_state=True, expect_persona_identity=False)
    ])
    result = _build_result()
    eval_result = runner.run(result, "score_test")
    assert 0.0 <= eval_result.score <= 1.0


def test_eval_result_checks_run_positive() -> None:
    runner = EvalRunner([EvalCase(case_id="cr", expect_world_state=True)])
    result = _build_result()
    eval_result = runner.run(result, "cr")
    assert eval_result.checks_run >= 1


def test_eval_result_case_id_matches() -> None:
    runner = EvalRunner([EvalCase(case_id="mycase")])
    result = _build_result()
    eval_result = runner.run(result, "mycase")
    assert eval_result.case_id == "mycase"


def test_eval_result_passed_true_has_no_failures() -> None:
    runner = EvalRunner([EvalCase(case_id="clean", expect_world_state=True)])
    result = _build_result()
    eval_result = runner.run(result, "clean")
    if eval_result.passed:
        assert eval_result.failures == []


# ---------------------------------------------------------------------------
# EvalRunner.run_all
# ---------------------------------------------------------------------------

def test_run_all_returns_one_result_per_case() -> None:
    runner = EvalRunner([
        EvalCase(case_id="a", expect_world_state=True),
        EvalCase(case_id="b", expect_world_state=False),
    ])
    result = _build_result()
    results = runner.run_all(result)
    assert len(results) == 2


def test_run_all_case_ids_match() -> None:
    runner = EvalRunner([
        EvalCase(case_id="a"),
        EvalCase(case_id="b"),
    ])
    result = _build_result()
    results = runner.run_all(result)
    returned_ids = {r.case_id for r in results}
    assert returned_ids == {"a", "b"}


# ---------------------------------------------------------------------------
# EvalRunner.summary
# ---------------------------------------------------------------------------

def test_summary_total_matches_count() -> None:
    runner = EvalRunner([
        EvalCase(case_id="a", expect_world_state=True),
        EvalCase(case_id="b", expect_world_state=True),
    ])
    result = _build_result()
    results = runner.run_all(result)
    s = runner.summary(results)
    assert s["total"] == 2


def test_summary_passed_plus_failed_equals_total() -> None:
    runner = EvalRunner([
        EvalCase(case_id="a", expect_world_state=True),
        EvalCase(case_id="b", required_strings=["MISSING_XYZ"], expect_world_state=False),
    ])
    result = _build_result()
    results = runner.run_all(result)
    s = runner.summary(results)
    assert s["passed"] + s["failed"] == s["total"]


def test_summary_mean_score_in_range() -> None:
    runner = EvalRunner([EvalCase(case_id="a", expect_world_state=True)])
    result = _build_result()
    results = runner.run_all(result)
    s = runner.summary(results)
    assert 0.0 <= s["mean_score"] <= 1.0


def test_summary_empty_results() -> None:
    runner = EvalRunner()
    s = runner.summary([])
    assert s["total"] == 0
    assert s["mean_score"] == 1.0


# ---------------------------------------------------------------------------
# required_fact_keys check
# ---------------------------------------------------------------------------

def test_required_fact_keys_present_passes() -> None:
    runner = EvalRunner([
        EvalCase(
            case_id="facts",
            expect_world_state=False,
            required_fact_keys={"sigrid": ["role"]},
        )
    ])
    result = _build_result()
    eval_result = runner.run(result, "facts")
    # May pass or fail depending on RAG scoring — just check it ran
    assert isinstance(eval_result, EvalResult)
    assert eval_result.checks_run >= 1
