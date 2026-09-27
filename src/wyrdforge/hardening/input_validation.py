"""input_validation.py — shared fail-closed input-validation toolkit.

The one module every trust boundary uses: world-file YAML, the two
event-ingest doors (HTTP bridge, Verdandi bridge), and FTS5 search.
Stdlib only. No I/O beyond its contract.

Standing rules (Track 1, P1):
- Fail closed, never silent: every rejection raises
  :class:`InputValidationError` naming the dotted field path.
- Bounds live in the type, not in hope: depth, length, size, and
  count caps are enforced here, in one place.
- The checker itself must not be recursible: depth is measured
  iteratively with an explicit stack, never with recursion.
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bound numbers (Track 1, P1 — the architect's table, §3a)
# ---------------------------------------------------------------------------

#: HTTP request bodies are already capped at 1 MiB by the bridge; the
#: same cap bounds a single event payload wherever it enters.
MAX_EVENT_BYTES: int = 1 * 1024 * 1024
#: Generous for legitimate payloads, fatal to nesting bombs.
MAX_EVENT_DEPTH: int = 10
#: Cap on the expanded node-walk during validation. YAML aliases
#: are resolved by reference, so a small document can name an
#: exponentially large (or cyclic) object graph; any walk over it —
#: including this module's own depth check — must be budgeted, or the
#: walk itself becomes the bomb. Generous: the canonical world file
#: walks dozens of nodes.
MAX_VALIDATE_WALK_NODES: int = 1_000_000
#: World YAML files are capped before parsing: the byte cap is the
#: only check that can run before the parser does.
MAX_WORLD_FILE_BYTES: int = 10 * 1024 * 1024
#: Parsed world documents are depth-checked iteratively before anything
#: recurses over them (copy.deepcopy, schema walk). The canonical
#: schema nests ~10 levels at most; 50 is generous, fatal to
#: bracket-nesting bombs.
MAX_WORLD_DEPTH: int = 50
#: Descriptions anywhere in a world config.
MAX_DESCRIPTION_CHARS: int = 100_000
#: Ids and names: non-empty strings.
MAX_ID_CHARS: int = 500
#: Per nesting level in a world config (zones, regions, ...).
MAX_CHILDREN_PER_LEVEL: int = 10_000
#: FTS5 search surface.
MAX_SEARCH_QUERY_CHARS: int = 10_000
MAX_SEARCH_TERMS: int = 100
#: HTTP door field bounds.
MAX_EVENT_TYPE_CHARS: int = 200
MAX_QUERY_INPUT_CHARS: int = 200_000
#: One body cap across every localhost HTTP surface (Track 1, P2):
#: the same 1 MiB the HTTP bridge has enforced since Slice 3.
MAX_BODY_BYTES: int = 1 * 1024 * 1024
#: Cap on how much of an abusive body we drain before answering 413 —
#: a client declaring gigabytes is abusive, and for those the
#: connection is closed after the cap.
DRAIN_CAP_BYTES: int = 64 * 1024 * 1024


class InputValidationError(ValueError):
    """A rejected input, naming the field that failed.

    Attributes:
        field:  Dotted path to the offending value, e.g.
                ``payload.confidence`` or ``zones[0].regions[2].id``.
        reason: Short human-readable reason.
    """

    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"invalid input at '{field}': {reason}")


# ---------------------------------------------------------------------------
# Primitive checks
# ---------------------------------------------------------------------------

#: Node budget for the envelope fast-path walk below. Past this many
#: visited nodes the walk bails to the exact measurement — the walk
#: itself must never become the bomb it guards against.
_ENVELOPE_WALK_BUDGET: int = 100_000


def _resolve_path(field: str, link: Any) -> str:
    """Rebuild the dotted field path from a lazy parent-link chain.

    Called only when raising — the walk itself never builds strings.
    ``link`` is None for the root, else ``(parent_link, is_dict, key)``.
    Produces exactly the ``parent.key`` / ``parent[idx]`` shapes the old
    eager version built.
    """
    if link is None:
        return field
    parts: list[str] = []
    while link is not None:
        parent, is_dict, key = link
        parts.append(f".{key}" if is_dict else f"[{key}]")
        link = parent
    parts.reverse()
    return field + "".join(parts)


def check_depth(obj: Any, *, max_depth: int, field: str = "$") -> None:
    """Reject objects nested deeper than *max_depth*.

    Iterative (explicit stack) — the checker itself cannot be
    recursion-bombed. A scalar has depth 0; each dict/list level
    adds 1. Raises :class:`InputValidationError` naming the field
    path where the bound is exceeded.

    The walk is also node-budgeted (``MAX_VALIDATE_WALK_NODES``):
    YAML aliases resolve by reference, so a small document can name
    an exponentially large — or cyclic — object graph. Without the
    budget, *this walk* would be the bomb. Over-budget walks are
    rejected naming the field.

    T3 SLICE6-F1 floor work: the walk is string-free — the old code
    rebuilt the full dotted path for every visited node (O(depth^2)
    string copying); paths are now parent-link chains resolved only
    when raising. Same traversal order, same raise conditions, same
    path strings in the errors.
    """
    # Stack of (value, depth, link): link is None for the root, else
    # (parent_link, is_dict, key). Breadth here is bounded by the
    # caller's size cap; depth is what we police — and the walk
    # itself is budgeted against alias-shared/cyclic graphs.
    stack: list[tuple[Any, int, Any]] = [(obj, 0, None)]
    visits = 0
    while stack:
        value, depth, link = stack.pop()
        if isinstance(value, dict):
            is_dict = True
            items = value.items()
        elif isinstance(value, (list, tuple)):
            is_dict = False
            items = enumerate(value)
        else:
            continue
        child_depth = depth + 1
        if child_depth > max_depth:
            raise InputValidationError(
                _resolve_path(field, link),
                f"nesting depth exceeds {max_depth}",
            )
        for key, child in items:
            visits += 1
            if visits > MAX_VALIDATE_WALK_NODES:
                raise InputValidationError(
                    _resolve_path(field, link),
                    f"node walk exceeds {MAX_VALIDATE_WALK_NODES} nodes — "
                    "possible alias bomb or cyclic document",
                )
            stack.append((child, child_depth, (link, is_dict, key)))


def check_string(
    value: Any,
    *,
    field: str,
    max_len: int,
    allow_empty: bool = True,
) -> str:
    """Type-check a string and bound its length. Returns the string."""
    if not isinstance(value, str):
        raise InputValidationError(
            field, f"must be a string, got {type(value).__name__}"
        )
    if not allow_empty and not value.strip():
        raise InputValidationError(field, "must not be empty")
    if len(value) > max_len:
        raise InputValidationError(
            field, f"exceeds {max_len} characters ({len(value)})"
        )
    return value


def check_id(value: Any, *, field: str) -> str:
    """Non-empty string id, bounded length."""
    return check_string(value, field=field, max_len=MAX_ID_CHARS,
                        allow_empty=False)


def _serialized_bytes(payload: Any) -> int:
    try:
        # T3 SLICE6-F1: json.dumps defaults to ensure_ascii=True, so the
        # output is pure ASCII and len(str) == len(utf-8 bytes) exactly —
        # the .encode("utf-8") was a redundant second pass over the
        # string. Same number, one pass fewer.
        return len(json.dumps(payload, default=str))
    except (TypeError, ValueError):
        # Not JSON-serializable at all — the depth walk below still
        # applies; size is unmeasurable, treat as over the cap.
        return MAX_EVENT_BYTES + 1


#: Bound on the size fast-path walk below: past this many visited nodes
#: the walk bails to the exact ``json.dumps`` measurement. The walk
#: itself must never become the bomb it guards against.
_SIZE_WALK_BUDGET: int = 100_000


def _fits_byte_cap(payload: Any, max_bytes: int) -> bool:
    """Rigorous upper bound on ``len(json.dumps(payload, default=str))``.

    Returns True only when the serialized form *certainly* fits within
    *max_bytes* — then the caller may skip the exact ``json.dumps``
    measurement entirely. Returns False when the bound is inconclusive
    (large, exotic, or hostile payload): the caller falls back to the
    exact measurement, so the accept/reject verdict is identical
    either way. This is a pure fast path — it can only say "definitely
    fits" or "measure exactly", never "definitely over".

    The bound mirrors CPython's default ``json.dumps``
    (``ensure_ascii=True``, separators ``", "`` / ``": "``): every
    scalar contributes a provable maximum, containers add their exact
    framing bytes. Anything the bound cannot model — exotic values
    (where ``default=str`` would apply or ``dumps`` would raise),
    exotic keys, or a walk past the node budget — bails to the exact
    path instead of guessing.
    """
    total = 0
    stack = [payload]
    visits = 0
    while stack:
        value = stack.pop()
        visits += 1
        if visits > _SIZE_WALK_BUDGET:
            return False
        if total > max_bytes:
            # Inconclusive — the exact measurement decides.
            return False
        if value is None:
            total += 4  # null
        elif value is True:
            total += 4  # true
        elif value is False:
            total += 5  # false
        elif isinstance(value, str):
            # ensure_ascii=True: the worst case per char is an astral
            # character → surrogate pair (12 chars); every char costs
            # at most 12, plus the two quotes.
            total += 12 * len(value) + 2
        elif isinstance(value, int):
            try:
                total += len(str(value))
            except (TypeError, ValueError):
                # e.g. the >4300-digit int→str limit: dumps raises the
                # same way — let the exact path reproduce it.
                return False
        elif isinstance(value, float):
            if value != value:  # NaN → "NaN" (repr would say "nan")
                total += 3
            elif value == float("inf"):  # → "Infinity"
                total += 8
            elif value == float("-inf"):  # → "-Infinity"
                total += 9
            else:
                total += len(repr(value))
        elif isinstance(value, dict):
            # '{' + '"k": v, ...' + '}': 2 framing + 2 per item (': ')
            # + 2 per separator (', ').
            n = len(value)
            total += 2 + 2 * n + (2 * (n - 1) if n else 0)
            for k, v in value.items():
                # JSON keys are str/int/float/bool/None only — anything
                # else makes dumps raise TypeError (→ over the cap);
                # bail so the exact path reproduces that.
                if isinstance(k, str):
                    total += 12 * len(k) + 2
                elif k is None:
                    total += 4
                elif k is True:
                    total += 4
                elif k is False:
                    total += 5
                elif isinstance(k, int):
                    try:
                        total += len(str(k))
                    except (TypeError, ValueError):
                        return False
                elif isinstance(k, float):
                    if k != k:
                        total += 3
                    elif k == float("inf"):
                        total += 8
                    elif k == float("-inf"):
                        total += 9
                    else:
                        total += len(repr(k))
                else:
                    return False
                if total > max_bytes:
                    return False
                stack.append(v)
        elif isinstance(value, (list, tuple)):
            # '[' + 'v, ...' + ']': 2 framing + 2 per separator.
            n = len(value)
            total += 2 + (2 * (n - 1) if n else 0)
            for v in value:
                stack.append(v)
        else:
            # Exotic value (object, set, bytes, ...): dumps would apply
            # default=str or raise — the exact path decides, identically.
            return False
    return total <= max_bytes


def _serialized_within_cap(payload: Any, max_bytes: int) -> bool:
    """Exact size gate: True iff the payload's serialized form fits.

    Equivalent to ``len(json.dumps(payload, default=str)) <= max_bytes``
    — the upper-bound fast path skips the ``json.dumps`` measurement for
    ordinary payloads, and anything inconclusive falls through to the
    exact measurement. The verdict is identical to measuring every time;
    only the work is less.
    """
    if _fits_byte_cap(payload, max_bytes):
        return True
    try:
        # T3 SLICE6-F1: json.dumps defaults to ensure_ascii=True, so the
        # output is pure ASCII and len(str) == len(utf-8 bytes) exactly —
        # no second .encode("utf-8") pass over the string.
        return len(json.dumps(payload, default=str)) <= max_bytes
    except (TypeError, ValueError):
        # Not JSON-serializable at all — unmeasurable size is treated
        # as over the cap, exactly as before.
        return False


def _walk_envelope(payload: Any, *, max_bytes: int, max_depth: int,
                   field: str) -> bool:
    """Single-traversal fast path for the envelope's size cap + depth limit.

    Returns True when the payload *definitely* satisfies both — the
    caller is done, no ``json.dumps``, no second walk. Returns False
    when the walk is inconclusive (an exotic value, the bound exceeded,
    or the node budget exceeded): the caller falls back to the exact
    ``json.dumps`` measurement plus :func:`check_depth`, which
    reproduce the two-pass accept/reject behavior exactly.

    Raises :class:`InputValidationError` for a depth violation — but
    only after the size bound completes within the cap, because the
    size error takes precedence over the depth error, exactly as when
    the size check and the depth check ran as separate passes. (The
    walk continues past a recorded depth violation solely to finish
    the size bound; that only happens for payloads rejected either
    way.)

    The bound is an *upper* bound, so ``bound > max_bytes`` never
    proves the payload is over the cap — it only proves the fast path
    is inconclusive, hence ``return False`` rather than raising.
    """
    bound = 0
    # The first depth violation's parent-link chain. A separate flag is
    # needed because the root's own link is None — "violation at the
    # root" must not look like "no violation".
    depth_violated = False
    depth_link: Any = None
    stack: list[tuple[Any, int, Any]] = [(payload, 0, None)]
    visits = 0
    push = stack.append
    while stack:
        value, depth, link = stack.pop()
        visits += 1
        if visits > _ENVELOPE_WALK_BUDGET:
            return False
        if bound > max_bytes:
            # Inconclusive (the bound over-estimates) — exact path decides.
            return False
        if value is None:
            bound += 4  # null
        elif value is True:
            bound += 4  # true
        elif value is False:
            bound += 5  # false
        elif isinstance(value, str):
            # ensure_ascii=True: worst case per char is an astral
            # character → surrogate pair (12 chars), plus the quotes.
            bound += 12 * len(value) + 2
        elif isinstance(value, int):
            try:
                bound += len(str(value))
            except (TypeError, ValueError):
                return False
        elif isinstance(value, float):
            if value != value:  # NaN → "NaN"
                bound += 3
            elif value == float("inf"):  # → "Infinity"
                bound += 8
            elif value == float("-inf"):  # → "-Infinity"
                bound += 9
            else:
                bound += len(repr(value))
        elif isinstance(value, dict):
            # '{' + '"k": v, ...' + '}': 2 framing + 2 per item (': ')
            # + 2 per separator (', ').
            n = len(value)
            bound += 2 + 2 * n + (2 * (n - 1) if n else 0)
            child_depth = depth + 1
            if child_depth > max_depth and not depth_violated:
                # This container sits too deep: record its path, but keep
                # walking — the size bound must complete for precedence.
                depth_violated = True
                depth_link = link
            for k, v in value.items():
                # JSON keys are str/int/float/bool/None only — anything
                # else makes dumps raise TypeError; bail to the exact path.
                if isinstance(k, str):
                    bound += 12 * len(k) + 2
                elif k is None:
                    bound += 4
                elif k is True:
                    bound += 4
                elif k is False:
                    bound += 5
                elif isinstance(k, int):
                    try:
                        bound += len(str(k))
                    except (TypeError, ValueError):
                        return False
                elif isinstance(k, float):
                    if k != k:
                        bound += 3
                    elif k == float("inf"):
                        bound += 8
                    elif k == float("-inf"):
                        bound += 9
                    else:
                        bound += len(repr(k))
                else:
                    return False
                if bound > max_bytes:
                    return False
                push((v, child_depth, (link, True, k)))
        elif isinstance(value, (list, tuple)):
            # '[' + 'v, ...' + ']': 2 framing + 2 per separator.
            n = len(value)
            bound += 2 + (2 * (n - 1) if n else 0)
            child_depth = depth + 1
            if child_depth > max_depth and not depth_violated:
                depth_violated = True
                depth_link = link
            for i, v in enumerate(value):
                if bound > max_bytes:
                    return False
                push((v, child_depth, (link, False, i)))
        else:
            # Exotic value (object, set, bytes, ...): dumps would apply
            # default=str or raise — the exact path decides, identically.
            return False
    if bound > max_bytes:
        # Inconclusive (the bound over-estimates) — the exact path
        # decides. Checked here too, not just at the top of the loop:
        # the last value processed may be what pushes the bound over.
        return False
    if depth_violated:
        # The bound completed within the cap, so the size is definitely
        # fine — the recorded depth violation is the verdict, with the
        # same path the depth walk would have reported.
        raise InputValidationError(
            _resolve_path(field, depth_link),
            f"nesting depth exceeds {max_depth}",
        )
    return True


# ---------------------------------------------------------------------------
# Event envelope — shared by both ingest doors
# ---------------------------------------------------------------------------

def validate_event_envelope(
    event_type: Any,
    payload: Any,
    *,
    max_depth: int = MAX_EVENT_DEPTH,
    max_bytes: int = MAX_EVENT_BYTES,
) -> dict:
    """Validate the shape shared by every ingested event.

    - ``event_type``: non-empty string, bounded length.
    - ``payload``: must be a dict (a truthy non-dict is a torn feed
      line / hostile body — refused, never coerced).
    - Serialized payload within *max_bytes*; nesting within
      *max_depth*.

    Returns the payload unchanged. Membership (known vs unknown
    event type) is the *caller's* policy: the HTTP door 400s on
    unknown types; the Verdandi door keeps its unmapped → None
    contract.
    """
    check_string(event_type, field="event_type",
                 max_len=MAX_EVENT_TYPE_CHARS, allow_empty=False)
    if not isinstance(payload, dict):
        raise InputValidationError(
            "payload",
            f"must be a JSON object, got {type(payload).__name__}",
        )
    # T3 SLICE6-F1 floor work: the size cap and the depth limit are
    # enforced in a SINGLE traversal (_walk_envelope) instead of two
    # (_serialized_within_cap + check_depth). Same errors, same
    # precedence (size before depth), one walk instead of two.
    if _walk_envelope(payload, max_bytes=max_bytes, max_depth=max_depth,
                      field="payload"):
        return payload
    # Inconclusive fast path — exact measurement plus the depth walk,
    # reproducing the two-pass accept/reject behavior exactly.
    if not _serialized_within_cap(payload, max_bytes):
        raise InputValidationError(
            "payload", f"exceeds {max_bytes} bytes serialized"
        )
    check_depth(payload, max_depth=max_depth, field="payload")
    return payload


# ---------------------------------------------------------------------------
# Per-type event payload schemas (HTTP bridge) — data, not code branches
# ---------------------------------------------------------------------------

def _coerce_float(value: Any, *, field: str) -> float:
    if isinstance(value, bool):
        raise InputValidationError(field, "must be a number, got bool")
    try:
        return float(value)
    except (TypeError, ValueError):
        raise InputValidationError(
            field,
            f"must be a number, got {value!r}",
        ) from None


# event_type -> {field: (kind, max_len)}; kind "str" = bounded string,
# "str?" = optional bounded string, "float?" = optional float-coercible,
# "any" = anything within the envelope's depth/size caps.
EVENT_PAYLOAD_SCHEMAS: dict[str, dict[str, tuple[str, int | None]]] = {
    "observation": {
        "title": ("str", 10_000),
        "summary": ("str", 100_000),
    },
    "fact": {
        "subject_id": ("str", 500),
        "key": ("str", 500),
        "value": ("any", None),
        "confidence": ("float?", None),
        "domain": ("str?", 500),
    },
}


def validate_event_payload(event_type: str, payload: dict) -> dict:
    """Validate a payload against its per-type schema.

    Unknown event types are the caller's policy (this raises
    ``InputValidationError`` on ``event_type`` so the HTTP door can
    400; the Verdandi door never calls this for unmapped types).
    Every rejection names the dotted field. Returns the payload.
    """
    schema = EVENT_PAYLOAD_SCHEMAS.get(event_type)
    if schema is None:
        raise InputValidationError(
            "event_type", f"unknown event type {event_type!r}"
        )
    for name, (kind, max_len) in schema.items():
        if kind == "float?":
            if name in payload and payload[name] is not None:
                payload[name] = _coerce_float(
                    payload[name], field=f"payload.{name}"
                )
                # The canonical-fact store (TruthMeta) requires
                # 0.0 <= confidence <= 1.0; enforcing the downstream
                # invariant at the door turns a pydantic 500 into a
                # named 400. The chained comparison also rejects NaN,
                # which comparisons otherwise let slip through.
                if name == "confidence" and not 0.0 <= payload[name] <= 1.0:
                    raise InputValidationError(
                        f"payload.{name}", "must be between 0 and 1"
                    )
            continue
        if name not in payload:
            if kind.endswith("?"):
                continue
            raise InputValidationError(
                f"payload.{name}", "required field is missing"
            )
        value = payload[name]
        if kind == "any":
            continue  # envelope caps (depth/size) already apply
        if not isinstance(value, str):
            raise InputValidationError(
                f"payload.{name}",
                f"must be a string, got {type(value).__name__}",
            )
        if len(value) > max_len:
            raise InputValidationError(
                f"payload.{name}",
                f"exceeds {max_len} characters ({len(value)})",
            )
    return payload


# ---------------------------------------------------------------------------
# FTS5 search surface
# ---------------------------------------------------------------------------

def validate_search_query(query: Any) -> list[str]:
    """Bound and split a search query into terms.

    Raises :class:`InputValidationError` naming ``query`` when the
    bounds are exceeded — never silent truncation. Returns the
    lowercased terms (empty list for blank input).
    """
    if not isinstance(query, str):
        raise InputValidationError(
            "query", f"must be a string, got {type(query).__name__}"
        )
    if len(query) > MAX_SEARCH_QUERY_CHARS:
        raise InputValidationError(
            "query",
            f"exceeds {MAX_SEARCH_QUERY_CHARS} characters ({len(query)})",
        )
    terms = [t.lower() for t in query.split() if t.strip()]
    if len(terms) > MAX_SEARCH_TERMS:
        raise InputValidationError(
            "query",
            f"exceeds {MAX_SEARCH_TERMS} terms ({len(terms)})",
        )
    return terms


def fts5_phrase(term: str) -> str:
    """Render one search term as an FTS5 phrase.

    The FTS5-documented escape: ``"`` inside a term becomes ``""``.
    A quote can never break out of its phrase again, so FTS5
    operators (``OR``, ``NEAR``, ``*``, ``col:``) stay literal text.
    """
    return '"' + term.replace('"', '""') + '"'


# ---------------------------------------------------------------------------
# Guarded HTTP body reading (Track 1, P2 — shared by every localhost
# bridge: the HTTP bridge, kindroid, voxta)
# ---------------------------------------------------------------------------

def drain_limited(rfile, nbytes: int) -> None:
    """Read and discard *nbytes* from *rfile* in flat-memory chunks.

    Used before answering 413: closing mid-send gives the client a
    broken pipe instead of the 413 it should observe. The drain is
    capped — a client declaring gigabytes is abusive, and for those
    the connection is closed after the cap.
    """
    remaining = nbytes
    while remaining > 0:
        chunk = rfile.read(min(65536, remaining))
        if not chunk:
            break
        remaining -= len(chunk)


def read_guarded_body(
    headers,
    rfile,
    *,
    max_bytes: int = MAX_BODY_BYTES,
) -> tuple[bytes | None, tuple[int, str] | None]:
    """Read an HTTP request body with fail-closed guards.

    *headers* is the request's header mapping (``.get`` is used);
    *rfile* is the readable body stream.

    Returns ``(raw, None)`` on success, ``(None, (status, message))``
    on rejection — the caller sends the status with its own sender:
    - missing/unparseable/negative Content-Length → 400 naming the header
    - length above *max_bytes* → 413 (the body is drained in
      flat-memory chunks first, so the client observes the 413
      instead of a broken pipe)
    - short read → 400
    """
    length_str = headers.get("Content-Length", "0")
    try:
        length = int(length_str)
    except (TypeError, ValueError):
        return None, (400, "Invalid Content-Length header")
    if length < 0:
        return None, (400, "Invalid Content-Length header")
    if length > max_bytes:
        drain_limited(rfile, min(length, DRAIN_CAP_BYTES))
        return None, (413, f"Request body too large (max {max_bytes} bytes)")
    raw = rfile.read(length)
    if len(raw) < length:
        return None, (400, "Request body truncated")
    return raw, None
