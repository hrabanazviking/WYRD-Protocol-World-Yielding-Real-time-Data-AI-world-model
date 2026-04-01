from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wyrdforge.models.bond import BondEdge, Hurt, Vow
from wyrdforge.models.evals import EvalCase, EvalResult
from wyrdforge.models.memory import (
    CanonicalFactRecord,
    ContradictionRecord,
    EpisodeSummaryRecord,
    ObservationRecord,
    PolicyRecord,
    SymbolicTraceRecord,
)
from wyrdforge.models.micro_rag import MicroContextPacket, RetrievalItem
from wyrdforge.models.persona import PersonaPacket

MODELS = {
    "observation_record.schema.json": ObservationRecord,
    "canonical_fact_record.schema.json": CanonicalFactRecord,
    "episode_summary_record.schema.json": EpisodeSummaryRecord,
    "symbolic_trace_record.schema.json": SymbolicTraceRecord,
    "contradiction_record.schema.json": ContradictionRecord,
    "policy_record.schema.json": PolicyRecord,
    "bond_edge.schema.json": BondEdge,
    "vow.schema.json": Vow,
    "hurt.schema.json": Hurt,
    "persona_packet.schema.json": PersonaPacket,
    "retrieval_item.schema.json": RetrievalItem,
    "micro_context_packet.schema.json": MicroContextPacket,
    "eval_case.schema.json": EvalCase,
    "eval_result.schema.json": EvalResult,
}


def main() -> None:
    schema_dir = Path(__file__).resolve().parents[1] / "src" / "wyrdforge" / "schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)
    for filename, model in MODELS.items():
        path = schema_dir / filename
        path.write_text(json.dumps(model.model_json_schema(), indent=2), encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
