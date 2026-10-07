---
description: Independent review of current changes (code-reviewer, plus security-auditor when sensitive) before commit.
argument-hint: "[optional: path or commit range]"
---
Review this scope: "$ARGUMENTS" (if empty: the uncommitted changes plus the last commit).
1. Run `git status`, `git diff --stat`, `make lint`, `make test` and keep the outputs.
2. Call `code-reviewer` with the scope and the outputs.
3. If the diff touches app/security, connectors, auth, OAuth, webhooks, llm/privacy, actions that send anything, farmer
   data or deploy files, also call `security-auditor`.
4. Summarise BLOCKING / SHOULD / NIT with owners. Do not fix anything unless I say so.
