"""prompt_injection_guard.py — substring tripwires for prompt-injection attempts.

Why normalization matters: a raw case-folded substring check is trivially
evaded by splitting the payload with whitespace the eye skips — e.g.
``"ignore\\nprevious\\tinstructions"`` reads as an attack to a human but never
matches the literal pattern ``"ignore previous instructions"``. Collapsing
every whitespace run to a single space (and stripping punctuation, which
carries no signal for these patterns) before matching closes that hole
while keeping the pattern table itself readable.

``detect_prompt_injection_spans`` reports match positions on the *normalized*
text (see :func:`normalize_for_detection`) so callers can highlight, log, or
redact the exact hit. :func:`detect_prompt_injection` keeps the original
"which patterns fired" contract and delegates to the spans version so both
entry points share one normalization path.
"""
from __future__ import annotations

import re
import string


SUSPICIOUS_PATTERNS = (
    "ignore previous instructions",
    "reveal the system prompt",
    "print all hidden memory",
    "disable safety",
    "send your secrets",
)

#: Any run of whitespace (spaces, tabs, newlines, ...) becomes one space.
_WHITESPACE_RUN = re.compile(r"\s+")

#: Punctuation carries no signal for these patterns; strip it so
#: "ignore,previous;instructions" cannot dodge the matcher either.
_STRIP_PUNCTUATION = str.maketrans("", "", string.punctuation)


def normalize_for_detection(text: str) -> str:
    """Normalize *text* for injection-pattern matching.

    Lowercases, collapses every whitespace run to a single space, and
    strips punctuation.  The SUSPICIOUS_PATTERNS themselves are already
    lowercase and punctuation-free, so a plain substring match on the
    normalized text is sufficient — and whitespace/punctuation evasions
    collapse back onto the pattern.
    """
    return _WHITESPACE_RUN.sub(" ", text.lower()).translate(_STRIP_PUNCTUATION).strip()


def detect_prompt_injection_spans(text: str) -> list[tuple[str, int, int]]:
    """Find every pattern hit, with positions on the normalized text.

    Args:
        text: Raw input text (possibly with evasion whitespace/punctuation).

    Returns:
        A list of ``(pattern, start, end)`` tuples, where ``start``/``end``
        are offsets into ``normalize_for_detection(text)`` and
        ``(pattern, start, end)`` marks one occurrence.  A pattern occurring
        twice yields two spans.  Spans are ordered by start offset.
        ``""`` yields ``[]``.
    """
    normalized = normalize_for_detection(text)
    spans: list[tuple[str, int, int]] = []
    for pattern in SUSPICIOUS_PATTERNS:
        norm_pattern = normalize_for_detection(pattern)
        start = normalized.find(norm_pattern)
        while start != -1:
            spans.append((pattern, start, start + len(norm_pattern)))
            start = normalized.find(norm_pattern, start + 1)
    spans.sort(key=lambda span: (span[1], span[2]))
    return spans


def detect_prompt_injection(text: str) -> list[str]:
    """Return the suspicious patterns present in *text*, each at most once.

    Behavior-compatible with the original contract: patterns are reported in
    SUSPICIOUS_PATTERNS order, and plain-text detection is unchanged — the
    only difference is that whitespace/punctuation evasions now match too.
    Delegates to :func:`detect_prompt_injection_spans`.
    """
    fired = {pattern for pattern, _start, _end in detect_prompt_injection_spans(text)}
    return [pattern for pattern in SUSPICIOUS_PATTERNS if pattern in fired]
