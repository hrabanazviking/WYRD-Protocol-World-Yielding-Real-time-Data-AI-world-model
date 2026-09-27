"""Hub-disappearance evidence bundles — Track 6, Incident 1.

Standing rules (Track 6, Incident 1 — the nerve-hub disappearances,
2026-09-26, cause UNPROVEN):

1. Instrument before theorizing. A death with no evidence is a death we
   learn nothing from.
2. Never fail silently. Volmarr is looped in briefly with facts, not
   theories: "hub down at HH:MM, resurrected at HH:MM, evidence attached,
   cause unknown."
3. No claimed root cause until proven. Five evidence bundles with the same
   signature, or it stays unknown.

This module defines the bundle format and enforces it. It does not collect
evidence — collection lives Verdandi-side / machine-health-side
(watchdog, Heilsiðr mem sense, runner logs); this repo cannot collect
without reaching across the repo boundary. Bundles are written to runtime
state, not the repo: ``~/.hermes/state/hub_evidence/hub-death-YYYYMMDD-HHMMSS.json``
(naming is local time of detection).

Rules of the format: any evidence field may be ``None`` — None means "not
obtainable," never invented. ``cause`` defaults to ``"unknown"``; it may
only differ from ``"unknown"`` when ``cause_evidence`` is non-empty — a
claimed cause without evidence is the exact failure Track 6 Incident 1
forbids. That law is enforced in code by ``validate_evidence_bundle``.

Pure module: stdlib only (``typing``), no I/O, no measurement, no third-party
imports. Incident record: ``docs/incident-record.md``. Bug ledger:
``docs/bug-ledger.md``.
"""

from typing import Any, Dict, List, Mapping, Optional, Sequence

SCHEMA_VERSION = 1

REQUIRED_FIELDS = (
    "schema_version",
    "incident",
    "detected_at",
    "resurrected_at",
    "last_heartbeat_at",
    "mem_available_kb_before",
    "mem_available_kb_after",
    "exit_code",
    "exit_signal",
    "watchdog_log",
    "cause",
    "cause_evidence",
)


def new_evidence_bundle(
    *,
    detected_at: str,
    resurrected_at: str,
    incident: str = "hub-disappearance",
    last_heartbeat_at: Optional[str] = None,
    mem_available_kb_before: Optional[int] = None,
    mem_available_kb_after: Optional[int] = None,
    exit_code: Optional[int] = None,
    exit_signal: Optional[int] = None,
    watchdog_log: Sequence[str] = (),
    cause: str = "unknown",
    cause_evidence: Sequence[Any] = (),
) -> Dict[str, Any]:
    """Build an evidence bundle.

    ``cause`` defaults to ``"unknown"`` — the honest default. Pass a
    different cause ONLY with ``cause_evidence`` to back it; a claimed
    cause without evidence fails validation (the Track 6 Incident 1 law).

    Timestamps are ISO 8601 strings in local time (e.g.
    ``"2026-09-26T20:14:00-04:00"``); any evidence field may be ``None``
    meaning "not obtainable," never invented.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "incident": incident,
        "detected_at": detected_at,
        "resurrected_at": resurrected_at,
        "last_heartbeat_at": last_heartbeat_at,
        "mem_available_kb_before": mem_available_kb_before,
        "mem_available_kb_after": mem_available_kb_after,
        "exit_code": exit_code,
        "exit_signal": exit_signal,
        "watchdog_log": list(watchdog_log),
        "cause": cause,
        "cause_evidence": list(cause_evidence),
    }


def validate_evidence_bundle(bundle: Mapping[str, Any]) -> List[str]:
    """Validate a bundle. Returns problems found; an empty list means valid.

    Checks:
    - ``bundle`` is a mapping at all.
    - ``schema_version`` equals ``SCHEMA_VERSION``.
    - Every ``REQUIRED_FIELDS`` key is present.
    - ``cause`` different from ``"unknown"`` requires non-empty
      ``cause_evidence`` — a claimed cause without evidence is the exact
      failure Track 6 Incident 1 forbids.

    Never raises on a malformed bundle — problems are returned, not thrown,
    so validation itself cannot fail silently.
    """
    problems: List[str] = []
    if not isinstance(bundle, Mapping):
        return ["bundle is not a mapping"]
    for field in REQUIRED_FIELDS:
        if field not in bundle:
            problems.append(f"missing required field: {field}")
    if "schema_version" in bundle and bundle["schema_version"] != SCHEMA_VERSION:
        problems.append(
            f"schema_version {bundle['schema_version']!r} != SCHEMA_VERSION {SCHEMA_VERSION}"
        )
    cause = bundle.get("cause", "unknown")
    cause_evidence = bundle.get("cause_evidence")
    if cause != "unknown" and not cause_evidence:
        problems.append(
            "claimed cause %r without evidence: cause_evidence must be non-empty "
            "(Track 6 Incident 1: never invent a cause)" % (cause,)
        )
    return problems
