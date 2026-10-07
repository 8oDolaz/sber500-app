# CLAUDE.md

Guidance for AI assistants working in this repository. Keep it in sync with the code: when a
convention here stops being true, fix this file in the same change.

## What this is

**kainem** is a family assistant built for the Sber 500 × Disrupt accelerator. Two surfaces:

- a **PWA** (React, Russian UI) where a family sees its tasks and events;
- a **Telegram bot** that registers the family, hands out invite links, and turns forwarded
  messages into task/event drafts via an LLM, which the user confirms before anything is saved.

Human-facing docs live in `README.md` (entry point), `docs/architecture.md` (system as built, with
diagrams), `docs/deployment.md`, `docs/load-test.md`, `docs/llm-cost-per-dau.md`, and `docs/adr/`.
Read `docs/architecture.md` before touching auth, capture, analytics or the data model.

## Branches: read this first

- `main` holds only the initial commit (a one-line README). **All code is on `dev`.**
- Base feature branches on `origin/dev` and target `dev` with pull requests, unless told otherwise.
- CI (`.github/workflows/ci.yml`) runs on every pull request and on pushes to `main`.
- Milestone history on `dev`: M0/M1 foundations + leader registration, M2 onboarding/main screen,
  M3 invites, M4 bot capture, M5 metrics/dashboards/load test/deploy kit. Commit messages use
  conventional prefixes (`feat:`, `docs:`, …) and mention the milestone when relevant.

## Repository layout

```
backend/                 Python 3.13 · uv · FastAPI · aiogram 3 · SQLAlchemy 2 (async) · Alembic · Procrastinate
  src/planner/
    domain/              pure rules, no I/O, no frameworks (identity, families, planning)
    application/         Principal and ports
    modules/<name>/      use cases + outbound adapters: service.py, tables.py (SQLAlchemy rows)
      identity, families, registration, planning, assistant (LLM gateway, extraction, capture),
      analytics (event catalog, tracker, ingest, DAU, LLM ledger, prices), notifications
    infra/               db, transactional outbox, jobs (Procrastinate), redis, ratelimit, telemetry, ids
    entrypoints/
      api/               FastAPI app factory, deps, routers/*
      bot/               aiogram handlers, capture, middlewares, texts (all bot copy)
      worker/            Procrastinate periodic jobs + outbox dispatcher loop
    bootstrap.py         composition root: builds the Container (the only module that imports everything)
    settings.py          pydantic-settings; every env var is declared here
    models.py            imports every table module so Base.metadata is complete
    cli.py               ops commands: python -m planner.cli <export-openapi|prices-sync|check-models|set-webhook|cost-report>
  migrations/            Alembic (env.py, versions/YYYYMMDD_<rev>_<slug>.py)
  tests/{unit,integration,evals}
  loadtest/locustfile.py
  prices/                LLM price YAML fallback
frontend/                pnpm 9 workspace · Node 22 · React 19 · Vite 6 · TypeScript 5.8 (strict)
  apps/pwa/              thin shell: Vite config, PWA manifest/service worker, main.tsx
  packages/ui-kit/       design tokens (tokens.css), styles, components
  packages/platform/     PlatformAdapter interface + web implementation (PWA vs future Telegram Mini App)
  packages/api-client/   openapi-fetch client; src/schema.ts is GENERATED from contracts/openapi.json
  packages/analytics/    batched client event tracking with anonymous_id
  packages/app-core/     screens, routes, auth (PKCE handshake, session), i18n/ru.ts (all UI copy), TanStack Query
  e2e/                   Playwright specs (real browser → Vite proxy → FastAPI → Postgres/Redis)
contracts/openapi.json   exported from FastAPI; the contract between backend and frontend (checked in CI)
infra/                   compose.yml (local), compose.loadtest.yml, compose.prod.yml (single VM behind Caddy),
                         .env.prod.example (template for the PROD_ENV_FILE secret), deploy/ (bootstrap.sh once
                         per VM, deploy.sh run by the Deploy workflow), grafana/, prometheus/, nginx/, caddy/,
                         postgres/grafana-reader.sql
docs/                    architecture, deployment, load test, LLM cost, adr/
Makefile                 the canonical dev commands (run from the repo root)
```

