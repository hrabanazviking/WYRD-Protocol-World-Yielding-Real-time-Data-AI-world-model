from __future__ import annotations

from datetime import UTC, datetime

from wyrdforge.models.common import Audit, EntityScope, Governance, Lifecycle, Provenance, RetrievalMeta, TruthMeta
from wyrdforge.models.memory import CanonicalFactContent, CanonicalFactPayload, CanonicalFactRecord


def build_seed_fact(record_id: str = "fact-001") -> CanonicalFactRecord:
    now = datetime.now(UTC)
    return CanonicalFactRecord(
        record_id=record_id,
        tenant_id="local",
        system_id="wyrdforge-demo",
        entity_scope=EntityScope(primary_subjects=["persona:veyrunn", "user:volmarr"], project_id="norse-saga"),
        content=CanonicalFactContent(
            title="persona role",
            summary="The persona acts as a calm, mystical, accuracy-seeking guide.",
            structured_payload=CanonicalFactPayload(
                fact_subject_id="persona:veyrunn",
                fact_key="temperament",
                fact_value="calm",
                domain="identity",
            ),
        ),
        truth=TruthMeta(confidence=0.97, approval_state="approved"),
        provenance=Provenance(source_type="developer_seed", source_ref="seed://persona", extracted_at=now, extracted_by="seed_loader"),
        lifecycle=Lifecycle(write_policy="canonical", retention_class="permanent"),
        retrieval=RetrievalMeta(lexical_terms=["persona", "calm", "mystical"], facets={"domain": ["identity", "global"]}, default_priority=0.8),
        governance=Governance(allowed_for_runtime=True, requires_review_before_promotion=False),
        audit=Audit(created_at=now, updated_at=now, created_by_agent="seed_loader", updated_by_agent="seed_loader"),
    )
