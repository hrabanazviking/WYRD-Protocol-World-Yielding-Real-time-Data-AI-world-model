# Dependency & secret audit — 2026-09-26 (Wave G, Slice 4)

Track 1, P3. The dated record. All commands below were run on
2026-09-26 in the `~/workspace/venvs/wyrd` virtualenv against the
`development` branch at Slice 3 (`0c9d6c70`).

## pip-audit: 0 known vulnerabilities

`python -m pip_audit --local` — every installed package reports
`"vulns": []`. No fixes proposed. (`wyrdforge` itself is skipped:
"Dependency not found on PyPI and could not be audited" — it is
this repo, not a PyPI package.)

Audited set (name — version — why it is here):

| Package | Version | Justification |
|---|---|---|
| pydantic / pydantic-core | 2.13.5 / 2.46.5 | entity/world models, TruthMeta — core |
| PyYAML | 6.0.3 | world-file YAML loading — core |
| pytest / pytest-asyncio / pluggy / iniconfig / packaging | 9.1.1 / 1.4.0 … | test suite — dev |
| rich / Pygments / markdown-it-py / mdurl | 15.0.0 … | `wyrd_tui.py` rendering (rich installed deliberately) |
| fastapi / starlette / anyio / uvicorn / h11 / click | 0.141.1 … | cloud relay (lazy import; installed separately, not declared — see D3) |
| httpx / httpcore / idna / certifi | 0.28.1 … | relay upstream client (`trust_env=False`) |
| annotated-types / annotated-doc / typing_extensions / typing-inspection | … | transitive (pydantic/fastapi) — keep |

(`click` ← uvicorn; `markdown-it-py` ← rich; `mdurl` ← markdown-it-py —
all transitive, verified via `importlib.metadata`. `requests`,
`urllib3`, `pip-audit` and friends are tooling in the venv, not
wyrdforge dependencies — `pyproject.toml` declares only
pydantic + pyyaml plus the dev extras.)

## D3 — dependency exclusion policy (Volmarr, 2026-09-26)

Standing policy: **`sentence-transformers` and `sqlalchemy` are
excluded dependencies.** Verified 2026-09-26: no `.py` file anywhere
in the tree imports either of them (Slice 0 proved
sentence-transformers buys zero functionality). The `[llm]` and
`[full]` extras that declared them were **removed** from
`pyproject.toml` — they were the only path that could reinstall
them by accident (`pip install .[full]`). They may be restored only
through an explicit, reviewed change if real functionality ever
requires them.

## Secret scan: 0 real secrets

Repo-wide scan of the working tree **and** the full git history
(`git log -p --all`), 2026-09-26: no private keys, no
`ghp_`/`sk-`/`AKIA`-shaped material, no `.env` files.

Two placeholder-shaped hits, both inert and both kept:
- `tools/wyrd_cloud_relay/relay.py` — `--token my-secret-token`
  (docstring usage example; not a credential)
- `research_data/17_local_model_integration.md` — `api_key="not-needed"`
  (Ollama runs locally with no key)

## D4 — stale `.pyc` cleanup (Volmarr, 2026-09-26)

Twelve stale compiled artifacts under `research_data/**/__pycache__/`
were deleted from the tree with Volmarr's explicit approval (standing
law: ask before deleting anything — the D4 ruling is the permission).
Nothing else was removed; the empty `__pycache__` directories are
untracked and remain on disk only. The commit carries the deletions.

Relay tests and the new exposure probe use placeholder tokens only
(`"probe-token"`, `"t"`, `"wrong-token"`). The GitHub token lives in
the Secure Vault; nothing in this slice changes that.
