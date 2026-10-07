.PHONY: dev down test test-unit test-integration lint fmt migrate api-key demo-item laya-up smoke-llm smoke-laya seed eval

API = cd apps/api && uv run

dev:
	docker compose up -d --build

down:
	docker compose --profile laya down

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
	$(API) python -m app.security.api_keys create --name $(or $(NAME),local-admin) --scopes $(or $(SCOPES),admin)

demo-item:
	$(API) python -m scripts.demo_item

# DE_LAYA_URL is set only here (compose maps it to LAYA_URL); plain `make dev` leaves it empty.
laya-up:
	DE_LAYA_URL=http://laya:8000 docker compose --profile laya up -d --build laya api worker

smoke-llm:
	$(API) python -m app.llm.smoke

smoke-laya:
	$(API) python -m app.triage.smoke

seed:
	@echo "seed: Phase 1 (not implemented yet)"

eval:
	@echo "eval: Phase 1 (not implemented yet; usage: make eval NICHE=x)"
