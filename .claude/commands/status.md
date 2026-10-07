---
description: Show what is built, what is in progress and the next step, from docs/PLAN.md and the repo.
---
Read docs/PLAN.md and `git log --oneline -15`. Report in under 15 lines:
- Current phase and % of its boxes done; any `[~]` in-progress items.
- The next 3 unticked tasks with their owner agents and whether they can run in parallel.
- Blockers: failing `make test` (run it if the repo has code), open questions in docs/plans/*.md, missing env keys
  (compare `.env.example` names with what config requires — never read `.env` values).
Suggest the exact next command (e.g. `/build-phase 1`).
