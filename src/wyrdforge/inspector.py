"""wyrdforge.inspector — the supported world inspector (Phase E4).

Roadmap §3.8/§2.6: before E4, inspection lived outside the core —
``tools/wyrd_tui.py`` (a genuine Rich/urllib TUI) spoke only HTTP,
depended on an undeclared package, and there was no state diff, no
entity timeline, no contradiction viewer, and no way to read the
evidence of a failure after a restart. This module is the inspector
as an engine surface: four read-only features over real engine
stores, plus the TUI promoted into the package beside it
(:mod:`wyrdforge.inspector_tui`).

The four features
-----------------
1. **State diff** — :func:`snapshot_world` captures a :class:`World`
   (live, or restored through :class:`WorldStore`) as a plain-data
   :class:`WorldSnapshot`; :func:`diff_snapshots` reports added /
   removed entities and, per surviving entity, tag / active changes
   and added / removed / changed components with per-field old→new
   values. Snapshots round-trip through JSON (:meth:`WorldSnapshot.
   to_dict` / :meth:`WorldSnapshot.from_dict`, :func:`save_snapshot`
   / :func:`load_snapshot`) so a diff can span processes and time:
   snapshot now, diff after the restart.
2. **Entity timeline** — :func:`entity_timeline` reads the Phase B4
   durable :class:`EventJournal` and returns, in ``journal_seq``
   order, every entry whose envelope names the entity. "Names" is
   the journal's own purge semantics (Phase C1): an exact structured
   string value anywhere in the envelope — a longer string merely
   *containing* the id (a free-text mention) does not count, so a
   timeline never invents a connection the record does not make.
3. **Contradiction viewer** — :func:`contradiction_views` renders
   the :class:`ContradictionDetector`'s records (open by default;
   ``include_resolved=True`` for the whole ledger) as
   :class:`ContradictionView` rows, resolving each claim's fact
   (subject / key / value) through the memory store when the claim
   record is a canonical fact. A claim that no longer resolves is
   shown by id with ``None`` fact fields — never invented.
4. **Durable dead-letter archaeology** — :func:`dead_letter_archaeology`
   reads the PERSISTED dead letters in the B4 journal file, not the
   bus's in-memory queue: the evidence survives ``EventBus.close()``
   and process restart, which is the whole point of archaeology.
   When a live bus is supplied, the report also counts its volatile
   queue so the two surfaces can be told apart.

Rich dependency decision (recorded, Phase E4)
---------------------------------------------
Core install stays lean — ``pydantic`` + ``pyyaml`` only, the
standing packaging policy. This module is stdlib + wyrdforge only
and every feature works without Rich, including the plain-text CLI
below. Rich is declared as the optional ``inspector`` extra in
``pyproject.toml`` (``pip install wyrdforge[inspector]``): it is
needed only by the TUI presentation layer, which already degraded
gracefully without it (a simple-CLI fallback) before E4 — that
graceful degradation is precisely why Rich does not belong in the
core dependency set.

Read-only doctrine
------------------
The inspector never writes to any store. Snapshots are projections
of live objects taken under ``world.lock`` (Phase B1 discipline);
the journal and memory store are only ever read through their own
read surfaces. No existing public signature changes; everything
here is additive.

CLI
---
``python -m wyrdforge.inspector`` (installed as ``wyrd-inspect``)::

    snapshot      --world-db world.db --world-id ID --out snap.json
    diff          BEFORE.json AFTER.json
    timeline      --journal journal.db --entity ENTITY_ID
    contradictions --memory memory.db [--all]
    dead-letters  --journal journal.db [--topic T] [--error-type E]
    tui           [--host H] [--port P] [--world YAML] [--offline]
                  [--journal journal.db] [--memory memory.db]
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wyrdforge.ecs.world import World
    from wyrdforge.persistence.event_journal import EventJournal, JournalEntry
    from wyrdforge.persistence.memory_store import PersistentMemoryStore
    from wyrdforge.persistence.world_store import WorldStore
    from wyrdforge.runtime.events import EventBus

__all__ = [
    "ComponentChange",
    "ContradictionView",
    "DeadLetterReport",
    "EntityChange",
    "EntitySnapshot",
    "WorldDiff",
    "WorldSnapshot",
    "contradiction_summary",
    "contradiction_views",
    "dead_letter_archaeology",
    "diff_snapshots",
    "diff_worlds",
    "entity_timeline",
    "format_contradictions",
    "format_dead_letters",
    "format_diff",
    "format_timeline",
    "load_snapshot",
    "main",
    "save_snapshot",
    "snapshot_from_store",
    "snapshot_world",
]


# ---------------------------------------------------------------------------
# 1. State snapshots + diff
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EntitySnapshot:
    """One entity as plain data: tags, active flag, component payloads.

    Component payloads are the components' own ``model_dump(mode=
    "json")`` output, verbatim — including their ``created_at`` /
    ``updated_at`` stamps, so a component that was merely touched
    diffs as changed on those fields. That is honest (the persisted
    bytes did change); callers who care only about domain fields can
    read :attr:`ComponentChange.fields` and ignore the stamps.

    Consequence, stated plainly: diffs are meaningful between
    snapshots of ONE world lineage (snapshot → time passes →
    snapshot; a store restore preserves payloads exactly). Two
    independently CONSTRUCTED worlds, even from identical code,
    differ in every component's creation stamps — bookkeeping
    noise, not state change.
    """

    entity_id: str
    tags: tuple[str, ...]
    active: bool
    components: dict[str, dict]

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "tags": list(self.tags),
            "active": self.active,
            "components": self.components,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EntitySnapshot":
        return cls(
            entity_id=str(data["entity_id"]),
            tags=tuple(data.get("tags", [])),
            active=bool(data.get("active", True)),
            components=dict(data.get("components", {})),
        )


@dataclass(frozen=True)
class WorldSnapshot:
    """A whole world as plain data — the diff/snapshot currency."""

    world_id: str
    world_name: str
    entities: dict[str, EntitySnapshot]

    def to_dict(self) -> dict:
        return {
            "format": "wyrd-snapshot/1",
            "world_id": self.world_id,
            "world_name": self.world_name,
            "entities": {
                eid: ent.to_dict() for eid, ent in sorted(self.entities.items())
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorldSnapshot":
        return cls(
            world_id=str(data["world_id"]),
            world_name=str(data.get("world_name", "")),
            entities={
                str(eid): EntitySnapshot.from_dict(ent)
                for eid, ent in data.get("entities", {}).items()
            },
        )


def snapshot_world(world: "World") -> WorldSnapshot:
    """Capture a live :class:`World` as a :class:`WorldSnapshot`.

    Taken under ``world.lock`` (Phase B1 discipline) using only the
    World's public read surface, INACTIVE entities included — an
    inspector that hid deactivated entities would lie by omission.
    """
    with world.lock:
        entities: dict[str, EntitySnapshot] = {}
        for entity in world.all_entities(active_only=False):
            components = {
                comp.component_type: comp.model_dump(mode="json")
                for comp in world.get_all_components(entity.entity_id)
            }
            entities[entity.entity_id] = EntitySnapshot(
                entity_id=entity.entity_id,
                tags=tuple(sorted(entity.tags)),
                active=bool(entity.active),
                components=components,
            )
        return WorldSnapshot(
            world_id=world.world_id,
            world_name=world.world_name,
            entities=entities,
        )


def snapshot_from_store(store: "WorldStore", world_id: str) -> WorldSnapshot:
    """Snapshot a persisted world: restore it, then snapshot it.

    Restoration goes through :meth:`WorldStore.load`, so the A4 load
    honesty rules apply exactly as for any other load.
    """
    return snapshot_world(store.load(world_id))


def save_snapshot(snapshot: WorldSnapshot, path: str | Path) -> None:
    """Write a snapshot as JSON (sorted, indented — diff-friendly)."""
    Path(path).write_text(
        json.dumps(snapshot.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_snapshot(path: str | Path) -> WorldSnapshot:
    """Read a snapshot written by :func:`save_snapshot`."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("format") != "wyrd-snapshot/1":
        raise ValueError(f"{path}: not a wyrd-snapshot/1 file")
    return WorldSnapshot.from_dict(data)


