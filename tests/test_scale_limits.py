"""Track 3 P3 — honest scale testing (docs/scale-limits.md is the record).

The module builds the scaled inputs and measures each hot path; the
DOC holds the judgment (breaking points in numbers), the TEST holds
the machinery — it fails if a scale run *errors*, never if one is
merely slow. Cross-checks that every scenario is named in the doc,
so a breaking point can never be measured and then silently dropped.

Scenarios (fixtures from tests/perf_fixtures.py):
- S1: 100k-event feed (10× the B1 benchmark feed) through
  build_from_events.
- S2: 10× memory corpus through parse_memory_beliefs, inside a
  generous machinery cap (it must complete, not be fast).
- S3: 2× world anchor density as the repo-side analogue of the 2×
  horizon — summary() cost at 1×/2× (context, no budget). The real
  24h Verdandi-side projection horizon is observed in the mirror, not
  repo-benchmarked; the doc says so.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from tests.perf_fixtures import build_memory_tree, make_feed
from wyrdforge.bridges.verdandi_bridge import (
    VerdandiBridge,
    parse_memory_beliefs,
)

DOC = Path(__file__).resolve().parents[1] / "docs" / "scale-limits.md"

SCALE_FEED_N = 100_000
CORPUS_SCALE = 10
# Machinery caps: the test must not hang forever; slowness is the
# doc's judgment, not a failure here.
S2_MACHINERY_CAP_S = 300


def _doc_text() -> str:
    assert DOC.exists(), "docs/scale-limits.md is missing"
    return DOC.read_text(encoding="utf-8")


def test_s1_scaled_feed_replay_completes():
    events = make_feed(SCALE_FEED_N)
    bridge = VerdandiBridge()
    t0 = time.perf_counter()
    fresh = bridge.build_from_events(events)
    elapsed = time.perf_counter() - t0
    assert fresh is not None
    per_event_us = elapsed / SCALE_FEED_N * 1e6
    assert per_event_us > 0  # the machinery ran, end to end
    text = _doc_text()
    assert "100,000-event feed" in text, (
        "S1 ran but docs/scale-limits.md does not record the "
        "100,000-event scenario — a measurement without a record "
        "is a silently accepted breaking point"
    )


def test_s2_scaled_corpus_parse_completes(tmp_path):
    now = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
    home = build_memory_tree(tmp_path, scale=CORPUS_SCALE, now=now)
    t0 = time.perf_counter()
    out = parse_memory_beliefs(home=str(home), now=now)
    elapsed = time.perf_counter() - t0
    assert elapsed < S2_MACHINERY_CAP_S, (
        f"10× corpus parse took {elapsed:.0f}s — machinery cap exceeded"
    )
    assert "person:volmarr" in out
    text = _doc_text()
    assert "10× memory corpus" in text, (
        "S2 ran but docs/scale-limits.md does not record the 10× "
        "corpus scenario"
    )


def test_s3_anchor_density_projection_cost():
    costs = {}
    for mult in (1, 2):
        events = make_feed(2000 * mult)
        bridge = VerdandiBridge().build_from_events(events)
        t0 = time.perf_counter()
        projection = bridge.summary()
        costs[mult] = time.perf_counter() - t0
        assert isinstance(projection, dict) and projection
    assert costs[2] >= 0  # context measurement, no budget to breach
    text = _doc_text()
    assert "anchor density" in text, (
        "S3 ran but docs/scale-limits.md does not record the "
        "horizon analogue"
    )


def test_every_scenario_recorded_in_doc():
    """The doc must name every breaking point or measured headroom —
    zero silently accepted."""
    text = _doc_text()
    for anchor in ("100,000-event feed", "10× memory corpus",
                   "anchor density", "breaking point"):
        assert anchor in text, (
            f"docs/scale-limits.md does not cover {anchor!r}"
        )
