"""Phase E4 — world inspector pinning tests.

Before E4, inspection lived outside the core: ``tools/wyrd_tui.py``
spoke only HTTP, Rich was an undeclared dependency, and there was no
state diff, no entity timeline, no contradiction viewer, and no way
to read a failure's evidence after a restart (roadmap §3.8/§2.6).
These tests pin the supported inspector's contract:

(a) state diff detects added / removed / changed entities and
    added / removed / changed components (with per-field old→new),
    over live worlds, over WorldStore-restored snapshots, and over
    the JSON snapshot round-trip the CLI diffs;
(b) the entity timeline returns exactly the durable journal entries
    naming the entity, in journal_seq order — exact structured
    matches only, free-text mentions excluded;
(c) the contradiction viewer lists the detector's real output with
    claim facts resolved through the store, open-only by default
    and the full ledger with include_resolved;
(d) dead-letter archaeology reads the PERSISTED letters from a
    fresh journal instance over the same file (a simulated
    restart), after EventBus.close() erased the volatile queue;
(e) the promotion surface: the TUI lives in the package, the tools
    path is a working shim, Rich is declared as the optional
    ``inspector`` extra (never a core dependency), and the
    wyrd-inspect console scripts are declared.
"""
from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path

import pytest

from wyrdforge.ecs.components.character import HealthComponent
from wyrdforge.ecs.components.identity import NameComponent, StatusComponent
from wyrdforge.ecs.world import World
from wyrdforge.inspector import (
    contradiction_summary,
    contradiction_views,
    dead_letter_archaeology,
    diff_snapshots,
    diff_worlds,
    entity_timeline,
    load_snapshot,
    main as inspector_main,
    save_snapshot,
    snapshot_from_store,
    snapshot_world,
)
from wyrdforge.persistence.event_journal import EventJournal
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.persistence.world_store import WorldStore
from wyrdforge.runtime.events import EventBus
from wyrdforge.services.contradiction_detector import ContradictionDetector
from wyrdforge.services.writeback_engine import WritebackEngine

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _world_v1() -> World:
    world = World(world_id="insp-world", world_name="Inspector World")
    world.create_entity(entity_id="gunnar", tags={"npc"})
    world.add_component("gunnar", NameComponent(entity_id="gunnar", name="Gunnar"))
    world.add_component("gunnar", HealthComponent(entity_id="gunnar", hp=100.0))
    world.create_entity(entity_id="sigrid", tags={"npc"})
    world.add_component("sigrid", NameComponent(entity_id="sigrid", name="Sigrid"))
    world.create_entity(entity_id="old_one", tags=set())
    return world


def _mutate_to_v2(world: World) -> None:
    """Apply one of every change kind to *world* in place."""
    world.remove_entity("old_one")                                  # removed entity
    world.create_entity(entity_id="new_one", tags={"arrival"})      # added entity
    gunnar_health = world.get_component_typed("gunnar", "health", HealthComponent)
    assert gunnar_health is not None
    gunnar_health.take_damage(30.0)                                 # changed component
    world.tag_entity("gunnar", "wounded")                           # tag added
    world.add_component(                                            # component added
        "sigrid", StatusComponent(entity_id="sigrid", state="alert")
    )
    world.remove_component("gunnar", "name")                        # component removed
    sigrid = world.get_entity("sigrid")
    assert sigrid is not None
    sigrid.deactivate()                                             # active flipped


def _world_v2() -> World:
    world = _world_v1()
    _mutate_to_v2(world)
    return world


def _lineage(tmp_path: Path):
    """(before, after) snapshots of ONE world lineage.

    The diff's real use: snapshot a world, let time pass, snapshot
    again. The after-world is restored through the store from the
    before-world's own save, so unchanged components keep their
    exact payloads (stamps included) and the diff shows only the
    mutations — two independently CONSTRUCTED worlds would differ
    in every component's creation stamps, which is bookkeeping
    noise, not state change.
    """
    store = WorldStore(tmp_path / "lineage.db")
    store.save(_world_v1())
    before = snapshot_from_store(store, "insp-world")
    world2 = store.load("insp-world")
    _mutate_to_v2(world2)
    return before, snapshot_world(world2)


def _journal_with_bus(tmp_path: Path) -> tuple[EventJournal, EventBus]:
    journal = EventJournal(tmp_path / "journal.db")
    bus = EventBus(journal=journal)
    for topic in ("world.entity_created", "world.component_added", "chat.message"):
        bus.register_topic(topic)
    return journal, bus


# ---------------------------------------------------------------------------
# (a) State diff
# ---------------------------------------------------------------------------


