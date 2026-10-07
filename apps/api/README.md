# Decision Engine API

Dev notes. Run everything from the repo root via `make`, or from here with `uv run`.

- Setup: `uv sync`
- Tests: `make test` (integration tests skip loudly when `TEST_DATABASE_URL` is unreachable)
- Lint: `make lint` (ruff check, ruff format --check, mypy); autofix with `make fmt`
- Run: `uv run uvicorn app.main:app --reload`
- LLM providers may only be imported under `app/llm` (ruff banned-api rule).
- `litellm` is pinned exactly; bump it deliberately and re-lock with `uv lock`.
