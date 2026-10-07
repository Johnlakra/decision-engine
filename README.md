# Decision Engine

A personal, then public, **decision engine**. Everything that might need a decision flows in: email,
Instagram DMs, news, webhooks from your other apps, CSV uploads, farmer voice notes. It is turned into
one JSON shape and sorted in milliseconds by **Laya** (keep/skip, which niche, how urgent). Only what
really needs thought goes to an LLM agent for that niche. You approve or reject on a simple swipe queue.
Every swipe becomes training data, so it gets better at *your* decisions.

```
 sources ──► ingest API ──► normalise to JSON ──► Laya triage ──► LangGraph niche agent ──► your approval ──► action / webhook
 (gmail, ig, rss,          (LLM structured     (needs decision?  (inbox, news, agri,      (swipe queue:      (label, reply draft,
  webhook, csv,             output, pydantic)   niche, urgency)   tech-stack, generic)     web + mobile)      push, callback)
  telegram, voice)                                                                                  └──► feedback → Laya fine-tune data
```

It is a **standalone service with an API**, so Opportunity Radar, the Sarvam app, a farmer app or any
future project can send it items and get decisions back.

## Status
This repository starts as a **build kit**: requirements, architecture, phased plan, schemas, niche
configs, and a team of Claude Code subagents and slash commands that build the code phase by phase.

## Build it with Claude Code
```bash
cd decision-engine
claude                         # opens Claude Code in this folder; it reads CLAUDE.md automatically
/status                        # what is built, what is next (docs/PLAN.md checklist)
/build-phase 0                 # skeleton: FastAPI, DB, Redis queue, LLM gateway, Laya client
/build-phase 1                 # news radar niche (easiest win)
/build-phase 2                 # web approval queue (Next.js)
...                            # see docs/PLAN.md for phases 0-8
/new-niche "job offers"        # add a niche any time (config, not code)
/new-connector whatsapp        # add a source
/review                        # independent review + tests before you commit
/deploy-check                  # free-tier deploy readiness (Render + Neon + Upstash + Laya VM)
```
Each phase ends with tests passing and its checklist ticked in `docs/PLAN.md`.

## Where to read
| File | What |
|---|---|
| `CLAUDE.md` | Rules every Claude Code session follows (stack, conventions, safety) |
| `docs/REQUIREMENTS.md` | Every functional and non-functional requirement, numbered |
| `docs/ARCHITECTURE.md` | Components, data flow, folder layout, tech choices and why |
| `docs/PLAN.md` | Phases 0-8 with tasks, owners (agents) and acceptance criteria |
| `docs/API.md` | The HTTP contract other projects integrate against |
| `docs/DATA_MODEL.md` | Postgres tables and the DecisionItem JSON |
| `docs/NICHES.md` | How a niche is defined, with the starter niches |
| `docs/LAYA.md` | Exactly how Laya is called, hosted, calibrated and fine-tuned |
| `docs/LLM_GATEWAY.md` | Free-tier model chain (Gemini, Groq, Cerebras, OpenRouter, Sarvam, Ollama) |
| `docs/CONNECTORS.md` | Gmail, Instagram, RSS, webhook, CSV, Telegram, voice: limits and rules |
| `docs/UI_UX.md` | Screens, the swipe queue, design tokens, accessibility, farmer mode |
| `docs/DEPLOY.md` | Free hosting now, paid path later |
| `docs/AGENTS.md` | The Claude Code team: who does what, and in which order |
| `schemas/` | JSON Schemas: decision item, niche, connector payload |
| `niches/` | Starter niche configs (YAML) |