def test_diff_detects_every_change_kind(tmp_path):
    before, after = _lineage(tmp_path)
    diff = diff_snapshots(before, after)
    assert not diff.is_empty
    assert diff.added_entities == ("new_one",)
    assert diff.removed_entities == ("old_one",)
    changes = {c.entity_id: c for c in diff.entity_changes}
    assert set(changes) == {"gunnar", "sigrid"}

    gunnar = changes["gunnar"]
    assert gunnar.tags_added == ("wounded",)
    assert gunnar.components_removed == ("name",)
    assert [c.component_type for c in gunnar.components_changed] == ["health"]
    hp_change = gunnar.components_changed[0].fields["hp"]
    assert hp_change == (100.0, 70.0)

    sigrid = changes["sigrid"]
    assert sigrid.components_added == ("status",)
    assert sigrid.active_before is True and sigrid.active_after is False

    summary = diff.summary()
    assert summary["added_entities"] == 1 and summary["removed_entities"] == 1
    assert summary["components_changed"] == 1


def test_diff_of_identical_worlds_is_empty():
    world = _world_v1()
    assert snapshot_world(world) == snapshot_world(world)
    diff = diff_snapshots(snapshot_world(world), snapshot_world(world))
    assert diff.is_empty
    assert diff.summary()["changed_entities"] == 0


def test_snapshot_round_trips_through_world_store(tmp_path):
    store = WorldStore(tmp_path / "world.db")
    store.save(_world_v1())
    before = snapshot_from_store(store, "insp-world")
    store.save(_world_v2())
    after = snapshot_from_store(store, "insp-world")
    diff = diff_snapshots(before, after)
    assert diff.added_entities == ("new_one",)
    assert diff.removed_entities == ("old_one",)
    # The snapshot includes INACTIVE entities (sigrid was deactivated).
    assert "sigrid" in after.entities and after.entities["sigrid"].active is False


def test_snapshot_json_round_trip_and_cli_diff(tmp_path, capsys):
    before, after = _lineage(tmp_path)
    snap_path = tmp_path / "before.json"
    save_snapshot(before, snap_path)
    loaded = load_snapshot(snap_path)
    assert loaded == before

    after_path = tmp_path / "after.json"
    save_snapshot(after, after_path)
    assert inspector_main(["diff", str(snap_path), str(after_path)]) == 0
    out = capsys.readouterr().out
    assert "+ entity new_one" in out
    assert "- entity old_one" in out
    assert "health.hp: 100.0 -> 70.0" in out


def test_snapshot_cli_from_world_db(tmp_path, capsys):
    store = WorldStore(tmp_path / "world.db")
    store.save(_world_v1())
    out_path = tmp_path / "snap.json"
    rc = inspector_main(
        ["snapshot", "--world-db", str(tmp_path / "world.db"),
         "--world-id", "insp-world", "--out", str(out_path)]
    )
    assert rc == 0
    assert "3 entities" in capsys.readouterr().out
    assert load_snapshot(out_path).world_id == "insp-world"


# ---------------------------------------------------------------------------
# (b) Entity timeline on the durable journal
# ---------------------------------------------------------------------------


def test_timeline_returns_entity_entries_in_journal_order(tmp_path):
    journal, bus = _journal_with_bus(tmp_path)
    bus.publish("world.entity_created", {"entity_id": "gunnar", "tags": ["npc"]},
                source="ecs.world")
    bus.publish("chat.message", {"speaker": "sigrid", "text": "hail"},
                source="chat")
    bus.publish("world.component_added",
                {"entity_id": "gunnar", "component_type": "health"},
                source="ecs.world")
    bus.publish("chat.message", {"participants": ["gunnar", "sigrid"]},
                source="chat")
    # A free-text MENTION of the id is not a structured naming — the
    # timeline must not claim this entry is about gunnar.
    bus.publish("chat.message", {"text": "gunnar was here yesterday"},
                source="chat")

    entries = entity_timeline(journal, "gunnar")
    assert [e.journal_seq for e in entries] == [1, 3, 4]
    assert [e.topic for e in entries] == [
        "world.entity_created", "world.component_added", "chat.message",
    ]
    assert entity_timeline(journal, "nobody") == []

    # The timeline is durable: a fresh journal over the same file
    # (a restart) returns the identical timeline.
    reopened = EventJournal(tmp_path / "journal.db")
    assert [e.journal_seq for e in entity_timeline(reopened, "gunnar")] == [1, 3, 4]


def test_timeline_cli(tmp_path, capsys):
    journal, bus = _journal_with_bus(tmp_path)
    bus.publish("world.entity_created", {"entity_id": "gunnar"}, source="ecs.world")
    assert inspector_main(
        ["timeline", "--journal", str(tmp_path / "journal.db"), "--entity", "gunnar"]
    ) == 0
    out = capsys.readouterr().out
    assert "timeline for gunnar (1 entries)" in out
    assert "world.entity_created" in out