## Commands

Run `make` targets from the repo root. Backend commands otherwise run from `backend/` with
`uv run …`; frontend commands from `frontend/` with `pnpm …`.

| Task | Command |
|---|---|
| Postgres (pgvector) + Redis | `make infra-up` / `make infra-down` |
| Backend deps | `cd backend && uv sync` (CI uses `uv sync --frozen`) |
| Migrate | `make migrate` (`uv run alembic upgrade head`) |
| API on :8000 | `make api` (`/healthz`, `/readyz`, `/metrics`, `/docs`) |
| Worker (jobs + outbox, metrics :9101) | `make worker` |
| Bot, long polling (needs a dev `BOT_TOKEN`) | `make bot` |
| Frontend deps | `cd frontend && pnpm install` (CI: `--frozen-lockfile`) |
| PWA dev server on :5173 (proxies `/api` → :8000) | `make web` (`/_kit` shows the UI kit in dev) |
| All tests | `make test` (backend `pytest -q`, frontend `vitest run`) |
| All lint | `make lint` (ruff format --check, ruff check, pyright, lint-imports, `pnpm typecheck`) |
| Regenerate API contract + TS client | `make contract` (**run after any change to API schemas or routes**) |
| E2E | `cd frontend && pnpm e2e` (needs `make infra-up`; starts its own API on :8010 and Vite on :5180) |
| Frontend build | `cd frontend && pnpm build` |
| Load test | `make loadtest` (against the full stack with `infra/compose.loadtest.yml`) |
| Everything in Docker | `docker compose -f infra/compose.yml --profile full up --build` → http://localhost:8080 |
| LLM cost report | `make cost-report` |

Backend tests need Postgres and Redis. They use `TEST_DATABASE_URL` / `TEST_REDIS_URL` when set
(as in CI) and otherwise start throwaway testcontainers, which requires Docker.

Local config: `cp backend/.env.example backend/.env`. `LLM_PROVIDER=fake` costs nothing and is the
default; `openai_compatible` uses the accelerator proxy and spends real budget.

## CI gates (what a pull request must pass)

1. **backend**: ruff format, ruff check, pyright, import-linter, pytest, and `alembic check`
   (models and migrations must match: every model change needs a migration).
2. **contract**: `export-openapi` + `pnpm gen:api` must produce no diff in `contracts/` or
   `frontend/packages/api-client/src/schema.ts`. Forgetting `make contract` fails CI.
3. **frontend**: typecheck, vitest, build.
4. **e2e**: Playwright against a real API with `ENABLE_TEST_ENDPOINTS=true` and the fake LLM.

Run `make lint && make test` locally before pushing. `pytest -m eval` is excluded by default
(`addopts = "-m 'not eval'"`): it calls the real LLM and spends money. Never add it to CI.

## Deployment

`.github/workflows/deploy.yml` deploys to one VM (Timeweb Cloud) over SSH: it rsyncs `backend/`,
`frontend/` and `infra/`, writes `infra/.env.prod` from the `PROD_ENV_FILE` secret, and runs
`infra/deploy/deploy.sh` on the server (pg_dump → `compose build --pull` → `up -d` → wait for the API
→ `set-webhook`, `prices-sync`, `check-models`, Grafana role → `/api/readyz` smoke test). It runs on
pushes to `main` and manually; without `DEPLOY_HOST`, `DEPLOY_SSH_KEY` and `PROD_ENV_FILE` in the
GitHub `production` environment it skips. `deploy.sh` must stay idempotent: every step may run again
on the next deploy. New production settings go into `infra/.env.prod.example` (the only committed
`.env.*` file besides `backend/.env.example`). Guide: `docs/deployment.md` §5.

## Backend conventions

