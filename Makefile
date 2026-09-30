.PHONY: infra-up infra-down migrate api worker bot web test lint contract loadtest cost-report

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

loadtest:        ## ~10 RPS for 5 minutes against the full stack with infra/compose.loadtest.yml (see docs/load-test.md)
	cd backend && MEMBER_ACTIONS_PER_SEC=0.18 uv run --group loadtest locust -f loadtest/locustfile.py --headless \
		--host http://localhost:$${WEB_PORT:-8080} -u 25 -r 5 -t 5m --csv lt-10rps --html lt-10rps.html

cost-report:     ## LLM ₽ per DAU for the last 7 days
	cd backend && uv run python -m planner.cli cost-report --days 7
