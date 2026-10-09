# kainem — system architecture (as built)

This describes the system as implemented: MVP milestones M0–M5. Decisions and their reasons are in [`docs/adr/`](adr).

kainem is a family assistant with two surfaces:
- a **PWA** (web app), where the family sees its tasks and events;
- a **Telegram bot**, which registers the family, sends invite links, and turns forwarded messages into tasks and events after the user confirms them.

## 1. System context

```mermaid
flowchart LR
    subgraph People
        L["Leader<br/>(creates the family)"]
        A["Acceptor<br/>(joins by invite)"]
    end

    subgraph Clients
        PWA["PWA<br/>React · Vite · service worker"]
        TG["Telegram app<br/>chat with kainem bot"]
    end

    subgraph Server["kainem (one VM, Docker)"]
        CADDY["Caddy<br/>TLS"]
        WEB["nginx<br/>PWA files + /api proxy"]
        API["API<br/>FastAPI"]
        BOT["Bot<br/>aiogram, long polling"]
        XRAY["xray<br/>VLESS client"]
        WORKER["Worker<br/>outbox + scheduled jobs"]
        PG[("PostgreSQL<br/>data · analytics · job queue")]
        RD[("Redis<br/>rate limits · quotas · DAU dedupe")]
        PROM["Prometheus"]
        GRAF["Grafana<br/>dashboards"]
    end

    TGAPI["Telegram Bot API"]
    VPN["VLESS server<br/>(outside Russia)"]
    LLM["Sber500 LLM proxy<br/>(LiteLLM → Cloud.ru:<br/>DeepSeek, GigaChat)"]

    L & A --> PWA & TG
    PWA -- HTTPS --> CADDY --> WEB -- "/api" --> API
    TG <--> TGAPI
    BOT -- "getUpdates, replies (SOCKS)" --> XRAY --> VPN --> TGAPI
    API & BOT --> PG & RD
    API -- "extraction" --> LLM
    WORKER --> PG
    PROM -- scrape --> API & WORKER & BOT
    GRAF --> PROM & PG
```

## 2. Deployment

`infra/compose.prod.yml` runs everything on one VM in a Russian cloud (152-FZ). Only Caddy is public; it also serves Grafana at `/grafana/` (sign-in required). Prometheus listens on `127.0.0.1` and is reached through an SSH tunnel. Telegram is blocked in Russia, so the bot long-polls the Bot API through a VLESS proxy instead of receiving a webhook (ADR 0004).

