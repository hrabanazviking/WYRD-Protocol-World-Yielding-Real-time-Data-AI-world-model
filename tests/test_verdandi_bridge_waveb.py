"""Wave B tests for bridges/verdandi_bridge.py.

Covers: component registration, memory thresholds, hub transitions,
stable IDs, memory add/remove, supersedes chains, caps + salience
ordering, reflection mapping, depth-2 refusal, 24h dedup, environment
facts + SSA expiry, the person roster, and the quiet window. Every
fixture is synthetic; nothing touches the live memory tree.
"""
import os
from datetime import datetime, timezone
from typing import get_args
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from wyrdforge.bridges import verdandi_bridge as vb
from wyrdforge.bridges.verdandi_bridge import VerdandiBridge
from wyrdforge.ecs.component import registered_types
from wyrdforge.ecs.components.theory_of_mind import BeliefSource

TS = 1790381094.0  # fixed nerve-feed timestamp
NY = ZoneInfo("America/New_York")


def _ledger():
    return {"last_sense_status": {}, "reflection_seen": {}}


def _bridge():
    return VerdandiBridge(ledger=_ledger())


# -- component registration -------------------------------------------------
def test_waveb_components_registered():
    for name in ("sense", "environment", "memory_beliefs", "reflection"):
        assert name in registered_types(), name


def test_sense_reading_status_constrained():
    with pytest.raises(ValidationError):
        vb.SenseReading(sense_kind="machine", metric="m",
                        status="purple")  # not ok/warn/red
    r = vb.SenseReading(sense_kind="machine", metric="m", status="ok")
    assert r.prev_status is None  # no baseline yet


def test_reflection_depth_schema_bounded():
    with pytest.raises(ValidationError):
        vb.ReflectionComponent(entity_id="reflection:x", thought="t",
                               depth=2)
    c = vb.ReflectionComponent(entity_id="reflection:x", thought="t",
                               depth=1)
    assert c.depth == 1


def test_belief_source_remembered():
    # BeliefSource is a Literal; "remembered" is its Wave B addition —
    # remembered provenance, distinct from observed/inferred belief.
    assert "remembered" in get_args(BeliefSource)


# -- memory thresholds (Heilsiðr's numbers, reused not invented) -------------
@pytest.mark.parametrize("mib,expected", [
    (2080, "ok"), (1000, "ok"), (999, "warn"), (500, "warn"),
    (499, "red"), (0, "red"), (None, "warn"),
])
def test_mem_status_thresholds(mib, expected):
    assert vb._mem_status(mib) == expected


def test_read_mem_available(tmp_path):
    p = tmp_path / "meminfo"
    p.write_text("MemTotal:        8000000 kB\n"
                 "MemAvailable:    2080688 kB\n")
    assert vb._read_mem_available_mib(str(p)) == 2080688 // 1024
    assert vb._read_mem_available_mib(str(tmp_path / "nope")) is None


@pytest.mark.parametrize("raw,expected", [
    ("ok", "ok"), ("note", "ok"), ("restarted", "warn"),
    ("failed", "red"), ("fault", "red"), ("cleared", "ok"),
])
def test_hub_liveness_mapping(tmp_path, raw, expected):
    d = tmp_path / "state" / "heilsiðr"
    d.mkdir(parents=True)
    (d / "hub.state").write_text(raw + "\n")
    status, level = vb._read_hub_liveness(str(tmp_path / "state"))
    assert status == expected
    assert level == raw


def test_hub_liveness_missing_is_warn(tmp_path):
    status, level = vb._read_hub_liveness(str(tmp_path / "state"))
    assert status == "warn"
    assert level is None


# -- the quiet window --------------------------------------------------------
@pytest.mark.parametrize("hour,minute,expected", [
    (10, 29, False), (10, 30, True), (10, 45, True),
    (11, 29, True), (11, 30, False), (9, 0, False), (12, 0, False),
])
def test_quiet_window(hour, minute, expected):
    at = datetime(2026, 9, 26, hour, minute, tzinfo=NY)
    assert vb._quiet_window_active(at) is expected


# -- stable identity ----------------------------------------------------------
def test_stable_ids_across_rebuilds():
    b1, b2 = _bridge(), _bridge()
    e1 = b1.ensure_entity(vb.VOLMARR_ID, {"person"})
    e2 = b2.ensure_entity(vb.VOLMARR_ID, {"person"})
    assert e1.entity_id == e2.entity_id == "person:volmarr"
    for eid in (vb.MACHINE_ID, vb.RHYTHM_ID, vb.PLACE_ANGOLA_ID,
                vb.PLACE_TORC_ID):
        assert b1.ensure_entity(eid).entity_id == \
            b2.ensure_entity(eid).entity_id == eid


