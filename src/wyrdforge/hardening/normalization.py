"""normalization.py — Unicode-safe persona_id normalisation guard.

The base normalisation algorithm (lowercase → replace non-alnum with ``_`` →
collapse → strip → truncate 64) works correctly for ASCII.  This module adds
a pre-processing layer that handles:

- Unicode letters and digits (kept, then lowercased via NFKD + ASCII encode)
- Emoji and other non-BMP characters (replaced with ``_``)
- NUL bytes and other control characters (stripped before processing)
- Extremely long inputs (truncated before regex to avoid ReDoS)
- Right-to-left override and other invisible Unicode formatting characters

Usage::

    from wyrdforge.hardening.normalization import safe_persona_id

    pid = safe_persona_id("Björn 🐺 Járnsíða")
    # → "bjorn_jarnsida"   (emoji removed, diacritics stripped)
"""
from __future__ import annotations

import re
import unicodedata

# Maximum length considered before stripping — prevents pathological regex input
_MAX_INPUT = 512


def safe_persona_id(name: str | bytes | None) -> str:
    """Convert any string to a safe WYRD ``persona_id``.

    Extends the standard normalisation with full Unicode safety:

    1. Accept ``bytes`` (UTF-8 decode, errors=replace).
    2. Strip NUL bytes and C0/C1 control characters.
    3. Remove Unicode formatting / invisible characters (category Cf, Cn).
    4. NFKD decomposition → encode ASCII with ``errors='ignore'`` (strips diacritics).
    5. Standard normalisation: lowercase → ``[^a-z0-9_]`` → ``_`` → collapse → strip.
    6. Truncate to 64 characters.

    Args:
        name: Input string, bytes, or None.

    Returns:
        A normalised persona_id string.  Empty string if input is empty or
        produces no valid characters after normalisation.
    """
    if name is None:
        return ""

    # Bytes → str
    if isinstance(name, bytes):
        name = name.decode("utf-8", errors="replace")

    # Guard against pathologically long input
    name = name[:_MAX_INPUT]

    # Strip NUL and control characters (except ordinary space/tab which are
    # handled by the replacement step below)
    name = _strip_controls(name)

    # Remove Unicode formatting characters (invisible, RTL overrides, etc.)
    name = _strip_format_chars(name)

    # NFKD → ASCII (strips diacritics: é→e, ö→o, ñ→n, etc.)
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", errors="ignore").decode("ascii")

    # Standard normalisation
    result = name.lower()
    result = re.sub(r"[^a-z0-9_]", "_", result)
    result = re.sub(r"_+", "_", result)
    result = result.strip("_")
    return result[:64]


def _strip_controls(s: str) -> str:
    """Remove NUL bytes and C0/C1 control characters, keeping printable chars."""
    out: list[str] = []
    for ch in s:
        cp = ord(ch)
        if cp == 0:
            continue  # NUL
        cat = unicodedata.category(ch)
        if cat.startswith("C") and cat != "Cf":
            # Cc = control, Cs = surrogate, Co = private use — skip
            # Cf (format) handled separately
            continue
        out.append(ch)
    return "".join(out)


def _strip_format_chars(s: str) -> str:
    """Remove Unicode Cf (format) characters like RTL overrides, zero-width chars."""
    return "".join(ch for ch in s if unicodedata.category(ch) != "Cf")


def is_valid_persona_id(pid: str) -> bool:
    """Return True if *pid* is already a valid normalised persona_id.

    A valid ID:
    - Is non-empty
    - Contains only ``[a-z0-9_]``
    - Does not start or end with ``_``
    - Has no consecutive underscores
    - Is at most 64 characters
    """
    if not pid or len(pid) > 64:
        return False
    if not re.fullmatch(r"[a-z0-9_]+", pid):
        return False
    if pid.startswith("_") or pid.endswith("_"):
        return False
    if "__" in pid:
        return False
    return True
