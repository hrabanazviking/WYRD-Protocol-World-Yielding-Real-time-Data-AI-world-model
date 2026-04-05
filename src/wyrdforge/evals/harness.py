"""EvalHarness — deterministic quality evaluation for WYRD context outputs.

Evaluates CharacterContextResult and WorldContextPacket outputs against
hand-crafted EvalCase specifications.  All checks are deterministic —
no LLM involvement.

Checks implemented:
    - context_fidelity:   Does formatted_for_llm contain expected strings?
    - factual_grounding:  Do canonical_facts cover the required subject+keys?
    - world_state_present: Is the WORLD STATE section present?
    - persona_identity:   Is identity content injected for the persona?
    - bond_state_present: Is bond state present when expected?
    - no_hallucinated_keys: Does the output avoid forbidden strings?
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from wyrdforge.runtime.character_context import CharacterContextResult


# ---------------------------------------------------------------------------
# EvalCase
# ---------------------------------------------------------------------------

@dataclass
class EvalCase:
    """Specification for one evaluation case.

    Attributes:
        case_id:            Unique identifier for this eval case.
        description:        Human-readable description of what is being tested.
        required_strings:   Strings that MUST appear in formatted_for_llm.
        forbidden_strings:  Strings that must NOT appear in formatted_for_llm.
        required_fact_keys: ``{subject_id: [fact_key, ...]}`` pairs that must
                            appear in the micro_packet's canonical_facts text.
        expect_world_state: Whether ``WORLD STATE`` must appear.
        expect_persona_identity: Whether ``IDENTITY`` must appear.
        expect_bond_state:  Whether ``BOND STATE`` must appear.
        metadata:           Optional free-form metadata dict.
    """

    case_id: str
    description: str = ""
    required_strings: list[str] = field(default_factory=list)
    forbidden_strings: list[str] = field(default_factory=list)
    required_fact_keys: dict[str, list[str]] = field(default_factory=dict)
    expect_world_state: bool = True
    expect_persona_identity: bool = False
    expect_bond_state: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# EvalResult
# ---------------------------------------------------------------------------

@dataclass
class EvalResult:
    """Result of running one EvalCase against a CharacterContextResult.

    Attributes:
        case_id:    Eval case that was run.
        passed:     True if ALL checks passed.
        failures:   List of failure descriptions (empty if passed).
        score:      Fraction of checks that passed (0.0–1.0).
        checks_run: Total number of checks evaluated.
    """

    case_id: str
    passed: bool
    failures: list[str]
    score: float
    checks_run: int


# ---------------------------------------------------------------------------
# EvalRunner
# ---------------------------------------------------------------------------

class EvalRunner:
    """Runs EvalCase specifications against CharacterContextResult outputs.

    Args:
        cases: List of EvalCase to register.  Can also be added later
               via :meth:`add_case`.
    """

    def __init__(self, cases: list[EvalCase] | None = None) -> None:
        self._cases: dict[str, EvalCase] = {}
        for c in (cases or []):
            self.add_case(c)

    def add_case(self, case: EvalCase) -> None:
        """Register an eval case.

        Args:
            case: EvalCase to add.
        """
        self._cases[case.case_id] = case

    def run(
        self,
        result: CharacterContextResult,
        case_id: str,
    ) -> EvalResult:
        """Run one eval case against a CharacterContextResult.

        Args:
            result:  Context result to evaluate.
            case_id: Which registered EvalCase to use.

        Returns:
            EvalResult with pass/fail details.

        Raises:
            KeyError: If case_id is not registered.
        """
        case = self._cases[case_id]
        failures: list[str] = []
        checks_run = 0

        text = result.formatted_for_llm

        # Check 1: required strings in formatted_for_llm
        for s in case.required_strings:
            checks_run += 1
            if s not in text:
                failures.append(f"required_string missing: {s!r}")

        # Check 2: forbidden strings not in formatted_for_llm
        for s in case.forbidden_strings:
            checks_run += 1
            if s in text:
                failures.append(f"forbidden_string present: {s!r}")

        # Check 3: world state section
        if case.expect_world_state:
            checks_run += 1
            if "WORLD STATE" not in text:
                failures.append("WORLD STATE section missing")

        # Check 4: persona identity section
        if case.expect_persona_identity:
            checks_run += 1
            if "IDENTITY" not in text:
                failures.append("IDENTITY section missing")

        # Check 5: bond state section
        if case.expect_bond_state:
            checks_run += 1
            if "BOND STATE" not in text:
                failures.append("BOND STATE section missing")

        # Check 6: required fact keys in micro_packet canonical_facts
        for subject_id, keys in case.required_fact_keys.items():
            for key in keys:
                checks_run += 1
                found = any(
                    subject_id in item.text and key in item.text
                    for item in result.micro_packet.canonical_facts
                )
                if not found:
                    failures.append(
                        f"fact not retrieved: subject={subject_id!r} key={key!r}"
                    )

        passed = len(failures) == 0
        score = (checks_run - len(failures)) / checks_run if checks_run > 0 else 1.0
        return EvalResult(
            case_id=case_id,
            passed=passed,
            failures=failures,
            score=score,
            checks_run=checks_run,
        )

    def run_all(
        self,
        result: CharacterContextResult,
    ) -> list[EvalResult]:
        """Run all registered eval cases against a result.

        Args:
            result: Context result to evaluate.

        Returns:
            List of EvalResult, one per registered case.
        """
        return [self.run(result, cid) for cid in self._cases]

    def summary(self, results: list[EvalResult]) -> dict[str, Any]:
        """Summarise a list of EvalResults.

        Args:
            results: Results from :meth:`run_all`.

        Returns:
            Dict with ``total``, ``passed``, ``failed``, ``mean_score``.
        """
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        mean_score = sum(r.score for r in results) / total if total > 0 else 1.0
        return {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "mean_score": round(mean_score, 4),
        }

    @property
    def case_ids(self) -> list[str]:
        """Registered case IDs."""
        return list(self._cases.keys())
