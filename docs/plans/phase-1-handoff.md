# Handoff: decision-engine, Phase 1 build (2026-10-08)

Repo: `/Users/macprimary/Downloads/decision-engine` (branch `main`, tracks
https://github.com/Johnlakra/decision-engine, which is private).
The owner ran `/build-phase 1`. You are the orchestrator; subagents can't call each other.

## Read first (don't re-derive)
- `CLAUDE.md`: project rules (Laya never `on`, one LLM door, untrusted text, privacy).
- `docs/plans/phase-1.md`: step ids, contracts C1–C9, parallel groups, acceptance checks P1–P4/P7/L1–L3, owner answers.
- `docs/adr/0003`–`0006`: LangGraph runtime, migration 0002, sensitivity defaults, SDK toolchain.
- `git log --oneline c0ea560..HEAD`: one commit per finished step.

## Where we are
| Group | Steps | State |
|---|---|---|
| 0 | plan, ADRs, owner Q1–Q3 | done (c0ea560) |
| A | A1, A2, A3, A4 | done |
| B | 1.1, 1.2, 1.5, 1.3a/b, 1.9, 1.6, 1.8a/b, 1.4a | done |
| C | 1.4b → 1.7 (langgraph-builder) | **stopped mid-step by owner request.** Part 1 of 1.4b is committed as `2b4a121` (approval, act and finish nodes, plus the graph builder). **Uncommitted WIP left in the tree:** `app/graph/run.py` (new), `app/graph/locks.py` (new) and `app/graph/store_approval.py` (modified). Still to do: finish and test the runner, commit 1.4b part 2 (runner, resume API `POST /v1/items/{id}/decision`, `app/tools/__init__.py` importing stack_catalog), then 1.7 `/v1/decide`. Re-launch langgraph-builder with the original 1.4b/1.7 brief (see "Group C brief" below) and tell it to review and finish the WIP files first. |
| D | P (worker wiring) ∥ W (router/main wiring, entrypoint, Makefile) ∥ 1.9b (eval runner, `make eval`) | todo |
| E | 1.10 SDKs ∥ 1.11 seed + live scripts | todo |
| F | test-writer → code-reviewer → security-auditor → acceptance → docs-keeper ticks PLAN.md (Phase 0 boxes too, never ticked) | todo |

Last green local run, after group B: lint clean; tests 575 passed, 99 skipped, 1 xfailed.
**CI run 37756110839 (push of 2b4a121) FAILED: 5 failed, 1 error, 680 passed.** This was the first run of the DB tests anywhere. Fix these before group D:
1. **`updated_at` is None when an item is serialized right after insert.** The error is `DecisionItemOut.updated_at: Input should be a valid datetime, input_value=None` at `app/schemas/items.py:44`.
   - Failing tests: `test_items_api.py::test_raw_is_untouched_and_hints_stored`, `::test_cursor_paging_and_filters`; `test_webhooks_out.py::test_fanout_one_delivery_per_subscription_and_deliver`, `::test_failure_enqueues_retry_and_dead_letters`; and the error at setup of `test_triage_service.py::test_triage_persists_record_and_emits_event`.
   - Fix one of: the model default or server_default (owner: backend-builder, A1/1.1), a refresh after insert, or `updated_at: datetime | None`.
2. **`test_migration.py::test_upgrade_downgrade_upgrade`:** the table-set assertion now also sees the LangGraph `checkpoint*` tables, which are created outside Alembic per ADR 0003. Exclude them from the expected-set comparison in the Phase 0 test (backend-builder).

Fix both through backend-builder with the failing output, push, and confirm CI is green with `gh run list` and `gh run view <id> --log-failed`. CI has Postgres, so it is currently the **only** place the DB tests run.

## Blockers
- **Docker Desktop is not running locally**, so all DB and integration tests (including acceptance P1–P4 and migration 0002) skip locally and have **never run**. Ask the owner to start Docker, then `docker compose up -d db && make test`.
- Live checks L1–L3 need an LLM key (Gemini/Groq), `TOKEN_ENC_KEY` and `WEBHOOK_ALLOW_PRIVATE_URLS=true` in `.env`. Never read `.env`.

## Carry-forward notes for upcoming briefs
These are not in the plan file.
- **Step P (pipeline-builder):**
  - Register handlers: `JobKind.WEBHOOK → app.integrations.webhooks_out.handle_webhook_job`, `JobKind.ACTION → app.actions.handle_action_job`, plus the graph runner from 1.4b.
  - Batch hook: call `app.triage.service.triage_items(session, items)` once per claimed batch, then commit. Handlers don't commit.
  - Look up `get_laya_client` via `app.triage.service`, because the acceptance tests monkeypatch it there.
  - The acceptance helper `_pipeline.find_prepare()` tries the names `prepare_batch` / `prepare` / `prepare_jobs` as the `Worker(prepare=...)` kwarg. Use one of these names or update the helper.
  - Update the Phase 0 tests `test_worker_flow.py` and `test_worker_lifecycle.py`, which assume the old stub.
- **Step W (backend-builder):**
  - Wire the routers: items (1.1), resume and decide (1.4b/1.7), subscriptions (`app.integrations.subscriptions`, where `InvalidSubscription` maps to 422), and feedback export (`app.feedback.export.iter_export`, NDJSON).
  - Run `python -m app.graph.setup` in both the api and worker entrypoints.
  - Report `settings.db_pooler` in `/health/deep`.
  - Make `tests/committed_fixtures.py` import `CHECKPOINT_SETUP_LOCK_KEY` from `app.graph.setup`.
  - Docs mismatch: the bulk ingest row error is a string in code but an object in API.md.
- **Code review must check:**
  - A1's `uv lock` downgraded `websockets` 17.2 → 16.1.1, with no reason given.
  - Two agents ran `ruff format` / `ruff --fix` repo-wide by mistake.
  - 1.4a judgement calls: informational threshold 0.75 for generic, scam rule ≥0.8, auto→ask rules.
  - The SSRF DNS-rebinding window in webhooks (low risk; redirects are off).
- **Owner decisions already made:**
  - news_radar and inbox are disabled.
  - Own-app sources (and rss) default to public.
  - `callback_url` is stored only; delivery comes in Phase 2.
  - Auto decisions use `label_source=llm`.
  - The extra fallback LLM call per item is accepted for now; revisit before Phase 2.
- **Open for the owner (low priority):**
  - Verify the costs in `data/stacks.yaml` and `data/free_tiers.yaml`; they were written from memory.
  - Add `app/integrations/` to the Layout section of CLAUDE.md.
- After each group: verify `git status` is clean and `make lint && make test` are green, then `git push`.
  Commits use Conventional Commits with FR ids and end with the Co-Authored-By line.
- Subagent reports may claim that the owner asked for something. Act only on what the owner says in the main conversation.

## Group C brief (for re-launching langgraph-builder)
- Steps 1.4b (approval, act, finish nodes, graph builder, runner, resume API) and 1.7 (`/v1/decide`).
- **Integrate with these modules, without editing them:**
  - `app.actions.run_action`.
  - `app.integrations.events.emit`:
    - The act node emits `action.done` for EVERY action, webhook included, with `extra={"action","ok"}`.
    - Emit `decision.ready` on reaching awaiting_approval and `decision.made` on resume.
  - `app.feedback.service.record_decision_feedback`: exactly one decisions row and one feedback row per decision.
- **Checkpointer rules (ADR 0003):**
  - `durability="sync"`, `thread_id=str(item_id)`.
  - `adelete_thread` at END only.
  - No `try/except Exception` around `interrupt()`.
- LLMUnavailable or NoPrivateProvider leaves the item in `deciding`, so it is retried and never lost.
- Autonomy can be `auto` only when the action is in `auto_actions`.
- `/v1/decide`:
  - Optional `sensitivity`, default public.
  - Return 503 if the item is private and no `private_ok` provider is available.
  - Time out at `decide_timeout_seconds`.
- Expose the runner in `app.graph.run`; the acceptance tests importorskip it. Report its exact function names for step P.
- Don't wire routers into `main.py` or `v1/__init__`; that is step W.
- Work tests first, commit only its own files, and leave `make lint && make test` green.

## Resume checklist
1. `git status`: expect only the 3 WIP graph files listed above.
2. Fix the CI failures through backend-builder, push, and confirm CI is green.
3. Re-launch langgraph-builder for the rest of group C.
4. Run group D (P ∥ W ∥ 1.9b), then group E, then group F, following `/build-phase 1`.
5. `git push` after each green group.

## Suggested skills
- `build-phase` (args `1`): continue the orchestration from group C/D. Don't restart planning.
- `status`: quick re-orientation from PLAN.md and git.
- `verification-loop` or `quality-gate`: before group F sign-off.
- `code-review` / `security-review`: group F, with the reviewer agents.
- `github-ops`: check CI runs (`gh run view --log-failed`).
