# kainem

_Sber 500 x Disrupt app repo._

A family assistant. People use it through a **PWA** (web app) and a **Telegram bot**. The bot registers the family, sends invite links, and turns forwarded messages into tasks and events.

| Document | What's in it |
|---|---|
| [`docs/deployment.md`](docs/deployment.md) | How to run locally with your bot and deploy to a server: files to create, credentials, commands, checks |
| [`docs/architecture.md`](docs/architecture.md) | The system as built: components, deployment, code structure, key flows, data model, analytics, security (with diagrams) |
| [`docs/load-test.md`](docs/load-test.md) | Load test: 10 RPS with 0 errors (5× also held), how to run it |
| [`docs/llm-cost-per-dau.md`](docs/llm-cost-per-dau.md) | LLM cost per daily active user: model, prices, scenarios, how it's measured |
| [`docs/adr/`](docs/adr) | Architecture decisions |

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
backend/loadtest/             Locust load test
backend/prices/               LLM price lists (fallback for the cost ledger)
infra/compose.yml             local Postgres + Redis (+ `full` profile: all services, Prometheus, Grafana)
infra/compose.loadtest.yml    load-test override (test endpoints on, per-IP limits raised)
infra/compose.prod.yml        single-VM deployment behind Caddy (TLS)
infra/grafana/, prometheus/   dashboards, data sources, alert rules
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

Everything in containers: `docker compose -f infra/compose.yml --profile full up --build`, then open http://localhost:8080 (or set `WEB_PORT`). This also starts Prometheus (http://localhost:9090) and Grafana (http://localhost:3000, admin/admin) with the kainem dashboards.

## Tests and checks

```bash
make test       # backend unit + integration (testcontainers start Postgres/Redis), frontend vitest
make lint       # ruff, pyright, import-linter (layer contracts), tsc
make contract   # after changing API schemas: regenerate openapi.json and the TS client
```

Integration tests use `TEST_DATABASE_URL` and `TEST_REDIS_URL` when they are set (as in CI). Otherwise they start throwaway containers.

## Telegram bot setup

Use a separate bot per environment (dev, staging, production). In @BotFather:

1. `/newbot` → put the token in `BOT_TOKEN` and the username (without `@`) in `BOT_USERNAME`.
2. `/setinline` → enable inline mode. The «Поделиться» button on the invite message uses it (placeholder: `пригласить в семью`).
3. `/setinlinefeedback` → `Enabled`, so shared invites are counted (`invite_shared`).
4. `/setcommands` → `start - Начать` and `invite - Ссылка-приглашение в семью`.

Locally the bot runs in long polling mode (`make bot`). On a server it runs as a webhook inside the API process: set `BOT_WEBHOOK_SECRET` and `PUBLIC_APP_URL`, then run `python -m planner.cli set-webhook`.

## LLM access (Sber500 accelerator)

- The proxy is OpenAI-compatible: `LLM_BASE_URL=https://shared1.multitool.works:4000/v1`, and `LLM_API_KEY` goes in env only, never in git.
- Set `LLM_PROVIDER=openai_compatible` to use it. `python -m planner.cli check-models` verifies the configured models still exist.
- Every call is written to the `llm_usage` ledger, with its cost in micro-rubles.
- A spend alert fires at 50% and 80% of `LLM_PROGRAM_BUDGET_RUB`. Each family also has a daily quota.
- `python -m planner.cli prices-sync` refreshes `model_prices` from the proxy's `/model/info`, or from a YAML file with `--file`.
- Extraction quality: `cd backend && LLM_API_KEY=… EVAL_MODELS=deepseek-v4.1-flash,gigachat-3-pro uv run pytest -m eval -s`. It runs the 30-message golden set (`tests/evals/extraction_cases.yaml`), prints accuracy and ₽ per call for each model, writes `eval-report.json`, and **spends budget**.
- With `LLM_PROVIDER=fake`, each message becomes one task titled with its first line. Local dev, e2e and load tests use this.
- See [ADR 0001](docs/adr/0001-llm-provider.md).

## Observability

- **Dashboards** (Grafana, provisioned from `infra/grafana/`):
  - "kainem — technical" (Prometheus): request rate, **5xx error rate**, latency percentiles, Telegram updates, LLM calls and spend, outbox lag, analytics rejects.
  - "kainem — product" (Postgres views `metrics_*`): **DAU**/WAU/MAU by platform, new users by source, new families, registration and invite funnels, AI confirm rate, **LLM ₽/day and ₽ per DAU**, retention, family activation.
  - Every view excludes test and load-test accounts and the fake LLM.
- **Alerts** (`infra/prometheus/alerts.yml`): 5xx above 2%, p95 latency above 1 s, failing bot updates, failing LLM calls, exhausted LLM budget, outbox lag, analytics rejects.
- **Metrics** (Prometheus): `/metrics` on the API (not exposed through nginx), `:9101/metrics` on the worker.
- **Logs:** structured JSON (structlog), with `x-request-id` propagated.
- **Errors:** Sentry, when `SENTRY_DSN` is set.
- **LLM cost:** `python -m planner.cli cost-report --days 7` prints ₽ per DAU from the ledger. Details are in [`docs/llm-cost-per-dau.md`](docs/llm-cost-per-dau.md).

## Load test

Locust scenarios in `backend/loadtest/`, run against the full stack with `infra/compose.loadtest.yml`. Results and commands are in [`docs/load-test.md`](docs/load-test.md).

## Deploy (single VM, GitHub Actions)

Full step-by-step guide: [`docs/deployment.md`](docs/deployment.md) §5. In short, for a VM in a Russian cloud (152-FZ, e.g. Timeweb Cloud):

1. Prepare the VM once: `infra/deploy/bootstrap.sh` (Docker, `deploy` user, firewall).
2. Fill `infra/.env.prod.example` and put it in the `PROD_ENV_FILE` secret of the GitHub `production`
   environment, with `DEPLOY_HOST` and `DEPLOY_SSH_KEY`.
3. Actions → **Deploy** → *Run workflow*. Pushes to `main` deploy automatically once configured.

The workflow rsyncs the sources and runs `infra/deploy/deploy.sh` on the server: database backup,
`docker compose up -d --build`, migrations, Telegram webhook, LLM prices, Grafana role, smoke test.

- **TLS:** Caddy terminates it for `DOMAIN` (automatic certificates) and is the only public service. Grafana and Prometheus listen on `127.0.0.1`; reach them through an SSH tunnel.
