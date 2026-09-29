.PHONY: infra-up infra-down migrate api worker bot web test lint contract

infra-up:        ## Postgres + Redis for local dev
	docker compose -f infra/compose.yml up -d postgres redis

infra-down:
	docker compose -f infra/compose.yml down

migrate:
	cd backend && uv run alembic upgrade head

api:             ## FastAPI on :8000
	cd backend && uv run uvicorn planner.entrypoints.api.app:create_app --factory --reload --port 8000

worker:          ## Procrastinate worker + outbox dispatcher (metrics on :9101)
	cd backend && uv run python -m planner.entrypoints.worker

bot:             ## Telegram bot in long-polling mode (needs BOT_TOKEN)
	cd backend && uv run python -m planner.entrypoints.bot

web:             ## PWA dev server on :5173 (proxies /api → :8000)
	cd frontend && pnpm dev

test:
	cd backend && uv run pytest -q
	cd frontend && pnpm test

lint:
	cd backend && uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run lint-imports
	cd frontend && pnpm typecheck

contract:        ## Regenerate OpenAPI spec and the TS client
	cd backend && uv run python -m planner.cli export-openapi ../contracts/openapi.json
	cd frontend && pnpm gen:api
