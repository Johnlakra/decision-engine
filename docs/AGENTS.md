# The Claude Code team

20 subagents in `.claude/agents/` and 8 slash commands in `.claude/commands/`. Subagents cannot call each other:
the main Claude Code session orchestrates them (that is what `/build-phase` tells it to do).

## Agents
| Agent | Model tier | Owns | Called by |
|---|---|---|---|
| `planner` | opus | `docs/plans/` — file-level task lists, parallel groups | every `/build-phase` |
| `architect` | opus | ADRs, ARCHITECTURE/DATA_MODEL/API contracts, `schemas/` | when a plan flags a design decision |
| `backend-builder` | sonnet | API scaffold, config, DB models, migrations, routers, API keys, rate limits | phases 0, 1, 5, 8 |
| `pipeline-builder` | sonnet | job queue + worker, normaliser, dedupe, Docling, actions registry | phases 0, 1, 5 |
| `laya-integrator` | sonnet | Laya service + client, triage modes, fallback, calibration, shadow report, exports | phases 0, 1, 2, 8 |
| `llm-gateway-builder` | sonnet | LiteLLM gateway, budgets, privacy routing, structured output, Sarvam, Ollama | phases 0, 4, 7 |
| `langgraph-builder` | sonnet | graph builder from YAML, nodes, interrupt approval, checkpointer, `/v1/decide` | phases 1, 8 |
| `connector-builder` | sonnet | RSS, Telegram, Gmail, Instagram, webhooks, CSV, voice | phases 2, 4, 5 |
| `integration-builder` | sonnet | outbound webhooks, SDKs, Opportunity Radar bridge, examples | phases 1, 2 |
| `niche-designer` | sonnet | `niches/*.yaml`, `evals/*.jsonl`, loader, wizard, stack catalog data | phases 0, 1, 2, 4, 7, 8, `/new-niche` |
| `agri-domain-expert` | sonnet | Agmarknet, Open-Meteo, PAU crop calendar, farmer advisory safety | phase 7 |
| `frontend-builder` | sonnet | Next.js web app | phases 3, 5, 7, 8 |
| `mobile-builder` | sonnet | Expo app, swipe queue, push, farmer mode | phase 6 |
| `ui-ux-designer` | sonnet | screen specs, tokens, mocks, UX reviews | phases 3, 6, 7, `/design-screen` |
| `test-writer` | sonnet | tests, fixtures, seed data, test matrix | every phase |
| `code-reviewer` | sonnet | read-only review with BLOCKING/SHOULD/NIT | every step, `/review` |
| `security-auditor` | sonnet | security + privacy audits, security tests | phases 0, 4, 5, 7, 8, `/deploy-check` |
| `devops-deployer` | sonnet | Docker, compose, CI/CD, Oracle VM, Render blueprint, backups | phases 0, 6, 8 |
| `feed-scout` | haiku | `data/feeds/*.yaml` verified news sources | phase 2, broken feeds |
| `docs-keeper` | haiku | ticks PLAN.md, keeps README/API/.env.example/CHANGELOG true | end of every step |

Model tiers are aliases (`opus`, `sonnet`, `haiku`) so agents follow the latest model in each tier. Cheapest capable
model per job: haiku for mechanical, verifiable edits; sonnet for building and judgement; opus for planning and design.

## Commands
| Command | Does |
|---|---|
| `/status` | where we are, next 3 tasks, blockers, the next command |
| `/build-phase N` | plan → (design) → build in parallel groups → test → review (+ security) → acceptance → commit → docs |
| `/new-niche "<sentence>"` | niche YAML + evals + validation, shadow mode, asks you before commit |
| `/new-connector <name>` | ADR if needed → connector → security audit → review |
| `/review [scope]` | independent review, no edits |
| `/deploy-check <A\|B>` | pre-deploy gate, no deploy without your confirmation |
| `/design-screen <screen>` | spec + HTML mock before building a screen |
| `/laya-report [niche] [days]` | shadow results and a switch-on recommendation, no mode change without you |

## Typical flow
```
/status
/build-phase 0          # ~1 session; you answer any owner questions it raises
/build-phase 1
/new-niche "decide which freelance (Fiverr) gig requests to accept"
/build-phase 2
/laya-report news_radar 14
...
/deploy-check A
```

## Parallel groups that work well
- Phase 0: {pipeline-builder: queue} ∥ {laya-integrator: service + client} ∥ {llm-gateway-builder} ∥ {devops-deployer: compose + CI}
  after backend-builder has created the scaffold and DB models.
- Phase 1: {pipeline-builder: normaliser + actions} ∥ {laya-integrator: triage} ∥ {niche-designer: tech_stack + generic}
  then {langgraph-builder} then {integration-builder}.
- Phase 3: ui-ux-designer first, then frontend-builder (one agent per screen group if files do not overlap).

## Tips
- Give agents the plan step id; they report FR ids covered, so `docs/TEST_MATRIX.md` stays honest.
- If two agents need the same file, run them one after another — never in parallel.
- Keep each step small enough to review (≤ ~400 changed lines).
- Your decisions (approve a niche, switch Laya on, deploy) are always asked, never assumed.
