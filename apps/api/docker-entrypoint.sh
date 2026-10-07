#!/bin/sh
# One image, two roles: `api` (default) migrates then serves; `worker` runs the job loop.
set -eu
case "${1:-api}" in
  api)
    alembic upgrade head
    exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 \
      --proxy-headers --forwarded-allow-ips='*'
    ;;
  worker)
    exec python -m app.workers.run
    ;;
  *)
    exec "$@"
    ;;
esac
