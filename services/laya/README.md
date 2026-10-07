# Laya service

Runs `laya-serve` 0.3.27 (CPU torch). The API never imports Laya; it calls `POST /v1/systemone/batch`.

- Build: `docker build -t de-laya services/laya`
- Run: `docker run -p 8000:8000 -e LAYA_API_KEY=... -v laya-models:/models de-laya` (or `make laya-up`)
- First start downloads about 1.5 GB of weights into `/models`; keep that volume.
- Env: `LAYA_API_KEY` (required, same value as the API's), `LAYA_MODELS=english` to save RAM
  (Hindi/Punjabi/Hinglish need `multilingual`), `LAYA_MAX_CONCURRENT` (over it: 503 + `Retry-After: 1`).
- Liveness: `GET /health` is open; with a valid Bearer token it also lists loaded checkpoints.
- Smoke: `make smoke-laya` (exit 0 ok, 1 fail, 2 skipped when `LAYA_URL` is empty).
- Limits: 64 states and 64 questions per batch, 50,000 chars per state. The client sends at most 32 states.
