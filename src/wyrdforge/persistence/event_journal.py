"""wyrdforge.persistence.event_journal — Durable event journal (Phase B4).

Roadmap §2.4/§2.6: before B4 the EventBus was the engine's only
metrics/failure surface and both of its histories were volatile — the
per-topic replay ring buffers and the dead-letter queue live in memory
only, so a restart erased the evidence of what happened and what
failed, and "what did the world look like at 14:03, and which events
made it so?" was unanswerable. This module is the durable counterpart:
an OPTIONAL, append-only SQLite journal of EventBus envelopes plus a
persisted dead-letter queue.

Design (smallest sound mechanism, following house patterns)
------------------------------------------------------------
- **Opt-in, off by default.** Nothing in the engine constructs an
  :class:`EventJournal` or attaches one to a bus unless the caller
  does. With no journal attached, the EventBus behaves byte-for-byte
  as before B4 (pinned by tests).
- **One file, one store, house durability.** The journal is its own
  SQLite file, opened through the Phase A1 factory
  (:func:`wyrdforge.hardening.state_io.connect_state_db` — WAL,
  ``synchronous=FULL``, ``foreign_keys=ON``, unified busy timeout) and
  the guarded/versioned open every other store uses
  (``open_verified_state_db``, schema v1). Each append is its own
  committed transaction on a fresh factory connection (the
  per-operation ``_connect()`` pattern of the other stores), so a
  committed journal entry survives process death and power loss to
  the same standard as the three truth stores.
- **Append-only.** Entries are only ever INSERTed; there is no update
  or delete path for journal entries. (Dead letters are the one
  exception by design: draining them is their documented semantics,
  exactly as on the bus — see below.) Phase C1 adds exactly one
  further, deliberate exception: :meth:`EventJournal.purge_subject`
  deletes entries (and persisted dead letters) naming one subject,
  on that subject's own erasure demand — an append-only log that
  kept a purged subject's words would fail the purge's absence
  guarantee in spirit. The journal therefore has exactly two
  deletion paths: dead-letter drain and per-subject purge (see
  ``persistence/purge.py``). ``journal_seq`` is an
  AUTOINCREMENT primary key: strictly monotonic in recorded order for
  the life of the file, never reused.
- **Bus sequence.** Every entry also carries the envelope's own bus
  ``seq`` (``bus_seq``). For a single-threaded publisher stream the
  journal's ``bus_seq`` column is strictly increasing in
  ``journal_seq`` order. Under concurrent publishers the journal
  records *completion* (flush) order, which may differ slightly from
  bus-seq order — ``journal_seq`` is the replay order, and the
  recorded ``bus_seq`` is preserved verbatim so either order can be
  audited. Both facts are stated here rather than hidden.
- **Classification.** Each entry is classified ``observation`` /
  ``fact`` / ``event``: an explicit ``kind=`` wins; otherwise the
  topic decides (a topic naming an observation/fact — e.g.
  ``memory.observation_added`` — classifies accordingly; everything
  else is an ``event``). The full envelope is stored verbatim as JSON
  alongside the columns, so classification is a view, never a lossy
  transform.

Bus integration (locking — the B1/EventBus discipline)
------------------------------------------------------
``EventBus.attach_journal(journal)`` is the only wiring. The bus
collects published envelopes and dead-letter entries into pending
lists while it holds its RLock (bookkeeping only — no I/O), and
flushes them to the journal AFTER the outermost ``publish()`` /
``publish_many()`` returns and the bus lock has been released. The
journal is therefore never written to while the bus lock is held —
the same reason the bus delivers replay backfill outside its lock.
The journal itself never calls back into the bus, holds no bus
reference, and serialises its own writers on its own lock, so the
flush cannot deadlock against a re-entering subscriber (pinned by a
test whose subscriber republishes to the same topic).

A journal write failure NEVER breaks publish/delivery (bus doctrine:
``publish()`` never raises because of a subscriber; the journal is
treated at least as gently). A failed append is logged at warning,
counted on the bus (``journal_status()["errors"]``), and the event's
live delivery is unaffected (pinned by test).

Dead letters, persisted
-----------------------
:meth:`record_dead_letter` stores bus dead-letter entries (the exact
dict shape the bus produces) in a ``dead_letters`` table.
:meth:`dead_letters`, :meth:`dead_letter_summary`, and
:meth:`take_dead_letters` mirror the bus's own three surfaces with
the same shapes and semantics — summary groups
``{topic: {error_type: count}}`` read-only; take drains (returns and
removes) oldest first. The difference is durability only: persisted
dead letters survive ``EventBus.close()`` (which clears the in-memory
queue) and process restart (both pinned by tests). Attaching a
journal does not change the in-memory API or its behaviour; the bus
keeps its own queue exactly as before and the journal is a second,
durable copy.

Replay — what it can and cannot reconstruct (honest scope)
------------------------------------------------------------
Bus envelopes are *notifications*: a topic, a payload dict, a source,
a turn id, a timestamp. They do not, in general, encode complete
World mutations — many producers publish after-the-fact summaries,
entity/component ids inside payloads are producer conventions (and
historically random uuids, roadmap §2.4), and not every World
mutation publishes at all. Rebuilding an ECS ``World`` from bus
envelopes alone would therefore be fabrication, not reconstruction,
and this module does not pretend to do it. What the journal DOES
support, soundly, is:

1. **Journal snapshot reconstruction** — :meth:`reconstruct_snapshot`
   folds the journal up to any ``journal_seq`` point (inclusive;
   ``None`` = the whole journal) into a :class:`JournalSnapshot`:
   the verbatim ordered envelopes, per-topic counts, the latest
   envelope per topic, and the persisted dead letters whose bus seq
   falls inside the folded range. A snapshot taken at a mid-stream
   point equals the snapshot of exactly that prefix — after a
   close/reopen too (pinned by tests). This is the journaled record
   set, reconstructed exactly.
2. **Event replay into a fresh bus** — :meth:`replay_to_bus`
   republishes the recorded envelopes, in ``journal_seq`` order,
   into a target bus (registering any topic the target does not know
   yet), so downstream projections rebuild themselves through their
   normal subscriptions: e.g. a ``ReplayPersistenceBridge`` on the
   target bus re-derives the same memory observations (same topics,
   payloads, sources, turn ids) it derived live. Topic, payload,
   source and turn_id are preserved verbatim; the target bus assigns
   fresh ``seq``/``issued_at`` by its own rules (when a complete,
   unfiltered journal starting at bus seq 1 is replayed into a fresh
   bus, the fresh seqs coincide with the originals, because both
   counters start at 1 and advance once per envelope — pinned).

Full World-state-at-a-time reconstruction remains snapshot restore's
job (WorldStore + Phase A5 backup), now complementable by the
journal: restore the snapshot, then answer "and then what happened?"
from the journal. That boundary is the design, stated plainly.

Backup scope (Phase A5 accounting)
----------------------------------
The journal file is deliberately NOT part of the A5 cross-store
bundle (``persistence/backup.py`` keeps its exact three-store set):
the journal is optional, is not one of the three truth stores, and a
deployment that enables it can copy the single journal file with the
same quiesce discipline if it wants it in a backup set. The exclusion
is recorded here and in ``backup.py``; nothing about A5 changes.

ReplayPersistenceBridge interplay
---------------------------------
The bridge (``services/bus_consumers.py``) persists envelopes as
*memory observations*; the journal persists them as *journal
entries*. The two write disjoint stores, and the bus flushes each
published envelope to the journal exactly once regardless of how
many bridges are subscribed — there is no double-record path. Both
may be active at once (pinned by test: one envelope = one journal
entry + one bridge observation).

Stdlib only, like the rest of the persistence layer.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

from wyrdforge.hardening.state_io import connect_state_db, open_verified_state_db

if TYPE_CHECKING:
    from wyrdforge.runtime.events import EventBus, EventEnvelope

log = logging.getLogger(__name__)

#: Schema version stamped as ``PRAGMA user_version`` on the journal DB.
#: v1: ``journal_entries`` + ``dead_letters`` (Phase B4).
CURRENT_SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS journal_entries (
    journal_seq   INTEGER PRIMARY KEY AUTOINCREMENT,
    bus_seq       INTEGER,
    topic         TEXT NOT NULL,
    kind          TEXT NOT NULL DEFAULT 'event',
    source        TEXT NOT NULL DEFAULT '',
    turn_id       TEXT,
    issued_at     TEXT NOT NULL DEFAULT '',
    payload_json  TEXT NOT NULL,
    envelope_json TEXT NOT NULL,
    recorded_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_journal_topic ON journal_entries(topic);
CREATE INDEX IF NOT EXISTS idx_journal_bus_seq ON journal_entries(bus_seq);

CREATE TABLE IF NOT EXISTS dead_letters (
    dead_letter_id INTEGER PRIMARY KEY AUTOINCREMENT,
    bus_seq        INTEGER,
    topic          TEXT NOT NULL,
    subscriber     TEXT NOT NULL DEFAULT '',
    error_type     TEXT NOT NULL,
    message        TEXT NOT NULL DEFAULT '',
    timestamp      TEXT NOT NULL DEFAULT '',
    recorded_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dead_letters_topic ON dead_letters(topic);
"""

