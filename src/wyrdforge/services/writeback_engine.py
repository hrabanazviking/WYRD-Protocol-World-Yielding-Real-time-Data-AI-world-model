from __future__ import annotations

import threading
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from wyrdforge.models.common import (
    Audit,
    EntityScope,
    Governance,
    Lifecycle,
    Provenance,
    RetrievalMeta,
    RetentionClass,
    StoreName,
    TruthMeta,
    WritePolicy,
)
from wyrdforge.models.memory import (
    CanonicalFactContent,
    CanonicalFactPayload,
    CanonicalFactRecord,
    EpisodeSummaryContent,
    EpisodeSummaryPayload,
    EpisodeSummaryRecord,
    MemoryContent,
    ObservationContent,
    ObservationKind,
    ObservationPayload,
    ObservationRecord,
    PolicyContent,
    PolicyPayload,
    PolicyRecord,
)
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.services.attribution import require_attributed_observation

if TYPE_CHECKING:
    from wyrdforge.runtime.events import EventBus

#: Topics emitted by WritebackEngine when wired to an EventBus
#: (opt-in via ``bus=``).
_WRITEBACK_TOPICS = ("writeback.written", "writeback.replay")


def _register_writeback_topics(bus: "EventBus") -> None:
    """Register the writeback.* topics once; tolerate double registration."""
    for topic in _WRITEBACK_TOPICS:
        try:
            bus.register_topic(topic)
        except ValueError:
            pass  # already registered — another producer got here first


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _base_provenance(source_type: str, source_ref: str) -> Provenance:
    return Provenance(
        source_type=source_type,
        source_ref=source_ref,
        extracted_at=_now(),
        extracted_by="writeback_engine",
    )


def _base_audit(agent: str = "writeback_engine") -> Audit:
    now = _now()
    return Audit(
        created_at=now,
        updated_at=now,
        created_by_agent=agent,
        updated_by_agent=agent,
    )


