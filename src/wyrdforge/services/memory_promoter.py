from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from wyrdforge.models.common import RetentionClass, WritePolicy
from wyrdforge.models.memory import MemoryRecord
from wyrdforge.persistence.memory_store import PersistentMemoryStore

_DEFAULT_CONFIG: dict[str, Any] = {
    "promotion": {
        "confidence_threshold": 0.80,
        "access_count_min": 2,
        "auto_promote_score_threshold": 0.70,
        "weights": {
            "confidence": 0.40,
            "access_count": 0.20,
            "recency": 0.20,
            "priority": 0.20,
        },
    },
    "decay": {
        "stale_after_days": {
            "ephemeral": 7,
            "short": 30,
            "medium": 90,
            "long": 365,
            "permanent": None,
        },
        "confidence_decay_per_period": 0.10,
        "minimum_confidence": 0.10,
    },
}


def _load_config(config_path: str | Path | None) -> dict[str, Any]:
    if config_path is None:
        default = Path("configs/memory_promotion.yaml")
        if default.exists():
            config_path = default
        else:
            return _DEFAULT_CONFIG
    path = Path(config_path)
    if not path.exists():
        return _DEFAULT_CONFIG
    with path.open("r", encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh) or {}
    # Merge with defaults (shallow merge per top-level key)
    merged = dict(_DEFAULT_CONFIG)
    for k, v in loaded.items():
        merged[k] = v
    return merged


class MemoryPromoter:
    """Evaluates MemoryRecords for promotion and handles decay.

    Promotion pipeline:
        EPHEMERAL → (score >= threshold) → PROMOTABLE → (approved) → CANONICAL

    The promoter scores records using configurable weights and marks
    eligible ones as PROMOTABLE. Final CANONICAL promotion is either
    automatic (if score is high enough) or awaits human/system review.
    """

    def __init__(
        self,
        store: PersistentMemoryStore,
        config_path: str | Path | None = None,
    ) -> None:
        self._store = store
        self._cfg = _load_config(config_path)

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def score_for_promotion(self, record: MemoryRecord) -> float:
        """Compute a promotion eligibility score in range [0.0, 1.0]."""
        cfg = self._cfg["promotion"]
        weights = cfg["weights"]
        access_min = max(1, cfg["access_count_min"])

        confidence_score = record.truth.confidence
        access_score = min(1.0, record.lifecycle.access_count / access_min)

        # Recency: how recently was the record accessed vs created?
        now = datetime.now(timezone.utc)
        created = record.audit.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        last_accessed = record.lifecycle.last_accessed_at
        if last_accessed is None:
            recency_score = 0.0
        else:
            if last_accessed.tzinfo is None:
                last_accessed = last_accessed.replace(tzinfo=timezone.utc)
            age_days = max(0.0, (now - created).total_seconds() / 86400.0)
            access_age_days = max(0.0, (now - last_accessed).total_seconds() / 86400.0)
            recency_score = 1.0 - min(1.0, access_age_days / max(1.0, age_days))

        priority_score = min(1.0, max(0.0, record.retrieval.default_priority))

        score = (
            confidence_score * weights["confidence"]
            + access_score * weights["access_count"]
            + recency_score * weights["recency"]
            + priority_score * weights["priority"]
        )
        return round(min(1.0, max(0.0, score)), 4)

    # ------------------------------------------------------------------
    # Promotion
    # ------------------------------------------------------------------

    def is_eligible(self, record: MemoryRecord) -> bool:
        """Return True if this record meets promotion eligibility criteria."""
        cfg = self._cfg["promotion"]
        if record.truth.confidence < cfg["confidence_threshold"]:
            return False
        if record.lifecycle.access_count < cfg["access_count_min"]:
            return False
        if record.lifecycle.write_policy in (WritePolicy.IMMUTABLE, WritePolicy.CANONICAL):
            return False  # already at top
        if record.truth.approval_state.value == "quarantined":
            return False
        return True

    def promote_if_eligible(self, record_id: str) -> bool:
        """Promote a record to PROMOTABLE or CANONICAL if it qualifies.

        Returns True if the record was promoted, False otherwise.
        """
        record = self._store.get(record_id)
        if record is None or not self.is_eligible(record):
            return False

        score = self.score_for_promotion(record)
        threshold = self._cfg["promotion"]["auto_promote_score_threshold"]

        if score >= threshold:
            # High confidence — mark as PROMOTABLE (awaits final canonical stamp)
            record.lifecycle.write_policy = WritePolicy.PROMOTABLE
            self._store.add(record)
            return True
        return False

    def run_promotion_pass(self) -> int:
        """Check all PENDING records and promote eligible ones.

        Returns the count of records promoted.
        """
        pending = self._store.list_pending_promotion()
        promoted = 0
        for record in pending:
            if self.promote_if_eligible(record.record_id):
                promoted += 1
        return promoted

    # ------------------------------------------------------------------
    # Decay
    # ------------------------------------------------------------------

    def decay_stale_records(self, *, dry_run: bool = False) -> int:
        """Reduce confidence on records not accessed within their stale window.

        Returns the count of records decayed.
        """
        cfg = self._cfg["decay"]
        stale_days_map: dict[str, float | None] = cfg["stale_after_days"]
        decay_amount: float = cfg["confidence_decay_per_period"]
        min_confidence: float = cfg["minimum_confidence"]

        now = datetime.now(timezone.utc)
        all_records = self._store.all()
        decayed = 0

        for record in all_records:
            if record.lifecycle.write_policy == WritePolicy.IMMUTABLE:
                continue
            retention = record.lifecycle.retention_class.value
            stale_days = stale_days_map.get(retention)
            if stale_days is None:
                continue  # permanent — never decays

            last_accessed = record.lifecycle.last_accessed_at or record.audit.created_at
            if last_accessed.tzinfo is None:
                last_accessed = last_accessed.replace(tzinfo=timezone.utc)

            age_days = (now - last_accessed).total_seconds() / 86400.0
            if age_days > stale_days:
                new_confidence = max(min_confidence, record.truth.confidence - decay_amount)
                if new_confidence < record.truth.confidence:
                    if not dry_run:
                        record.truth.confidence = new_confidence
                        self._store.add(record)
                    decayed += 1

        return decayed
