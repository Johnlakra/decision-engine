#!/bin/sh
# One image, two roles: `api` (default) migrates, creates the LangGraph checkpoint tables
# (outside Alembic, ADR 0003; idempotent and advisory-locked) then serves; `worker` also runs
# the checkpoint setup so it never races a cold api.
set -eu
case "${1:-api}" in
  api)
    alembic upgrade head
    python -m app.graph.setup
    exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 \
      --proxy-headers --forwarded-allow-ips='*'
    ;;
  worker)
    python -m app.graph.setup
    exec python -m app.workers.run
    ;;
  *)
    exec "$@"
    ;;
esac