# ---------------------------------------------------------------------------
# (c) Contradiction viewer over real detector output
# ---------------------------------------------------------------------------


def _contradiction_store(tmp_path: Path):
    store = PersistentMemoryStore(tmp_path / "memory.db")
    engine = WritebackEngine(store)
    detector = ContradictionDetector(store)
    f1 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="location",
        fact_value="mead_hall", confidence=0.8,
    )
    f2 = engine.write_canonical_fact(
        fact_subject_id="gunnar", fact_key="location",
        fact_value="docks", confidence=0.9,
    )
    created = detector.check_and_record(f2)
    assert len(created) == 1
    return store, detector, f1, f2, created[0]


def test_contradiction_viewer_lists_detector_output(tmp_path):
    store, _detector, f1, f2, contradiction = _contradiction_store(tmp_path)
    views = contradiction_views(store)
    assert len(views) == 1
    view = views[0]
    assert view.contradiction_id == contradiction.record_id
    assert view.resolution_state == "open"
    assert view.reason == contradiction.content.structured_payload.contradiction_reason
    # Both claims resolved through the store to their real facts.
    assert view.claim_a_fact == ("gunnar", "location", "docks")
    assert view.claim_b_fact == ("gunnar", "location", "mead_hall")
    assert {view.claim_a_record_id, view.claim_b_record_id} == {f1.record_id, f2.record_id}
    assert contradiction_summary(views) == {"open": 1}


def test_contradiction_viewer_open_default_and_full_ledger(tmp_path):
    store, detector, _f1, f2, contradiction = _contradiction_store(tmp_path)
    assert detector.resolve(contradiction.record_id, preferred_record_id=f2.record_id)
    # Open-only default: the resolved record leaves the operator view.
    assert contradiction_views(store) == []
    # The full ledger still shows it, resolved, with its preference.
    views = contradiction_views(store, include_resolved=True)
    assert len(views) == 1
    assert views[0].resolution_state == "resolved"
    assert views[0].preferred_record_id == f2.record_id
    assert contradiction_summary(views) == {"resolved": 1}


def test_contradiction_viewer_empty_store(tmp_path):
    store = PersistentMemoryStore(tmp_path / "memory.db")
    assert contradiction_views(store) == []
    assert contradiction_views(store, include_resolved=True) == []


# ---------------------------------------------------------------------------
# (d) Durable dead-letter archaeology
# ---------------------------------------------------------------------------


def test_dead_letter_archaeology_survives_restart(tmp_path):
    journal, bus = _journal_with_bus(tmp_path)

    def _boom(envelope):
        raise RuntimeError("subscriber exploded")

    bus.subscribe("world.entity_created", _boom)
    bus.publish("world.entity_created", {"entity_id": "gunnar"}, source="test")
    assert len(bus.dead_letters()) == 1  # volatile copy exists pre-restart
    bus.close()  # clears the in-memory queue — the restart erasure
    assert bus.dead_letters() == []

    # Archaeology: a FRESH journal instance over the same file.
    reopened = EventJournal(tmp_path / "journal.db")
    report = dead_letter_archaeology(reopened)
    assert report.total == 1
    letter = report.letters[0]
    assert letter["topic"] == "world.entity_created"
    assert letter["error_type"] == "RuntimeError"
    assert letter["message"] == "subscriber exploded"
    assert letter["dead_letter_id"] == 1
    assert report.summary == {"world.entity_created": {"RuntimeError": 1}}
    assert report.volatile_count is None

    # Filters are exact matches.
    assert dead_letter_archaeology(reopened, topic="chat.message").total == 0
    assert dead_letter_archaeology(
        reopened, error_type="RuntimeError"
    ).total == 1
    # A live bus supplied for contrast reports its own volatile count.
    fresh_bus = EventBus()
    assert dead_letter_archaeology(reopened, bus=fresh_bus).volatile_count == 0


def test_dead_letter_archaeology_cli(tmp_path, capsys):
    journal, bus = _journal_with_bus(tmp_path)

    def _boom(envelope):
        raise ValueError("nope")

    bus.subscribe("chat.message", _boom)
    bus.publish("chat.message", {"text": "hi"}, source="test")
    bus.close()
    assert inspector_main(
        ["dead-letters", "--journal", str(tmp_path / "journal.db")]
    ) == 0
    out = capsys.readouterr().out
    assert "1 persisted dead letter(s)" in out
    assert "ValueError: nope" in out


