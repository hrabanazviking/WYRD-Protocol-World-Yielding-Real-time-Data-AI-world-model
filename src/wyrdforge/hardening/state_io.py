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
from typing import Callable

log = logging.getLogger(__name__)


class CorruptStateError(Exception):
    """A state file exists but cannot be opened, read, or migrated.

    Attributes:
        path: the state file that failed.
        reason: one of ``"not-a-database"`` | ``"integrity-failed"`` |
            ``"unknown-version"`` | ``"unmigratable"``.
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
                    detail: str = "") -> Path:
    """Move a corrupt state file aside for later inspection.

    The file (plus any SQLite ``-wal`` / ``-shm`` companions) is moved to
    ``<parent>/quarantine/<stem>-YYYYMMDD-HHMMSS<ext>`` and announced
    exactly once per path per process via ``logging.warning`` — the
    warning names the reason so the announcement is informative, not
    just noise.

    Quarantine preserves the bytes — it never deletes. A name collision
    (same second) gets a ``-2``, ``-3`` suffix rather than overwriting.
    """
    path = Path(path)
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
    return dest


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
        conn = sqlite3.connect(str(path))
        # Cheap smoke: SELECT 1 is a no-op, but reading user_version
        # forces SQLite to parse the database header — that is what
        # actually rejects garbage bytes.
        conn.execute("SELECT 1").fetchone()
        version = _read_user_version(conn)
        conn.execute("PRAGMA journal_mode=WAL")
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
