"""Schema-conformance tests for docs/contradiction-ledger.md — Track 7, Phase 1.

Follows tests/test_bug_ledger.py: lenient parser, field presence, not prose
quality. Pins the roadmap's "every fired divergence gets a ledger entry"
discipline at the structure level. The slice ships the ledger with schema,
rules, and a dated head note — live entries begin when the worker wiring is
approved, so the entry tests pass vacuously until then (and bite the moment
a malformed entry appears).
"""

import re
from pathlib import Path

LEDGER = Path(__file__).resolve().parents[1] / "docs" / "contradiction-ledger.md"

ENTRY_FIELDS = [
    "Date fired",
    "Divergence kind",
    "What the model believed",
    "What reality said",
    "Domain rule applied",
    "What changed",
    "Status",
]

DIVERGENCE_KINDS = {"stale_wish", "stale_mood", "stale_memory_belief", "sense_transition"}

DOMAIN_RULES = {
    "event-domain: the live event wins",
    "value-domain: memory wins",
}


def _text():
    assert LEDGER.exists(), f"contradiction ledger missing at {LEDGER}"
    return LEDGER.read_text(encoding="utf-8")


def _entries(text):
    """Split on ### CONTRADICTION-NNN lines in the '## Entries' section."""
    section = text.split("## Entries", 1)[1]
    pattern = re.compile(r"^### (CONTRADICTION-\d+)\b(.*)$", re.M)
    matches = list(pattern.finditer(section))
    out = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(section)
        out.append((m.group(1), section[start:end]))
    return out


def test_ledger_exists_and_names_the_track():
    text = _text()
    assert "Track 7" in text


def test_entry_schema_template_documents_all_fields():
    """The schema example itself must show every field — the template is law."""
    schema = _text().split("## Entry schema", 1)[1].split("\n## ", 1)[0]
    for field in ENTRY_FIELDS:
        assert f"**{field}:**" in schema, f"schema template missing field: {field}"


def test_every_entry_has_all_fields():
    for title, body in _entries(_text()):
        missing = [f for f in ENTRY_FIELDS if f"- **{f}:**" not in body]
        assert not missing, f"{title} missing fields: {missing}"


def test_entry_kinds_and_domain_rules_in_allowed_sets():
    for title, body in _entries(_text()):
        kind = re.search(r"- \*\*Divergence kind:\*\*\s*(\S+)", body)
        assert kind and kind.group(1) in DIVERGENCE_KINDS, f"{title}: bad kind"
        rule = re.search(r"- \*\*Domain rule applied:\*\*\s*(.+?)(?:\n|$)", body)
        assert rule, f"{title}: no domain rule"
        assert rule.group(1).strip() in DOMAIN_RULES, (
            f"{title}: domain rule '{rule.group(1).strip()}' not allowed"
        )


def test_entry_confidence_values_in_unit_interval():
    for title, body in _entries(_text()):
        for m in re.finditer(r"confidence\s+(\d+(?:\.\d+)?)\s*→\s*(\d+(?:\.\d+)?)", body):
            before, after = float(m.group(1)), float(m.group(2))
            assert 0.0 <= before <= 1.0, f"{title}: confidence {before} out of range"
            assert 0.0 <= after <= 1.0, f"{title}: confidence {after} out of range"


def test_feed_status_head_is_dated():
    m = re.search(r"^## Feed status — updated (\d{4}-\d{2}-\d{2})", _text(), re.M)
    assert m, "no '## Feed status — updated YYYY-MM-DD' head note"


def test_monthly_read_note_is_dated():
    section = _text().split("## Monthly read", 1)[1].split("\n## ", 1)[0]
    assert re.search(r"\d{4}-\d{2}-\d{2}", section), "monthly read note must be dated"


def test_ledger_does_not_invent_entries():
    """Until the worker wiring is approved, the ledger must hold no entries —
    the ledger must not invent divergences it did not witness."""
    text = _text()
    entries = _entries(text)
    assert entries == [], (
        f"ledger must ship empty (wiring not approved); found {[t for t, _ in entries]}"
    )
