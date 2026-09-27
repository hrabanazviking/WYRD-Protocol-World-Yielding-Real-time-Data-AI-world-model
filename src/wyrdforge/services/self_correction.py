"""Self-correction engine — Track 7, Phase 2 (confidence with teeth).

THE HONEST LIMIT (T7-P4, stated where the corrections happen, not just in
the roadmap): this module adjusts confidence on the repo's own canonical
facts. When it steps a belief down or reports "I was wrong", what changes is
the *worker's account* of the world — a better account, not an objective transcript.
The model *changed its mind*; it did not *always know*. This is not a flaw to fix; it is the boundary of what a self-model can honestly
claim.

Confidence rules (T7-P2) — the constants in code with tests, not vibes:
    CONFIDENCE_STEP_DOWN  = 0.2 — one contradiction steps down 0.2, never to
        zero in one blow (one contradiction can be noise), downward, visibly.
    CONFIDENCE_STEP_UP    = 0.1 — re-confirmation rebuilds trust slower than
        it breaks, on purpose.
    UNCERTAINTY_THRESHOLD = 0.3 — strictly below 0.3, a fact stops being
        asserted and renders as *uncertain*, with its history.

Roadmap-arithmetic note (named, not silent): the roadmap's acceptance says
"contradict three times, 0.9 -> 0.7 -> 0.5 -> uncertain" — but three steps
of 0.2 from 0.9 reach 0.3, and the threshold is *strictly* below 0.3, so
three contradictions do not reach uncertainty. The constants above are the
load-bearing part; the "three times" is illustrative. The pinned behavior is
four contradictions: 0.9 -> 0.7 -> 0.5 -> 0.3 -> 0.1 (uncertain).

Writer discipline: the writer of TruthMeta.confidence_history is
SelfCorrectionService.contradict() / .reconfirm() (module functions below).
Readers are PassiveOracle.build_context_packet and the contradiction ledger
(docs/contradiction-ledger.md). No other writer touches confidence — the
memory tree is never written by the heartbeat (architecture anti-loop guard:
automatic belief rewriting from divergences is forbidden; the divergence
fires loudly, the correction follows the confidence rules).

History convention: history[0] is the confidence the chain started from;
each later entry is the post-step value. So contradict(0.9) seeds
[0.9, 0.7] — the full chain the oracle renders as "was 0.9 -> 0.7".
"""
from __future__ import annotations

CONFIDENCE_STEP_DOWN: float = 0.2
CONFIDENCE_STEP_UP: float = 0.1
UNCERTAINTY_THRESHOLD: float = 0.3


def _clamp(value: float) -> float:
    """Keep confidence inside [0.0, 1.0].

    Rounded to 10 decimals so the uncertainty-threshold comparison is exact,
    not float-dust-sensitive: the documented chain 0.9 -> 0.7 -> 0.5 -> 0.3
    -> 0.1 is literal, and 0.3 stays strictly above the 0.3 threshold.
    """
    return round(max(0.0, min(1.0, value)), 10)


def contradict(
    confidence: float,
    history: list[float] | None = None,
) -> tuple[float, list[float]]:
    """Step confidence down one contradiction.

    Steps down CONFIDENCE_STEP_DOWN, floored at 0.0 — never to zero in one
    blow, because one contradiction can be noise. Appends the new value to
    the history (seeding it with the starting confidence when empty).

    Returns (new_confidence, new_history). Pure: inputs are never mutated.
    """
    hist = list(history) if history else [confidence]
    new_confidence = _clamp(confidence - CONFIDENCE_STEP_DOWN)
    hist.append(new_confidence)
    return new_confidence, hist


def reconfirm(
    confidence: float,
    history: list[float] | None = None,
) -> tuple[float, list[float]]:
    """Step confidence up one re-confirmation.

    Steps up CONFIDENCE_STEP_UP, capped at 1.0 — trust rebuilds slower than
    it breaks, on purpose. History convention matches contradict().

    Returns (new_confidence, new_history). Pure: inputs are never mutated.
    """
    hist = list(history) if history else [confidence]
    new_confidence = _clamp(confidence + CONFIDENCE_STEP_UP)
    hist.append(new_confidence)
    return new_confidence, hist


def is_uncertain(confidence: float) -> bool:
    """True when confidence is *strictly* below UNCERTAINTY_THRESHOLD.

    The roadmap's "< 0.3", not "<=": a fact at exactly 0.3 still renders
    asserted. This strictness is load-bearing — see the roadmap-arithmetic
    note in the module docstring.
    """
    return confidence < UNCERTAINTY_THRESHOLD


def format_confidence_history(history: list[float]) -> str:
    """Render a confidence chain the way the oracle shows it: '0.9 -> 0.7'."""
    return " -> ".join(f"{v:.10g}" for v in history)


def format_correction(believed: str, reality_showed: str, believes_now: str) -> str:
    """The T7-P3 announcement: all three facts, once, plainly.

    Never a rewrite of history — the old belief stays in the ledger with its
    confidence history. The model *changed its mind*; it did not *always know*.
    """
    return (
        f"Correction: believed '{believed}'; "
        f"reality showed '{reality_showed}'; "
        f"now believes '{believes_now}'."
    )


class SelfCorrectionService:
    """Thin object wrapper around the module functions.

    This service is the canonical writer of TruthMeta.confidence_history
    (see the module docstring for the writer discipline). It holds no
    state — every method is pure.
    """

    def contradict(
        self,
        confidence: float,
        history: list[float] | None = None,
    ) -> tuple[float, list[float]]:
        """Step confidence down one contradiction. See contradict()."""
        return contradict(confidence, history)

    def reconfirm(
        self,
        confidence: float,
        history: list[float] | None = None,
    ) -> tuple[float, list[float]]:
        """Step confidence up one re-confirmation. See reconfirm()."""
        return reconfirm(confidence, history)

    def is_uncertain(self, confidence: float) -> bool:
        """True when strictly below the threshold. See is_uncertain()."""
        return is_uncertain(confidence)

    def format_correction(
        self, believed: str, reality_showed: str, believes_now: str
    ) -> str:
        """Format the three-fact announcement. See format_correction()."""
        return format_correction(believed, reality_showed, believes_now)
