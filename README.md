# kainem

_Sber 500 x Disrupt app repo._

A family assistant. People use it through a **PWA** (web app) and a **Telegram bot**. The bot registers the family, sends invite links, and turns forwarded messages into tasks and events.

Architecture decisions: [`docs/adr/`](docs/adr).

## Repository layout

```
backend/     Python 3.13 · FastAPI · aiogram 3 · SQLAlchemy 2 + Alembic · Procrastinate
  src/planner/
    domain/ application/      pure core (grows from M1)
    modules/analytics/        event catalog, tracker, ingest, activity (DAU), llm ledger, prices
    modules/assistant/        LLM gateway: OpenAI-compatible proxy adapter + fake provider
    infra/                    db, transactional outbox, jobs, telemetry
    entrypoints/{api,bot,worker}
    bootstrap.py              composition root
  migrations/                 Alembic
  tests/{unit,integration}
frontend/    pnpm workspace · React 19 · Vite 6 · vite-plugin-pwa
  apps/pwa/                   PWA shell: manifest, service worker, web platform adapter
  packages/ui-kit/            design tokens (SPEC §2) and components
  packages/platform/          PlatformAdapter interface and web implementation
  packages/analytics/         batched client tracking with anonymous_id
  packages/api-client/        typed client generated from contracts/openapi.json
  packages/app-core/          screens and routing (platform-agnostic)
contracts/openapi.json        exported from FastAPI; source for the TS client
infra/compose.yml             local Postgres + Redis (+ `full` profile for all services)
docs/adr/                     architecture decision records
```

## Local development

Requirements: Docker, [uv](https://docs.astral.sh/uv/), Node 22 LTS (see `frontend/.nvmrc`), pnpm 9.

```bash
make infra-up                          # Postgres (pgvector) + Redis
cp backend/.env.example backend/.env   # LLM_PROVIDER=fake spends nothing
cd backend && uv sync && cd ..
make migrate
make api        # http://127.0.0.1:8000  (/healthz, /readyz, /metrics, /docs)
make worker     # jobs + outbox dispatcher, metrics on :9101
make bot        # optional: long polling, needs BOT_TOKEN of a *dev* bot
cd frontend && pnpm install && cd ..
make web        # http://localhost:5173  (/_kit shows the UI kit in dev)
```

Everything in containers: `docker compose -f infra/compose.yml --profile full up --build`, then open http://localhost:8080 (or set `WEB_PORT`).

## Tests and checks

```bash
make test       # backend unit + integration (testcontainers start Postgres/Redis), frontend vitest
make lint       # ruff, pyright, import-linter (layer contracts), tsc
make contract   # after changing API schemas: regenerate openapi.json and the TS client
```

Integration tests use `TEST_DATABASE_URL` and `TEST_REDIS_URL` when they are set (as in CI). Otherwise they start throwaway containers.

## LLM access (Sber500 accelerator)

- The proxy is OpenAI-compatible: `LLM_BASE_URL=https://shared1.multitool.works:4000/v1`, and `LLM_API_KEY` goes in env only, never in git.
- Set `LLM_PROVIDER=openai_compatible` to use it. `python -m planner.cli check-models` verifies the configured models still exist.
- Every call is written to the `llm_usage` ledger, with its cost in micro-rubles.
- A spend alert fires at 50% and 80% of `LLM_PROGRAM_BUDGET_RUB`. Each family also has a daily quota.
- `python -m planner.cli prices-sync` refreshes `model_prices` from the proxy's `/model/info`, or from a YAML file with `--file`.
- See [ADR 0001](docs/adr/0001-llm-provider.md).

## Observability

- **Metrics** (Prometheus): `/metrics` on the API, `:9101/metrics` on the worker.
  - `http_requests_total{route,status}`
  - `bot_updates_total{update_type,status}`
  - `llm_calls_total`, `llm_spend_rub_total`
  - `outbox_lag_seconds`
  - `analytics_events_rejected_total{reason}`
- **Logs:** structured JSON (structlog), with `x-request-id` propagated.
- **Errors:** Sentry, when `SENTRY_DSN` is set.
- **Product analytics:** the `analytics_events` table (partitioned by month), `user_activity_daily` for DAU (definition: [ADR 0003](docs/adr/0003-active-user.md)), and `llm_usage`.
