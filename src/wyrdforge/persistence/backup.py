"""wyrdforge.persistence.backup — Cross-store backup & restore (Phase A5).

Before A5 there was no backup story in core at all (roadmap §2.7):
restore *primitives* existed per store, but no consistent bundle of
all three stores, because copying the three DB files live can capture
three different turns. This module is the Phase A closer: ONE
consistent bundle of the world, memory, and bond stores, with a
manifest, integrity verification, and a restore that never destroys
live state on a failed verification.

Quiesce discipline (the honesty at the heart of the design)
------------------------------------------------------------
Cross-store consistency cannot be manufactured by this module alone —
there is no cross-store transaction coordinator in WYRD, and three
separate SQLite files have no shared commit point. What makes a
bundle consistent is a **quiesce**:

    The caller stops the turn pipeline (no TurnLoop turn in flight,
    no store writes from any thread) for the duration of
    :func:`create_backup`. Memory-store callers should also call
    ``PersistentMemoryStore.close()`` first so no thread-local
    connection lingers.

Under that quiesce this module then guarantees, mechanically:

- Each store is opened through the one shared factory
  (:func:`wyrdforge.hardening.state_io.connect_state_db`), its WAL is
  checkpointed (``PRAGMA wal_checkpoint(TRUNCATE)``; a busy checkpoint
  — evidence the quiesce does not hold — aborts the backup with
  :class:`BackupError`), and the copy is taken with SQLite's backup
  API (``Connection.backup``), which produces a transactionally
  consistent snapshot of that store even if a stray reader is active.
- Stores are copied in the fixed order world → memory → bond, so a
  bundle's provenance is deterministic.
- The bundle therefore represents one quiesced moment: every store as
  of the same between-turns boundary. Without the quiesce the bundle
  is still per-store consistent, but the three stores may straddle a
  turn — the docstring, not the code, is where that truth lives, and
  operators must honour it.

Bundle layout
-------------
A bundle is a directory::

    manifest.json     format tag, timestamps, per-store entries
    world.db          SQLite backup-API copies (no -wal/-shm files)
    memory.db
    bond.db

Each manifest entry records the store name, bundle filename, the
store's ``PRAGMA user_version`` schema version, the file's SHA-256,
its byte size, and its ``PRAGMA integrity_check`` result at backup
time. The manifest itself is written with
:func:`wyrdforge.hardening.state_io.atomic_write_json` — the helper
that waited for its first caller.

Restore discipline
------------------
:func:`restore_backup` verifies BEFORE it touches anything:

1. The manifest parses and carries the expected format tag.
2. Every listed bundle file exists, its size and SHA-256 match the
   manifest, its ``integrity_check`` is ``ok``, and its schema
   version is not newer than this code knows for that store (the
   house unknown-version doctrine: never misread a newer schema).

Only then is each verified file staged beside its target
(``<name>.restore-staging-<stamp>``), re-verified in place, and
placed with ``os.replace``. A pre-existing target (plus any
``-wal``/``-shm`` companions) is first moved — never deleted — into
``<target-dir>/quarantine/pre-restore-<stamp>-<name>``, following the
repo's quarantine conventions, so a restore is itself recoverable.
If verification fails at any pre-placement step, live state is
untouched, byte for byte.

A thin CLI rides on the same functions::

    python -m wyrdforge.persistence.backup backup  --state-dir DIR --bundle DIR
    python -m wyrdforge.persistence.backup restore --bundle DIR --state-dir DIR
    python -m wyrdforge.persistence.backup verify  --bundle DIR

The directory form uses the conventional filenames ``world.db`` /
``memory.db`` / ``bond.db``; the library API takes explicit per-store
paths, which is what bridges with caller-chosen filenames should use.

Stdlib only, like the rest of the persistence layer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from wyrdforge.hardening.state_io import atomic_write_json, connect_state_db
from wyrdforge.persistence.bond_store import (
    CURRENT_SCHEMA_VERSION as BOND_SCHEMA_VERSION,
)
from wyrdforge.persistence.memory_store import (
    CURRENT_SCHEMA_VERSION as MEMORY_SCHEMA_VERSION,
)
from wyrdforge.persistence.world_store import (
    CURRENT_SCHEMA_VERSION as WORLD_SCHEMA_VERSION,
)

log = logging.getLogger(__name__)

#: Manifest format tag. Bump only on a breaking bundle-layout change;
#: restore refuses anything else rather than guessing.
BACKUP_FORMAT = "wyrd-backup/1"

MANIFEST_NAME = "manifest.json"

#: The three stores, in fixed backup order. Phase B4 note: the
#: optional event journal (``persistence/event_journal.py``) is
#: deliberately NOT a fourth bundle member — it is an opt-in
#: auxiliary log, not one of the three truth stores, and this set
#: stays exactly three (decision recorded in the journal module's
#: docstring). A deployment that enables journaling and wants it
#: backed up copies the single journal file separately, under the
#: same quiesce discipline.
STORE_NAMES: tuple[str, ...] = ("world", "memory", "bond")

#: Conventional bundle / state-dir filename per store.
STORE_FILENAMES: dict[str, str] = {
    "world": "world.db",
    "memory": "memory.db",
    "bond": "bond.db",
}

#: The schema version this code knows per store (PRAGMA user_version).
KNOWN_SCHEMA_VERSIONS: dict[str, int] = {
    "world": WORLD_SCHEMA_VERSION,
    "memory": MEMORY_SCHEMA_VERSION,
    "bond": BOND_SCHEMA_VERSION,
}


class BackupError(Exception):
    """A backup, verification, or restore step failed safely.

    Raised only in states where no live target has been destroyed:
    verification failures happen before any placement, and placement
    preserves the previous files under ``quarantine/`` first.
    """


@dataclass(frozen=True)
class StoreBackupEntry:
    """One store's line in a bundle manifest."""

    name: str
    file: str
    schema_version: int
    sha256: str
    size_bytes: int
    integrity_check: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "file": self.file,
            "schema_version": self.schema_version,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "integrity_check": self.integrity_check,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "StoreBackupEntry":
        return cls(
            name=str(data["name"]),
            file=str(data["file"]),
            schema_version=int(data["schema_version"]),  # type: ignore[arg-type]
            sha256=str(data["sha256"]),
            size_bytes=int(data["size_bytes"]),  # type: ignore[arg-type]
            integrity_check=str(data["integrity_check"]),
        )