#: Entry kinds the journal classifies into.
KIND_OBSERVATION = "observation"
KIND_FACT = "fact"
KIND_EVENT = "event"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_kind(topic: str, payload: object = None) -> str:
    """Classify an envelope as observation / fact / event by topic.

    A topic naming an observation (``memory.observation_added``,
    ``*.observation.*``) classifies as an observation; likewise for
    facts; everything else is a plain event. Payload is accepted for
    future refinement and currently unused — classification is a
    view over the verbatim envelope, never a transform of it.
    """
    lowered = topic.lower()
    if "observation" in lowered:
        return KIND_OBSERVATION
    if "fact" in lowered:
        return KIND_FACT
    return KIND_EVENT


def _names_subject_exact(node: object, subject_id: str) -> bool:
    """True when *subject_id* is an exact string value in *node*.

    Recursive over dicts (keys and values) and lists/tuples. A
    longer string merely containing the id (a free-text mention)
    does not count — Phase C1 matches structured fields only.
    """
    if isinstance(node, str):
        return node == subject_id
    if isinstance(node, dict):
        return any(
            _names_subject_exact(key, subject_id)
            or _names_subject_exact(value, subject_id)
            for key, value in node.items()
        )
    if isinstance(node, (list, tuple)):
        return any(_names_subject_exact(item, subject_id) for item in node)
    return False


