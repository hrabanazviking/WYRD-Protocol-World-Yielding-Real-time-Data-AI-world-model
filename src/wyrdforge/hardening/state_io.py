"""wyrdforge.hardening.state_io — Corrupt-state detection and repair (Track 5).

One shared helper for every state file this repo writes — "less programs
that do more." The quarantine pattern comes from the forge queue (PROVEN):
announce once, move the corrupt file aside, keep going; never silently
drop the bytes, never block the pipeline, never nag on the next run.

Standing rules this module enforces (Track 6, Incident 3; Track 5):
- A corrupt state file is quarantined with an announcement, never deleted.
- A missing file is normal — fresh state is created and stamped.
- A file claiming a *newer* schema than this code knows is quarantined,
  never misread and never silently ignored.
- Schema versions live on the projection/convenience files (the SQLite
  stores), never on the world object itself (pure projection — the world
  is rebuilt fresh every run).

Stdlib only: ``sqlite3``, ``pathlib``, ``os``, ``json``, ``logging``,
``datetime``, ``tempfile``. No I/O beyond the documented contract.
"""
from __future__ import annotations

import json
import logging
import operator
import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from collections.abc import Iterable

    from wyrdforge.runtime.events import EventBus

#: Topic emitted by quarantine_file when wired to an EventBus
#: (opt-in via ``bus=``).
_STATE_TOPICS = ("state.quarantined",)


def _register_state_topics(bus: "EventBus") -> None:
    """Register the state.* topics once; tolerate double registration."""
    for topic in _STATE_TOPICS:
        try:
            bus.register_topic(topic)
        except ValueError:
            pass  # already registered — another producer got here first

log = logging.getLogger(__name__)


class CorruptStateError(Exception):
    """A state file exists but cannot be opened, read, or migrated.

    Attributes:
        path: the state file that failed.
        reason: one of ``"not-a-database"`` | ``"integrity-failed"`` |
            ``"unknown-version"`` | ``"unmigratable"`` | ``"not-json"`` |
            ``"invalid-content"``.
        detail: human-readable explanation (safe to log; never invents
            a cause — it names what was observed).

    Never raised for a merely-missing file — missing is normal, and the
    callers create fresh state instead.
    """

    def __init__(self, path: str | Path, reason: str, detail: str = "") -> None:
        super().__init__(f"{path}: corrupt state ({reason}): {detail}")
        self.path = Path(path)
        self.reason = reason
        self.detail = detail


#: Paths already announced this process. "Announce once, don't nag" —
#: the forge queue's proven behavior, mirrored here.
_ANNOUNCED: set[str] = set()


def _reset_announced() -> None:
    """Test-only helper: clear the per-process announce-once ledger."""
    _ANNOUNCED.clear()


def _announce_once(path: Path, message: str, *args: object) -> bool:
    """Log one warning per path per process. Returns True if announced."""
    key = str(path)
    if key in _ANNOUNCED:
        return False
    _ANNOUNCED.add(key)
    log.warning(message, *args)
    return True


def _local_stamp() -> str:
    """Local-time stamp matching the evidence-bundle naming convention."""
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def quarantine_file(path: str | Path, reason: str = "",
                    detail: str = "", *,
                    bus: "EventBus | None" = None) -> Path:
    """Move a corrupt state file aside for later inspection.

    The file (plus any SQLite ``-wal`` / ``-shm`` companions) is moved to
    ``<parent>/quarantine/<stem>-YYYYMMDD-HHMMSS<ext>`` and announced
    exactly once per path per process via ``logging.warning`` — the
    warning names the reason so the announcement is informative, not
    just noise.

    Quarantine preserves the bytes — it never deletes. A name collision
    (same second) gets a ``-2``, ``-3`` suffix rather than overwriting.

    When ``bus`` is given, a ``state.quarantined`` event is published
    after the move; ``bus=None`` (the default) preserves the exact
    historical behavior. Bus errors never disturb the quarantine.
    """
    path = Path(path)
    if bus is not None:
        _register_state_topics(bus)
    dest_dir = path.parent / "quarantine"
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = _local_stamp()
    dest = dest_dir / f"{path.stem}-{stamp}{path.suffix}"
    n = 1
    while dest.exists():
        n += 1
        dest = dest_dir / f"{path.stem}-{stamp}-{n}{path.suffix}"
    os.replace(str(path), str(dest))
    for companion in ("-wal", "-shm"):
        sidecar = path.parent / (path.name + companion)
        if sidecar.exists():
            os.replace(str(sidecar), str(dest.parent / (dest.name + companion)))
    why = f" ({reason}: {detail})" if reason else ""
    _announce_once(
        path,
        f"Corrupt state file %s{why} quarantined to %s; running fresh",
        path,
        dest,
    )
    # Wired event: announce the quarantine after the move completed.
    # Bus trouble must never disturb a quarantine.
    if bus is not None:
        try:
            bus.publish(
                "state.quarantined",
                {
                    "path": str(path),
                    "dest": str(dest),
                    "reason": reason,
                    "detail": detail,
                },
                source="hardening.state_io",
            )
        except Exception:
            pass
    return dest


