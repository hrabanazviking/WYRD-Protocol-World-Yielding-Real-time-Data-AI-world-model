"""wyrdforge.persistence.purge — Per-subject purge (Phase C1).

Roadmap §5.4 / §9 C1: a resident of a public world can demand to be
forgotten (GDPR/CCPA), and before C1 the engine offered only
per-record deletes — there was no way to erase one *subject* across
the stores. This module is that erasure: a service-level
:func:`purge_subject` spanning the three truth stores plus the
derived artifacts in scope, leaving a tombstone as the only trace.
C1 is a Heimdall launch gate.

What a "subject" is (from the stores' own shapes)
-------------------------------------------------
A subject is identified by ONE string id, the same id every store
already uses for a person/persona (e.g. ``"persona:veyrunn"``,
``"resident:alice"``). Purge matches on **structured subject fields
only** — never on free-text mentions:

- **Memory** (:meth:`PersistentMemoryStore.purge_subject`): a record
  is the subject's when the subject appears in
  ``entity_scope.primary_subjects`` / ``secondary_subjects``, in an
  observation's ``participants``, or as a canonical fact's
  ``fact_subject_id``. One deliberate extension: observations derived
  by ``ReplayPersistenceBridge`` (tagged ``replay-persistence``,
  carrying a verbatim bus envelope as their summary) are derived
  copies, not original records — one whose envelope names the
  subject is deleted too.
- **Bond** (:meth:`PersistentBondStore.purge_subject`): every edge
  where the subject is ``entity_a`` or ``entity_b``, with its vows
  and hurts (the store's existing one-transaction cascade).
- **World** (:meth:`WorldStore.purge_subject`): every entity that
  *is* the subject — ``entity_id == subject_id``, or carrying a
  ``PersonaRefComponent`` whose ``persona_id`` is the subject —
  across every world in the file, with all of its components and
  any A4-quarantined component payloads for it.
- **Journal** (:meth:`EventJournal.purge_subject`): see below.

Mention rule (the surgical boundary): a record/component on another
subject that merely *mentions* this subject in free text (a summary,
a fact value, a ``known_to`` list, a belief's topic) is NOT deleted
or rewritten — it is the other subject's data, and purge must leave
other subjects byte-identical (pinned by tests). The one structural
exception: ``ContainerComponent.children`` is containment *state*,
not a mention — a purged entity's id is scrubbed from surviving
containers' children lists so the world does not keep presenting a
ghost as present. Shared records (e.g. an observation listing the
subject among several participants) are deleted whole, not
redacted: their text is the subject's own utterances, and reliable
redaction of free text is not possible — stated here, not hidden.

Journal & dead letters — IN scope (deliberate decision)
-------------------------------------------------------
The B4 journal is a fourth file holding verbatim envelopes —
including, potentially, the subject's utterances. Its module
docstring excludes it from A5 *truth backups* because it is a
notification log, not a truth store; that reasoning does not extend
to erasure. A purge that left the subject's words sitting in the
journal would fail the absence guarantee in spirit, so journal
entries whose stored envelope/payload names the subject ARE
deleted, and persisted dead letters whose message names the subject
are deleted with them. This is a deliberate, documented exception
to the journal's append-only design (recorded in
``event_journal.py`` too): the journal has exactly two deletion
paths — dead-letter drain (its own semantics) and per-subject purge.

Quarantine vs purge (doctrine reconciliation)
---------------------------------------------
Phase A4's quarantine doctrine — preserve bytes, announce, keep
going — governs data the engine *refused*: it is kept because nobody
asked for it to be destroyed and losing it silently would be a truth
failure. Purge is the opposite act on the opposite authority: the
subject themselves demands destruction. Purge therefore DESTROYS by
design, including A4-quarantined component payloads belonging to the
subject, and leaves only the tombstone below. The two doctrines do
not conflict: quarantine preserves refused data against accidents;
purge erases a subject's data on request.

Ordering, failure honesty, idempotency
--------------------------------------
Cross-store atomicity does not exist (Phase A3 finding: three files,
no coordinator), so purge proceeds store-by-store in a fixed order —
**world → memory → bond → journal** (the A5 backup order, journal
last as the derived artifact). Each store's own purge is a single
transaction. A store that raises does NOT abort the purge: the
failure is recorded in the report (store name + error), the
remaining stores are still purged (erasure should remove as much as
it can), and the report's ``complete`` is False with ``store_status``
saying exactly which stores were purged, which failed, and which
were not in scope. A half-purge never claims success. Re-running
:func:`purge_subject` is idempotent: already-purged stores simply
find nothing, so a retry after a failure converges to completion.

Tombstone (what remains, and why)
---------------------------------
Every purge call — successful, partial, or a no-op for a subject
that never existed — appends ONE row to the tombstone store (its own
small SQLite file, opened with the same A1 factory discipline):

``tombstone_id`` (uuid), ``subject_id_hash`` (SHA-256 hex of the
subject id), ``purged_at`` (UTC), ``scope_json`` (per-store removal
counts + per-store status — numbers and status words only).

The tombstone deliberately stores the id's *hash*, not the id: it
proves compliance for a known subject (hash the id, look it up)
without itself becoming a new plaintext roster of erased people.
The honest tradeoff, stated plainly: subject ids are low-entropy,
so the hash is dictionary-reversible by anyone who can guess the
id — the tombstone protects against casual disclosure, not against
an adversary enumerating candidate ids. It stores NO content: no
text, no payloads, nothing the subject said. If writing the
tombstone itself fails, :func:`purge_subject` raises — a purge with
no compliance record must be loud, not silent (the stores are
already purged at that point; a re-run is safe and writes it).

Documented limits (not redesigned here)
---------------------------------------
- **Backups**: an A5 bundle taken *before* a purge still holds the
  subject, and restoring it resurrects the subject in the live
  stores. A5 is not redesigned (a restore-time tombstone check would
  need the restore API to know about tombstone files it has no
  contract with). The operational rule is: **re-run purge after any
  restore of a pre-purge backup** — purge is idempotent, so this is
  cheap and converges.
- **Verdandi mirror inputs**: excluded by source, per roadmap §8.
  The mirror is a pure projection rebuilt from the nerve feed; there
  is nothing stored in WYRD to purge. Erasure of the feed itself is
  Verdandi's side of the seam, not this module's.
- **Byte-level scrubbing**: purge removes rows from every table,
  index (including the memory FTS5 index — pinned by a
  search-after-purge test), and query surface. Freed SQLite pages
  may retain bytes until the file is vacuumed; the memory store
  runs a best-effort incremental vacuum after purging, and a full
  ``VACUUM`` remains an operator step for the other files.
- **File-level quarantine** (``state_io``'s quarantined corrupt DB
  files) is operator territory, outside the stores' purge scope.

Stdlib only, like the rest of the persistence layer.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from wyrdforge.hardening.state_io import connect_state_db, open_verified_state_db

if TYPE_CHECKING:
    from wyrdforge.persistence.bond_store import PersistentBondStore
    from wyrdforge.persistence.event_journal import EventJournal
    from wyrdforge.persistence.memory_store import PersistentMemoryStore
    from wyrdforge.persistence.world_store import WorldStore

#: Schema version stamped as ``PRAGMA user_version`` on the
#: tombstone DB. v1: ``purge_tombstones`` (Phase C1).
TOMBSTONE_SCHEMA_VERSION = 1

_TOMBSTONE_SCHEMA = """
CREATE TABLE IF NOT EXISTS purge_tombstones (
    tombstone_id    TEXT PRIMARY KEY,
    subject_id_hash TEXT NOT NULL,
    purged_at       TEXT NOT NULL,
    scope_json      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tombstones_subject
    ON purge_tombstones(subject_id_hash);
"""

#: Store keys, in purge order (world → memory → bond → journal).
STORE_ORDER: tuple[str, ...] = ("world", "memory", "bond", "journal")

STATUS_PURGED = "purged"
STATUS_FAILED = "failed"
STATUS_NOT_IN_SCOPE = "not-in-scope"


def subject_id_hash(subject_id: str) -> str:
    """SHA-256 hex of a subject id — the tombstone's only identifier."""
    return hashlib.sha256(subject_id.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class PurgeFailure:
    """One store whose purge raised — named, with the error kept."""

    store: str
    error_type: str
    error: str


@dataclass(frozen=True)
class PurgeReport:
    """Exactly what one :func:`purge_subject` call did.

    Counts are removals performed by THIS call (a re-purge of an
    already-purged subject reports zeros, honestly). ``complete`` is
    True only when every in-scope store purged without failure.
    """

    subject_id_hash: str
    tombstone_id: str
    purged_at: str
    complete: bool
    store_status: dict[str, str]
    memory_records_removed: int = 0
    bond_edges_removed: int = 0
    bond_vows_removed: int = 0
    bond_hurts_removed: int = 0
    world_entities_removed: int = 0
    world_components_removed: int = 0
    world_quarantined_removed: int = 0
    container_references_removed: int = 0
    journal_entries_removed: int = 0
    dead_letters_removed: int = 0
    failures: tuple[PurgeFailure, ...] = ()


@dataclass(frozen=True)
class Tombstone:
    """One durable purge record — identifier hash + counts, no content."""

    tombstone_id: str
    subject_id_hash: str
    purged_at: str
    scope: dict


class PurgeTombstoneStore:
    """The durable home of purge tombstones (its own SQLite file).

    Opened through the house guarded/versioned open and the A1
    connection factory, exactly like the other stores.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn, _recovered = open_verified_state_db(
            self._db_path, current_version=TOMBSTONE_SCHEMA_VERSION
        )
        with conn:
            conn.executescript(_TOMBSTONE_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return connect_state_db(self._db_path, row_factory=True)

    @property
    def db_path(self) -> Path:
        return self._db_path

    def record(
        self,
        *,
        subject_hash: str,
        purged_at: str,
        scope: dict,
    ) -> str:
        """Append one tombstone; return its id. Never updates/deletes."""
        tombstone_id = f"tomb_{uuid.uuid4().hex[:16]}"
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO purge_tombstones "
                "(tombstone_id, subject_id_hash, purged_at, scope_json) "
                "VALUES (?,?,?,?)",
                (
                    tombstone_id,
                    subject_hash,
                    purged_at,
                    json.dumps(scope, sort_keys=True),
                ),
            )
        return tombstone_id

    def for_subject(self, subject_id: str) -> list[Tombstone]:
        """All tombstones recorded for *subject_id* (looked up by hash)."""
        return self._by_hash(subject_id_hash(subject_id))

    def _by_hash(self, subject_hash: str) -> list[Tombstone]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT tombstone_id, subject_id_hash, purged_at, scope_json "
                "FROM purge_tombstones WHERE subject_id_hash=? "
                "ORDER BY purged_at, tombstone_id",
                (subject_hash,),
            ).fetchall()
        return [
            Tombstone(
                tombstone_id=row["tombstone_id"],
                subject_id_hash=row["subject_id_hash"],
                purged_at=row["purged_at"],
                scope=json.loads(row["scope_json"]),
            )
            for row in rows
        ]

    def all(self) -> list[Tombstone]:
        """Every tombstone, oldest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT tombstone_id, subject_id_hash, purged_at, scope_json "
                "FROM purge_tombstones ORDER BY purged_at, tombstone_id"
            ).fetchall()
        return [
            Tombstone(
                tombstone_id=row["tombstone_id"],
                subject_id_hash=row["subject_id_hash"],
                purged_at=row["purged_at"],
                scope=json.loads(row["scope_json"]),
            )
            for row in rows
        ]


def purge_subject(
    subject_id: str,
    *,
    tombstones: PurgeTombstoneStore,
    world_store: "WorldStore | None" = None,
    memory_store: "PersistentMemoryStore | None" = None,
    bond_store: "PersistentBondStore | None" = None,
    journal: "EventJournal | None" = None,
) -> PurgeReport:
    """Erase *subject_id* from every store handed in, and tombstone it.

    Stores left as ``None`` are reported ``not-in-scope`` and left
    untouched — the caller owns the scope, this function never goes
    looking for stores on its own. Order, failure semantics,
    idempotency, and the tombstone's shape are specified in the
    module docstring. An empty ``subject_id`` is refused with
    ``ValueError``: an unscoped purge is a store wipe, not a purge,
    and this function will not perform one.
    """
    if not subject_id:
        raise ValueError("purge_subject requires a non-empty subject_id")

    counts: dict[str, int] = {
        "memory_records_removed": 0,
        "bond_edges_removed": 0,
        "bond_vows_removed": 0,
        "bond_hurts_removed": 0,
        "world_entities_removed": 0,
        "world_components_removed": 0,
        "world_quarantined_removed": 0,
        "container_references_removed": 0,
        "journal_entries_removed": 0,
        "dead_letters_removed": 0,
    }
    status: dict[str, str] = {}
    failures: list[PurgeFailure] = []

    def _attempt(store: str, fn) -> None:
        try:
            result = fn()
        except Exception as exc:  # recorded, never hidden; purge continues
            status[store] = STATUS_FAILED
            failures.append(
                PurgeFailure(
                    store=store,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
            )
            return
        status[store] = STATUS_PURGED
        counts.update(result)

    # Fixed order: world → memory → bond → journal.
    if world_store is None:
        status["world"] = STATUS_NOT_IN_SCOPE
    else:
        _attempt("world", lambda: _world_counts(world_store.purge_subject(subject_id)))
    if memory_store is None:
        status["memory"] = STATUS_NOT_IN_SCOPE
    else:
        _attempt(
            "memory",
            lambda: {
                "memory_records_removed": len(
                    memory_store.purge_subject(subject_id)
                )
            },
        )
    if bond_store is None:
        status["bond"] = STATUS_NOT_IN_SCOPE
    else:
        _attempt("bond", lambda: _bond_counts(bond_store.purge_subject(subject_id)))
    if journal is None:
        status["journal"] = STATUS_NOT_IN_SCOPE
    else:
        _attempt(
            "journal", lambda: _journal_counts(journal.purge_subject(subject_id))
        )

    complete = all(
        status[store] in (STATUS_PURGED, STATUS_NOT_IN_SCOPE)
        for store in STORE_ORDER
    )
    purged_at = _utc_now().isoformat()
    scope = {
        "counts": dict(counts),
        "store_status": dict(status),
        "complete": complete,
        "failures": [
            {"store": f.store, "error_type": f.error_type, "error": f.error}
            for f in failures
        ],
    }
    # Written last and allowed to raise (see module docstring): a
    # purge with no compliance record must be loud.
    tombstone_id = tombstones.record(
        subject_hash=subject_id_hash(subject_id),
        purged_at=purged_at,
        scope=scope,
    )
    return PurgeReport(
        subject_id_hash=subject_id_hash(subject_id),
        tombstone_id=tombstone_id,
        purged_at=purged_at,
        complete=complete,
        store_status=dict(status),
        failures=tuple(failures),
        **counts,
    )


def _world_counts(result: dict) -> dict[str, int]:
    return {
        "world_entities_removed": int(result["entities"]),
        "world_components_removed": int(result["components"]),
        "world_quarantined_removed": int(result["quarantined_components"]),
        "container_references_removed": int(result["container_references_removed"]),
    }


def _bond_counts(result: dict) -> dict[str, int]:
    return {
        "bond_edges_removed": int(result["edges"]),
        "bond_vows_removed": int(result["vows"]),
        "bond_hurts_removed": int(result["hurts"]),
    }


def _journal_counts(result: dict) -> dict[str, int]:
    return {
        "journal_entries_removed": int(result["entries"]),
        "dead_letters_removed": int(result["dead_letters"]),
    }


__all__ = [
    "STATUS_FAILED",
    "STATUS_NOT_IN_SCOPE",
    "STATUS_PURGED",
    "STORE_ORDER",
    "TOMBSTONE_SCHEMA_VERSION",
    "PurgeFailure",
    "PurgeReport",
    "PurgeTombstoneStore",
    "Tombstone",
    "purge_subject",
    "subject_id_hash",
]
