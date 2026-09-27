"""Tests for src/wyrdforge/incident_evidence.py — Track 6, Incident 1.

Pins the "never invent a cause" law in code: a bundle may claim a cause
only when cause_evidence backs it. Also pins the honest default
(cause="unknown") and the format contract (required fields, schema
version). Everything is synthetic; no I/O, no measurement.
"""

from wyrdforge import incident_evidence as ie


def _valid_bundle():
    return ie.new_evidence_bundle(
        detected_at="2026-09-26T20:14:00-04:00",
        resurrected_at="2026-09-26T20:15:00-04:00",
        last_heartbeat_at="2026-09-26T20:13:41-04:00",
        mem_available_kb_before=412000,
        mem_available_kb_after=398000,
        watchdog_log=["hub missing at 20:14:02, respawned pid 12345"],
    )


def test_valid_bundle_passes():
    assert ie.validate_evidence_bundle(_valid_bundle()) == []


def test_missing_required_field_named():
    bundle = _valid_bundle()
    del bundle["detected_at"]
    problems = ie.validate_evidence_bundle(bundle)
    assert any("detected_at" in p for p in problems)


def test_claimed_cause_without_evidence_rejected():
    bundle = _valid_bundle()
    bundle["cause"] = "memory-pressure"
    bundle["cause_evidence"] = []
    problems = ie.validate_evidence_bundle(bundle)
    assert problems, "a claimed cause without evidence must be rejected"
    assert any("without evidence" in p for p in problems)


def test_claimed_cause_with_evidence_accepted():
    bundle = _valid_bundle()
    bundle["cause"] = "memory-pressure"
    bundle["cause_evidence"] = [
        "exit signal 9 with MemAvailable 41200k at death, five incidents same signature"
    ]
    assert ie.validate_evidence_bundle(bundle) == []


def test_constructor_defaults_cause_to_unknown():
    bundle = ie.new_evidence_bundle(
        detected_at="2026-09-26T20:14:00-04:00",
        resurrected_at="2026-09-26T20:15:00-04:00",
    )
    assert bundle["cause"] == "unknown"
    assert bundle["cause_evidence"] == []
    assert bundle["schema_version"] == ie.SCHEMA_VERSION
    assert ie.validate_evidence_bundle(bundle) == []


def test_wrong_schema_version_rejected():
    bundle = _valid_bundle()
    bundle["schema_version"] = 999
    problems = ie.validate_evidence_bundle(bundle)
    assert any("schema_version" in p for p in problems)


def test_non_mapping_bundle_rejected():
    problems = ie.validate_evidence_bundle("not a bundle")
    assert problems


def test_nullable_evidence_fields_accepted():
    # None means "not obtainable," never invented — all defaults are None.
    bundle = ie.new_evidence_bundle(
        detected_at="2026-09-26T20:14:00-04:00",
        resurrected_at="2026-09-26T20:15:00-04:00",
    )
    assert bundle["last_heartbeat_at"] is None
    assert bundle["exit_code"] is None
    assert ie.validate_evidence_bundle(bundle) == []
