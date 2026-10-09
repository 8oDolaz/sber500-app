# Load test

Acceptance criterion: load testing up to **10 RPS**. Result: **passed with 0 errors**. The same stack also held **~52 RPS** with 0 errors.

## Setup

| | |
|---|---|
| Date | 2026-09-30 |
| Tool | Locust 2.46 (`backend/loadtest/locustfile.py`) |
| Target | The full Docker stack from `infra/compose.yml` (`--profile full`) plus `infra/compose.loadtest.yml`. Requests go through nginx (`:8088`) → API (one uvicorn process) → Postgres 17 + Redis 7; a worker drains the outbox. |
| Machine | One developer laptop running both the stack and Locust. Staging numbers will differ; rerun there when it exists. |
| LLM | Fake provider: every forwarded message becomes one task. No budget is spent. |

### Traffic mix

Each simulated user behaves like a person, not like a single endpoint hammered in a loop.

**Family members** (80% of users, signed in; each performs about 0.18 actions per second):

| Weight | Action | Requests |
|---|---|---|
| 6 | Open the main screen | `/v1/me` + tasks + events |
| 2 | Forward a message to the bot, then «Сохранить» | Extraction → draft → task |
| 2 | Send a client analytics batch | 1 |
| 1 | Tick a task | Read tasks, then PATCH |
| 1 | Refresh the session | Rotates the refresh cookie |

**Guests** (20% of users, not signed in; one action every 8–12 s): open the PWA shell → pre-login analytics → start a Telegram login → one poll, which answers 202 "pending".

Each simulated user first registers through the bot, signs in with the magic link and completes onboarding. Those setup requests are included in the totals.

### Keeping production data clean

- Every account is `is_test` and every analytics batch is tagged `app_version=loadtest`. The dashboard views exclude both, so a load test never shows up in DAU or ₽/DAU.
- All traffic comes from one IP, so the override raises the per-IP login and analytics limits and turns the test-only endpoints on.
- **Never apply `compose.loadtest.yml` to a real environment.**

## Results

| Run | Duration | Users | Requests | Throughput | Failures | p50 | p95 | p99 | Max |
|---|---|---|---|---|---|---|---|---|---|
| **Target** | 5 min | 25 | 3 051 | **10.2 RPS** | **0** | 27 ms | 75 ms | 150 ms | 212 ms |
| Stress (5×) | 2 min | 125 | 6 196 | 51.7 RPS | 0 | 94 ms | 320 ms | 480 ms | 1.2 s |

**Server side** (Prometheus and Postgres, after both runs):
- 0 responses with status 5xx out of 9 737.
- Outbox lag stayed at 0 s; all 3 763 outbox messages were delivered.
- 565 LLM calls, all successful, all through the fake provider.

**Container CPU and memory** (averaged over `docker stats` samples):

| Container | CPU at 10 RPS | CPU at 52 RPS | Memory |
|---|---|---|---|
| api (1 uvicorn process) | ~7% of a core | ~62% of a core | ~225 MiB |
| postgres | ~6% | ~29% | ~105 MiB |
| worker | ~1% | ~4% | ~92 MiB |
| redis | ~2% | ~3% | ~15 MiB |
| nginx (web) | ~0% | ~3% | ~15 MiB |

### Reading the results

- The 10 RPS target uses about a tenth of one core on the API. The single API process is the first bottleneck: it reached about 62% of a core at 52 RPS.
- If more headroom is needed, add uvicorn workers (`--workers N`) or more API containers. The API is stateless (sessions live in Postgres, rate limits in Redis), so both are straightforward.
- The slowest endpoint under stress is «forwarded message» (p99 1.1 s at 52 RPS): it runs extraction plus several writes. With a real LLM, the provider's own latency (typically 1–5 s) will dominate this step. The user waits for the draft card either way; nothing else waits on it.
- Everything else stays under 0.5 s at p99, even at 5× the target.

## How to run

```bash
# Stack with the load-test override (test endpoints on, per-IP limits raised, fake LLM)
WEB_PORT=8088 docker compose -f infra/compose.yml -f infra/compose.loadtest.yml --profile full up -d --build

cd backend
# ~10 RPS for 5 minutes, with CSV and HTML reports
MEMBER_ACTIONS_PER_SEC=0.18 uv run --group loadtest locust -f loadtest/locustfile.py --headless \
  --host http://localhost:8088 -u 25 -r 5 -t 5m --csv lt-10rps --html lt-10rps.html

# Stress: 125 users (~50 RPS) for 2 minutes
MEMBER_ACTIONS_PER_SEC=0.18 uv run --group loadtest locust -f loadtest/locustfile.py --headless \
  --host http://localhost:8088 -u 125 -r 10 -t 2m --csv lt-50rps
```

While a run is going, watch the "kainem — technical" dashboard in Grafana (<http://localhost:3000>): request rate, 5xx share, latency percentiles and outbox lag.

To drive a real LLM, set `LLM_PROVIDER=openai_compatible` with a key and keep the rate low: each «forwarded message» is one paid call.