#: Unified busy timeout for every state-store connection, in
#: milliseconds. Before the Phase A persistence hardening pack the
#: three stores disagreed: the world and bond stores relied on
#: ``connect(timeout=5.0)`` alone, while the memory store paired
#: ``connect(timeout=10.0)`` with ``PRAGMA busy_timeout=5000`` — and
#: the pragma silently overrode the connect timeout, so 5 s was the
#: memory store's *effective* behaviour all along. All stores now
#: standardise on that effective value, stated once, here.
STATE_BUSY_TIMEOUT_MS = 5000

#: sqlite3 connect() timeout in seconds. Kept exactly equal to the
#: busy timeout the factory installs, so the two mechanisms can never
#: contradict each other again.
STATE_CONNECT_TIMEOUT_S = STATE_BUSY_TIMEOUT_MS / 1000.0


def connect_state_db(
    path: str | Path,
    *,
    row_factory: bool = False,
    extra_pragmas: "Iterable[str]" = (),
) -> sqlite3.Connection:
    """The one connection factory for every WYRD state store.

    Phase A persistence hardening pack: before this factory existed,
    each store opened its SQLite connections by hand and the three had
    drifted apart — durability rested on SQLite's unpinned
    ``synchronous`` default (zero ``PRAGMA synchronous`` anywhere in
    the tree), the bond store never enabled ``foreign_keys``, and the
    busy timeouts disagreed (see :data:`STATE_BUSY_TIMEOUT_MS`).

    Every connection this factory returns carries the uniform pack:

    - ``journal_mode=WAL`` — the house journal mode.
    - ``synchronous=FULL`` — durability pinned, never defaulted: a
      committed turn survives power loss.
    - ``foreign_keys=ON`` — declared constraints are enforced on
      every store, the bond store included.
    - ``busy_timeout=5000`` — one contention behaviour for all
      stores, equal to the connect() timeout.

    Args:
        path:          The SQLite state file.
        row_factory:   Set ``sqlite3.Row`` as the row factory (the
                       world and bond stores' historical behaviour).
        extra_pragmas: Store-specific extras applied after the pack,
                       in order (the memory store passes its
                       ``auto_vacuum=INCREMENTAL`` here — a storage
                       choice, not part of the durability pack).

    The caller owns the returned connection (context-manage or close
    it). No schema is created here — stores keep that job.
    """
    conn = sqlite3.connect(str(path), timeout=STATE_CONNECT_TIMEOUT_S)
    if row_factory:
        conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"PRAGMA busy_timeout={STATE_BUSY_TIMEOUT_MS}")
    for pragma in extra_pragmas:
        conn.execute(pragma)
    return conn


def _read_user_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    try:
        return int(row[0]) if row else 0
    except (TypeError, ValueError):
        return 0


def _stamp_version(conn: sqlite3.Connection, version: int) -> None:
    version = operator.index(version)
    conn.execute(f"PRAGMA user_version={version}")


def _run_migrations(
    path: Path,
    conn: sqlite3.Connection,
    from_version: int,
    to_version: int,
    migrations: dict[int, Callable[[sqlite3.Connection], None]],
) -> None:
    """Run the forward migration chain ``from_version -> to_version``.

    ``migrations`` maps the version being migrated *from* to a callable
    performing that step's DDL. Versions with no registered step need no
    DDL — the stamp is the migration (this is how every unstamped DB in
    the wild becomes v1). Forward-only; downgrades do not exist.
    """
    for step in range(from_version, to_version):
        migrate = migrations.get(step)
        if migrate is None:
            continue
        try:
            migrate(conn)
        except Exception as exc:
            raise CorruptStateError(
                path,
                "unmigratable",
                f"migration v{step} -> v{step + 1} failed: {exc}",
            ) from exc
    conn.commit()


