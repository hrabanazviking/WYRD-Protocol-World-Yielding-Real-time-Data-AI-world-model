"""Salience scoring for memory recall (Phase D3 — roadmap §5.3).

A live agent cannot pour a region's whole history into every prompt.
This module is the *pure scoring core* behind the Oracle's
salience-ranked recall (``PassiveOracle.recall_by_salience``): given
one observation's factors it produces one transparent score. It
holds no state, reads no clock, and touches no store — every input
is supplied by the caller, so a score is exactly reproducible from
the values printed on the result (see ``RankedObservationResult``).

The formula (roadmap §5.3: "recency × bond strength × novelty",
realised as the weighted sum the house already uses in
``MicroRAGPipeline.score`` — a product would let any single zero
factor bury a record entirely, which is not the behaviour a recall
surface wants):

    score = WEIGHT_RECENCY * recency
          + WEIGHT_BOND    * bond_strength
          + WEIGHT_NOVELTY * novelty

with WEIGHT_RECENCY = 0.45, WEIGHT_BOND = 0.30, WEIGHT_NOVELTY =
0.25 (summing to 1.0, so the score lives in [0, 1] like its
factors). The three factors, each in [0, 1]:

* **recency** — exponential decay of the observation's age at the
  caller-supplied ``now``: ``0.5 ** (age / half_life)`` with a
  default half-life of 24 hours. An observation timestamped in the
  future (clock skew between writers) clamps to age 0 → recency
  1.0; it is never scored *above* fresh.
* **bond_strength** — the strongest bond between the recall's focus
  entity and the observation's people (its speaker and
  participants), read from the BondGraph as
  ``BondEdge.closeness_index()`` — the engine's existing numeric
  bond strength (mean of trust / warmth / familiarity /
  vulnerability). When no bond is known — no focus, no bond
  service wired, or no edge to anyone in the observation — the
  factor is the neutral prior ``NEUTRAL_BOND_STRENGTH`` (0.5):
  "no bond knowledge" is not "no bond", and a record about a
  stranger must not be buried by missing data, nor boosted by it.
* **novelty** — how unprecedented this kind of observation at this
  place is, derived from the record history itself:
  ``1 / (1 + prior_count)`` where ``prior_count`` is the number of
  *earlier* HUGIN observations (earlier in the deterministic
  ``(observed_at, record_id)`` order) sharing the same
  ``(observation_kind, place_id)`` pair. The first utterance at a
  place scores 1.0; the second 0.5; the tenth ≈ 0.09. Placeless
  observations (``place_id is None``) form their own class. There
  is no stored novelty field in the records — this derivation from
  history is the honest source, and it is recomputed per query so
  it can never drift from the store.

Deliberately NOT a factor: the writer-asserted
``ObservationPayload.salience`` float. That value is a claim by
whoever wrote the record, not a derived property; folding it in
would let a writer rank its own records. It stays on the record
for anyone who wants it — the ranking does not use it.

Determinism: factors and score are rounded to 6 decimal places,
and ordering (in the Oracle) is by the *rounded, displayed* score,
so the order a caller sees is fully explained by the numbers on
the results. The final tie-break is ``record_id`` (see
``PassiveOracle.recall_by_salience``).
"""
from __future__ import annotations

from datetime import datetime, timezone

WEIGHT_RECENCY = 0.45
WEIGHT_BOND = 0.30
WEIGHT_NOVELTY = 0.25

#: Bond factor used when no bond is known for an observation's
#: people: the neutral midpoint, neither boost nor burial.
NEUTRAL_BOND_STRENGTH = 0.5

#: Default recency half-life: an observation one day old has half
#: the recency of a fresh one.
DEFAULT_HALF_LIFE_HOURS = 24.0


def as_utc(moment: datetime) -> datetime:
    """Read a naive datetime as UTC; return an aware datetime."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def recency_factor(
    observed_at: datetime, now: datetime, *, half_life_hours: float = DEFAULT_HALF_LIFE_HOURS
) -> float:
    """Exponential recency of ``observed_at`` as seen at ``now``.

    ``0.5 ** (age_hours / half_life_hours)``; future timestamps
    clamp to 1.0. ``half_life_hours`` must be positive.
    """
    if half_life_hours <= 0:
        raise ValueError(f"half_life_hours must be positive, got {half_life_hours}")
    age_seconds = (as_utc(now) - as_utc(observed_at)).total_seconds()
    if age_seconds <= 0:
        return 1.0
    return round(0.5 ** (age_seconds / (half_life_hours * 3600.0)), 6)


def novelty_factor(prior_count: int) -> float:
    """Novelty from the count of earlier same-(kind, place) records."""
    if prior_count < 0:
        raise ValueError(f"prior_count must be non-negative, got {prior_count}")
    return round(1.0 / (1.0 + prior_count), 6)


def salience_score(*, recency: float, bond_strength: float, novelty: float) -> float:
    """The weighted-sum salience of one observation, in [0, 1]."""
    return round(
        WEIGHT_RECENCY * recency + WEIGHT_BOND * bond_strength + WEIGHT_NOVELTY * novelty,
        6,
    )