# ---------------------------------------------------------------------------
# (e) Promotion surface — TUI in-package, shim, Rich declaration
# ---------------------------------------------------------------------------


def test_tui_promoted_into_package_and_tools_shim_works():
    from wyrdforge import inspector_tui

    assert inspector_tui.handle_tui_command("/help", inspector_tui.TuiState(), None)
    spec = importlib.util.spec_from_file_location(
        "wyrd_tui_shim", REPO_ROOT / "tools" / "wyrd_tui.py"
    )
    assert spec is not None and spec.loader is not None
    shim = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shim)
    # The shim re-exports the package implementation itself.
    assert shim.handle_tui_command is inspector_tui.handle_tui_command
    assert shim.main is inspector_tui.main


def test_tui_inspector_commands_against_real_stores(tmp_path):
    from wyrdforge import inspector_tui

    journal, bus = _journal_with_bus(tmp_path)
    bus.publish("world.entity_created", {"entity_id": "gunnar"}, source="ecs.world")

    def _boom(envelope):
        raise RuntimeError("archaeology target")

    bus.subscribe("chat.message", _boom)
    bus.publish("chat.message", {"text": "hi"}, source="test")
    bus.close()

    _store, _detector, _f1, _f2, _c = _contradiction_store(tmp_path)
    ctx = inspector_tui.InspectorContext(
        journal_path=str(tmp_path / "journal.db"),
        memory_path=str(tmp_path / "memory.db"),
    )
    state = inspector_tui.TuiState()

    out = inspector_tui.handle_tui_command("/timeline gunnar", state, None, ctx)
    assert "timeline for gunnar (1 entries)" in out
    out = inspector_tui.handle_tui_command("/deadletters", state, None, ctx)
    assert "1 persisted dead letter(s)" in out
    out = inspector_tui.handle_tui_command("/contradictions", state, None, ctx)
    assert "1 contradiction(s)" in out and "mead_hall" in out

    # Without a context the commands say what they need — no invention.
    out = inspector_tui.handle_tui_command("/timeline gunnar", state, None)
    assert "--journal" in out
    # Legacy 3-argument callers are untouched.
    assert inspector_tui.handle_tui_command("/world", state, None).startswith("World:")


def test_tui_diff_command_offline_baseline(tmp_path):
    from wyrdforge import inspector_tui

    state = inspector_tui.TuiState()
    state.baseline_snapshot = snapshot_world(_world_v1())
    state.world_path = str(tmp_path / "does-not-matter.yaml")
    # The world file does not exist, so the reload cannot produce a
    # fresh snapshot — the command reports that honestly.
    out = inspector_tui.handle_tui_command("/diff", state, None,
                                           inspector_tui.InspectorContext())
    assert "no longer loads" in out
    # And without a baseline it directs the operator to the CLI.
    out = inspector_tui.handle_tui_command("/diff", inspector_tui.TuiState(), None)
    assert "wyrd-inspect" in out


def test_rich_declared_as_optional_extra_never_core():
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    core_deps = [d.split(">=")[0].split("[")[0].strip().lower()
                 for d in pyproject["project"]["dependencies"]]
    assert "rich" not in core_deps
    extras = pyproject["project"]["optional-dependencies"]
    assert any(d.lower().startswith("rich") for d in extras["inspector"])
    scripts = pyproject["project"]["scripts"]
    assert scripts["wyrd-inspect"] == "wyrdforge.inspector:main"
    assert scripts["wyrd-inspect-tui"] == "wyrdforge.inspector_tui:main"


def test_tui_no_rich_fallback_actually_degrades(monkeypatch, capsys):
    # Regression pin for a pre-E4 defect: run_tui constructed
    # rich.Console() BEFORE checking _RICH_AVAILABLE, so without
    # Rich the promised simple-CLI fallback raised NameError
    # instead of degrading. This venv has no Rich, so the fallback
    # path is the live one here.
    import argparse

    from wyrdforge import inspector_tui

    assert inspector_tui._RICH_AVAILABLE is False
    monkeypatch.setattr("builtins.input", lambda _prompt="": (_ for _ in ()).throw(EOFError))
    args = argparse.Namespace(
        host="localhost", port=8765, world="", offline=True,
        timeout=5, journal="", memory="",
    )
    inspector_tui.run_tui(args)  # must return, not raise NameError
    assert "simple mode" in capsys.readouterr().out


def test_inspector_core_needs_no_rich(tmp_path):
    # The data surfaces import and run with Rich absent from this
    # environment (the dedicated venv has no rich installed).
    with pytest.raises(ImportError):
        import rich  # noqa: F401
    before, after = _lineage(tmp_path)
    assert diff_snapshots(before, after).added_entities == ("new_one",)