def test_person_roster_configurable_constant():
    assert vb.PERSON_ROSTER == ("veyrunn", "aurora", "caducea", "runa")


# -- memory → belief parsing --------------------------------------------------
def _fake_home(tmp_path):
    home = tmp_path / "home"
    (home / "memory" / "bank").mkdir(parents=True)
    (home / "memory" / "people").mkdir(parents=True)
    (home / "MEMORY.md").write_text(
        "- Volmarr's name is Volmarr Wyrd.\n"
        "- NO pseudocode ever — instant firing offense.\n"
        "- Volmarr lives in Angola, Indiana.\n")
    (home / "memory" / "bank" / "test.md").write_text(
        "- [fact|high] Volmarr's winter base is Truth or Consequences, "
        "NM. (src: memory/2026-09-24.md:45)\n"
        "- supersedes: Volmarr's winter base is Truth or Consequences, "
        "NM. (src: memory/2026-09-24.md:45)\n"
        "- [fact|high] Volmarr's winter base is Truth or Consequences, "
        "NM, Nov-Mar. (src: memory/2026-09-25.md:12)\n"
        "- Volmarr's winter base is Truth or Consequences, NM. "
        "(src: memory/2026-09-24.md:45)\n"
        "- [preference|medium] Volmarr prefers new gear. "
        "(src: memory/2026-09-24.md:50)\n")
    (home / "memory" / "2026-09-26.md").write_text(
        "- [event|medium] Shipped Wave B of the WYRD expansion.\n")
    (home / "memory" / "people" / "veyrunn.md").write_text(
        "---\nsummary: Sacred Whisper of Mystery.\n---\n"
        "## Facts\n" +
        "".join(f"- Veyrunn fact number {i}.\n" for i in range(12)))
    return str(home)


def test_parse_memory_beliefs_sources_and_caps():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        from pathlib import Path
        home = _fake_home(Path(tmp))
        at = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
        parsed = vb.parse_memory_beliefs(home=home, now=at)
        volmarr = parsed["person:volmarr"]
        srcs = {b.src for b in parsed["person:volmarr"]}
        # FILE:LINE citations on every belief.
        assert any(s.startswith("MEMORY.md:") for s in srcs)
        assert any(s.startswith("bank/test.md:") for s in srcs)
        assert any(s.startswith("memory/2026-09-26.md:") for s in srcs)
        # Standing rule detected, confidence 1.0.
        standing = [b for b in volmarr if b.salience == "standing"]
        assert standing and all(b.confidence == 1.0 for b in standing)
        # The superseded winter-base claim is gone; the new one stands.
        claims = [b.claim for b in volmarr]
        assert not any(c.rstrip().endswith("NM. (src: memory/2026-09-24.md:45)")
                       and "Nov-Mar" not in c for c in claims)
        assert any("Nov-Mar" in c for c in claims)
        # Person page: capped at 8, salience-ordered. (The entity
        # association is the parse dict's key, not a belief field.)
        vey = parsed["person:veyrunn"]
        assert len(vey) == 8
        # Roster present; place routing worked.
        assert "person:aurora" in parsed  # empty page → empty list
        assert any("angola" in b.claim.lower()
                   for b in parsed[vb.PLACE_ANGOLA_ID])
        assert any("consequences" in b.claim.lower()
                   for b in parsed[vb.PLACE_TORC_ID])


def test_volmarr_cap_forty():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp) / "home"
        (home / "memory" / "bank").mkdir(parents=True)
        (home / "memory" / "people").mkdir(parents=True)
        (home / "memory" / "bank" / "big.md").write_text(
            "".join(f"- [fact|medium] Synthetic claim number {i}. "
                    f"(src: memory/2026-09-26.md:{i})\n" for i in range(60)))
        at = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
        parsed = vb.parse_memory_beliefs(home=str(home), now=at)
        assert len(parsed["person:volmarr"]) == vb.MAX_VOLMARR_BELIEFS == 40