@dataclass(frozen=True)
class ComponentChange:
    """One component whose payload differs between two snapshots."""

    component_type: str
    before: dict
    after: dict
    #: field name -> (old value, new value); a field present on only
    #: one side pairs its value with None on the other.
    fields: dict[str, tuple[object, object]]


@dataclass(frozen=True)
class EntityChange:
    """Everything that changed about one surviving entity."""

    entity_id: str
    tags_added: tuple[str, ...] = ()
    tags_removed: tuple[str, ...] = ()
    active_before: bool | None = None
    active_after: bool | None = None
    components_added: tuple[str, ...] = ()
    components_removed: tuple[str, ...] = ()
    components_changed: tuple[ComponentChange, ...] = ()

    @property
    def changed(self) -> bool:
        return bool(
            self.tags_added
            or self.tags_removed
            or self.active_before is not None
            or self.components_added
            or self.components_removed
            or self.components_changed
        )


@dataclass(frozen=True)
class WorldDiff:
    """The difference between two snapshots of (usually) one world."""

    world_id: str
    added_entities: tuple[str, ...]
    removed_entities: tuple[str, ...]
    entity_changes: tuple[EntityChange, ...]

    @property
    def is_empty(self) -> bool:
        return not (
            self.added_entities or self.removed_entities or self.entity_changes
        )

    def summary(self) -> dict[str, int]:
        return {
            "added_entities": len(self.added_entities),
            "removed_entities": len(self.removed_entities),
            "changed_entities": len(self.entity_changes),
            "components_added": sum(
                len(c.components_added) for c in self.entity_changes
            ),
            "components_removed": sum(
                len(c.components_removed) for c in self.entity_changes
            ),
            "components_changed": sum(
                len(c.components_changed) for c in self.entity_changes
            ),
        }