def open_state_db(
    path: str | Path,
    *,
    current_version: int,
    migrations: dict[int, Callable[[sqlite3.Connection], None]] | None = None,
) -> sqlite3.Connection:
    """Strict open of a versioned SQLite state file. Raises on corruption.

    - Missing file: created lazily, stamped ``user_version=current_version``,
      info-logged. Missing is normal.
    - Present, version == current: returned as-is.
    - Present, version < current: forward migrations run in order, the new
      version is stamped, info-logged.
    - Present, version > current: ``CorruptStateError("unknown-version")`` —
      a newer schema than this code knows is quarantined by the caller,
      never misread.
    - Not a database at all: ``CorruptStateError("not-a-database")``.

    The returned connection is in WAL mode. Callers that want to survive
    corruption instead of handling it should use :func:`open_or_quarantine`.
    """
    path = Path(path)
    existed = path.exists()
    conn = None
    try:
        conn = connect_state_db(path)
        # Cheap smoke: SELECT 1 is a no-op, but reading user_version
        # forces SQLite to parse the database header — that is what
        # actually rejects garbage bytes.
        conn.execute("SELECT 1").fetchone()
        version = _read_user_version(conn)
    except sqlite3.Error as exc:
        if conn is not None:
            conn.close()
        raise CorruptStateError(
            path, "not-a-database", f"SQLite cannot open it: {exc}"
        ) from exc
    if version > current_version:
        conn.close()
        raise CorruptStateError(
            path,
            "unknown-version",
            f"schema v{version} is newer than this code knows (v{current_version})",
        )
    if version < current_version:
        _run_migrations(path, conn, version, current_version, migrations or {})
        _stamp_version(conn, current_version)
        conn.commit()
        if existed:
            log.info("Migrated state DB %s v%d -> v%d", path, version, current_version)
        else:
            log.info("Created state DB %s (schema v%d)", path, current_version)
    return conn


def open_or_quarantine(
    path: str | Path,
    *,
    current_version: int,
    migrations: dict[int, Callable[[sqlite3.Connection], None]] | None = None,
) -> tuple[sqlite3.Connection, bool]:
    """The call-site API. Returns ``(conn, recovered)``.

    On corruption (:class:`CorruptStateError`): the file is quarantined
    (announced once per process) and a fresh DB is opened instead —
    ``recovered`` is True. Never raises for corruption; the corrupt
    bytes are preserved in ``quarantine/`` and the run continues.
    """
    path = Path(path)
    try:
        return (
            open_state_db(path, current_version=current_version, migrations=migrations),
            False,
        )
    except CorruptStateError as exc:
        quarantine_file(path, reason=exc.reason, detail=exc.detail)
        return (
            open_state_db(path, current_version=current_version, migrations=migrations),
            True,
        )


def prune_quarantine(directory: str | Path, keep: int = 10) -> int:
    """Delete the oldest quarantined files, keeping the ``keep`` newest.

    Quarantine preserves bytes — that is its job — but an unattended forge
    accumulates quarantined files forever. This is the bounded counterpart:
    it keeps the ``keep`` newest files (by mtime, so a forensics trail
    survives) and deletes the rest. Only files directly inside
    ``directory`` are considered; subdirectories are never touched.

    Args:
        directory: The quarantine directory to prune.
        keep:      How many of the newest files to keep (>= 0).

    Returns:
        The number of files deleted.

    Raises:
        ValueError: If ``keep`` is negative.
    """
    if keep < 0:
        raise ValueError(f"keep must be >= 0, got {keep}")
    directory = Path(directory)
    if not directory.is_dir():
        return 0
    files = sorted(
        (p for p in directory.iterdir() if p.is_file()),
        key=lambda p: (p.stat().st_mtime, p.name),
        reverse=True,
    )
    pruned = 0
    for stale in files[keep:]:
        try:
            stale.unlink()
            pruned += 1
        except OSError:
            log.warning("prune_quarantine: could not delete %s", stale)
    if pruned:
        log.info(
            "prune_quarantine: removed %d file(s) from %s, kept %d newest",
            pruned,
            directory,
            keep,
        )
    return pruned