class WritebackEngine:
    """Converts structured turn output into MemoryRecord writes.

    Handles five record types:
        - ObservationRecord  → HUGIN store  (raw turn events)
        - EpisodeSummaryRecord → MUNIN store (distilled summaries)
        - CanonicalFactRecord → MIMIR store  (world/character facts)
        - PolicyRecord        → ORLOG store  (behavioral rules)

    All writes default to EPHEMERAL write_policy — the MemoryPromoter
    handles elevation to PROMOTABLE / CANONICAL over time.

    In Phase 2, input is structured dicts (not raw LLM text).
    Phase 4 will add an LLM-output parser that feeds this engine.

    Helheim Hardening: process_turn supports idempotent replays.  When an
    idempotency_key is supplied, the result of the first call is cached in a
    bounded in-memory record (OrderedDict capped at
    ``IDEMPOTENCY_RECORD_CAP`` entries, oldest evicted first).  A repeat
    call with the same key returns the cached result — identical record ids
    — without writing new records to the stores.

    Phase A3 (turn-atomic writeback): process_turn stages the whole
    turn first — it builds the observation and every fact record
    WITHOUT writing anything — then commits them through a single
    ``store.add_many(...)`` call, i.e. one memory-store transaction.
    A failure while building (e.g. a malformed fact dict) happens
    before any write; a failure inside the commit rolls the whole
    batch back. Either way no fractured, partially-committed turn
    can survive. The idempotency record is only populated after a
    successful commit, so a failed turn stays retryable under the
    same key. The standalone ``write_*`` methods keep their exact
    historical behaviour (build one record, ``store.add`` it).

    Phase C3 (provenance enforcement): an utterance-kind observation
    must be attributed — an explicit ``speaker_id`` or identified
    ``participants`` — or the write is refused with
    ``UnattributedUtteranceError`` before anything is written (see
    ``services/attribution.py``). The check lives in the staging
    builder, so a refusal inside ``process_turn`` leaves zero records
    and does not consume the idempotency key. Non-utterance kinds
    (system/engine observations) are unaffected.
    """

    #: Cap on the in-memory idempotency record: bounds replay memory.
    IDEMPOTENCY_RECORD_CAP = 1024

    def __init__(
        self,
        store: PersistentMemoryStore,
        *,
        default_tenant_id: str = "default",
        default_system_id: str = "wyrd",
        bus: "EventBus | None" = None,
    ) -> None:
        self._store = store
        self._tenant_id = default_tenant_id
        self._system_id = default_system_id
        # Phase B1: the idempotency check → commit → record sequence in
        # process_turn is a check-then-act on this map; behind the
        # threading HTTP server one engine serves every request thread,
        # and two concurrent calls carrying the same key could both
        # miss the map and both write the turn (reproduced pre-B1: 8
        # concurrent same-key callers produced 2 distinct writes).
        # _lock serialises process_turn so the sequence is atomic.
        # The standalone write_* methods take no lock: they touch no
        # engine state, and the memory store is already thread-safe
        # (per-thread connections).
        self._lock = threading.RLock()
        # idempotency_key -> {"observations": [...], "facts": [...]} (record lists)
        self._idempotency: OrderedDict[str, dict[str, list]] = OrderedDict()
        # Opt-in inner-communications wiring: bus=None preserves the exact
        # historical behavior; a bus wires write events into the EventBus.
        self._bus = bus
        if self._bus is not None:
            _register_writeback_topics(self._bus)

    # ------------------------------------------------------------------
    # Observation (HUGIN)
    # ------------------------------------------------------------------

    def _build_observation(
        self,
        *,
        title: str,
        summary: str,
        observation_kind: str = "utterance",
        participants: list[str] | None = None,
        speaker_id: str | None = None,
        salience: float = 0.5,
        place_id: str | None = None,
        confidence: float = 0.6,
        tags: list[str] | None = None,
        entity_scope: dict[str, Any] | None = None,
    ) -> ObservationRecord:
        """Build an ObservationRecord WITHOUT writing it (A3 staging).

        Phase C3: an utterance-kind build with neither ``speaker_id``
        nor identified ``participants`` raises
        ``UnattributedUtteranceError`` here — during staging, before
        any store write — so both the standalone writer and the
        atomic ``process_turn`` path refuse cleanly.
        """
        now = _now()
        clean_speaker = speaker_id.strip() if speaker_id else None
        record = ObservationRecord(
            record_id=_new_id("obs"),
            tenant_id=self._tenant_id,
            system_id=self._system_id,
            entity_scope=EntityScope(**(entity_scope or {})),
            content=ObservationContent(
                title=title,
                summary=summary,
                structured_payload=ObservationPayload(
                    observation_kind=ObservationKind(observation_kind),
                    speaker_id=clean_speaker or None,
                    normalized_claims=[summary],
                    participants=participants or [],
                    observed_at=now,
                    place_id=place_id,
                    salience=salience,
                ),
            ),
            truth=TruthMeta(confidence=confidence),
            provenance=_base_provenance("turn", "writeback_engine"),
            lifecycle=Lifecycle(
                write_policy=WritePolicy.EPHEMERAL,
                retention_class=RetentionClass.SHORT,
            ),
            retrieval=RetrievalMeta(
                lexical_terms=list(set((tags or []) + title.lower().split())),
                default_priority=salience,
            ),
            governance=Governance(),
            audit=_base_audit(),
        )
        # Phase C3 gate: refuse an unattributed utterance at build
        # (staging) time — nothing has been written yet on any path.
        require_attributed_observation(record)
        return record

    def write_observation(self, **kwargs: Any) -> ObservationRecord:
        """Write a raw observation to the HUGIN store.

        Utterance-kind writes (the default kind) must be attributed:
        pass ``speaker_id=`` or ``participants=`` or the write is
        refused with ``UnattributedUtteranceError`` (Phase C3).
        Non-utterance kinds are engine/system records and need no
        speaker.
        """
        record = self._build_observation(**kwargs)
        self._store.add(record)
        return record

    # ------------------------------------------------------------------
    # Episode Summary (MUNIN)
    # ------------------------------------------------------------------

    def _build_episode_summary(
        self,
        *,
        title: str,
        summary: str,
        episode_id: str | None = None,
        start_turn: int = 0,
        end_turn: int = 0,
        major_events: list[str] | None = None,
        open_threads: list[str] | None = None,
        confidence: float = 0.7,
        tags: list[str] | None = None,
    ) -> EpisodeSummaryRecord:
        """Build an EpisodeSummaryRecord WITHOUT writing it (A3 staging)."""
        eid = episode_id or _new_id("ep")
        return EpisodeSummaryRecord(
            record_id=_new_id("epsum"),
            tenant_id=self._tenant_id,
            system_id=self._system_id,
            entity_scope=EntityScope(),
            content=EpisodeSummaryContent(
                title=title,
                summary=summary,
                structured_payload=EpisodeSummaryPayload(
                    episode_id=eid,
                    start_turn=start_turn,
                    end_turn=end_turn,
                    major_events=major_events or [],
                    open_threads=open_threads or [],
                    recommended_retrieval_tags=tags or [],
                ),
            ),
            truth=TruthMeta(confidence=confidence),
            provenance=_base_provenance("episode", "writeback_engine"),
            lifecycle=Lifecycle(
                write_policy=WritePolicy.REVIEWED,
                retention_class=RetentionClass.MEDIUM,
            ),
            retrieval=RetrievalMeta(
                lexical_terms=list(set((tags or []) + title.lower().split())),
                default_priority=0.5,
            ),
            governance=Governance(),
            audit=_base_audit(),
        )

    def write_episode_summary(self, **kwargs) -> EpisodeSummaryRecord:
        """Write a distilled episode summary to the MUNIN store."""
        record = self._build_episode_summary(**kwargs)
        self._store.add(record)
        return record

    # ------------------------------------------------------------------
    # Canonical Fact (MIMIR)
    # ------------------------------------------------------------------

    def _build_canonical_fact(
        self,
        *,
        fact_subject_id: str,
        fact_key: str,
        fact_value: str,
        domain: str = "general",
        confidence: float = 0.8,
        tags: list[str] | None = None,
        value_type: str = "string",
    ) -> CanonicalFactRecord:
        """Build a CanonicalFactRecord WITHOUT writing it (A3 staging)."""
        title = f"{fact_subject_id}.{fact_key} = {fact_value}"
        return CanonicalFactRecord(
            record_id=_new_id("fact"),
            tenant_id=self._tenant_id,
            system_id=self._system_id,
            entity_scope=EntityScope(primary_subjects=[fact_subject_id]),
            content=CanonicalFactContent(
                title=title,
                summary=f"{fact_subject_id}: {fact_key} is {fact_value}",
                structured_payload=CanonicalFactPayload(
                    fact_subject_id=fact_subject_id,
                    fact_key=fact_key,
                    fact_value=fact_value,
                    value_type=value_type,
                    domain=domain,
                ),
            ),
            truth=TruthMeta(confidence=confidence),
            provenance=_base_provenance("inference", "writeback_engine"),
            lifecycle=Lifecycle(
                write_policy=WritePolicy.EPHEMERAL,
                retention_class=RetentionClass.LONG,
            ),
            retrieval=RetrievalMeta(
                lexical_terms=list(
                    set((tags or []) + [fact_subject_id, fact_key, fact_value.lower()])
                ),
                default_priority=0.6,
            ),
            governance=Governance(),
            audit=_base_audit(),
        )

    def write_canonical_fact(self, **kwargs) -> CanonicalFactRecord:
        """Write a canonical world/character fact to the MIMIR store."""
        record = self._build_canonical_fact(**kwargs)
        self._store.add(record)
        return record

    # ------------------------------------------------------------------
    # Policy (ORLOG)
    # ------------------------------------------------------------------

    def _build_policy(
        self,
        *,
        title: str,
        rule_text: str,
        policy_kind: str = "behavioral",
        applies_to_domains: list[str] | None = None,
        priority: int = 100,
        confidence: float = 0.95,
    ) -> PolicyRecord:
        """Build a PolicyRecord WITHOUT writing it (A3 staging)."""
        return PolicyRecord(
            record_id=_new_id("pol"),
            tenant_id=self._tenant_id,
            system_id=self._system_id,
            entity_scope=EntityScope(),
            content=PolicyContent(
                title=title,
                summary=rule_text[:220],
                structured_payload=PolicyPayload(
                    policy_kind=policy_kind,
                    rule_text=rule_text,
                    applies_to_domains=applies_to_domains or [],
                    priority=priority,
                ),
            ),
            truth=TruthMeta(confidence=confidence),
            provenance=_base_provenance("config", "writeback_engine"),
            lifecycle=Lifecycle(
                write_policy=WritePolicy.IMMUTABLE,
                retention_class=RetentionClass.PERMANENT,
            ),
            retrieval=RetrievalMeta(
                lexical_terms=[policy_kind, "policy"] + (applies_to_domains or []),
                default_priority=0.9,
            ),
            governance=Governance(
                sensitivity="medium",
                requires_review_before_promotion=False,
            ),
            audit=_base_audit(),
        )

    def write_policy(self, **kwargs) -> PolicyRecord:
        """Write a behavioral policy to the ORLOG store."""
        record = self._build_policy(**kwargs)
        self._store.add(record)
        return record

    # ------------------------------------------------------------------
    # Batch writeback
    # ------------------------------------------------------------------

    def process_turn(
        self,
        *,
        user_input: str,
        response_text: str,
        participants: list[str] | None = None,
        speaker_id: str | None = None,
        place_id: str | None = None,
        facts: list[dict] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, list]:
        """Write a full conversation turn to memory stores.

        Always writes an ObservationRecord for the turn.
        Optionally writes CanonicalFactRecords if `facts` are provided.

        Args:
            user_input:    The user's message text.
            response_text: The AI's response text.
            participants:  Entity IDs present in the turn.
            speaker_id:    Entity ID of the speaker whose words
                           ``user_input`` carries (Phase C3). The
                           turn's utterance is attributed when either
                           ``speaker_id`` or ``participants`` identifies
                           who spoke; with neither, the turn is refused
                           (``UnattributedUtteranceError``) before any
                           write and the idempotency key is not
                           consumed. A replay of an already-committed
                           key returns the cached result as before.
            place_id:      Location entity ID where this turn occurred.
            facts:         Optional list of dicts, each with:
                           {fact_subject_id, fact_key, fact_value, confidence?, domain?}
            idempotency_key: Optional caller-supplied key.  If a key was seen
                           before (within the bounded record), the previously
                           returned result is returned WITHOUT writing new
                           records.  ``None`` disables idempotency and always
                           writes.  Backward compatible: existing keyword
                           callers are unaffected.

        Returns:
            dict with 'observations' and 'facts' lists of written records.

        Atomicity (Phase A3): the turn is staged (all records built,
        nothing written) and then committed in ONE store transaction
        via ``store.add_many``. Any failure — a malformed fact dict
        during staging, or a store error during commit — leaves NO
        part of the turn in the store, and the idempotency key is
        not consumed, so the caller may retry the same turn.

        Thread-safety (Phase B1): the whole call runs under the
        engine lock (see ``__init__``), so the idempotency
        check → commit → record sequence cannot interleave with
        another thread's. Bus events are emitted after the lock is
        released, never inside it.
        """
        with self._lock:
            result, pending_emits = self._process_turn_locked(
                user_input=user_input,
                response_text=response_text,
                participants=participants,
                speaker_id=speaker_id,
                place_id=place_id,
                facts=facts,
                idempotency_key=idempotency_key,
            )
        for topic, payload in pending_emits:
            self._emit(topic, payload)
        return result

    def _process_turn_locked(
        self,
        *,
        user_input: str,
        response_text: str,
        participants: list[str] | None = None,
        speaker_id: str | None = None,
        place_id: str | None = None,
        facts: list[dict] | None = None,
        idempotency_key: str | None = None,
    ) -> tuple[dict[str, list], list[tuple[str, dict]]]:
        """Body of process_turn; caller holds ``self._lock``.

        Returns the result dict plus the bus emissions to publish
        after the lock is released.
        """
        pending_emits: list[tuple[str, dict]] = []
        if idempotency_key is not None and idempotency_key in self._idempotency:
            cached = self._idempotency[idempotency_key]
            # Refresh recency, then return copies so callers cannot mutate
            # the cached record lists.
            self._idempotency.move_to_end(idempotency_key)
            pending_emits.append(
                ("writeback.replay", {"idempotency_key": idempotency_key})
            )
            return {
                "observations": list(cached["observations"]),
                "facts": list(cached["facts"]),
            }, pending_emits

        # --- Stage (A3): build every record, write NOTHING yet. ---
        # A malformed fact dict raises here, before any store write,
        # where the pre-A3 code had already committed the observation.
        obs = self._build_observation(
            title=f"Turn: {user_input[:80]}",
            summary=f"User: {user_input[:120]} | Response: {response_text[:120]}",
            observation_kind="utterance",
            participants=participants or [],
            speaker_id=speaker_id,
            place_id=place_id,
            salience=0.5,
        )

        written_facts: list[CanonicalFactRecord] = []
        for fact_def in (facts or []):
            fact_record = self._build_canonical_fact(
                fact_subject_id=fact_def["fact_subject_id"],
                fact_key=fact_def["fact_key"],
                fact_value=fact_def["fact_value"],
                confidence=fact_def.get("confidence", 0.75),
                domain=fact_def.get("domain", "general"),
            )
            written_facts.append(fact_record)

        # --- Commit (A3): one transaction for the whole turn. ---
        self._commit_turn_records([obs, *written_facts])

        result: dict[str, list] = {"observations": [obs], "facts": written_facts}

        if idempotency_key is not None:
            # Store copies; evict oldest when the record is full.
            self._idempotency[idempotency_key] = {
                "observations": list(result["observations"]),
                "facts": list(result["facts"]),
            }
            while len(self._idempotency) > self.IDEMPOTENCY_RECORD_CAP:
                self._idempotency.popitem(last=False)

        pending_emits.append(
            (
                "writeback.written",
                {
                    "record_ids": {
                        "observations": [r.record_id for r in result["observations"]],
                        "facts": [r.record_id for r in result["facts"]],
                    },
                    "idempotency_key": idempotency_key,
                },
            )
        )

        return result, pending_emits

    # ------------------------------------------------------------------
    # Turn commit (Phase A3)
    # ------------------------------------------------------------------

    def _commit_turn_records(self, records: list) -> None:
        """Commit one turn's staged records atomically.

        Primary path: the memory store's ``add_many`` — a single
        SQLite transaction, so a mid-batch failure rolls back every
        record of the turn. Fallback for store-like objects without
        ``add_many`` (test doubles / foreign stores): sequential
        ``add`` with a best-effort compensating delete of whatever
        already landed if a later add raises, then re-raise — the
        no-partial-turn invariant is preserved on that path too,
        as long as the store honours ``delete``.
        """
        add_many = getattr(self._store, "add_many", None)
        if callable(add_many):
            add_many(records)
            return
        written: list = []
        try:
            for record in records:
                self._store.add(record)
                written.append(record)
        except Exception:
            for record in written:
                try:
                    self._store.delete(record.record_id)
                except Exception:
                    pass  # best effort; the original error propagates
            raise

    # ------------------------------------------------------------------
    # Bus wiring helper
    # ------------------------------------------------------------------

    def _emit(self, topic: str, payload: dict) -> None:
        """Publish an event envelope; never disturb write semantics.

        No-op when this engine is not bus-wired.  Bus errors are
        swallowed — a write is a write regardless of bus health.
        """
        bus = getattr(self, "_bus", None)
        if bus is None:
            return
        try:
            bus.publish(topic, payload, source="services.writeback")
        except Exception:
            pass
