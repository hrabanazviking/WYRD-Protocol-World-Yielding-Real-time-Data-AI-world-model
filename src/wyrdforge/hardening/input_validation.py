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
    """
    # Stack of (value, depth, path). Breadth here is bounded by the
    # caller's size cap; depth is what we police — and the walk
    # itself is budgeted against alias-shared/cyclic graphs.
    stack: list[tuple[Any, int, str]] = [(obj, 0, field)]
    visits = 0
    while stack:
        value, depth, path = stack.pop()
        if isinstance(value, dict):
            items = list(value.items())
        elif isinstance(value, (list, tuple)):
            items = list(enumerate(value))
        else:
            continue
        child_depth = depth + 1
        if child_depth > max_depth:
            raise InputValidationError(
                path, f"nesting depth exceeds {max_depth}"
            )
        for key, child in items:
            visits += 1
            if visits > MAX_VALIDATE_WALK_NODES:
                raise InputValidationError(
                    path,
                    f"node walk exceeds {MAX_VALIDATE_WALK_NODES} nodes — "
                    f"possible alias bomb or cyclic document",
                )
            if isinstance(value, dict):
                child_path = f"{path}.{key}"
            else:
                child_path = f"{path}[{key}]"
            stack.append((child, child_depth, child_path))


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
        return len(json.dumps(payload, default=str).encode("utf-8"))
    except (TypeError, ValueError):
        # Not JSON-serializable at all — the depth walk below still
        # applies; size is unmeasurable, treat as over the cap.
        return MAX_EVENT_BYTES + 1


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
    if _serialized_bytes(payload) > max_bytes:
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