def diff_snapshots(before: WorldSnapshot, after: WorldSnapshot) -> WorldDiff:
    """Diff two snapshots. Pure function over plain data.

    The snapshots are expected to be of the same world; the diff's
    ``world_id`` is the AFTER snapshot's. Entity order in every
    result tuple is sorted by entity id, so diffs are deterministic.
    """
    before_ids = set(before.entities)
    after_ids = set(after.entities)
    changes: list[EntityChange] = []
    for eid in sorted(before_ids & after_ids):
        b = before.entities[eid]
        a = after.entities[eid]
        comp_changes: list[ComponentChange] = []
        for ctype in sorted(set(b.components) & set(a.components)):
            if b.components[ctype] == a.components[ctype]:
                continue
            fields: dict[str, tuple[object, object]] = {}
            for key in sorted(set(b.components[ctype]) | set(a.components[ctype])):
                old = b.components[ctype].get(key)
                new = a.components[ctype].get(key)
                if old != new:
                    fields[key] = (old, new)
            comp_changes.append(
                ComponentChange(
                    component_type=ctype,
                    before=b.components[ctype],
                    after=a.components[ctype],
                    fields=fields,
                )
            )
        change = EntityChange(
            entity_id=eid,
            tags_added=tuple(sorted(set(a.tags) - set(b.tags))),
            tags_removed=tuple(sorted(set(b.tags) - set(a.tags))),
            active_before=b.active if b.active != a.active else None,
            active_after=a.active if b.active != a.active else None,
            components_added=tuple(
                sorted(set(a.components) - set(b.components))
            ),
            components_removed=tuple(
                sorted(set(b.components) - set(a.components))
            ),
            components_changed=tuple(comp_changes),
        )
        if change.changed:
            changes.append(change)
    return WorldDiff(
        world_id=after.world_id,
        added_entities=tuple(sorted(after_ids - before_ids)),
        removed_entities=tuple(sorted(before_ids - after_ids)),
        entity_changes=tuple(changes),
    )


def diff_worlds(before: "World", after: "World") -> WorldDiff:
    """Diff two live worlds (snapshots both, then diffs them)."""
    return diff_snapshots(snapshot_world(before), snapshot_world(after))


