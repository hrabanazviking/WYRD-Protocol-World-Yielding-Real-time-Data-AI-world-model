"""Shared synthetic fixtures for the Track 3 performance benchmarks.

Two generators, both deterministic (seeded ``random.Random``):

- :func:`make_feed` — a synthetic nerve-feed: N event dicts with
  ``{"type", "data", "_ts"}`` covering every handler in
  ``VerdandiBridge._handlers()`` with realistic payload shapes, so the
  replay exercises the real handler paths (anchors, beliefs, utterance
  components).
- :func:`build_memory_tree` — a synthetic memory corpus under a
  directory: ``MEMORY.md`` + ``memory/bank/*.md`` + seven daily logs +
  ``memory/people/*.md`` for every ``PERSON_ROSTER`` slug. Sized to the
  real 2026-09-27 corpus at ``scale=1`` (see :data:`CORPUS`); ``scale``
  multiplies every count. :func:`parse_memory_beliefs` reads only from
  the passed ``home`` tree, so the synthetic tree is a faithful
  stand-in for the attach phase.

Shared by ``tests/test_performance_budgets.py`` and
``tests/test_scale_limits.py`` so both modules measure the same shapes.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Corpus sizing — the real tree on 2026-09-27 (docs/performance-budgets.md
# § "Corpus size the memory budget is tied to"). The synthetic tree at
# scale=1 reproduces these counts; the budget is re-baselined when the
# corpus doubles, never silently.
# ---------------------------------------------------------------------------
CORPUS = {
    "memory_md_bullets": 75,      # ~/MEMORY.md "-" bullets
    "bank_bullets": 1896,         # ~/memory/bank/*.md bullets, 4 files
    "bank_files": 4,
    "daily_bullets": 1364,        # last-7-days daily logs (5 exist; 7 slots)
    "daily_logs": 7,
    "people_slugs": ("veyrunn", "aurora", "caducea", "runa"),  # PERSON_ROSTER
    "people_bullets": 30,         # per person page
}

# ---------------------------------------------------------------------------
# Synthetic nerve feed
# ---------------------------------------------------------------------------

_BASE_TS = 1759000000.0  # fixed epoch: deterministic _ts values


def _payload_builders() -> dict[str, object]:
    """One realistic payload builder per mapped event type."""
    return {
        "utterance": lambda i: {
            "speaker": "volmarr" if i % 2 == 0 else "unnr",
            "text": f"benchmark utterance {i} about the heath and the work",
            "emotion": ["warm", "curious"] if i % 3 else [],
        },
        "emote": lambda i: {
            "speaker": "unnr", "emote": "💜", "emotion": ["love"],
        },
        "mood_shift": lambda i: {
            "after": {"valence": 0.6, "energy": 0.5, "tension": 0.3},
            "why": f"benchmark reason {i}",
        },
        "wish_made": lambda i: {"wish_id": f"w-{i}", "text": f"wish text {i}"},
        "wish_pursued": lambda i: {"wish_id": f"w-{i}", "text": f"wish {i}"},
        "wish_fulfilled": lambda i: {"wish_id": f"w-{i}", "text": f"wish {i}"},
        "wish_released": lambda i: {"wish_id": f"w-{i}", "text": f"wish {i}"},
        "reward": lambda i: {"trigger": "reaction", "note": f"note {i}"},
        "shadow": lambda i: {"signal": f"signal {i}"},
        "joy_struck": lambda i: {"what": f"joy {i}"},
        "work_started": lambda i: {"kind": "slice", "note": f"note {i}"},
        "work_finished": lambda i: {"kind": "slice", "outcome": "done"},
        "job_start": lambda i: {"job_id": f"job-{i}"},
        "job_end": lambda i: {"job_id": f"job-{i}", "summary": f"done {i}"},
        "mythic_law_breach": lambda i: {"law": "frith", "file": f"f{i}.py"},
        "arc_opened": lambda i: {"signal": f"signal {i}", "note": f"n{i}"},
        "arc_closed": lambda i: {"arc_id": f"arc-{i}"},
        "entity.relationship_updated": lambda i: {
            "entity_id": f"entity-{i % 50}", "status": "open", "trust": 0.8,
        },
        "self_recognized": lambda i: {
            "verdicts": {"craft": "aligned", "care": "aligned"},
            "note": f"note {i}",
        },
        "self_reflection": lambda i: {"depth": 0, "text": f"thought {i}"},
    }


def make_feed(n: int, seed: int = 20260927) -> list[dict]:
    """Build ``n`` synthetic nerve events covering every mapped type.

    Types cycle deterministically (shuffled once with ``seed``); every
    ``self_reflection`` carries unique depth-0 text so the 24h
    duplicate-suppression never drops one — the benchmark measures the
    mapping work, not the refusal path.
    """
    builders = _payload_builders()
    types = list(builders)
    rng = random.Random(seed)
    order = types[:]
    rng.shuffle(order)
    events: list[dict] = []
    for i in range(n):
        etype = order[i % len(order)]
        events.append({
            "type": etype,
            "data": builders[etype](i),
            "_ts": _BASE_TS + i,
        })
    return events


# ---------------------------------------------------------------------------
# Synthetic memory tree
# ---------------------------------------------------------------------------

_WORDS = (
    "heathen third path frith wyrd hamingja forge anchor belief memory "
    "bridge mirror nerve heartbeat slice audit doc test budget corpus scale "
    "volmarr unnr longhall kindred work rest mead saga rune seidr galdr "
    "world tree root branch leaf stone fire water wind home road sky"
).split()


def _sentence(rng: random.Random, lo: int = 8, hi: int = 22) -> str:
    return " ".join(rng.choice(_WORDS) for _ in range(rng.randint(lo, hi)))


def _bank_bullet(rng: random.Random, i: int) -> str:
    tag = rng.choice(["", "[fact|high] ", "[event|medium] ", "[opinion|low] "])
    text = f"- {tag}{_sentence(rng)} (src: memory/2026-09-2{rng.randint(0,6)}.md:{i})"
    if i % 97 == 0:  # a supersedes pair, like the real bank's versioning
        text += f"\n- supersedes: {_sentence(rng, 6, 10)} (src: memory/bank/old.md:{i})"
    return text


def build_memory_tree(home: Path, scale: int = 1,
                      now: datetime | None = None) -> Path:
    """Write a synthetic memory corpus under ``home``; return ``home``.

    ``scale`` multiplies every count (scale=1 ≈ the real 2026-09-27
    corpus; scale=10 is the T3-P3 scale input). Daily logs cover the
    seven days ending at ``now`` (UTC when omitted) so they line up
    with ``parse_memory_beliefs(now=...)``'s 7-day window.
    """
    rng = random.Random(4242 + scale)
    now = now or datetime.now(timezone.utc)
    home = Path(home)
    mem = home / "memory"
    (mem / "bank").mkdir(parents=True, exist_ok=True)
    (mem / "people").mkdir(parents=True, exist_ok=True)

    # 1. MEMORY.md — plain bullets; a few carry standing-rule markers.
    lines = ["# MEMORY.md (synthetic)", ""]
    for i in range(CORPUS["memory_md_bullets"] * scale):
        prefix = "- Standing rule: " if i % 15 == 0 else "- "
        lines.append(f"{prefix}{_sentence(rng)}.")
    (home / "MEMORY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # 2. The bank — tagged claims with (src:) cites, split over N files.
    total = CORPUS["bank_bullets"] * scale
    per_file = total // CORPUS["bank_files"]
    for f in range(CORPUS["bank_files"]):
        count = per_file + (total % CORPUS["bank_files"] if f == 0 else 0)
        body = [f"# bank{f}.md (synthetic)", ""]
        body += [_bank_bullet(rng, i) for i in range(count)]
        (mem / "bank" / f"bank{f}.md").write_text(
            "\n".join(body) + "\n", encoding="utf-8")

    # 3. Daily logs — the seven days ending at ``now``.
    per_day = (CORPUS["daily_bullets"] * scale) // CORPUS["daily_logs"]
    for d in range(CORPUS["daily_logs"]):
        day = (now - timedelta(days=d)).strftime("%Y-%m-%d")
        body = [f"# {day} (synthetic)", ""]
        for i in range(per_day):
            tag = "[event|high] " if i % 4 == 0 else ""
            body.append(f"- {tag}{_sentence(rng)}.")
        (mem / f"{day}.md").write_text("\n".join(body) + "\n",
                                       encoding="utf-8")

    # 4. People pages — frontmatter summary + section bullets, one per
    # PERSON_ROSTER slug (INDEX.md is never parsed; not generated).
    for slug in CORPUS["people_slugs"]:
        page = [
            "---",
            f"display_name: {slug.title()}",
            f"summary: Synthetic page for {slug}, benchmark fixture.",
            "---",
            "",
            f"# {slug.title()}",
            "",
            "## Facts",
        ]
        page += [f"- {_sentence(rng)}." for _ in
                 range(CORPUS["people_bullets"] * scale)]
        page += ["", "## History", ""]
        page += [f"- {_sentence(rng)}." for _ in
                 range(CORPUS["people_bullets"] * scale // 2)]
        (mem / "people" / f"{slug}.md").write_text(
            "\n".join(page) + "\n", encoding="utf-8")
    return home