def test_memory_belief_rewrite_not_duplicate():
    b = _bridge()
    mk = lambda claim, src: vb.MemoryBelief(
        subject="person:volmarr:x", claim=claim, src=src)
    b.attach_memory_beliefs("person:volmarr", [mk("first", "bank/a.md:1")])
    b.attach_memory_beliefs("person:volmarr", [mk("second", "bank/a.md:1")])
    comp = b.world.get_component("person:volmarr", "memory_beliefs")
    assert len(comp.beliefs) == 1
    assert comp.beliefs[0].claim == "second"


# -- the self-reflection loop --------------------------------------------------
def test_reflection_mapping_verbatim():
    b = _bridge()
    thought = "  Noticing   I track wishes   more warmly than moods.  "
    desc = b.apply_event("self_reflection",
                         {"thought": thought, "seq": 7, "depth": 0}, TS)
    assert desc is not None
    comp = b.world.get_component("reflection:7", "reflection")
    assert comp is not None
    # Verbatim — the bridge never drafts or templates the thought.
    assert comp.thought == "Noticing I track wishes more warmly than moods."
    assert comp.depth == 0
    # Anchor + self-understanding updated.
    anchors = [a for e, a in b.world.iter_components("temporal_anchor")]
    assert any(a.label.startswith("thought:") for a in anchors)
    belief = b._beliefs().get_belief("unnr:self-understanding")
    assert belief is not None and belief.claim == comp.thought


def test_reflection_depth2_refused():
    b = _bridge()
    desc = b.apply_event("self_reflection",
                         {"thought": "a thought about a thought",
                          "seq": 8, "depth": 2}, TS)
    assert desc is None
    assert b.world.get_entity("reflection:8") is None


def test_reflection_empty_thought_dropped_never_invented():
    b = _bridge()
    assert b.apply_event("self_reflection", {"seq": 9}, TS) is None
    assert b.apply_event("self_reflection",
                         {"thought": "   ", "seq": 9}, TS) is None


def test_reflection_seq_collision_refused_not_overwritten():
    b = _bridge()
    desc = b.apply_event("self_reflection",
                         {"thought": "the first thought on seq 23",
                          "seq": 23, "depth": 0}, TS)
    assert desc is not None
    # A different thought claiming the same seq must be refused — never
    # silently overwrite the first thought's component.
    refused = b.apply_event("self_reflection",
                            {"thought": "a different thought",
                             "seq": 23, "depth": 0}, TS)
    assert refused is None
    comp = b.world.get_component("reflection:23", "reflection")
    assert comp is not None
    assert comp.thought == "the first thought on seq 23"
    assert b.world.get_entity("reflection:9") is None


def test_reflection_24h_dedup():
    ledger = _ledger()
    b = VerdandiBridge(ledger=ledger)
    thought = "The mirror held steady today."
    assert b.apply_event("self_reflection",
                         {"thought": thought, "seq": 1}, TS) is not None
    # Same thought within 24h: dropped, not republished.
    assert b.apply_event("self_reflection",
                         {"thought": thought, "seq": 2},
                         TS + 3600) is None
    assert b.world.get_entity("reflection:2") is None
    # A different thought is genuinely new.
    assert b.apply_event("self_reflection",
                         {"thought": "Something else entirely.",
                          "seq": 3}, TS + 3600) is not None
    assert len(ledger["reflection_seen"]) == 2


def test_reflection_handler_registered():
    assert "self_reflection" in _bridge()._handlers()


# -- environment facts ---------------------------------------------------------
def test_environment_facts_ssa_expiry():
    before = vb.environment_facts(
        now=datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc))
    aspects = {f.aspect for f in before}
    assert {"quiet_window", "daily_article", "price_watch",
            "ssa_appointment"} <= aspects
    ssa = next(f for f in before if f.aspect == "ssa_appointment")
    assert ssa.valid_until == "2026-09-28"
    after = vb.environment_facts(
        now=datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc))
    assert "ssa_appointment" not in {f.aspect for f in after}
    # Every fact carries a real source.
    assert all(f.src for f in before)


def test_summary_sections():
    b = _bridge()
    b.ensure_entity(vb.MACHINE_ID, {"environment"})
    b.attach_senses(vb.sample_senses(
        meminfo_path="/nonexistent", state_dir="/nonexistent",
        feed_path="/nonexistent",
        now=datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)))
    s = b.summary()
    assert isinstance(s["senses"], list) and s["senses"]
    assert s["sense_transitions"] == []
    assert isinstance(s["memory_beliefs"], list)
    assert isinstance(s["reflections"], list)