def _envelope_to_dict(envelope: object) -> dict:
    """Normalise an EventEnvelope (or envelope-shaped dict) to a dict."""
    if hasattr(envelope, "to_dict"):
        return dict(envelope.to_dict())  # type: ignore[attr-defined]
    if isinstance(envelope, dict):
        return dict(envelope)
    raise TypeError(
        "journal entries must be EventEnvelope instances or dicts, "
        f"got {type(envelope).__name__}"
    )


@dataclass(frozen=True)
class JournalEntry:
    """One durable journal entry — a verbatim envelope plus its seqs."""

    journal_seq: int
    bus_seq: int | None
    topic: str
    kind: str
    source: str
    turn_id: str | None
    issued_at: str
    payload: dict
    envelope: dict
    recorded_at: str

    def to_envelope(self) -> "EventEnvelope":
        """Rebuild the recorded :class:`EventEnvelope` verbatim."""
        from wyrdforge.runtime.events import EventEnvelope

        return EventEnvelope(**dict(self.envelope))


@dataclass(frozen=True)
class JournalSnapshot:
    """The journal folded up to one point — the reconstructed record set.

    ``entries`` are the verbatim envelopes in journal order;
    ``per_topic_counts`` and ``latest_by_topic`` are derived views of
    exactly those entries; ``dead_letters`` are the persisted dead
    letters whose bus seq lies within the folded entries' bus-seq
    range (all persisted dead letters when the whole journal is
    folded). Two snapshots are equal iff the folded record sets are
    identical — that equality is the replay-correctness test surface.
    """

    entries: tuple[JournalEntry, ...]
    per_topic_counts: dict[str, int]
    latest_by_topic: dict[str, JournalEntry]
    dead_letters: tuple[dict, ...]
    through_journal_seq: int | None
    max_bus_seq: int | None


@dataclass(frozen=True)
class ReplayReport:
    """Outcome of a :meth:`EventJournal.replay_to_bus` call."""

    replayed: int
    first_journal_seq: int | None
    last_journal_seq: int | None
    topics_registered: tuple[str, ...]