@dataclass(frozen=True)
class BackupManifest:
    """A parsed bundle manifest."""

    format: str
    created_at: str
    package_version: str
    stores: tuple[StoreBackupEntry, ...] = field(default_factory=tuple)

    def entry(self, name: str) -> StoreBackupEntry:
        for entry in self.stores:
            if entry.name == name:
                return entry
        raise BackupError(f"manifest has no entry for store {name!r}")

    def to_dict(self) -> dict[str, object]:
        return {
            "format": self.format,
            "created_at": self.created_at,
            "package_version": self.package_version,
            "stores": [entry.to_dict() for entry in self.stores],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "BackupManifest":
        raw_stores = data.get("stores")
        if not isinstance(raw_stores, list):
            raise BackupError("manifest 'stores' is missing or not a list")
        return cls(
            format=str(data.get("format", "")),
            created_at=str(data.get("created_at", "")),
            package_version=str(data.get("package_version", "")),
            stores=tuple(StoreBackupEntry.from_dict(s) for s in raw_stores),
        )


@dataclass(frozen=True)
class RestoreReport:
    """Outcome of a successful :func:`restore_backup`."""

    bundle_dir: Path
    restored: tuple[str, ...]
    pre_restore_copies: dict[str, Path]


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _probe_db(path: Path) -> tuple[int, str]:
    """(user_version, integrity_check) of *path*, opened read-only.

    Read-only on purpose: probing a bundle file must never mutate the
    bytes its manifest hashes.
    """
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        version_row = conn.execute("PRAGMA user_version").fetchone()
        version = int(version_row[0]) if version_row else 0
        rows = conn.execute("PRAGMA integrity_check").fetchall()
        problems = [str(r[0]) for r in rows if str(r[0]).lower() != "ok"]
        integrity = "ok" if not problems else "; ".join(problems[:5])
        return version, integrity
    finally:
        conn.close()


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _package_version() -> str:
    try:
        import wyrdforge

        return str(wyrdforge.__version__)
    except Exception:
        return "unknown"


def _check_store_names(paths: Mapping[str, str | Path], what: str) -> dict[str, Path]:
    names = set(paths)
    expected = set(STORE_NAMES)
    if names != expected:
        raise BackupError(
            f"{what} must name exactly the stores {sorted(expected)}; "
            f"got {sorted(names)}"
        )
    return {name: Path(paths[name]) for name in STORE_NAMES}


def _backup_one_store(source: Path, dest: Path) -> StoreBackupEntry:
    """Copy one store into the bundle via SQLite's backup API.

    The source is opened through the shared factory, its WAL is
    checkpointed (a busy checkpoint means the quiesce does not hold —
    refuse rather than snapshot a moving target), and the copy is a
    ``Connection.backup`` snapshot: transactionally consistent for
    this store, with no -wal/-shm companions in the bundle.
    """
    name = next(n for n, f in STORE_FILENAMES.items() if f == dest.name)
    if not source.exists():
        raise BackupError(
            f"backup source for store {name!r} does not exist: {source} "
            "(construct the store first — a missing file is not a backup)"
        )
    src = connect_state_db(source)
    try:
        busy, _log_frames, _checkpointed = src.execute(
            "PRAGMA wal_checkpoint(TRUNCATE)"
        ).fetchone()
        if busy:
            raise BackupError(
                f"WAL checkpoint for store {name!r} ({source}) was busy — "
                "the quiesce does not hold; stop all store writers and retry"
            )
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    version, integrity = _probe_db(dest)
    if integrity != "ok":
        raise BackupError(
            f"backup copy of store {name!r} failed integrity_check: {integrity}"
        )
    return StoreBackupEntry(
        name=name,
        file=dest.name,
        schema_version=version,
        sha256=_sha256_file(dest),
        size_bytes=dest.stat().st_size,
        integrity_check=integrity,
    )


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------


def create_backup(
    sources: Mapping[str, str | Path],
    bundle_dir: str | Path,
) -> BackupManifest:
    """Back up all three stores into ONE bundle under a quiesce.

    Args:
        sources:    ``{"world": path, "memory": path, "bond": path}`` —
                    the live store files. The caller owns the quiesce
                    (see the module docstring): no turn in flight, no
                    store writes for the duration of this call.
        bundle_dir: Destination bundle directory (created if needed).
                    Refused if it already holds a manifest — bundles
                    are never silently overwritten.

    Returns:
        The :class:`BackupManifest` that was written into the bundle.

    Raises:
        BackupError: A source is missing, a WAL checkpoint is busy
            (quiesce violated), a copy fails integrity, or the bundle
            directory already holds a backup.
    """
    src_paths = _check_store_names(sources, "backup sources")
    bundle_dir = Path(bundle_dir)
    if (bundle_dir / MANIFEST_NAME).exists():
        raise BackupError(
            f"bundle directory {bundle_dir} already holds a backup "
            f"({MANIFEST_NAME} present) — refusing to overwrite it"
        )
    bundle_dir.mkdir(parents=True, exist_ok=True)
    entries = tuple(
        _backup_one_store(src_paths[name], bundle_dir / STORE_FILENAMES[name])
        for name in STORE_NAMES
    )
    manifest = BackupManifest(
        format=BACKUP_FORMAT,
        created_at=datetime.now(timezone.utc).isoformat(),
        package_version=_package_version(),
        stores=entries,
    )
    atomic_write_json(bundle_dir / MANIFEST_NAME, manifest.to_dict())
    log.info(
        "wyrd backup: bundle written to %s (stores: %s)",
        bundle_dir,
        ", ".join(f"{e.name} v{e.schema_version} {e.size_bytes}B" for e in entries),
    )
    return manifest


def store_paths_in_dir(
    state_dir: str | Path,
    filenames: Mapping[str, str] | None = None,
) -> dict[str, Path]:
    """Per-store paths under one directory, by conventional filename."""
    names = dict(STORE_FILENAMES)
    if filenames:
        names.update(filenames)
    base = Path(state_dir)
    return {name: base / names[name] for name in STORE_NAMES}


def create_backup_from_dir(
    state_dir: str | Path,
    bundle_dir: str | Path,
    filenames: Mapping[str, str] | None = None,
) -> BackupManifest:
    """Directory convenience wrapper over :func:`create_backup`."""
    return create_backup(store_paths_in_dir(state_dir, filenames), bundle_dir)


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def load_manifest(bundle_dir: str | Path) -> BackupManifest:
    """Read and format-check a bundle's manifest (no file checks)."""
    bundle_dir = Path(bundle_dir)
    manifest_path = bundle_dir / MANIFEST_NAME
    if not manifest_path.exists():
        raise BackupError(f"no manifest at {manifest_path} — not a WYRD bundle")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise BackupError(f"manifest at {manifest_path} is unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise BackupError(f"manifest at {manifest_path} is not a JSON object")
    manifest = BackupManifest.from_dict(data)
    if manifest.format != BACKUP_FORMAT:
        raise BackupError(
            f"bundle format {manifest.format!r} is not {BACKUP_FORMAT!r} — "
            "refusing to guess at an unknown bundle layout"
        )
    seen = {entry.name for entry in manifest.stores}
    if seen != set(STORE_NAMES):
        raise BackupError(
            f"manifest stores {sorted(seen)} do not match the expected "
            f"{sorted(STORE_NAMES)}"
        )
    return manifest


def verify_bundle(bundle_dir: str | Path) -> BackupManifest:
    """Verify a bundle end to end WITHOUT touching any live state.

    Per store file: existence, byte size, SHA-256 vs the manifest,
    ``integrity_check == ok``, and schema version not newer than this
    code knows. Any mismatch raises :class:`BackupError`.

    Returns:
        The verified :class:`BackupManifest`.
    """
    bundle_dir = Path(bundle_dir)
    manifest = load_manifest(bundle_dir)
    for entry in manifest.stores:
        path = bundle_dir / entry.file
        if not path.exists():
            raise BackupError(
                f"bundle file for store {entry.name!r} is missing: {path}"
            )
        size = path.stat().st_size
        if size != entry.size_bytes:
            raise BackupError(
                f"bundle file for store {entry.name!r} has size {size}, "
                f"manifest says {entry.size_bytes} — bundle is tampered or torn"
            )
        digest = _sha256_file(path)
        if digest != entry.sha256:
            raise BackupError(
                f"bundle file for store {entry.name!r} fails SHA-256 "
                "verification against the manifest — bundle is tampered or torn"
            )
        try:
            version, integrity = _probe_db(path)
        except sqlite3.Error as exc:
            raise BackupError(
                f"bundle file for store {entry.name!r} cannot be probed: {exc}"
            ) from exc
        if integrity != "ok":
            raise BackupError(
                f"bundle file for store {entry.name!r} fails "
                f"integrity_check: {integrity}"
            )
        if entry.integrity_check != "ok":
            raise BackupError(
                f"manifest records a non-ok integrity_check for store "
                f"{entry.name!r}: {entry.integrity_check!r}"
            )
        if version != entry.schema_version:
            raise BackupError(
                f"bundle file for store {entry.name!r} has schema "
                f"v{version}, manifest says v{entry.schema_version}"
            )
        known = KNOWN_SCHEMA_VERSIONS[entry.name]
        if version > known:
            raise BackupError(
                f"bundle store {entry.name!r} claims schema v{version}, "
                f"newer than this code knows (v{known}) — never misread "
                "a newer schema; upgrade WYRD and retry"
            )
    return manifest


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------


def _preserve_existing(target: Path, stamp: str) -> Path | None:
    """Move an existing target aside under quarantine/; never delete.

    Returns the preserved copy's path, or None when there was nothing
    (no target file and no WAL companions) to preserve.
    """
    companions = [
        target.parent / (target.name + suffix) for suffix in ("-wal", "-shm")
    ]
    if not target.exists() and not any(c.exists() for c in companions):
        return None
    quarantine_dir = target.parent / "quarantine"
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    dest = quarantine_dir / f"pre-restore-{stamp}-{target.name}"
    n = 1
    base = dest
    while dest.exists():
        n += 1
        dest = quarantine_dir / f"{base.name}-{n}"
    if target.exists():
        os.replace(str(target), str(dest))
    for companion in companions:
        if companion.exists():
            suffix = companion.name[len(target.name):]  # "-wal" / "-shm"
            os.replace(str(companion), str(quarantine_dir / (dest.name + suffix)))
    log.warning(
        "wyrd restore: pre-existing state %s preserved at %s before restore",
        target,
        dest,
    )
    return dest


def restore_backup(
    bundle_dir: str | Path,
    targets: Mapping[str, str | Path],
) -> RestoreReport:
    """Restore a verified bundle into *targets*.

    Verification (manifest, hashes, integrity, schema versions) runs
    to completion BEFORE any target is touched — a tampered or
    corrupt bundle leaves live state byte-for-byte untouched. Each
    verified file is then staged beside its target and re-verified
    (hash + integrity) before placement; a pre-existing target is
    preserved under ``quarantine/`` (see the module docstring), never
    silently overwritten and never deleted.

    Args:
        bundle_dir: A bundle written by :func:`create_backup`.
        targets:    ``{"world": path, "memory": path, "bond": path}``
                    — where each store should be restored to.

    Raises:
        BackupError: Any verification or staging failure. Failures
            before placement leave live state untouched; a failure
            mid-placement leaves the preserved pre-restore copies in
            ``quarantine/`` and says so in the error.
    """
    bundle_dir = Path(bundle_dir)
    manifest = verify_bundle(bundle_dir)
    target_paths = _check_store_names(targets, "restore targets")
    stamp = _stamp()

    # Stage + re-verify everything before placing anything.
    staged: dict[str, Path] = {}
    try:
        for entry in manifest.stores:
            target = target_paths[entry.name]
            target.parent.mkdir(parents=True, exist_ok=True)
            staging = target.parent / f"{target.name}.restore-staging-{stamp}"
            n = 1
            base = staging
            while staging.exists():
                n += 1
                staging = target.parent / f"{base.name}-{n}"
            shutil.copyfile(bundle_dir / entry.file, staging)
            if _sha256_file(staging) != entry.sha256:
                raise BackupError(
                    f"staged copy for store {entry.name!r} fails SHA-256 "
                    "re-verification — aborting before any placement; "
                    "live state is untouched"
                )
            _version, integrity = _probe_db(staging)
            if integrity != "ok":
                raise BackupError(
                    f"staged copy for store {entry.name!r} fails "
                    f"integrity_check: {integrity} — aborting before "
                    "any placement; live state is untouched"
                )
            staged[entry.name] = staging
    except BaseException:
        # Nothing has been placed; the staged copies are evidence of a
        # failed restore, so preserve them under quarantine/ rather
        # than deleting them.
        for staging in staged.values():
            try:
                quarantine_dir = staging.parent / "quarantine"
                quarantine_dir.mkdir(parents=True, exist_ok=True)
                os.replace(
                    str(staging),
                    str(quarantine_dir / f"failed-restore-{stamp}-{staging.name}"),
                )
            except OSError:
                pass
        raise

    # Place: preserve the incumbent, then swap the verified copy in.
    pre_restore: dict[str, Path] = {}
    placed: list[str] = []
    try:
        for entry in manifest.stores:
            target = target_paths[entry.name]
            preserved = _preserve_existing(target, stamp)
            if preserved is not None:
                pre_restore[entry.name] = preserved
            os.replace(str(staged[entry.name]), str(target))
            placed.append(entry.name)
    except OSError as exc:
        raise BackupError(
            f"restore failed mid-placement after placing {placed}: {exc}. "
            "Pre-restore copies of every replaced target are preserved "
            "under each target's quarantine/ directory."
        ) from exc
    log.info(
        "wyrd restore: bundle %s restored (stores: %s)",
        bundle_dir,
        ", ".join(placed),
    )
    return RestoreReport(
        bundle_dir=bundle_dir,
        restored=tuple(placed),
        pre_restore_copies=pre_restore,
    )


def restore_backup_to_dir(
    bundle_dir: str | Path,
    state_dir: str | Path,
    filenames: Mapping[str, str] | None = None,
) -> RestoreReport:
    """Directory convenience wrapper over :func:`restore_backup`."""
    return restore_backup(bundle_dir, store_paths_in_dir(state_dir, filenames))


# ---------------------------------------------------------------------------
# CLI — python -m wyrdforge.persistence.backup {backup|restore|verify}
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wyrdforge.persistence.backup",
        description="WYRD cross-store backup & restore (Phase A5).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_backup = sub.add_parser("backup", help="back up all three stores into a bundle")
    p_backup.add_argument("--state-dir", required=True)
    p_backup.add_argument("--bundle", required=True)

    p_restore = sub.add_parser("restore", help="verify and restore a bundle")
    p_restore.add_argument("--bundle", required=True)
    p_restore.add_argument("--state-dir", required=True)

    p_verify = sub.add_parser("verify", help="verify a bundle without restoring")
    p_verify.add_argument("--bundle", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            manifest = create_backup_from_dir(args.state_dir, args.bundle)
            print(f"backup written: {args.bundle} ({len(manifest.stores)} stores)")
        elif args.command == "restore":
            report = restore_backup_to_dir(args.bundle, args.state_dir)
            print(f"restored: {', '.join(report.restored)} -> {args.state_dir}")
        elif args.command == "verify":
            manifest = verify_bundle(args.bundle)
            print(
                f"bundle ok: {manifest.format} created {manifest.created_at} "
                f"({len(manifest.stores)} stores)"
            )
    except BackupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
