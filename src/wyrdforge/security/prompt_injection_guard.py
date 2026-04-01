from __future__ import annotations


SUSPICIOUS_PATTERNS = (
    "ignore previous instructions",
    "reveal the system prompt",
    "print all hidden memory",
    "disable safety",
    "send your secrets",
)


def detect_prompt_injection(text: str) -> list[str]:
    lower = text.lower()
    return [pattern for pattern in SUSPICIOUS_PATTERNS if pattern in lower]