class EventJournal:
    """Append-only durable journal of bus envelopes + dead letters.

    Args:
        db_path: File path for the journal's SQLite database. The
            file is created (schema v1) if missing; a corrupt file
            takes the house quarantine path via the guarded open,
            exactly like the other stores.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema / connections
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        conn, _recovered = open_verified_state_db(
            self._db_path, current_version=CURRENT_SCHEMA_VERSION
        )
        with conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        # Phase A1 factory: WAL + synchronous=FULL + foreign_keys=ON +
        # unified busy timeout — the same durability pack as the
        # three truth stores.
        return connect_state_db(self._db_path, row_factory=True)

    @property
    def db_path(self) -> Path:
        return self._db_path

    # ------------------------------------------------------------------
    # Append (the journal's only write path for entries)
    # ------------------------------------------------------------------

    def append(self, envelope: object, *, kind: str | None = None) -> int:
        """Append one envelope; return its ``journal_seq``.

        Append-only: this INSERT is the only mutation entries ever
        get. The envelope is stored verbatim (``envelope_json``) as
        well as in columns, so no field can be lost to a column
        mismatch.
        """
        data = _envelope_to_dict(envelope)
        topic = str(data.get("topic", ""))
        payload = data.get("payload") or {}
        bus_seq_raw = data.get("seq")
        bus_seq = int(bus_seq_raw) if bus_seq_raw is not None else None
        entry_kind = kind or classify_kind(topic, payload)
        with self._lock:
            with self._connect() as conn:
                cursor = conn.execute(
                    "INSERT INTO journal_entries "
                    "(bus_seq, topic, kind, source, turn_id, issued_at, "
                    "payload_json, envelope_json, recorded_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        bus_seq,
                        topic,
                        entry_kind,
                        str(data.get("source", "") or ""),
                        data.get("turn_id"),
                        str(data.get("issued_at", "") or ""),
                        json.dumps(payload, sort_keys=True, default=str),
                        json.dumps(data, sort_keys=True, default=str),
                        _utc_now_iso(),
                    ),
                )
                return int(cursor.lastrowid)

    def append_many(self, envelopes: Iterable[object]) -> list[int]:
        """Append several envelopes in one transaction; return seqs."""
        seqs: list[int] = []
        rows = []
        for envelope in envelopes:
            data = _envelope_to_dict(envelope)
            topic = str(data.get("topic", ""))
            payload = data.get("payload") or {}
            bus_seq_raw = data.get("seq")
            rows.append(
                (
                    int(bus_seq_raw) if bus_seq_raw is not None else None,
                    topic,
                    classify_kind(topic, payload),
                    str(data.get("source", "") or ""),
                    data.get("turn_id"),
                    str(data.get("issued_at", "") or ""),
                    json.dumps(payload, sort_keys=True, default=str),
                    json.dumps(data, sort_keys=True, default=str),
                    _utc_now_iso(),
                )
            )
        if not rows:
            return seqs
        with self._lock:
            with self._connect() as conn:
                for row in rows:
                    cursor = conn.execute(
                        "INSERT INTO journal_entries "
                        "(bus_seq, topic, kind, source, turn_id, issued_at, "
                        "payload_json, envelope_json, recorded_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        row,
                    )
                    seqs.append(int(cursor.lastrowid))
        return seqs

    # ------------------------------------------------------------------
    # Read-back
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> JournalEntry:
        return JournalEntry(
            journal_seq=int(row["journal_seq"]),
            bus_seq=(int(row["bus_seq"]) if row["bus_seq"] is not None else None),
            topic=str(row["topic"]),
            kind=str(row["kind"]),
            source=str(row["source"]),
            turn_id=row["turn_id"],
            issued_at=str(row["issued_at"]),
            payload=json.loads(row["payload_json"]),
            envelope=json.loads(row["envelope_json"]),
            recorded_at=str(row["recorded_at"]),
        )

    def entries(
        self,
        *,
        after_journal_seq: int = 0,
        through_journal_seq: int | None = None,
        topic: str | None = None,
    ) -> list[JournalEntry]:
        """Entries in journal order, optionally windowed/filtered."""
        sql = "SELECT * FROM journal_entries WHERE journal_seq > ?"
        params: list[object] = [after_journal_seq]
        if through_journal_seq is not None:
            sql += " AND journal_seq <= ?"
            params.append(through_journal_seq)
        if topic is not None:
            sql += " AND topic = ?"
            params.append(topic)
        sql += " ORDER BY journal_seq"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def count(self, *, topic: str | None = None) -> int:
        with self._connect() as conn:
            if topic is None:
                row = conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM journal_entries WHERE topic=?", (topic,)
                ).fetchone()
        return int(row[0])

    def latest_journal_seq(self) -> int | None:
        with self._connect() as conn:
            row = conn.execute("SELECT MAX(journal_seq) FROM journal_entries").fetchone()
        return int(row[0]) if row and row[0] is not None else None

    def integrity_check(self) -> bool:
        with self._connect() as conn:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            return result is not None and result[0] == "ok"

    # ------------------------------------------------------------------
    # Dead letters — persisted mirror of the bus's three surfaces
    # ------------------------------------------------------------------

    def record_dead_letter(self, entry: dict) -> int:
        """Persist one bus dead-letter entry; return its durable id."""
        with self._lock:
            with self._connect() as conn:
                cursor = conn.execute(
                    "INSERT INTO dead_letters "
                    "(bus_seq, topic, subscriber, error_type, message, "
                    "timestamp, recorded_at) VALUES (?,?,?,?,?,?,?)",
                    (
                        entry.get("seq"),
                        str(entry.get("topic", "")),
                        str(entry.get("subscriber", "")),
                        str(entry.get("error_type", "")),
                        str(entry.get("message", "")),
                        str(entry.get("timestamp", "")),
                        _utc_now_iso(),
                    ),
                )
                return int(cursor.lastrowid)

    @staticmethod
    def _row_to_dead_letter(row: sqlite3.Row) -> dict:
        # The bus's entry shape, plus the durable id under its own key
        # so durable entries can be told apart from volatile ones.
        return {
            "seq": row["bus_seq"],
            "topic": row["topic"],
            "subscriber": row["subscriber"],
            "error_type": row["error_type"],
            "message": row["message"],
            "timestamp": row["timestamp"],
            "dead_letter_id": int(row["dead_letter_id"]),
        }

    def dead_letters(self) -> list[dict]:
        """Persisted dead letters, oldest first (bus shape + id)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM dead_letters ORDER BY dead_letter_id"
            ).fetchall()
        return [self._row_to_dead_letter(row) for row in rows]

    def dead_letter_summary(self) -> dict[str, dict[str, int]]:
        """Counts grouped ``{topic: {error_type: count}}`` — read-only.

        Same shape as ``EventBus.dead_letter_summary()``.
        """
        summary: dict[str, dict[str, int]] = {}
        for entry in self.dead_letters():
            per_topic = summary.setdefault(entry["topic"], {})
            per_topic[entry["error_type"]] = per_topic.get(entry["error_type"], 0) + 1
        return summary

    def take_dead_letters(self) -> list[dict]:
        """Drain the persisted queue: return and remove, oldest first.

        Same semantics as ``EventBus.take_dead_letters()``, made
        durable: the drain is one transaction, so a crash mid-drain
        cannot half-forget the evidence.
        """
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM dead_letters ORDER BY dead_letter_id"
                ).fetchall()
                conn.execute("DELETE FROM dead_letters")
        return [self._row_to_dead_letter(row) for row in rows]

    def dead_letter_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM dead_letters").fetchone()
        return int(row[0])

    # ------------------------------------------------------------------
    # Per-subject purge (Phase C1) — the journal's second deletion path
    # ------------------------------------------------------------------

    def purge_subject(self, subject_id: str) -> dict:
        """Delete journal traces naming *subject_id* (Phase C1).

        An entry is deleted when its stored envelope names the
        subject as an exact structured value (recursively over the
        envelope dict — payload values, source, turn id; a longer
        string merely *containing* the id is a free-text mention and
        does NOT match). A persisted dead letter carries no envelope
        — its only content field is the recorded failure ``message``
        — so a dead letter is deleted when that message names the
        subject (substring, the one place "names" can only mean the
        message text; see ``persistence/purge.py``).

        Both deletions run in ONE transaction under the journal's
        own lock. Returns ``{"entries": n, "dead_letters": n}`` —
        removals performed by THIS call.
        """
        with self._lock:
            with self._connect() as conn:
                entry_ids: list[int] = []
                for row in conn.execute(
                    "SELECT journal_seq, envelope_json FROM journal_entries"
                ).fetchall():
                    try:
                        envelope = json.loads(row["envelope_json"])
                    except (ValueError, TypeError):
                        continue  # cannot prove it names the subject
                    if _names_subject_exact(envelope, subject_id):
                        entry_ids.append(int(row["journal_seq"]))
                if entry_ids:
                    conn.executemany(
                        "DELETE FROM journal_entries WHERE journal_seq=?",
                        [(seq,) for seq in entry_ids],
                    )
                letter_ids = [
                    int(row["dead_letter_id"])
                    for row in conn.execute(
                        "SELECT dead_letter_id, message FROM dead_letters"
                    ).fetchall()
                    if subject_id in (row["message"] or "")
                ]
                if letter_ids:
                    conn.executemany(
                        "DELETE FROM dead_letters WHERE dead_letter_id=?",
                        [(lid,) for lid in letter_ids],
                    )
        return {"entries": len(entry_ids), "dead_letters": len(letter_ids)}

    # ------------------------------------------------------------------
    # Reconstruction & replay (honest scope — see module docstring)
    # ------------------------------------------------------------------

    def reconstruct_snapshot(
        self, *, through_journal_seq: int | None = None
    ) -> JournalSnapshot:
        """Fold the journal up to a point into a :class:`JournalSnapshot`.

        ``through_journal_seq=None`` folds the whole journal. The
        snapshot is a pure function of the stored rows: the same
        prefix always reconstructs the same snapshot, across
        close/reopen and process restarts.
        """
        folded = self.entries(through_journal_seq=through_journal_seq)
        per_topic: dict[str, int] = {}
        latest: dict[str, JournalEntry] = {}
        bus_seqs = [e.bus_seq for e in folded if e.bus_seq is not None]
        for entry in folded:
            per_topic[entry.topic] = per_topic.get(entry.topic, 0) + 1
            latest[entry.topic] = entry
        if folded:
            max_bus = max(bus_seqs) if bus_seqs else None
            letters = tuple(
                entry
                for entry in self.dead_letters()
                if entry["seq"] is None or max_bus is None or entry["seq"] <= max_bus
            )
        else:
            letters = ()
        return JournalSnapshot(
            entries=tuple(folded),
            per_topic_counts=per_topic,
            latest_by_topic=latest,
            dead_letters=letters,
            through_journal_seq=through_journal_seq,
            max_bus_seq=(max(bus_seqs) if bus_seqs else None),
        )

    def replay_to_bus(
        self,
        bus: "EventBus",
        *,
        after_journal_seq: int = 0,
        through_journal_seq: int | None = None,
        topics: Iterable[str] | None = None,
    ) -> ReplayReport:
        """Republish journaled envelopes into *bus*, in journal order.

        Topics the target bus has not registered are registered first
        (a fresh bus must be able to receive its own history).
        Payload, source and turn_id are preserved verbatim; the target
        bus assigns fresh seq/issued_at by its own rules. Returns a
        :class:`ReplayReport` — this method never swallows a publish
        error: replay is an operator action, and a failure should be
        loud there (unlike live journaling, which must never break a
        publisher).
        """
        wanted = set(topics) if topics is not None else None
        selected = [
            entry
            for entry in self.entries(
                after_journal_seq=after_journal_seq,
                through_journal_seq=through_journal_seq,
            )
            if wanted is None or entry.topic in wanted
        ]
        known = set(bus.topics())
        registered: list[str] = []
        for entry in selected:
            if entry.topic not in known:
                bus.register_topic(entry.topic)
                known.add(entry.topic)
                registered.append(entry.topic)
        for entry in selected:
            bus.publish(
                entry.topic,
                dict(entry.payload),
                source=entry.source,
                turn_id=entry.turn_id,
            )
        return ReplayReport(
            replayed=len(selected),
            first_journal_seq=selected[0].journal_seq if selected else None,
            last_journal_seq=selected[-1].journal_seq if selected else None,
            topics_registered=tuple(registered),
        )


__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "EventJournal",
    "JournalEntry",
    "JournalSnapshot",
    "ReplayReport",
    "classify_kind",
]