# ---------------------------------------------------------------------------
# 2. Entity timeline (Phase B4 durable journal)
# ---------------------------------------------------------------------------


def _names_exact(node: object, needle: str) -> bool:
    """True when *needle* is an exact string value inside *node*.

    Recursive over dicts (keys and values) and lists/tuples — the
    Phase C1 / journal-purge semantics: a longer string merely
    containing the id is a free-text mention and does NOT match.
    """
    if isinstance(node, str):
        return node == needle
    if isinstance(node, dict):
        return any(
            _names_exact(key, needle) or _names_exact(value, needle)
            for key, value in node.items()
        )
    if isinstance(node, (list, tuple)):
        return any(_names_exact(item, needle) for item in node)
    return False


def entity_timeline(
    journal: "EventJournal", entity_id: str
) -> list["JournalEntry"]:
    """The journal entries naming *entity_id*, in journal order.

    Reads the durable journal (never a bus's volatile replay ring),
    so the timeline survives restarts exactly as the journal does.
    An entry names the entity when its stored envelope carries the
    id as an exact structured value — the payload conventions the
    engine itself uses (``{"entity_id": ...}`` from World events,
    participant lists, source fields) all match; free-text mentions
    do not.
    """
    return [
        entry
        for entry in journal.entries()
        if _names_exact(entry.envelope, entity_id)
    ]


# ---------------------------------------------------------------------------
# 3. Contradiction viewer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContradictionView:
    """One contradiction record, with its claims resolved for display."""

    contradiction_id: str
    title: str
    reason: str
    resolution_state: str
    preferred_record_id: str | None
    claim_a_record_id: str
    claim_b_record_id: str
    #: (subject, key, value) of each claim when the claim record
    #: resolves to a canonical fact in the store; None otherwise.
    claim_a_fact: tuple[str, str, str] | None
    claim_b_fact: tuple[str, str, str] | None
    created_at: str


def _fact_triple(store: "PersistentMemoryStore", record_id: str):
    from wyrdforge.models.memory import CanonicalFactRecord

    record = store.get(record_id)
    if not isinstance(record, CanonicalFactRecord):
        return None
    payload = record.content.structured_payload
    return (payload.fact_subject_id, payload.fact_key, payload.fact_value)


def contradiction_views(
    store: "PersistentMemoryStore", *, include_resolved: bool = False
) -> list[ContradictionView]:
    """Contradiction records as display rows, in store order.

    ``include_resolved=False`` (the operator's default view) lists
    exactly what :meth:`ContradictionDetector.find_open_contradictions`
    lists — the detector's own output, unresolved only. With
    ``include_resolved=True`` the whole contradiction ledger in the
    memory store is listed (open, resolved, quarantined).
    """
    from wyrdforge.models.memory import ContradictionRecord

    if include_resolved:
        records = [
            r
            for r in store.list_by_record_type("contradiction")
            if isinstance(r, ContradictionRecord)
        ]
    else:
        from wyrdforge.services.contradiction_detector import ContradictionDetector

        records = ContradictionDetector(store).find_open_contradictions()
    views: list[ContradictionView] = []
    for record in records:
        payload = record.content.structured_payload
        views.append(
            ContradictionView(
                contradiction_id=record.record_id,
                title=record.content.title,
                reason=payload.contradiction_reason,
                resolution_state=payload.resolution_state,
                preferred_record_id=payload.preferred_record_id,
                claim_a_record_id=payload.claim_a_record_id,
                claim_b_record_id=payload.claim_b_record_id,
                claim_a_fact=_fact_triple(store, payload.claim_a_record_id),
                claim_b_fact=_fact_triple(store, payload.claim_b_record_id),
                created_at=record.audit.created_at.isoformat(),
            )
        )
    return views


def contradiction_summary(views: list[ContradictionView]) -> dict[str, int]:
    """Counts by resolution state over a view list."""
    summary: dict[str, int] = {}
    for view in views:
        summary[view.resolution_state] = summary.get(view.resolution_state, 0) + 1
    return summary


