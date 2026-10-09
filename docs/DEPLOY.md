# Deploy

Verify every free-tier limit on the provider's pricing page before relying on it; these were the published
numbers around Oct 2026.

## Profile A — all-in-one free VM (recommended to start)
One **Oracle Cloud Always Free** ARM VM (up to 4 OCPU / 24 GB RAM across Always Free A1 shapes; same place the
Opportunity Radar README recommends). Docker Compose runs everything:
```
db (postgres:16 + pgvector)  redis  api  worker  laya (4 GB limit)  caddy (HTTPS, reverse proxy)
```
- Why: Laya needs ~4 GB RAM; a polling worker keeps Postgres busy all day (bad for scale-to-zero DBs); one box = ₹0.
- Backups: nightly `pg_dump` to Oracle Object Storage (Always Free 20 GB) or to Neon as a cold copy; keep 7 days.
- Domain: any cheap domain or `*.duckdns.org`; Caddy issues TLS automatically.
- Web app: Vercel Hobby (personal, non-commercial) pointing at the API; or `next start` on the same VM.
- Opportunity Radar can run on the same VM and share the `laya` service.

## Profile B — managed free tiers (Render + Neon + Upstash)
| Piece | Where | Limit that matters |
|---|---|---|
| API + worker (one service, `start.sh` runs both) | Render free web service | 512 MB RAM, 0.1 CPU, spins down after 15 min idle (~1 min cold start), 750 instance-hours/month per workspace |
| Postgres | Neon free | 100 CU-hours/month, 1 GB storage/project, scale-to-zero after 5 min idle |
| Redis | Upstash free | 500K commands/month — budgets only, never queue polling |
| Laya | your PC / Oracle VM / any ≥ 4 GB box, reached via HTTPS + `LAYA_API_KEY` | Render free cannot hold it |
| Web | Vercel Hobby | non-commercial |
**Trade-off**: an always-polling worker keeps Neon awake (0.25 CU × 24 h × 30 ≈ 180 CU-h > 100 free). In Profile B
the worker must: poll only during active hours (`WORKER_ACTIVE_HOURS=7-23`), back off to 5 min when idle, and be
woken by the API on new items (in-process trigger). Expect slower first responses. Move to paid Neon/Render (or
Profile A) once used daily.

## Paid path (phase 8)
Render Starter (no spin-down) or a small VM for API/worker; Neon Launch (pay per CU-hour); Laya on a 8 GB VM
(GPU only if > ~50 items/s); paid LLM primary for `decide`/`draft` with acceptable data terms (enables private
items without Ollama); Sentry for errors. All are env changes; no code changes.

## Files the devops-deployer agent creates
`docker-compose.yml` (profiles: `laya`, `ollama`, `prod`), `apps/api/Dockerfile` (multi-stage, uv, non-root),
`services/laya/Dockerfile`, `deploy/Caddyfile`, `deploy/oracle-setup.sh` (Docker, firewall, swap, unattended
upgrades), `render.yaml` (Blueprint for Profile B), `.github/workflows/ci.yml` (lint, test with postgres+pgvector
service, build images), `.github/workflows/deploy.yml` (SSH deploy to VM on tag), `Makefile` targets.

## Pre-deploy gate (`/deploy-check`)
security-auditor sign-off · `make test` green · migrations applied on a copy · `/health/deep` green on staging ·
secrets present (not printed) · budgets set · `LAYA_API_KEY` set · CORS allow-list · backups tested by a restore.

## Local vs production exposure
- Local `docker-compose.yml` publishes Postgres on `127.0.0.1:5432` only (loopback, dev tooling). Redis is not published.
- The future `prod` profile must take `POSTGRES_PASSWORD` from the environment (no `de:de` default), must not publish the db
  or redis ports at all (internal network only), and only Caddy exposes 80/443. Not built yet; this is a requirement note.
- The API image copies only `data/free_tiers.yaml` and `data/stacks.yaml` (explicit in the Dockerfile and `.dockerignore`),
  so a private file added to `data/` can never be baked into an image.