**Layering is enforced by import-linter** (`backend/pyproject.toml`), in this order:
`entrypoints → bootstrap → modules → application → domain`. Also:

- `planner.domain` imports no frameworks and no `planner.infra` (no SQLAlchemy, FastAPI, aiogram,
  Redis, httpx, openai, Procrastinate). Domain objects are frozen dataclasses that validate in
  `__post_init__` and raise domain errors (`PlanningError`, …).
- `planner.infra` never imports `modules`, `entrypoints` or `bootstrap`.
- Only `bootstrap.py` wires everything. New services are added to the `Container` dataclass and
  constructed in `build_container()`; entrypoints read them from the container, never instantiate.

**Services** (`modules/<name>/service.py`):
- Take `Database`, `Tracker` and `app_version` in the constructor.
- Either open their own unit of work with `async with self._db.transaction() as session:`
  (commit on success, rollback on error) or accept an `AsyncSession` so callers can compose several
  writes in one transaction (see `PlanningService.create_task`). Read-only queries use `self._db.sessions()`.
- **Every write goes through a command on a service.** The PWA, the bot and the LLM drafts all create
  tasks through the same `PlanningService` call, so validation, family scoping and analytics live once.
- Track analytics inside the same session as the change via `self._tracker.track(session, Event(...), ctx)`.
  Server events go through the transactional outbox, so "created but not counted" cannot happen.

**Tables** (`modules/<name>/tables.py`): SQLAlchemy 2 `Mapped[...]` classes named `<Thing>Row`,
inheriting `planner.infra.db.Base` (which carries the constraint naming convention). UUID primary keys
come from `planner.infra.ids.new_id()`. Timestamps are `DateTime(timezone=True)` in UTC; all-day
dates are `Date`. Every family-owned row has `family_id` with `ondelete="CASCADE"`.
A new table module must be imported in `planner/models.py` or Alembic and tests will not see it.

**Migrations**: `cd backend && uv run alembic revision --autogenerate -m "<slug>"`. Files are named
`YYYYMMDD_<rev>_<slug>.py` and excluded from ruff. Procrastinate tables and `analytics_events_*`
partitions are excluded from autogenerate (`migrations/env.py`). Metric definitions live as SQL views
in `*_m5_metrics_views.py`; every view must exclude test users, load-test traffic and the fake LLM.

**API** (`entrypoints/api`):
- `create_app()` is a factory (`uvicorn … --factory`). It refuses to start in staging/production
  with the dev `JWT_SECRET`.
- Routers live in `routers/*.py` with `APIRouter(prefix="/v1/…")` and are registered in `app.py`.
  Pydantic response models are defined next to the router with an `of(row)` classmethod.
- Use the typed dependencies from `deps.py`: `ContainerDep`, `AuthDep` (must be signed in),
  `MemberDep` (family-scoped routes `/v1/families/{family_id}/…` check membership on every request),
  `PlatformDep` (validated `X-Client-Platform` header), `ClientIpDep`.
- The `Principal` comes only from a verified access token, never from client input.
- Test-only routes (`routers/testing.py`, `/v1/test/*`) exist only when `ENABLE_TEST_ENDPOINTS=true`
  **and** `ENV` is `local` or `test`. They simulate the bot for e2e tests and are excluded from the schema.
- The middleware in `app.py` sets `x-request-id`, records Prometheus metrics, and records DAU activity.

**Bot** (`entrypoints/bot`):
- aiogram 3. Services are injected into handlers by parameter name through `Dispatcher(**services)`
  in `bot/app.py`. Add a new service there before using it in a handler.
- `handlers.py` holds commands/callbacks/inline queries; `capture.py` handles everything else in a
  private chat (must stay registered after the command router).
- **All bot copy lives in `texts.py`**, HTML parse mode: escape anything user-provided with `html.escape`.
- Locally the bot long-polls (`make bot`). In production it runs as a webhook inside the API
  (`/api/webhooks/telegram`, verified by `BOT_WEBHOOK_SECRET`). One bot token per environment.

