.PHONY: dev down test test-unit test-integration lint fmt migrate api-key demo-item laya-up smoke-llm smoke-laya seed eval

API = cd apps/api && uv run

dev:
	docker compose up -d --build

down:
	docker compose down

test:
	$(API) pytest -q

test-unit:
	$(API) pytest -q tests/unit

test-integration:
	$(API) pytest -q -m integration tests/integration

lint:
	$(API) ruff check .
	$(API) ruff format --check .
	$(API) mypy app

fmt:
	$(API) ruff check --fix .
	$(API) ruff format .

migrate:
	$(API) alembic upgrade head

api-key:
	$(API) python -m app.security.api_keys create

demo-item:
	$(API) python -m scripts.demo_item

laya-up:
	docker compose --profile laya up -d laya

smoke-llm:
	$(API) python -m app.llm.smoke

smoke-laya:
	$(API) python -m app.triage.smoke

seed:
	@echo "seed: Phase 1 (not implemented yet)"

eval:
	@echo "eval: Phase 1 (not implemented yet; usage: make eval NICHE=x)"