# ---------------------------------------------------------------------------
# 4. Durable dead-letter archaeology
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeadLetterReport:
    """The persisted dead letters in one journal file.

    ``letters`` are the journal's durable entries (bus shape plus a
    ``dead_letter_id``); ``summary`` is the journal's own
    ``{topic: {error_type: count}}`` grouping, computed AFTER any
    topic/error filter is applied. ``volatile_count`` is the live
    bus's in-memory queue length when a bus was supplied, else None
    — the contrast is the point: the volatile queue dies with the
    process, these letters do not.
    """

    letters: tuple[dict, ...]
    summary: dict[str, dict[str, int]]
    volatile_count: int | None = None

    @property
    def total(self) -> int:
        return len(self.letters)


def dead_letter_archaeology(
    journal: "EventJournal",
    *,
    topic: str | None = None,
    error_type: str | None = None,
    bus: "EventBus | None" = None,
) -> DeadLetterReport:
    """Read the PERSISTED dead letters from a journal.

    The journal may be a fresh instance over an old file — that is
    the archaeology case: a previous process failed, restarted, and
    its in-memory queue is gone, but the letters it persisted are
    still here. Filters are exact matches on the letter's topic /
    error_type.
    """
    letters = [
        letter
        for letter in journal.dead_letters()
        if (topic is None or letter["topic"] == topic)
        and (error_type is None or letter["error_type"] == error_type)
    ]
    summary: dict[str, dict[str, int]] = {}
    for letter in letters:
        per_topic = summary.setdefault(letter["topic"], {})
        per_topic[letter["error_type"]] = per_topic.get(letter["error_type"], 0) + 1
    return DeadLetterReport(
        letters=tuple(letters),
        summary=summary,
        volatile_count=(len(bus.dead_letters()) if bus is not None else None),
    )


# ---------------------------------------------------------------------------
# Plain-text rendering (CLI + TUI share these; no Rich needed)
# ---------------------------------------------------------------------------


def format_diff(diff: WorldDiff) -> str:
    if diff.is_empty:
        return f"world {diff.world_id}: no differences"
    lines = [f"world {diff.world_id}:"]
    for eid in diff.added_entities:
        lines.append(f"  + entity {eid}")
    for eid in diff.removed_entities:
        lines.append(f"  - entity {eid}")
    for change in diff.entity_changes:
        lines.append(f"  ~ entity {change.entity_id}")
        for tag in change.tags_added:
            lines.append(f"      + tag {tag}")
        for tag in change.tags_removed:
            lines.append(f"      - tag {tag}")
        if change.active_before is not None:
            lines.append(
                f"      active: {change.active_before} -> {change.active_after}"
            )
        for ctype in change.components_added:
            lines.append(f"      + component {ctype}")
        for ctype in change.components_removed:
            lines.append(f"      - component {ctype}")
        for comp in change.components_changed:
            for fname, (old, new) in comp.fields.items():
                lines.append(f"      {comp.component_type}.{fname}: {old!r} -> {new!r}")
    return "\n".join(lines)


def format_timeline(entries: list["JournalEntry"], entity_id: str) -> str:
    if not entries:
        return f"no journal entries name {entity_id!r}"
    lines = [f"timeline for {entity_id} ({len(entries)} entries):"]
    for entry in entries:
        lines.append(
            f"  #{entry.journal_seq} [{entry.kind}] {entry.topic} "
            f"(bus seq {entry.bus_seq}, {entry.issued_at or 'no timestamp'})"
        )
    return "\n".join(lines)


def format_contradictions(views: list[ContradictionView]) -> str:
    if not views:
        return "no contradictions"
    lines = [f"{len(views)} contradiction(s):"]
    for view in views:
        lines.append(f"  {view.contradiction_id} [{view.resolution_state}] {view.title}")
        lines.append(f"    {view.reason}")
        for label, claim_id, fact in (
            ("claim A", view.claim_a_record_id, view.claim_a_fact),
            ("claim B", view.claim_b_record_id, view.claim_b_fact),
        ):
            if fact is not None:
                subject, key, value = fact
                lines.append(f"    {label} {claim_id}: {subject}.{key} = {value!r}")
            else:
                lines.append(f"    {label} {claim_id}: (claim record not a stored fact)")
        if view.preferred_record_id:
            lines.append(f"    preferred: {view.preferred_record_id}")
    return "\n".join(lines)