**Worker** (`entrypoints/worker/tasks.py`): Procrastinate periodic tasks decorated with
`@job_app.periodic(cron=…, periodic_id=…)` + `@job_app.task(queue="maintenance")`, plus the
`outbox_loop`. Procrastinate uses the sync DSN (`settings.sync_database_url`).

**Settings** (`settings.py`): pydantic-settings, `.env` file, env var names are the upper-cased
field names. Secrets are `SecretStr` (read with `.get_secret_value()`). Add new config here and
document it in `backend/.env.example` and, if deploy-relevant, in `docs/deployment.md`.

**Analytics events** (`modules/analytics/catalog.py`): adding a metric means defining a Pydantic
model with `@analytics_event("name", source=…, counts_as_active=…, preauth_allowed=…)` and calling
`tracker.track(...)` on the server or `track()` in the frontend. Client events are validated against
this catalog; pre-login events are accepted only when `preauth_allowed=True`. The DAU definition is
ADR 0003: changing it requires a new ADR, not a code tweak.

**LLM** (`modules/assistant`): one `LLMProvider` port with `OpenAICompatibleProvider` (real, via the
accelerator proxy) and `FakeProvider` (tests, CI, load tests). Every call is ledgered in `llm_usage`
with cost in micro-rubles; `LLMBudgetExceeded` (HTTP 429 from the proxy) is never retried and the
product degrades to "save as plain task". Message text is fenced as untrusted data in prompts; only
first names go to the model. Extraction quality has a golden set in `tests/evals/`.

**Observability**: structlog with dotted event names (`"outbox.loop_failed"`, `"llm.spend_checked"`)
and keyword fields; Prometheus metrics are declared in `infra/telemetry.py`. Grafana dashboards and
alert rules are in `infra/grafana/` and `infra/prometheus/alerts.yml`. Keep them updated when
metrics change.

**Style**: ruff, line length 120, target py313, rules `E F W I B UP ASYNC BLE RUF SIM`. Cyrillic in
strings and comments is intentional (RUF001-003 are ignored). `BLE001` (blind except) needs a
`# noqa: BLE001 — reason` where the loop must survive. pyright in `standard` mode over `src` and `tests`.
Use modern typing (`X | None`, `list[...]`, `StrEnum`, PEP 695 generics).

## Frontend conventions

- pnpm workspace with `apps/*` and `packages/*`; packages are `@kainem/<name>` with `workspace:*`
  dependencies and `main: src/index.ts` (no build step for packages). Each package has its own
  `typecheck` script; `pnpm -r typecheck` runs them all.
- `tsconfig.base.json`: `strict`, `noUncheckedIndexedAccess`, `verbatimModuleSyntax`, `jsx: react-jsx`.
  Use `import type` for types.
- **Do not edit `packages/api-client/src/schema.ts` by hand**: it is generated by `pnpm gen:api`
  from `contracts/openapi.json`. The client (`openapi-fetch`) adds platform headers, the bearer
  token, and refreshes once on a 401 outside `/v1/auth/*`.
- **All UI copy is in `packages/app-core/src/i18n/ru.ts`.** The product is Russian-only. Strings
  marked `TODO(design)` are placeholders awaiting real copy from Figma.
- Screens live in `packages/app-core/src/screens/`, named after the SPEC screen letters in comments
  (A welcome, C onboarding, D home, …). Routing is `react-router` 7 with `RequireSession` /
  `GuestOnly` guards in `routes.tsx`. Data fetching uses TanStack Query and refetches on focus.
- Platform-specific behaviour (storage, share, install prompt, launch context) goes through the
  `PlatformAdapter` in `packages/platform`; do not call browser APIs directly from screens.
- Design tokens are CSS variables in `packages/ui-kit/src/tokens.css`; components in `components.tsx`.
- Analytics: `services.analytics.track("event_name", props)` with names from the backend catalog.
- The service worker must never cache `/api/*` (`navigateFallbackDenylist` in `apps/pwa/vite.config.ts`).

## Testing conventions

