# WYRD Protocol — Security Notes

How WYRD treats input it did not write. The rule everywhere is the
same: **fail closed, never silent**. Hostile or malformed input is
rejected at the boundary where it arrives, with an error that names
the field — never deep in the machinery, never swallowed.

## Trust boundaries

| Door | What arrives | Where it is checked |
|---|---|---|
| World-file YAML | files on disk (yours, but YAML is treacherous) | `loaders/world_loader.py` → `hardening/config_validator.py` |
| HTTP bridge (`/event`, `/query`, `/facts`) | request bodies from the network | `bridges/http_api.py` → `hardening/input_validation.py` |
| Verdandi nerve feed | JSONL events from `~/.hermes/state/nerve_feed.jsonl` | `bridges/verdandi_bridge.py` → `hardening/input_validation.py` |
| FTS5 search | query strings | `persistence/memory_store.py` → `hardening/input_validation.py` |
| Promotion config | `configs/memory_promotion.yaml` | `services/memory_promoter.py` |

The shared checker lives in `wyrdforge/hardening/input_validation.py`
(`InputValidationError`, depth/string checks, the event envelope,
per-type schemas, search bounds). One module, one set of bound
numbers — not one hopeful check per call site.

## The three doors, concretely

**World YAML.** Files over 10 MiB are refused before parsing (alias
bombs expand *inside* the parser, so the cap is pre-parse). After
parsing, the document passes an **iterative depth gate** (50 levels —
the canonical schema nests ~10) and a **node-walk budget** (1,000,000
node visits): YAML aliases resolve *by reference*, so a 418-byte
document can name a ~16M-node object graph, and `&c [*c]` is a true
cycle — without the budget, the validator's own walk would be the
bomb. Deep nesting, alias webs, and cycles are refused naming the
file. List, scalar, and null documents are refused naming the file.
Unknown fields — top-level or nested — are hard errors naming the
dotted path (`$.zones[0].bogus`): a typo'd key that silently defaulted
is how a world loses a zone without anyone noticing. The loader keeps
its historical defaults (filename stem for a missing `world_id`,
`world_name` falling back to `world_id`) — normalized onto a copy,
then the canonical schema is enforced.

**HTTP events.** `/event` validates the envelope (event type,
dict-shaped payload, 1 MiB / depth-10 caps) and the per-type schema:
`observation` needs `title`/`summary`; `fact` needs
`subject_id`/`key`/`value` with an optional numeric `confidence`
(`confidence` must satisfy `0.0 <= confidence <= 1.0` — the
canonical-fact store's `TruthMeta` model requires it, so the door
enforces both ends (and rejects NaN) as a 400 instead of
letting it become a pydantic 500 downstream).
Violations return **400 naming the field** — malformed input never
reaches `push_event`, so it can never become a 500. `/query` bounds
`persona_id`/`location_id`/`bond_id` (500 chars) and `user_input`
(200,000 chars); `/facts` bounds `entity_id`. Bodies over 1 MiB get
413 without being processed: the bridge drains the body in bounded
flat-memory chunks (so the client sees the 413 instead of a broken
pipe) and never parses it.

**Verdandi nerve events.** The feed is occasionally torn, so this
door *refuses* instead of raising: `apply_event` returns `None` for
non-string event types, truthy non-dict payloads, over-deep or
over-size payloads — the torn line is dropped, the run continues.
Inside the handlers, wrong-typed values are coerced or dropped
(mood readings keep only numbers; emotion lists drop non-scalars;
`verdicts` must be a mapping), and stored strings are capped.

## FTS5 search

Search terms are rendered as FTS5 phrases with the documented quote
escape (`"` → `""` inside the term), so a quote can never break out
of its phrase. FTS5 operators (`OR`, `NEAR`, `*`, `title:`) in user
input are matched **literally**, not interpreted. Queries are capped
at 10,000 characters / 100 terms — violations raise `ValueError`
naming `query`, never silently truncated.

## SQLite hygiene

`incremental_vacuum` coerces its page count through
`operator.index()` before interpolation, and the state-version stamp
does the same — an integer reaches the SQL text, never a raw value.
All other SQL uses bound parameters throughout.

## What this does NOT cover (Track 1, P2/P3)

CORS and exposure decisions, the cloud relay, the Kindroid/Voxta
bridges, dependency and secret audits, and the accepted-risk register
are separate slices with their own decision gates. This slice is
input validation only.