| Container | Role | Scales by |
|---|---|---|
| `caddy` | TLS (Let's Encrypt), the only public ports (80/443) | — |
| `web` | nginx: PWA static files; `/api/*` → API. Blocks `/api/metrics`, sets the real client IP | stateless |
| `api` | FastAPI REST, 2 uvicorn workers; runs migrations on start. Also serves the Telegram webhook route, unused in production (ADR 0004) | more workers or containers (stateless) |
| `bot` | aiogram in long-polling mode: commands, invites, capture; metrics on `:9102` | exactly one per bot token |
| `xray` | Xray-core VLESS client: SOCKS proxy `xray:1080` for Bot API traffic only; config from the `XRAY_CONFIG` secret | — |
| `worker` | Procrastinate jobs (spend check, price sync, draft expiry, partitions, cleanup) + the outbox dispatcher loop | one is enough; the dispatcher uses `SKIP LOCKED` |
| `postgres` | All data, analytics tables, the job queue (pgvector image, ready for embeddings later) | managed Postgres later |
| `redis` | Rate limits, per-family LLM quota, DAU dedupe, bot «Изменить» state | — |
| `prometheus`, `grafana` | Technical and product dashboards, alert rules | — |

Load test ([`load-test.md`](load-test.md)): **10.2 RPS with 0 errors** (p95 75 ms) and 52 RPS with 0 errors. The API used about 7% of one core at 10 RPS.

## 3. Code structure

A **modular monolith with ports and adapters**. Both toolchains live in one repo:
- the backend is Python 3.13 (uv);
- the frontend is TypeScript (pnpm workspace);
- `contracts/openapi.json` is the contract between them, and CI fails if the generated TS client drifts from the backend.

```mermaid
flowchart TB
    subgraph entry["entrypoints (adapters in)"]
        E1["api/ — FastAPI routers"]
        E2["bot/ — aiogram handlers"]
        E3["worker/ — jobs, outbox loop"]
    end
    BOOT["bootstrap.py — composition root"]
    subgraph modules["modules (use cases + adapters out)"]
        M1["identity — users, Telegram login,<br/>sessions"]
        M2["families — families, members,<br/>invites"]
        M3["registration — /start flows,<br/>onboarding"]
        M4["planning — tasks, events"]
        M5["assistant — LLM gateway,<br/>extraction, drafts"]
        M6["analytics — catalog, tracker,<br/>DAU, LLM ledger"]
        M7["notifications — bot chats"]
    end
    APP["application — Principal, ports"]
    DOM["domain — pure rules: handshake, roles,<br/>NewTask/NewEvent"]
    INFRA["infra — db, outbox, jobs,<br/>telemetry, rate limit"]

    entry --> BOOT --> modules --> APP --> DOM
    modules --> INFRA
```

**Rules**, enforced in CI by `import-linter`:
- the domain imports no frameworks and does no I/O;
- infra never imports modules or entrypoints;
- layers only depend downward.

**Every write goes through a command.** The PWA, the bot and the LLM drafts all create tasks through the same `PlanningService` call. Validation, family scoping and analytics therefore live in one place.

**Frontend packages:**
- `ui-kit`: the Figma tokens and components.
- `platform`: the `PlatformAdapter` for PWA vs a future Telegram Mini App, including add-to-home-screen.
- `api-client`: generated from the OpenAPI spec; refreshes on 401.
- `analytics`: batched client events with an `anonymous_id`.
- `app-core`: screens, routing, the session gate, TanStack Query.
- `apps/pwa`: the thin shell.

## 4. Key flows

### 4.1 Leader registration: the PWA logs in through the bot (ADR 0002)

```mermaid
sequenceDiagram
    actor U as Leader
    participant P as PWA
    participant API
    participant B as Bot (in API)
    participant T as Telegram

    U->>P: «Зарегистрироваться» (screen B)
    P->>P: verifier = random (kept on device), challenge = S256(verifier)
    P->>API: POST /v1/auth/tg-handshake {challenge, anonymous_id, utm}
    API-->>P: nonce, t.me/<bot>?start=login_<nonce>
    P->>T: open deep link (handshake saved on device)
    U->>T: Start
    T->>B: /start login_<nonce>
    B->>API: ensure user → family + invite → bind nonce → magic token
    B->>T: E1 «зарегистрировано» · E2 invite + «Поделиться» · E3 magic link
    loop every 2 s while visible (resumes after reload)
        P->>API: POST …/exchange {verifier}
        API-->>P: 202 pending … then session
    end
    API-->>P: access JWT (memory) + refresh cookie (httpOnly, rotating)
    P->>U: onboarding (C) → «В семью» → main screen (D)
```

The nonce appears in a public URL, but it is useless without the verifier. On iOS, a PWA installed to the home screen doesn't share storage with Safari. Polling works there, while a link from Telegram would open in Safari.

### 4.2 Acceptor joins by invite

```mermaid
sequenceDiagram
    actor L as Leader
    actor A as Acceptor
    participant B as Bot
    participant API
    L->>A: forwards the invite (or «Поделиться» → inline card)
    A->>B: /start inv_<token>
    B->>API: valid invite? → ensure user (source = invite, referrer = leader)<br/>→ member (adult) → active family → magic token
    B->>A: F «Ты получил приглашение…» + link
    A->>API: magic link → session → onboarding → the leader's family
```

A dead or revoked invite creates no account. The bot offers «Создать своё пространство» instead.

### 4.3 Capture: a message becomes a task or event (screens G → H)

```mermaid
sequenceDiagram
    actor U as User
    participant B as Bot
    participant C as CaptureService
    participant G as LLM gateway
    participant X as LLM proxy
    participant DB as Postgres

    U->>B: forwards «в 13:00 у дашки танцы забудь дим»
    B->>C: capture(text, source=forwarded, written_at=forward date)
    C->>G: extraction prompt (message fenced as untrusted data)
    G->>X: chat completion (JSON)
    X-->>G: items + usage + cost header
    G->>DB: llm_usage row (tokens, ₽, latency, status)
    C->>DB: draft_actions (pending, 24 h TTL)
    B->>U: card «Событие: Танцы у Даши · вт 29.09 в 13:00» [Сохранить][Изменить][Отмена]
    U->>B: Сохранить
    B->>C: confirm → PlanningService.create_event → events
    B->>U: «зафиксировал!»
    Note over U: The PWA refetches when it regains focus: the event is on screen D
```

Nothing is written before «Сохранить» (propose → confirm). If the LLM is unavailable (budget, timeout, invalid output) or finds nothing, the card offers «Сохранить как задачу» without the LLM.

Photos and image files take the same path (ADR 0005): the extraction model is a vision model, the bot downloads the image into memory (never stored), and the caption is the message text. A photo without a caption that can't be read gets a "write it as text" reply instead of a «Сохранить как задачу» card.

## 5. Data model

```mermaid
erDiagram
    USERS ||--o{ IDENTITIES : "logs in via (telegram)"
    USERS ||--o{ SESSIONS : "refresh tokens (rotating)"
    USERS ||--o{ LOGIN_HANDSHAKES : "PWA ↔ bot"
    USERS ||--o{ MAGIC_TOKENS : "single-use links"
    USERS ||--o{ MEMBERS : "is"
    FAMILIES ||--o{ MEMBERS : has
    FAMILIES ||--o{ INVITES : issues
    FAMILIES ||--o{ TASKS : owns
    FAMILIES ||--o{ EVENTS : owns
    FAMILIES ||--o{ DRAFT_ACTIONS : "proposed writes"
    USERS ||--o{ USER_ACTIVITY_DAILY : "active on (DAU)"
    USERS ||--o{ LLM_USAGE : "cost attributed to"
    FAMILIES ||--o{ LLM_USAGE : "quota per family"
    ANALYTICS_EVENTS }o--o| USERS : "user_id / anonymous_id"
```

- **Tenancy:** every family-owned row has `family_id`. Family-scoped routes (`/v1/families/{id}/…`) check membership on each request.
- **Time:** instants are stored in UTC with the family's IANA timezone; all-day events and due dates are dates.
- **Secrets at rest:** login tokens, magic links and refresh tokens are stored as SHA-256 hashes.

## 6. Analytics and metrics

```mermaid
flowchart LR
    CMD["Commands<br/>(same transaction)"] --> OB[("outbox_messages")]
    OB -- "worker, SKIP LOCKED" --> AE[("analytics_events<br/>partitioned by month")]
    FE["PWA track()<br/>batched, anonymous_id"] -- "POST /v1/analytics/events<br/>(validated against the catalog)" --> AE
    MW["Activity middleware<br/>API + bot"] --> UAD[("user_activity_daily")]
    GW["LLM gateway"] --> LU[("llm_usage<br/>₽ in micro-units")]
    AE & UAD & LU --> V["metrics_* views<br/>(no test users, no load tests,<br/>no fake LLM)"] --> GP["Grafana: product"]
    APIM["API / worker /metrics"] --> PR["Prometheus<br/>+ alert rules"] --> GT["Grafana: technical"]
```

- **Server events are transactional:** they are written through the outbox in the same transaction as the change, so "created but not counted" can't happen.
- **Client events** are validated against the event catalog; pre-login events are accepted only from an allowlist.
- **DAU** follows ADR 0003: user-initiated actions only, reporting day in Europe/Moscow, one row per user, day and platform.
- **LLM cost** comes from the ledger: one row per provider call with the proxy-reported cost. The analysis is in [`llm-cost-per-dau.md`](llm-cost-per-dau.md).
- **Dashboards:** "kainem — technical" covers request rate, 5xx share, latency, bot, LLM, outbox and analytics rejects. "kainem — product" covers DAU/WAU/MAU, platforms, new users and families, the registration and invite funnels, AI confirm rate, ₽/day, ₽/DAU, retention and activation.
- **Alerts:** 5xx above 2%, high latency, bot failures, bot down or Telegram unreachable through the proxy, LLM failures and budget exhaustion, outbox lag, analytics rejects. Spend alerts fire at 50% and 80% of the program budget.

## 7. Security

- **Auth:**
  - Telegram identity only.
  - A PKCE-style handshake and single-use hashed magic links.
  - Access JWTs live 15 minutes in memory only.
  - Refresh cookies are httpOnly, SameSite=Lax, scoped to `/api/v1/auth`, and rotate on every use. Reusing a rotated one revokes the whole login.
- **Rate limits:**
  - Per IP on login and pre-login analytics; per user on bot captures.
  - The client IP is set by the edge (Caddy → nginx) and can't be spoofed with `X-Forwarded-For`.
- **Webhook:** when used, Telegram calls are verified by the secret token header. Production long-polls instead (ADR 0004).
- **LLM:**
  - Message text is fenced as data, and prompt injection is part of the eval set.
  - Nothing is written without user confirmation.
  - There's a per-family daily ₽ quota and program budget alerts.
  - Only first names go to the model, no contact data.
- **Test-only endpoints** exist only when `ENABLE_TEST_ENDPOINTS=true` *and* `ENV` is `local` or `test`. The API refuses to start in staging or production with the development JWT secret.
- **Data residency:** the VM runs in a Russian cloud, and the LLM is Cloud.ru via the Sber500 proxy (ADR 0001).

## 8. Where things are

| | |
|---|---|
| Decisions | [`docs/adr/`](adr): 0001 LLM provider, 0002 PWA login through the bot, 0003 active user, 0004 Telegram through a VLESS proxy, 0005 photo capture through a vision model |
| Load test | [`docs/load-test.md`](load-test.md), `backend/loadtest/locustfile.py` |
| LLM cost per DAU | [`docs/llm-cost-per-dau.md`](llm-cost-per-dau.md), `python -m planner.cli cost-report` |
| Extraction quality | `backend/tests/evals/` (`pytest -m eval`) |
| Metrics definitions | `backend/migrations/versions/*_m5_metrics_views.py` |
| Dashboards and alerts | `infra/grafana/`, `infra/prometheus/` |
| Deployment | `infra/compose.prod.yml`, `infra/.env.prod.example`, README "Deploy" |