Backend (`backend/tests`):
- `unit/` tests domain and pure logic, no infra. `integration/` tests are auto-marked
  `integration` by path and get Postgres/Redis through the session-scoped `infra_urls` fixture.
- The `container` fixture builds a real `Container` with a `FakeProvider`, truncates all tables and
  flushes Redis before each test. The `client` fixture (integration conftest) gives an
  `httpx.AsyncClient` over the ASGI app with the lifespan running; the bot dispatcher is reachable
  through `client.app`. `tests/integration/telegram.py` holds helpers to feed fake Telegram updates.
- pytest runs in `asyncio_mode = "auto"` with a session-scoped loop: `async def` tests need no decorator.
- `evals/` (`-m eval`) hits the real proxy, needs `LLM_API_KEY`, and spends budget. Run deliberately.

Frontend:
- Vitest + jsdom + Testing Library, files `*.test.ts(x)` next to the code. `vitest.setup.ts` installs
  `fake-indexeddb` and cleans up after each test. `packages/app-core/src/test-utils.tsx` provides
  `fakeBackend`, `makeServices`, `renderApp`, `memoryStorage`, `fakeInstall`: use them instead of
  mocking `fetch` ad hoc.
- Playwright e2e (`frontend/e2e/*.spec.ts`) drives an iPhone 13 viewport and simulates the bot side
  through `/api/v1/test/*`. Screenshots are written to `e2e/screens/` (gitignored).

## Invariants to preserve

- **Nothing is written from a bot message before the user presses «Сохранить»** (propose → confirm,
  drafts expire after 24 h).
- **Family scoping**: every family-owned query filters by `family_id`; family routes use `MemberDep`.
- **Secrets at rest are hashed** (login tokens, magic links, refresh tokens: SHA-256). Access JWTs
  live 15 minutes in memory only; refresh cookies are httpOnly, rotate on use, and reuse revokes the chain.
- **Never commit secrets.** `.env`, `infra/.env.prod`, keys and certificates are gitignored; the only
  committed env files are `*.example`. `LLM_API_KEY` stays in env.
- **Dashboards exclude test data**: `users.is_test`, `app_version = 'loadtest'`, the fake LLM.
- Dotfolders are gitignored wholesale (`.*/`) except `.github/`. Do not rely on committing
  `.claude/`, `.vscode/` or similar.
- Time: store instants in UTC with the family's IANA timezone; all-day events and due dates are dates.
- Data residency: the stack is designed to run in a Russian cloud (152-FZ) with the Cloud.ru-backed
  LLM proxy (ADR 0001). Do not add third-party services that move user data abroad without an ADR.

## Checklist for common changes

- **New API endpoint**: router in `entrypoints/api/routers/`, register in `app.py`, use `deps.py`
  dependencies, then `make contract`, then use the typed client in the frontend. Add an integration test.
- **New table or column**: `tables.py` → import in `models.py` if new module → `alembic revision
  --autogenerate` → review the migration → `alembic check` passes → update `conftest.py` TRUNCATE list
  if the table holds per-test data → update `docs/architecture.md` §5 if the model changed.
- **New analytics event**: catalog model → `tracker.track` / frontend `track` → consider the
  `metrics_*` views and Grafana product dashboard → never change the DAU definition without an ADR.
- **New setting**: `settings.py` → `backend/.env.example` → `docs/deployment.md` table if operators must set it.
- **New bot text or UI string**: `bot/texts.py` or `i18n/ru.ts`, never inline.
- **New background job**: `worker/tasks.py` with a `periodic_id`, queue `maintenance`.
- **Architecture decision**: add `docs/adr/000N-<slug>.md` (Status, Context, Decision, Consequences)
  and reference it from `docs/architecture.md`.

## Known gaps and TODOs in the code

- Several bot and UI strings are marked `TODO(design)` pending final copy from Figma.
- Postgres is the pgvector image "ready for embeddings later"; no embeddings are used yet.
- A Telegram Mini App shell is anticipated by `PlatformAdapter` but only the PWA exists.
