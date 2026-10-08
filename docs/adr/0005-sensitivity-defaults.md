# 0005 — Sensitivity defaults and effective sensitivity for LLM routing

**Status:** accepted · 2026-10-08 · Requirements: FR-01, FR-12, FR-24, FR-31, FR-35, NFR-04, NFR-06 ·
Plan: phase 1 steps 1.1, 1.2, 1.3a, 1.4a, 1.7 (owner questions Q1, Q2, answered 2026-10-08)

## Context
- CLAUDE.md privacy invariant: items with `sensitivity: private` (email bodies, DMs by default) go only to providers
  marked `private_ok` (Ollama, or a paid tier allowed by `OPENAI_PRIVATE_OK`). `llm.gateway` enforces this per call
  from its `sensitivity` argument (LLM_GATEWAY.md). Every free-tier provider today (Gemini, Groq, Cerebras,
  OpenRouter, Sarvam) is `private_ok: false`.
- `items.sensitivity` is `NOT NULL DEFAULT 'private'` (migration 0001). API.md only said "default: private for
  gmail/instagram/telegram". Nothing defined the default for other sources.
- Niches also declare `sensitivity` (`schemas/niche.schema.json`, default `public`). Today `generic.yaml` and
  `inbox.yaml` say `private`, and `agriculture.yaml` says `private` (disabled). If the graph used the **stricter** of
  item and niche, every item that falls back to `generic` would need a private provider. With no Ollama running, those
  items would retry and end `failed` or wait. That includes the Phase 1 school-ERP check whenever routing falls back.
- `/v1/decide` (FR-35) has no sensitivity field. Opportunity Radar (FR-96) sends public scored items.
- **Owner answer Q2 (2026-10-08):** items from own-app sources (`manual`, `webhook`, `radar`, `seed`) default to
  `public`. `gmail`, `instagram`, `telegram` and `voice` stay `private` by default. The `generic` niche should not force
  private routing; the item's own sensitivity wins.
- **Owner answer Q1 (2026-10-08):** `news_radar` and `inbox` are `enabled: false` until Phases 2 and 4. In Phase 1 the
  enabled niches are `generic` and `tech_stack`.

## Options considered

### Default for a new item
| | (a) Source table: own-app sources public, personal-message sources private, anything else private | (b) Everything private unless hinted | (c) Everything public unless hinted |
|---|---|---|---|
| Privacy | Fail-closed for unknown sources; personal messages always private by default | Safest | Personal data could reach free tiers by mistake: breaks the invariant's "DMs by default" |
| Free-tier cost (no Ollama) | Own-app items use Gemini/Groq at ₹0 | Every item needs Ollama or a paid private tier, or it waits; breaks NFR-04 for the owner's own traffic | ₹0 |
| Ops burden | One small table in code | Run Ollama (≥ 8 GB box) from day one | None |

### Effective sensitivity once a niche is chosen
| | (a) Item wins, a niche can only **raise** it, and `generic` is `public` | (b) Item wins, niche ignored | (c) Stricter of item and niche, `generic` stays `private` |
|---|---|---|---|
| Privacy | A private item is never downgraded. A niche whose content is personal by nature (inbox, agriculture farmers) raises a public item to private | A public-hinted item routed to `inbox` would go to a free tier | Safest |
| `generic` fallback | Uses the item's sensitivity, so public own-app items work without Ollama | Same | Every fallback item needs a private provider: without Ollama they wait or fail |
| Rule fit | "Niches are config": the behavior comes from each YAML's `sensitivity`, no niche name in code | Niche field becomes dead config | Same |

## Decision
1. **Item sensitivity at ingest** (`app/ingest/sensitivity.py`, `resolve_item_sensitivity(source: str, hints: Hints | None,
   source_row_sensitivity: str | None = None) -> Literal["public","private"]`), first match wins:
   1. `hints.sensitivity`, when given (the caller declares its own data).
   2. The `sources` row's `sensitivity`, for connector items (Phase 2+; `None` in Phase 1).
   3. Source-type default:

      | Source | Default |
      |---|---|
      | `manual`, `webhook`, `radar`, `seed` | `public` (owner answer Q2) |
      | `gmail`, `instagram`, `telegram`, `voice` | `private` |
      | `rss` | `public` (published web content; confirm with the owner when Phase 2 adds RSS) |
      | anything else (`csv`, custom slugs, unknown) | `private` (fail closed) |

   The table is a constant in that module. Uploads (FR-04) pass their mapping's `sensitivity` as the hint.
2. **Effective sensitivity in the graph** (`effective_sensitivity(item_sensitivity, niche: NicheConfig) -> ...`): it is
   `private` if the item is `private` **or** the routed niche's YAML says `private`. Otherwise it is `public`. An item's
   own `private` is never downgraded. The function lives in `app/graph/` and is used by extract, tools (`private_ok`
   filter) and decide. Normalise and triage run before a niche is chosen and use the item's sensitivity only.
3. **`generic` does not force private routing.** `niches/generic.yaml` changes to `sensitivity: public`, so a `generic`
   item uses its own sensitivity. No pipeline code special-cases the `generic` name.
4. **`/v1/decide`**: new optional body field `sensitivity: "public" | "private"`, default `public` (the caller is an
   own app holding a `decide`-scoped key). With `niche`, the effective value is rule 2 applied to the body value and the
   niche. Laya calls are local and not affected. When the effective value is `private` and no `private_ok` provider is
   available for a needed LLM call (fallback classify, explain, or the niche decision), the response is `503`
   problem+json (`type: .../no-private-provider`). The text is never sent to a non-private provider.
5. **Failure mode stays "never lose an item":** a private item with no private provider goes to `needs_human_triage`
   (triage) or waits in `deciding` and retries (graph), per LLM_GATEWAY.md. It never falls back to a public provider.

## Consequences
- The owner's own-app traffic (school-ERP check, seed, radar) runs on free tiers with no Ollama. P1 works with
  `hints` omitted.
- Personal-message sources and unknown sources stay private by default. Private items still need Ollama or
  `OPENAI_PRIVATE_OK=true`. With Q1, no private niche is enabled in Phase 1, so this only matters for items a caller
  marks private.
- A caller can mark a `gmail` item `public` through `hints`. That is an explicit choice by an authenticated caller and
  is allowed. Connectors (Phase 2+) never set public hints for personal sources.
- `/v1/decide` gains an additive field (allowed in v1).
- Tests: `tests/unit/ingest/test_sensitivity.py` covers every row of the table plus hint precedence. The graph test
  `test_decide.py` covers item private + niche public → private, item public + niche private → private, and item
  public + `generic` → public.

## Revisit when
- A paid private-ok provider becomes the default (then private routing costs money and may need budgets per tenant).
- Multi-tenant hardening (Phase 8.5): untrusted tenants may need a stricter default (private unless declared).
- RSS ships (confirm the `rss` row) or a new personal-message connector is added (add it to the private row).

## Migration steps
1. niche-designer: `niches/generic.yaml` → `sensitivity: public`; `niches/news_radar.yaml` and `niches/inbox.yaml` →
   `enabled: false` (owner answer Q1) until Phases 2 and 4.
2. backend-builder (1.1): `app/ingest/sensitivity.py` and its unit test. No DB migration: the column default
   `'private'` stays as the fail-closed backstop.
3. langgraph-builder (1.4a, 1.7): `effective_sensitivity` and the `/v1/decide` field.
4. docs-keeper: none beyond this ADR. API.md is updated with it.