def format_dead_letters(report: DeadLetterReport) -> str:
    if report.total == 0:
        return "no persisted dead letters"
    lines = [f"{report.total} persisted dead letter(s):"]
    for letter in report.letters:
        lines.append(
            f"  #{letter['dead_letter_id']} [{letter['topic']}] "
            f"{letter['error_type']}: {letter['message']} "
            f"(subscriber {letter['subscriber'] or '?'}, bus seq {letter['seq']}, "
            f"{letter['timestamp'] or 'no timestamp'})"
        )
    if report.volatile_count is not None:
        lines.append(
            f"  (the live bus currently holds {report.volatile_count} "
            "volatile letter(s), which a restart would erase)"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI — the backup module's main() pattern (Phase A5/E2 precedent)
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wyrd-inspect",
        description="WYRD world inspector (Phase E4) — diff, timeline, "
        "contradictions, durable dead letters, and the TUI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_snap = sub.add_parser("snapshot", help="snapshot a persisted world to JSON")
    p_snap.add_argument("--world-db", required=True)
    p_snap.add_argument("--world-id", required=True)
    p_snap.add_argument("--out", required=True)

    p_diff = sub.add_parser("diff", help="diff two snapshot JSON files")
    p_diff.add_argument("before")
    p_diff.add_argument("after")

    p_tl = sub.add_parser("timeline", help="an entity's durable journal timeline")
    p_tl.add_argument("--journal", required=True)
    p_tl.add_argument("--entity", required=True)

    p_con = sub.add_parser("contradictions", help="view contradiction records")
    p_con.add_argument("--memory", required=True)
    p_con.add_argument(
        "--all", action="store_true", help="include resolved/quarantined records"
    )

    p_dl = sub.add_parser("dead-letters", help="read persisted dead letters")
    p_dl.add_argument("--journal", required=True)
    p_dl.add_argument("--topic")
    p_dl.add_argument("--error-type")

    p_tui = sub.add_parser("tui", help="launch the inspector TUI")
    p_tui.add_argument("--host", default="localhost")
    p_tui.add_argument("--port", type=int, default=8765)
    p_tui.add_argument("--world", default="")
    p_tui.add_argument("--offline", action="store_true")
    p_tui.add_argument("--timeout", type=int, default=5)
    p_tui.add_argument("--journal", default="")
    p_tui.add_argument("--memory", default="")

    args = parser.parse_args(argv)
    try:
        if args.command == "snapshot":
            from wyrdforge.persistence.world_store import WorldStore

            snap = snapshot_from_store(WorldStore(args.world_db), args.world_id)
            save_snapshot(snap, args.out)
            print(
                f"snapshot written: {args.out} "
                f"({len(snap.entities)} entities, world {snap.world_id})"
            )
        elif args.command == "diff":
            diff = diff_snapshots(load_snapshot(args.before), load_snapshot(args.after))
            print(format_diff(diff))
        elif args.command == "timeline":
            from wyrdforge.persistence.event_journal import EventJournal

            entries = entity_timeline(EventJournal(args.journal), args.entity)
            print(format_timeline(entries, args.entity))
        elif args.command == "contradictions":
            from wyrdforge.persistence.memory_store import PersistentMemoryStore

            views = contradiction_views(
                PersistentMemoryStore(args.memory), include_resolved=args.all
            )
            print(format_contradictions(views))
        elif args.command == "dead-letters":
            from wyrdforge.persistence.event_journal import EventJournal

            report = dead_letter_archaeology(
                EventJournal(args.journal),
                topic=args.topic,
                error_type=args.error_type,
            )
            print(format_dead_letters(report))
        elif args.command == "tui":
            from wyrdforge.inspector_tui import run_from_args

            run_from_args(args)
    except (KeyError, ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
