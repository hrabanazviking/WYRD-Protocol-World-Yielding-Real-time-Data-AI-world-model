from __future__ import annotations

from pydantic import Field

from .common import StrictModel
from .micro_rag import RetrievalItem, TruthPacket


class ExpectedBehavior(StrictModel):
    must_do: list[str] = Field(default_factory=list)
    must_not_do: list[str] = Field(default_factory=list)


class ScoringWeights(StrictModel):
    factual_integrity_weight: float = 1.0
    uncertainty_honesty_weight: float = 1.0
    relational_safety_weight: float = 1.0
    exploit_resistance_weight: float = 1.0


class EvalSetup(StrictModel):
    truth_packet: TruthPacket = Field(default_factory=TruthPacket)
    runtime_memory: list[RetrievalItem] = Field(default_factory=list)
    user_prompt: str


class EvalCase(StrictModel):
    eval_id: str
    category: str
    title: str
    setup: EvalSetup
    expected_behavior: ExpectedBehavior = Field(default_factory=ExpectedBehavior)
    scoring: ScoringWeights = Field(default_factory=ScoringWeights)


class DimensionScore(StrictModel):
    value: int = Field(ge=0, le=3)
    rationale: str


class EvalResult(StrictModel):
    eval_id: str
    factual_integrity: DimensionScore
    uncertainty_honesty: DimensionScore
    relational_safety: DimensionScore
    exploit_resistance: DimensionScore
    weighted_average: float
    pass_fail: bool