def read_json_state(
    path: str | Path,
    *,
    validator: Callable[[object], bool] | None = None,
) -> object:
    """Read-side companion to :func:`atomic_write_json`.

    Reads *path* as JSON and returns the parsed object. On a JSON decode
    failure — or when *validator* rejects the content — the file is
    quarantined (bytes preserved, announced once) and a
    :class:`CorruptStateError` is raised, mirroring the strict-open
    philosophy of :func:`open_state_db`: corrupt state is never silently
    misread, never silently dropped.

    Args:
        path:      The JSON state file to read.
        validator: Optional callable ``obj -> bool``. Return a truthy
                   value for acceptable content. A falsy return — or an
                   exception from the validator itself — counts as
                   rejection.

    Returns:
        The parsed JSON object.

    Raises:
        FileNotFoundError: The file does not exist (missing is normal;
            callers create fresh state instead — same rule as the DB
            helpers).
        CorruptStateError: ``reason="not-json"`` when the bytes are not
            valid JSON; ``reason="invalid-content"`` when the validator
            rejects the parsed object. In both cases the file has already
            been quarantined.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise CorruptStateError(path, "not-json", f"cannot read file: {exc}") from exc
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        quarantine_file(path, reason="not-json", detail=str(exc))
        raise CorruptStateError(
            path, "not-json", f"file is not valid JSON: {exc}"
        ) from exc
    if validator is not None:
        try:
            accepted = validator(obj)
        except Exception as exc:
            quarantine_file(
                path, reason="invalid-content", detail=f"validator raised: {exc}"
            )
            raise CorruptStateError(
                path, "invalid-content", f"validator raised {exc!r}"
            ) from exc
        if not accepted:
            quarantine_file(path, reason="invalid-content", detail="validator rejected content")
            raise CorruptStateError(
                path, "invalid-content", "validator rejected content"
            )
    return obj


def open_verified_state_db(
    path: str | Path,
    *,
    current_version: int,
    migrations: dict[int, Callable[[sqlite3.Connection], None]] | None = None,
) -> tuple[sqlite3.Connection, bool]:
    """Open a state DB and verify its structural integrity, not just its header.

    Why this exists: :func:`open_or_quarantine` only proves SQLite can
    *parse* the file header. Bit-rot, a torn write that landed inside a
    data page, or deliberate tampering can leave a file that opens fine
    but is structurally corrupt — every later read then fails in a new
    and exciting place. This helper runs ``PRAGMA integrity_check`` after
    the guarded open; if the check reports anything other than ``ok`` the
    file is quarantined (bytes preserved for forensics) and a fresh DB is
    opened instead, with ``recovered=True``.

    Args:
        path:            The SQLite state file.
        current_version:  Schema version this code knows (forwarded to
                         :func:`open_or_quarantine`).
        migrations:      Forward migration map (forwarded).

    Returns:
        ``(conn, recovered)`` — ``recovered`` is True when the file was
        quarantined for *any* reason (unreadable header OR failed
        integrity check) and a fresh DB was opened instead.
    """
    path = Path(path)
    conn, recovered = open_or_quarantine(
        path, current_version=current_version, migrations=migrations
    )
    try:
        rows = conn.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.Error as exc:
        # The check itself blew up: the file is corrupt by definition.
        rows = [(f"integrity_check raised: {exc}",)]
    problems = [str(row[0]) for row in rows if str(row[0]).lower() != "ok"]
    if not problems:
        return conn, recovered
    conn.close()
    detail = "; ".join(problems[:5])
    if len(problems) > 5:
        detail += f" (+{len(problems) - 5} more)"
    quarantine_file(path, reason="integrity-failed", detail=detail)
    conn, _ = open_or_quarantine(
        path, current_version=current_version, migrations=migrations
    )
    return conn, True


def atomic_write_json(path: str | Path, obj: object) -> None:
    """The blessed path for any FUTURE JSON state writer in this repo.

    Writes to a temp file in the same directory, flushes + fsyncs, then
    ``os.replace()`` over the destination. Readers see the old file or
    the new file — never a half-written one (the 19:55 torn-read rule,
    in code). On failure the temp file is removed and no partial file
    is left at the destination.

    No current callers — the helper exists so the rule is executable,
    not just documented. Any future JSON state writer uses this; no
    exceptions for "it's just a small file."
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
