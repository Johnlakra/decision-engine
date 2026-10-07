# Niches

A niche is a YAML file in `niches/` validated by `schemas/niche.schema.json`. It says what belongs to it (for Laya
routing), which extra Laya questions to ask, what to extract, which tools and actions it may use, how autonomous
it is, and the decide prompt. **Adding a niche needs no pipeline code**; only a new *tool* or *action* needs code
(registered in `tools/registry.py` / `actions/registry.py`).

## Starter niches
| Niche | Phase | Autonomy | Private | Tools | What it decides |
|---|---|---|---|---|---|
| `generic` | 1 | ask | yes | — | fallback for anything needing a decision |
| `tech_stack` | 1 | suggest | no | `stack_catalog.shortlist`, `stack_catalog.free_tiers` | which stack/hosting/DB for a project brief |
| `news_radar` | 2 | auto (archive only) | no | — | keep/skip + save-and-act / read later / not interested |
| `inbox` | 4 | ask | yes | — | reply / remind / delegate / archive, with draft reply |
| `agriculture` | 7 | ask (+ expert review) | yes | `farmer.profile`, `open_meteo.forecast`, `agmarknet.prices`, `crop_calendar.lookup` | irrigate, sell/hold, see expert |

## Field guide
- `description` — one sentence, concrete nouns. It becomes this niche's criterion in Laya's `niche` question, so it
  must separate this niche from the others. Bad: "important stuff". Good: "a farmer's question about crops…".
- `triage.questions` — extra Laya questions (≤ 8) asked once the niche is known; choice keys short; ≤ 12 options.
- `triage.discard_if` — confident answers that end processing (status `discarded`), e.g. news `keep = B` at ≥ 0.85.
- `extract` — JSON Schema of entities; the LLM fills it (structured output). Keep fields optional.
- `tools` — registry names. Each tool declares args schema, TTL, and whether it may run for private items.
- `prompt` — the decide step's system prompt. Content is passed separately as fenced data; say what to do when
  information is missing; forbid inventing links/prices.
- `actions` / `autonomy` / `auto_actions` — see FR-34. `auto` requires a non-empty `auto_actions`.
- `expert_review` — routes matching items to the expert queue (agriculture).
- `few_shot` — how many recent human corrections are added to the prompt.
- `evals` — path to labelled examples (≥ 30 rows; balanced; include hi/pa when the niche supports them).

## Built-in tools to implement
| Tool | Phase | Source | Notes |
|---|---|---|---|
| `stack_catalog.shortlist` | 1 | `data/stacks.yaml` (curated: ~30 stacks with tags, skills, offline, cost, free tiers) | filter by extracted requirements → top 6 |
| `stack_catalog.free_tiers` | 1 | `data/free_tiers.yaml` with `as_of` dates | never present as current without the date |
| `open_meteo.forecast` | 7 | `https://api.open-meteo.com/v1/forecast` (free, keyless) | 7-day rain, ET0, temp for lat/lon; cache 3 h |
| `agmarknet.prices` | 7 | data.gov.in resource `9ef84268-d588-465a-a308-a864a43d0070` (own API key) | modal/min/max ₹/quintal; daily after ~14:00 IST; cache 6 h; 30-day trend + nearby mandis |
| `crop_calendar.lookup` | 7 | `data/crop_calendar_pa.yaml` from PAU package of practices (versioned, cited) | stage by sowing date, irrigation windows; **no chemical doses** |
| `farmer.profile` | 7 | `farmers` table | crop, sowing date, village→lat/lon |
| `web_search` | later | provider with free tier | only for public niches; results cited |

## Ideas for more niches (each is just a YAML + evals)
job offers & freelancing leads · client project requests (Softech) · event/ministry requests (venue, dates, approvals) ·
bills & subscriptions (pay / cancel / dispute) · school ERP support tickets · shopping deals · learning resources ·
Fiverr gigs · crypto alerts from the radar (act / watch / ignore) · health appointment reminders (private; suggest only).

## `/new-niche "<description>"` flow
niche-designer drafts YAML + 30 eval rows → validates against schema → runs `make eval NICHE=x` (Laya zero-shot +
LLM fallback) → reports accuracy and confusing pairs with existing niches (description overlap) → the owner approves →
enabled in **shadow** Laya mode.
