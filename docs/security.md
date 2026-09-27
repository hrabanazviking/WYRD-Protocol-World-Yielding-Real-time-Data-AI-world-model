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

## Exposure inventory (Track 1, P2 — Wave G, Slice 4)

Every HTTP surface, in one place. Probed live by
`tests/test_exposure_probe.py`.

| Surface | Port | Default bind | Auth | Body handling |
|---|---|---|---|---|
| `WyrdHTTPServer` (`bridges/http_api.py`) | 8765 | `localhost` | none (loopback-only) | guarded `Content-Length` → 400; 1 MiB cap → 413 (Slice 3) |
| voxta (`bridges/voxta_bridge.py`) | 8766 | `localhost` | none (loopback-only) | guarded `Content-Length` → 400; 1 MiB cap → 413 (Slice 4) |
| kindroid (`bridges/kindroid_bridge.py`) | 8767 | `localhost` | none (loopback-only) | guarded `Content-Length` → 400; 1 MiB cap → 413 (Slice 4) |
| cloud relay (`tools/wyrd_cloud_relay/relay.py`) | 9000 | `0.0.0.0` | Bearer token (optional — startup refuses unsafe postures without one; see D2) | FastAPI/uvicorn stack |

The three local bridges are loopback-only with no authentication —
the roadmap's own model ("Bearer tokens and localhost defaults are
the model"), confirmed and documented here, not rebuilt. The probe
asserts each default bind resolves to a loopback address only: **0
unauthenticated write endpoints reachable from off-loopback.**

All three share one body cap — `MAX_BODY_BYTES` = 1 MiB, enforced by
`read_guarded_body()` in `hardening/input_validation.py` — and one
rule: garbage `Content-Length` is a 400 naming the header (never a
silently dropped connection), an over-cap body is a 413 after a
flat-memory drain (never an unbounded read).

## D1 — CORS origin policy (Volmarr, 2026-09-26)

**Named, dated decision: the relay keeps CORS `*` as its default.**

Why not a narrowed static list: the named browser client is the
D&D Beyond *extension*, whose origin is `chrome-extension://<id>` —
unknowable before install. A static allowlist
(`https://www.owlbear.rodeo`, …) would not cover it, so narrowing
would be fake security that breaks the documented happy path.

The narrowing mechanism exists anyway, so the decision stays
operational: `--cors-origins` / `WYRD_CORS_ORIGINS`
(comma-separated) on the relay. The dead `build_cors_headers`
helper (whose multi-origin branch emitted an invalid
`Access-Control-Allow-Origin`) was deleted; `CORSMiddleware` is the
live path.

## D2 — relay authentication coupling (Volmarr, 2026-09-26)

The relay **refuses to start** (`RelaySecurityError`, exit 2) when:
- the bind host is not loopback (`0.0.0.0` included) and no bearer
  token is configured (`--token` / `WYRD_RELAY_TOKEN`), or
- CORS origins include `"*"` (membership, not equality — Starlette
  treats `"*"` anywhere in the list as allow-all) and no bearer
  token is configured —
  `*` clears preflights for every web page the operator has open,
  so `*` + no auth would be an open world-API proxy. (`*` + Bearer
  is safe: tokens are not ambient like cookies.)

Loopback bind without a token starts anyway, with a loud stderr
warning — local development stays frictionless.

The gate runs in the CLI entrypoint; programmatic use of
`create_app()` skips it — the deployer's responsibility.

## Dependency & secret hygiene (Track 1, P3 — Wave G, Slice 4)

- pip-audit, 2026-09-26: **0 known vulnerabilities** across the
  installed set. Dated record:
  `docs/audits/dependency-audit-2026-09-26.md`.
- Secret scan (tree + full git history), 2026-09-26: **0 real
  secrets**; two inert placeholders documented in the audit record.
- D3 standing policy (Volmarr, 2026-09-26): `sentence-transformers`
  and `sqlalchemy` are **excluded** — nothing in the tree imports
  them, and the `[llm]`/`[full]` extras that declared them were
  removed from `pyproject.toml`. Every remaining dependency carries
  a one-line justification comment.
- Proxy-env posture: every HTTP client bypasses proxy env vars for
  localhost traffic — the relay via `httpx(trust_env=False)`, the
  Ollama connector via a proxy-bypassing opener for loopback
  targets (non-loopback targets keep normal proxy behavior).
  `tools/wyrd_tui.py` also uses `urlopen` with proxy env, but its
  world-load path is separately broken and out of this slice's
  scope — noted, not fixed.

## What this does NOT cover

Sandboxing component code and any new auth system (OAuth, user
management) are roadmap non-goals — deliberately not built. The
local bridges' no-auth loopback model is confirmed above, not
rebuilt.
