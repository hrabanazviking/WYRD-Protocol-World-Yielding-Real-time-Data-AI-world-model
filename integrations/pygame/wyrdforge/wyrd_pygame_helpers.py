"""wyrd_pygame_helpers.py — Pure-logic helpers for the WYRD pygame bridge.

No external dependencies. These functions can be imported and unit-tested
without pygame, wyrdforge, or a running WyrdHTTPServer.
"""
from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# Persona ID normalisation (universal WYRD algorithm)
# ---------------------------------------------------------------------------

def normalize_persona_id(name: str) -> str:
    """Convert any string to a valid WYRD persona_id.

    Rules:
    - Lowercase
    - Non-alphanumeric characters → ``_``
    - Consecutive underscores collapsed to one
    - Leading / trailing underscores stripped
    - Maximum 64 characters

    Examples::

        normalize_persona_id("Sigrid Stormborn")  # → "sigrid_stormborn"
        normalize_persona_id("NPC #42!")          # → "npc_42"
        normalize_persona_id("")                  # → ""
    """
    if not name:
        return ""
    result = name.lower()
    result = re.sub(r"[^a-z0-9_]", "_", result)
    result = re.sub(r"_+", "_", result)
    result = result.strip("_")
    return result[:64]


# ---------------------------------------------------------------------------
# JSON string escaping
# ---------------------------------------------------------------------------

def escape_json(s: str) -> str:
    """Escape a string for safe inclusion inside a JSON string literal.

    Handles: ``"`` ``\\`` ``\\b`` ``\\f`` ``\\n`` ``\\r`` ``\\t`` and
    control characters (U+0000–U+001F).
    """
    if s is None:
        return ""
    out: list[str] = []
    for ch in s:
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\b":
            out.append("\\b")
        elif ch == "\f":
            out.append("\\f")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return "".join(out)


# ---------------------------------------------------------------------------
# Request body builders
# ---------------------------------------------------------------------------

def build_query_body(persona_id: str, user_input: str) -> str:
    """Build a JSON body for ``POST /query``.

    Falls back to a default prompt when *user_input* is blank.
    """
    if not user_input or not user_input.strip():
        user_input = "What is the current world state?"
    return (
        f'{{"persona_id":"{escape_json(persona_id)}",'
        f'"user_input":"{escape_json(user_input)}",'
        f'"use_turn_loop":false}}'
    )


def build_observation_body(title: str, summary: str) -> str:
    """Build a JSON body for ``POST /event`` (observation type)."""
    return (
        '{"event_type":"observation","payload":{'
        f'"title":"{escape_json(title)}",'
        f'"summary":"{escape_json(summary)}"'
        "}}"
    )


def build_fact_body(subject_id: str, key: str, value: str) -> str:
    """Build a JSON body for ``POST /event`` (fact type)."""
    return (
        '{"event_type":"fact","payload":{'
        f'"subject_id":"{escape_json(subject_id)}",'
        f'"key":"{escape_json(key)}",'
        f'"value":"{escape_json(value)}"'
        "}}"
    )


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def parse_response(json_str: str) -> str:
    """Extract the ``response`` field from a WyrdHTTPServer JSON reply.

    Returns an empty string on any parse failure.
    """
    if not json_str:
        return ""
    m = re.search(r'"response"\s*:\s*"((?:[^"\\]|\\.)*)"', json_str)
    if m:
        raw = m.group(1)
        # Unescape basic JSON escapes
        raw = raw.replace('\\"', '"')
        raw = raw.replace("\\\\", "\\")
        raw = raw.replace("\\n", "\n")
        raw = raw.replace("\\r", "\r")
        raw = raw.replace("\\t", "\t")
        return raw
    return ""


# ---------------------------------------------------------------------------
# Fact list parsing
# ---------------------------------------------------------------------------

class WyrdFact:
    """A single subject/key/value fact returned by ``GET /facts``."""

    __slots__ = ("subject_id", "key", "value")

    def __init__(self, subject_id: str, key: str, value: str) -> None:
        self.subject_id = subject_id
        self.key = key
        self.value = value

    def __repr__(self) -> str:  # pragma: no cover
        return f"WyrdFact({self.subject_id!r}, {self.key!r}, {self.value!r})"


def to_facts(json_str: str) -> list[WyrdFact]:
    """Parse the ``GET /facts`` JSON array into a list of :class:`WyrdFact`.

    Returns an empty list on any parse failure.
    """
    if not json_str:
        return []
    results: list[WyrdFact] = []
    pattern = re.compile(
        r'"subject_id"\s*:\s*"([^"]*)"'
        r'.*?"key"\s*:\s*"([^"]*)"'
        r'.*?"value"\s*:\s*"([^"]*)"',
        re.DOTALL,
    )
    for m in pattern.finditer(json_str):
        results.append(WyrdFact(m.group(1), m.group(2), m.group(3)))
    return results
