"""Schema-conformance tests for docs/bug-ledger.md — Track 2, Phase 1.

Lenient parser: field presence, not prose quality. This pins the roadmap's
"every future fix adds an entry" discipline at the structure level — a fix
that ships without a well-formed ledger entry fails the suite.
"""

import re
from pathlib import Path

LEDGER = Path(__file__).resolve().parents[1] / "docs" / "bug-ledger.md"

BUG_FIELDS = [
    "Severity at find",
    "Date found",
    "Observed",
    "Reproduction",
    "Root cause",
    "Fix",
    "Pinning test",
    "Status",
]

SEVERITIES = {"bleeding", "limping", "cosmetic"}
STATUSES = ("fixed", "open", "quarantined")
DISPOSITIONS = {
    "fixed",
    "noted (not code)",
    "deliberately not applied (ordered out of scope)",
}


def _text():
    assert LEDGER.exists(), f"bug ledger missing at {LEDGER}"
    return LEDGER.read_text(encoding="utf-8")


def _entries(text, prefix):
    """Split on ### <PREFIX><n> lines; return (title, body) pairs.
    Only the '## Entries' section is scanned — the schema examples above
    it use the same shapes with enumerated values, not real entries."""
    section = text.split("## Entries", 1)[1]
    pattern = re.compile(rf"^### ({prefix}\d+)\b(.*)$", re.M)
    matches = list(pattern.finditer(section))
    out = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append((m.group(1), section[start:end]))
    return out


def test_ledger_has_bug_entries():
    entries = _entries(_text(), "BUG-")
    assert len(entries) >= 4, f"expected the four backfilled BUG entries, got {len(entries)}"


def test_every_bug_entry_has_all_fields():
    for title, body in _entries(_text(), "BUG-"):
        missing = [f for f in BUG_FIELDS if f"- **{f}:**" not in body]
        assert not missing, f"{title} missing fields: {missing}"


def test_bug_severity_and_status_in_allowed_sets():
    for title, body in _entries(_text(), "BUG-"):
        sev = re.search(r"- \*\*Severity at find:\*\*\s*(\w+)", body)
        assert sev and sev.group(1) in SEVERITIES, f"{title}: bad severity"
        status = re.search(r"- \*\*Status:\*\*\s*([^\n]+)", body)
        assert status, f"{title}: no Status line"
        assert status.group(1).strip().startswith(STATUSES), (
            f"{title}: status '{status.group(1).strip()}' not in {STATUSES}"
        )


def test_audit_entries_have_valid_disposition():
    entries = _entries(_text(), "AUDIT-F")
    assert entries, "expected Wave D AUDIT-F entries"
    for title, body in entries:
        m = re.search(r"- \*\*Disposition:\*\*\s*(.+?)(?:\n|$)", body)
        assert m, f"{title}: no Disposition line"
        assert m.group(1).strip() in DISPOSITIONS, (
            f"{title}: disposition '{m.group(1).strip()}' not allowed"
        )


def test_triage_section_present_and_dated():
    text = _text()
    m = re.search(r"^## Triage — updated (\d{4}-\d{2}-\d{2})", text, re.M)
    assert m, "no '## Triage — updated YYYY-MM-DD' section head"


def test_triage_names_open_verification():
    text = _text()
    triage = text.split("## Triage", 1)[1].split("## ", 1)[0]
    assert "BUG-004" in triage, "BUG-004's open verification must appear in triage"


def test_incident_record_cross_link():
    assert "incident-record.md" in _text(), "ledger must cross-link the incident record"
