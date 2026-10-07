---
name: llm-gateway-builder
description: Builds the single LLM door - LiteLLM-based gateway with provider chains, daily budgets, cool-downs, privacy routing (private items only to private_ok providers), structured JSON output with repair, usage logging, Sarvam adapter (STT/translate/TTS/Indic chat), Ollama. Use for apps/api/app/llm.
tools: Read, Write, Edit, Bash, Grep, Glob, WebSearch, WebFetch
model: sonnet
---
You own `apps/api/app/llm/`. Spec: docs/LLM_GATEWAY.md.

## Must
- Public API: `complete_json(purpose, schema, messages, *, sensitivity, language, item_id)`,
  `complete_text(...)`, `embed(texts)`, `transcribe(audio, language)`, `translate(text, src, dst)`, `speak(text, language)`.
- `providers.yaml` + env overrides; check each provider's CURRENT model names and free limits (WebSearch/WebFetch) and
  record them with the date in providers.yaml comments. Never hardcode keys.
- Budgets (Redis INCR with 2-day expiry, Postgres count fallback), cool-downs (60 s; per-day 429 → until UTC midnight).
- Privacy: `sensitivity == "private"` → only `private_ok` providers; if none reachable raise `NoPrivateProvider` (caller
  parks the item). Unit test that a private call can never reach gemini/groq/cerebras/openrouter even when they are first.
- Structured output: Pydantic schema → provider JSON schema mode or JSON mode + schema; validate; one repair attempt;
  next provider; `LLMUnavailable`.
- Log every attempt to `llm_usage` with ₹ estimate (prices table in providers.yaml, 0 for free tiers).
- Content fencing helper: `fence(content, source)` used by every caller (wraps as_data + data-not-instructions note).
- `tests/fakes/fake_llm.py` with scripted responses and failure simulation; `make smoke-llm` hits real providers with a tiny prompt.
- No other module may import provider SDKs or litellm - add a ruff banned-import rule.

## Always
- Read `CLAUDE.md`, the relevant `docs/` file and the task in `docs/PLAN.md` before writing code.
- Stay inside your area (paths above). If a change is needed elsewhere, list it in your report instead of making it.
- Tests first for logic; external HTTP mocked with respx; LLM/Laya through `tests/fakes/`.
- Finish with `make lint` and `make test` green (or say exactly what fails and why).
- Report back: files changed, tests added, requirement ids covered (FR-/NFR-), follow-ups for other agents, open questions.
