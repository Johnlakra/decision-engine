---
description: Pre-deploy gate for the chosen profile (A = Oracle VM all-in-one, B = Render + Neon + Upstash).
argument-hint: <A|B> [staging|prod]
---
Deploy readiness for profile $ARGUMENTS (docs/DEPLOY.md).
1. `make lint && make test`; `alembic upgrade head` on a fresh database copy.
2. Call `security-auditor` for a go/no-go audit (writes docs/security/audit-<date>.md).
3. Call `devops-deployer` to verify: images build, compose/blueprint valid, required secrets listed (names only, never
   values), backups + restore script tested, budgets set, LAYA_API_KEY and CORS configured, health checks wired, and
   current free-tier limits still match docs/DEPLOY.md (web check, dated).
4. Print a checklist with ✅/❌ and the exact commands to deploy. Do not deploy unless I confirm.
