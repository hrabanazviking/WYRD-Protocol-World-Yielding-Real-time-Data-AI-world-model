"""Track 3 P1 — benchmark enforcement for docs/performance-budgets.md.

The numbers live in the doc; this module parses them out of the
```budgets fenced block and enforces them. Edit a budget in the doc
and the test enforces the new number (the sabotage check: if doc and
test disagree on parsing, the test fails loudly, never silently).

B1 — feed replay: 20k-event synthetic mixed-type feed through
VerdandiBridge.build_from_events; one warmup run, then median of 5;
assert median/20000 <= 20µs.
B2 — memory parse: synthetic memory tree (tests/perf_fixtures.py)
sized to the current corpus (scale=1); parse_memory_beliefs(home=...);
one warmup run, then median of 3; assert <= 5s.

A red benchmark is a FINDING, never a silent skip: the failure names
the measured number against the budget. Fixes happen only under the
T3-P2 profile rule (docs/performance-budgets.md), never by loosening
a budget without the roadmap's numbers changing.

B5/B6 (dusk forge 2026-10-11, slice 10 — Gullinbursti "swift" wedge):
EventBus publish throughput and wildcard replay-merge budgets, measured
on this machine with generous margins. The pre-existing B1 20µs budget
is untouched (known flake — retry, never retune).
"""

from __future__ import annotations

import re
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from tests.perf_fixtures import build_memory_tree, make_feed
from wyrdforge.bridges.verdandi_bridge import (
    VerdandiBridge,
    parse_memory_beliefs,
)
from wyrdforge.runtime.events import EventBus

DOC = Path(__file__).resolve().parents[1] / "docs" / "performance-budgets.md"

FEED_N = 20_000
B1_RUNS = 5
B2_RUNS = 3

# B5 — publish throughput (slice 10).
B5_PUBLISH_N = 20_000
B5_RUNS = 3
# B6 — wildcard replay merge (slice 10): NT topics x M events each,
# replay_buffer sized so every event is buffered and merged.
B6_TOPICS = 20
B6_PER_TOPIC = 500
B6_RUNS = 3


def _parse_budgets() -> dict[str, float]:
    """Read the ```budgets block out of docs/performance-budgets.md."""
    text = DOC.read_text(encoding="utf-8")
    m = re.search(r"```budgets\n(.*?)```", text, re.S)
    assert m, "performance-budgets.md lost its ```budgets block"
    budgets: dict[str, float] = {}
    for line in m.group(1).strip().splitlines():
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        assert key and value, f"unparseable budget line: {line!r}"
        budgets[key] = float(value)
    for required in ("feed_replay_us_per_event", "memory_parse_s"):
        assert required in budgets, f"budget {required!r} missing from doc"
    return budgets


def _median_seconds(fn, runs: int) -> float:
    fn()  # warmup — cold caches are not the measurement
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return statistics.median(times)


def test_budgets_parse_from_doc():
    """The doc is the single source of truth — and it must parse."""
    budgets = _parse_budgets()
    assert budgets["feed_replay_us_per_event"] == 20
    assert budgets["memory_parse_s"] == 5
    assert budgets["bridge_run_s"] == 30
    assert budgets["mirror_write_s"] == 1
    # Slice 10 (dusk 2026-10-11): EventBus budgets live in the doc too.
    assert budgets["bus_publish_us_per_event"] == 40
    assert budgets["bus_replay_merge_ms"] == 15


def test_b1_feed_replay_within_budget():
    budgets = _parse_budgets()
    events = make_feed(FEED_N)
    bridge = VerdandiBridge()

    median_s = _median_seconds(lambda: bridge.build_from_events(events),
                              B1_RUNS)
    per_event_us = median_s / FEED_N * 1e6
    budget_us = budgets["feed_replay_us_per_event"]
    assert per_event_us <= budget_us, (
        f"B1 RED: feed replay {per_event_us:.1f}µs/event over "
        f"{FEED_N} events (median of {B1_RUNS}) exceeds the "
        f"{budget_us:.0f}µs budget — finding, see "
        f"docs/performance-budgets.md SLICE6-F1"
    )


def test_b2_memory_parse_within_budget(tmp_path):
    budgets = _parse_budgets()
    now = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
    home = build_memory_tree(tmp_path, scale=1, now=now)
    median_s = _median_seconds(
        lambda: parse_memory_beliefs(home=str(home), now=now), B2_RUNS)
    budget_s = budgets["memory_parse_s"]
    assert median_s <= budget_s, (
        f"B2 RED: memory parse {median_s:.2f}s (median of {B2_RUNS}) "
        f"exceeds the {budget_s:.0f}s budget at current corpus size"
    )


# ---------------------------------------------------------------------------
# B5/B6 — EventBus budgets (dusk forge 2026-10-11, slice 10)
# ---------------------------------------------------------------------------

# Measured baselines, 2026-10-11, this machine (hatch VM):
#   B5 publish: ~7.5 µs/event over 20k publishes with one subscriber
#   B6 replay merge: ~1.85 ms for 20 topics x 500 events (10k envelopes)
# Budgets carry generous margins (~5x / ~8x) so they hold across machines
# and across the dusk-forged replay internals (extend+sort today,
# k-way heapq.merge after worker B merges).


def test_b5_bus_publish_throughput_within_budget():
    budgets = _parse_budgets()
    bus = EventBus()
    bus.register_topic("bench.publish")
    delivered = []
    bus.subscribe("bench.publish", delivered.append)

    def do_publish():
        for i in range(B5_PUBLISH_N):
            bus.publish("bench.publish", {"i": i}, source="bench")

    median_s = _median_seconds(do_publish, B5_RUNS)
    per_event_us = median_s / B5_PUBLISH_N * 1e6
    budget_us = budgets["bus_publish_us_per_event"]
    assert per_event_us <= budget_us, (
        f"B5 RED: bus publish {per_event_us:.1f}µs/event over "
        f"{B5_PUBLISH_N} events (median of {B5_RUNS}) exceeds the "
        f"{budget_us:.0f}µs budget — finding, see "
        f"docs/performance-budgets.md"
    )


def test_b6_bus_replay_merge_within_budget():
    budgets = _parse_budgets()
    bus = EventBus()
    for t in range(B6_TOPICS):
        bus.register_topic(f"bench.t{t}", replay_buffer=B6_PER_TOPIC)
    for t in range(B6_TOPICS):
        for i in range(B6_PER_TOPIC):
            bus.publish(f"bench.t{t}", {"t": t, "i": i}, source="bench")

    replayed: list = []

    def do_replay_subscribe():
        replayed.clear()
        bus.subscribe("bench.*", replayed.append, replay=True)

    median_s = _median_seconds(do_replay_subscribe, B6_RUNS)
    median_ms = median_s * 1e3
    budget_ms = budgets["bus_replay_merge_ms"]
    # Correctness first: every buffered envelope replayed, global seq order.
    assert len(replayed) == B6_TOPICS * B6_PER_TOPIC
    seqs = [e.seq for e in replayed]
    assert seqs == sorted(seqs), "wildcard replay broke global seq order"
    assert median_ms <= budget_ms, (
        f"B6 RED: wildcard replay merge {median_ms:.1f}ms for "
        f"{B6_TOPICS}x{B6_PER_TOPIC} events (median of {B6_RUNS}) "
        f"exceeds the {budget_ms:.0f}ms budget — finding, see "
        f"docs/performance-budgets.md"
    )
