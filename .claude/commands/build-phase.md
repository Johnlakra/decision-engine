---
description: Build one phase of docs/PLAN.md end to end with the agent team (plan → build in parallel → test → review → docs).
argument-hint: <phase number, e.g. 0>
---
Build **phase $ARGUMENTS** of docs/PLAN.md. You are the orchestrator: subagents cannot call each other, so you call them.

1. **Plan** — call the `planner` agent for phase $ARGUMENTS. Read its `docs/plans/phase-$ARGUMENTS.md`.
   If it lists design decisions, call `architect` first and wait for the ADRs. If it lists questions for the owner,
   ask them now (one message, all questions) and stop until answered.
2. **Design (UI phases only: 3, 6, 7)** — call `ui-ux-designer` to write screen specs and tokens before builders start.
3. **Build** — for each parallel group in the plan, launch the owner agents in parallel (one Agent call each, same
   message) with: the step ids, files they own, interfaces to honour, FR ids, and "tests first". Wait for the group,
   read their reports, resolve conflicts (two agents touching one file = run them sequentially), then the next group.
4. **Test** — call `test-writer` to fill gaps against the phase's FR ids and acceptance checks. Run `make lint && make test`.
   Failures go back to the owning builder with the failing output.
5. **Review** — call `code-reviewer` on `git diff` for the phase. Send BLOCKING items to their owners; repeat review
   until approve. For phases with auth, connectors, private data, webhooks or deploy (0, 4, 5, 7, 8) also call
   `security-auditor`.
6. **UX review (UI phases)** — call `ui-ux-designer` to review screenshots; fix via `frontend-builder`/`mobile-builder`.
7. **Acceptance** — run every acceptance check listed for the phase in docs/PLAN.md yourself and paste the results.
8. **Commit** — small Conventional Commits per step (`feat(triage): … (FR-20)`), then call `docs-keeper` to tick boxes.
9. Report: what was built, acceptance results, commits, follow-ups, and the next command.

Never skip tests or review to go faster. Never enable a Laya niche in `on` mode in this command.
