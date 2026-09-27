"""Track 2 P2/P3 machinery tests.

The policy docs (docs/reproduction-first-policy.md, docs/triage-cadence.md)
hold the *procedure*; this module enforces the *machinery*: the docs exist,
they cross-reference each other and the bug ledger, the ledger's triage head
is dated, and every quarantined ledger entry carries a reason, an owner, and
a future re-check date.

These tests check machinery, not judgment. They run in milliseconds and stay
in the normal suite.
"""

import datetime as dt
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
DOCS = REPO / "docs"
POLICY = DOCS / "reproduction-first-policy.md"
CADENCE = DOCS / "triage-cadence.md"
LEDGER = DOCS / "bug-ledger.md"

TODAY = dt.date.today()


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def test_policy_docs_exist_and_nonempty():
    for doc in (POLICY, CADENCE):
        assert doc.is_file(), f"missing policy doc: {doc}"
        assert len(_read(doc).strip()) > 500, f"policy doc suspiciously short: {doc}"


def test_policy_docs_cross_reference():
    """Both docs name each other and the bug ledger by path.

    A broken cross-reference is a dangling pointer in the procedure —
    it fails the suite.
    """
    policy = _read(POLICY)
    cadence = _read(CADENCE)
    assert "docs/bug-ledger.md" in policy
    assert "docs/triage-cadence.md" in policy
    assert "docs/bug-ledger.md" in cadence
    assert "docs/reproduction-first-policy.md" in cadence
    # The named targets must actually exist.
    for target in ("docs/bug-ledger.md", "docs/triage-cadence.md",
                   "docs/reproduction-first-policy.md"):
        assert (REPO / target).is_file(), f"cross-reference target missing: {target}"


def test_reproduction_rule_stated_verbatim():
    """The roadmap's rule must appear in the policy doc verbatim."""
    policy = _read(POLICY).lower()
    assert "no fix without a failing test first" in policy
    assert "the commit contains both" in policy


def test_workflow_steps_named_in_order():
    """The three workflow steps must appear in order.

    Sabotage check: deleting any step (e.g. the confirm-red step) fails
    the suite — the procedure is not the procedure without all three.
    """
    policy = _read(POLICY)
    steps = (
        "Step 1 \u2014 Write the failing test",
        "Step 2 \u2014 Confirm it red",
        "Step 3 \u2014 Fix and commit together",
    )
    positions = [policy.find(step) for step in steps]
    assert all(pos >= 0 for pos in positions), (
        f"missing workflow step(s): "
        f"{[s for s, p in zip(steps, positions) if p < 0]}"
    )
    assert positions == sorted(positions), "workflow steps out of order"


def test_triage_tiers_verbatim():
    """The three roadmap tiers with their windows must appear in the cadence doc."""
    cadence = _read(CADENCE).lower()
    for tier in ("bleeding", "limping", "cosmetic"):
        assert tier in cadence, f"missing triage tier: {tier}"
    assert "same day" in cadence
    assert "this week" in cadence
    assert "ledger + backlog" in cadence


def test_ledger_triage_head_is_dated():
    """The ledger's head Triage section must exist and carry a non-future date."""
    ledger = _read(LEDGER)
    match = re.search(
        r"^## Triage\s*[\u2014\u2013-]\s*updated\s+(\d{4}-\d{2}-\d{2})",
        ledger,
        re.MULTILINE,
    )
    assert match, "ledger head '## Triage \u2014 updated YYYY-MM-DD' not found"
    triage_date = dt.date.fromisoformat(match.group(1))
    assert triage_date <= TODAY, (
        f"triage head date {triage_date} is in the future"
    )


def _quarantine_blocks(entries_text: str):
    """Return the parenthesized content of every quarantined Status line.

    The open paren is found by regex; the close paren is found by depth
    counting so that a reason may itself contain parentheses without
    truncating the block. Entries written as ``**Status:**quarantined``
    (no space) are also caught — a missing space must not make a
    quarantine entry invisible to the completeness check.
    """
    opener = re.compile(r"\*\*Status:\*\*\s*quarantined\s*\(")
    blocks = []
    for m in opener.finditer(entries_text):
        depth = 1
        i = m.end()
        while i < len(entries_text) and depth:
            ch = entries_text[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            i += 1
        if depth == 0:
            blocks.append(entries_text[m.end():i - 1])
    return blocks


def _validate_quarantine_body(body: str):
    """Check one quarantine block; return (reason, owner, recheck) or raise.

    The reason must be real text — a block that jumps straight to
    ``owner:`` with no reason is a parking lot wearing a nametag.
    """
    reason = body.split(";", 1)[0].strip()
    assert reason and not re.match(r"(?i)^(owner|re-check)\s*:", reason), (
        f"quarantined entry missing a real reason: {body[:80]!r}"
    )
    owner = re.search(r"owner:\s*([^\s;)]+)", body)
    assert owner and owner.group(1).strip(), (
        f"quarantined entry missing an owner: {body[:80]!r}"
    )
    recheck = re.search(r"re-check\s+(\d{4}-\d{2}-\d{2})", body)
    assert recheck, (
        f"quarantined entry missing a re-check date: {body[:80]!r}"
    )
    recheck_date = dt.date.fromisoformat(recheck.group(1))
    assert recheck_date > TODAY, (
        f"quarantined entry re-check date {recheck_date} is not in the "
        f"future — the review is overdue; date the review in the ledger"
    )
    return reason, owner.group(1), recheck.group(1)


def test_quarantine_entries_complete():
    """Every quarantined entry names a reason, an owner, and a future re-check date.

    A quarantine without an owner and a re-check date is a parking lot —
    it fails the suite.
    """
    ledger = _read(LEDGER)
    # Scope to the actual entries: the schema template above "## Entries"
    # also shows a quarantined status line, but it is not a bug entry.
    assert "## Entries" in ledger
    entries_text = ledger.split("## Entries", 1)[1]
    blocks = _quarantine_blocks(entries_text)
    assert blocks, "no quarantined entries found under ## Entries"

    for body in blocks:
        _validate_quarantine_body(body)


def test_quarantine_parsing_edge_cases():
    """The machinery must catch deficient entries and tolerate honest ones.

    - A quarantined block with no reason text (jumping straight to
      ``owner:``) must fail the reason check.
    - ``**Status:**quarantined`` with no space must still be detected —
      a missing space must not hide the entry from the check.
    - A reason containing parentheses must not truncate the block; a
      complete entry with nested parens validates cleanly.
    """
    # No reason text: the "reason" would be the owner field itself.
    with pytest.raises(AssertionError):
        _validate_quarantine_body("owner: forge; re-check 2026-10-26")

    # No space after **Status:** — still found, still checked.
    found = _quarantine_blocks(
        "## Entries\n- **Status:**quarantined (stale timing; re-check 2020-01-01)\n"
    )
    assert len(found) == 1
    with pytest.raises(AssertionError):
        _validate_quarantine_body(found[0])  # missing owner

    # Nested parens in the reason: block is whole, entry validates.
    found = _quarantine_blocks(
        "## Entries\n- **Status:** quarantined "
        "(flaky (timing) under load; owner: forge; re-check 2026-10-26)\n"
    )
    assert len(found) == 1
    reason, owner, recheck = _validate_quarantine_body(found[0])
    assert owner == "forge" and recheck == "2026-10-26"
    assert "timing" in reason
