# 0006 — SDK toolchain: openapi-python-client and openapi-typescript + openapi-fetch

**Status:** accepted · 2026-10-08 · Requirements: FR-42, FR-96, FR-111, NFR-04, NFR-05, NFR-12 · Plan: phase 1 step 1.10
## Context
ARCHITECTURE §4 promises "thin SDKs generated from OpenAPI" in `packages/client-py/` and `packages/client-ts/`.
Opportunity Radar (FR-96) and later the web and mobile apps call `/v1`. Webhook receivers must verify
`X-DE-Signature: t=<unix>,v1=<hex>` (API.md, `app/security/hmac.py`). The repo has **no Node package yet** (no
`package.json` anywhere), so this ADR also picks the first Node toolchain. Acceptance P8: `make sdk` followed by
`git diff --exit-code packages/` shows no diff, so generation must be deterministic.

Facts (checked 2026-10-08):
- `openapi-python-client` 0.29.1 (2026-08-30), MIT, supports OpenAPI 3.0 and 3.1, needs Python ≥ 3.11 to run. Generated
  clients depend on `httpx`, `attrs`, `python-dateutil`. It has a `--config` file (`project_name_override`,
  `package_name_override`, `post_hooks`, `literal_enums`, …) and `--meta poetry|pdm|setup`
  ([PyPI](https://pypi.org/project/openapi-python-client/), [README](https://github.com/openapi-generators/openapi-python-client)).
- `openapi-typescript` 7.13.0, MIT, peer `typescript ^5`, OpenAPI 3.0/3.1 → `.d.ts` types only, no runtime
  ([npm](https://www.npmjs.com/package/openapi-typescript)).
- `openapi-fetch` 0.17.0, MIT, one dependency (`openapi-typescript-helpers`), about 6 kB min, typed `fetch` wrapper over
  the generated `paths` type ([npm](https://www.npmjs.com/package/openapi-fetch)).
- Node release schedule: v24 is Active LTS until 2026-10-20, then Maintenance until 2028-04-30. v26 becomes LTS on
  2026-10-28 ([nodejs/Release schedule.json](https://github.com/nodejs/Release/blob/main/schedule.json)).
- FastAPI emits OpenAPI 3.1.

## Options considered

### Python SDK
| | (a) `openapi-python-client` (pinned, run with `uvx`, dev only) | (b) OpenAPI Generator (`openapi-generator-cli`, Java) | (c) Hand-written httpx client |
|---|---|---|---|
| Output | Typed attrs models + sync/async httpx functions | Verbose, older style; needs a JVM or Docker | Exactly what we want, but drifts from the API |
| Ops burden | One pinned tool through `uvx`, no new runtime | JVM in CI | Every API change edited twice |
| Cost | Free, MIT | Free, Apache-2.0 | Free |

### TypeScript SDK
| | (a) `openapi-typescript` + `openapi-fetch` | (b) `@hey-api/openapi-ts` (generates SDK functions) | (c) OpenAPI Generator `typescript-fetch` |
|---|---|---|---|
| Output | Types only + a 6 kB generic client; nothing generated at runtime | Generated functions and a client runtime; more files to diff | Large generated classes |
| Fit for Next.js (server route handlers) and Expo | Plain `fetch`, works in both | Works | Works, heavy |
| Determinism (P8) | One `.d.ts` file | Many files; plugin config churn | Many files, JVM |
| Cost | Free, MIT | Free, MIT | Free, Apache-2.0 |

### Node package manager (first Node package in the repo)
| | (a) npm (bundled with Node), `package-lock.json` | (b) pnpm through Corepack | (c) Bun |
|---|---|---|---|
| Install | Nothing extra | Corepack or a global install; Corepack is no longer bundled with newer Node lines | Separate runtime |
| Expo / React Native | Default, no hoisting config | Needs `node-linker=hoisted` for some Expo setups | Not the Expo default |
| Ops burden | Lowest | One more tool in CI and Docker | Two JS runtimes |

## Decision
1. **Python SDK:** `openapi-python-client==0.29.1`, run as
   `uvx openapi-python-client@0.29.1 generate --path packages/openapi.json --config packages/client-py/openapi-python-client.yaml --meta pdm --output-path <tmp> --overwrite`.
   The `make sdk` recipe then copies **only** the inner generated package to
   `packages/client-py/src/decision_engine_client/_generated/` (replaced wholesale) and discards the generated
   project files. `packages/client-py/pyproject.toml` (hatchling, Python ≥ 3.10, deps `httpx`, `attrs`,
   `python-dateutil`) and the hand-written modules are never regenerated:
   - `decision_engine_client/client.py`: `DecisionEngine(base_url, api_key, *, timeout=10, retries=3)` with retries on
     `429` (honours `Retry-After`) and `5xx`, and convenience methods `create_item`, `create_items_bulk`, `get_item`,
     `list_items`, `decide_item`, `decide`.
   - `decision_engine_client/signature.py`: `verify_signature(secret: bytes, body: bytes, header: str, *, tolerance_s=300,
     now: int | None = None) -> None`, raising `InvalidSignature`. It re-implements the `t=,v1=` algorithm
     (stdlib only) and must not import `app`. `tests/unit/test_sdk_signature_compat.py` proves it accepts
     `app.security.hmac.sign(...)` output and rejects tampered or stale bodies.
   - Config file: `project_name_override: decision-engine-client-generated`,
     `package_name_override: _generated`, `literal_enums: true`,
     `post_hooks: ["ruff check . --fix-only", "ruff format ."]`. The hooks use the `ruff` locked in
     `apps/api/uv.lock` (run inside `uv run --project apps/api`), so output is deterministic.
   The generator is a dev-time tool only. It is not a dependency of `apps/api`.
2. **TypeScript SDK:** `packages/client-ts/` is an ESM package `@decision-engine/client`:
   - devDependencies `openapi-typescript` 7.13.0 and `typescript` 5.x; dependency `openapi-fetch` 0.17.0. All exact
     versions (no `^`) in `package.json`.
   - `src/schema.d.ts` is generated by `openapi-typescript ../openapi.json -o src/schema.d.ts` and committed.
   - `src/index.ts`: `createClient({ baseUrl, apiKey })` wraps `openapi-fetch` `createClient<paths>()` with an
     `Authorization: Bearer` middleware. The API key is for server-side use only (web route handlers, Node services).
     Never ship it to a browser (ARCHITECTURE §1).
   - `src/verifySignature.ts`: `verifySignature(secret, body, header, { toleranceS = 300, now })` using Web Crypto
     (`crypto.subtle`, HMAC-SHA-256), constant-time compare, same `t=,v1=` scheme. It works on Node ≥ 20 and edge
     runtimes. It is tested with Vitest against a vector produced by `app.security.hmac.sign`, which is committed as a
     fixture.
   - `tsc` builds to `dist/` (gitignored). Lint is `tsc --noEmit` with `strict: true`. Generated `schema.d.ts` is
     excluded from ESLint.
3. **Node toolchain:** Node **24 LTS** (`.nvmrc` = `24`, `"engines": {"node": ">=22"}`) and **npm** with a committed
   `package-lock.json`. Use `npm ci` in CI. No Corepack, no pnpm, no Bun. When `apps/web` and `apps/mobile` arrive they
   join as npm workspaces from a root `package.json`. Moving to Node 26 after its LTS date (2026-10-28) is a routine
   bump, not an ADR.
4. **Spec export:** `apps/api/scripts/export_openapi.py` writes `packages/openapi.json` from `create_app().openapi()`
   with `json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"`. It does not need a database or secrets
   (the app factory must not connect at import time).
5. **`make sdk`** runs: export spec → Python generation + copy → `npm ci && npm run gen` in `packages/client-ts`.
   CI (devops follow-up) runs `make sdk && git diff --exit-code packages/` (P8).
6. **Distribution:** not published to PyPI or npm in the MVP. Consumers install from the private Git repo
   (`uv add "decision-engine-client @ git+https://…#subdirectory=packages/client-py"`; npm `github:` dependency or
   `npm pack`). Publishing is a later decision.

## Consequences
- First Node package in the repo: CI needs `actions/setup-node` (Node 24) and an npm cache. `make lint` gains
  `npm --prefix packages/client-ts run lint` (eslint + `tsc --noEmit`).
- The generated Python code is large but isolated in `_generated/`. Public import paths go through the hand-written
  `client.py`, so a generator upgrade does not break consumers.
- Signature verification exists three times (server, Python SDK, TS SDK). Compatibility tests in both SDKs pin it to
  the server's output, so drift fails CI.
- Every route needs tags and an example (W's `test_openapi.py`) so the generated names are stable and readable.
- No paid dependency, no runtime cost. All tools are MIT.

## Revisit when
- An SDK is published publicly (then: semver, changelog, provenance).
- `apps/web` / `apps/mobile` need a workspace layout that npm workspaces cannot serve.
- `openapi-python-client` 1.0 or `openapi-fetch` 1.0 changes the generated surface.

## Migration steps
1. integration-builder (1.10): `scripts/export_openapi.py`, `packages/client-py/` (pyproject, config, `client.py`,
   `signature.py`, `_generated/`), `packages/client-ts/` (`package.json`, `package-lock.json`, `tsconfig.json`,
   `.nvmrc`, `src/`, README with examples), `tests/unit/test_sdk_signature_compat.py`, the Vitest signature test.
2. backend-builder: the `sdk` target in `/Makefile`, and `.gitignore` for `packages/client-ts/{node_modules,dist}`.
3. devops-deployer: CI job (setup-node 24, `npm ci`, `make sdk`, `git diff --exit-code packages/`).
4. Rollback: delete `packages/client-*` and the Makefile target. No runtime code depends on the SDKs.
