# Deployment guide

How to run kainem: first locally on your computer (with your real Telegram bot), then on a server.

Everything runs in Docker. You never install Python or Node on the server.

## 1. What you need

| | Local run | Server |
|---|---|---|
| Docker with Compose v2 | yes | yes |
| A Telegram bot | yes: a **dev** bot | yes: a **separate prod** bot (see below) |
| Sber500 LLM key | optional (a fake LLM works without it) | yes |
| A Linux VM (2 vCPU, 4 GB RAM is plenty) in a Russian cloud | — | yes (152-FZ) |
| A domain with an A record pointing at the VM | — | yes |

**Use two different bots.** A bot token works either in polling mode (local) or with a webhook (server), not both at once. Setting a webhook stops local polling, and polling fails while a webhook is set.

## 2. Create the Telegram bot (once per bot)

In [@BotFather](https://t.me/BotFather):

1. `/newbot` → pick a name and a username ending in `bot`. Save the **token** and the **username** (without `@`).
2. `/setinline` → choose the bot → enter the placeholder text `пригласить в семью`. This powers the «Поделиться» button on invite messages.
3. `/setinlinefeedback` → choose the bot → `Enabled`. This lets kainem count shared invites.
4. `/setcommands` → choose the bot → send:
   ```
   start - Начать
   invite - Ссылка-приглашение в семью
   ```

## 3. Files you create

None of these files are committed: they are gitignored because they hold secrets. Templates are in the repo.

| File | Created from | Used by |
|---|---|---|
| `backend/.env` | `backend/.env.example` | Local run: all backend containers (API, worker, bot) |
| `infra/.env` | — (two lines, see 4.1) | Local run: compose variables (the web port) |
| `infra/.env.prod` | `infra/.env.prod.example` | Server: every container |

### Credentials and settings

| Setting | Where to get it | Local (`backend/.env`) | Server (`infra/.env.prod`) |
|---|---|---|---|
| `BOT_TOKEN` | BotFather, step 2.1 | dev bot token | prod bot token |
| `BOT_USERNAME` | BotFather, without `@` | dev bot username | prod bot username |
| `BOT_WEBHOOK_SECRET` | Any random string: `python3 -c "import secrets;print(secrets.token_urlsafe(32))"` | any value | **required**, random |
| `PUBLIC_APP_URL` | Where the app is opened in a browser | `http://localhost:<WEB_PORT>` | `https://<DOMAIN>` |
| `JWT_SECRET` | Random: `python3 -c "import secrets;print(secrets.token_urlsafe(48))"` | can stay empty (dev default) | **required**: the API refuses to start without it |
| `LLM_PROVIDER` | — | `fake` (free) or `openai_compatible` | `openai_compatible` |
| `LLM_API_KEY` | Sber500 organizers (`accelerator-…` key) | only with `openai_compatible` | **required** |
| `LLM_MODEL_EXTRACTION` | A model from `GET /v1/models` on the proxy | `deepseek-v4.1-flash` | same, or the eval winner |
| `LLM_PROGRAM_BUDGET_RUB` | Your program budget | `50000` | `75000` (total) |
| `POSTGRES_PASSWORD` | Random | — (dev uses `kainem`) | **required** |
| `DATABASE_URL` | Built from the password | `postgresql+asyncpg://kainem:kainem@localhost:5432/kainem` | `postgresql+asyncpg://kainem:<POSTGRES_PASSWORD>@postgres:5432/kainem` |
| `DOMAIN` | Your domain | — | e.g. `kainem.example.ru` |
| `GRAFANA_ADMIN_PASSWORD` | Random | — (dev: `admin`) | **required** |
| `GRAFANA_PG_PASSWORD` | Random (read-only DB role, step 5.4) | — | **required** |
| `SENTRY_DSN` | sentry.io project, optional | empty | optional |

Never paste tokens or keys into chats or commits. They only belong in these files.

## 4. Run locally

### 4.1 Configure

```bash
cp backend/.env.example backend/.env        # skip if you already have one
```

Edit `backend/.env`:

```ini
BOT_TOKEN=<dev bot token>
BOT_USERNAME=<dev bot username>
PUBLIC_APP_URL=http://localhost:8088
LLM_PROVIDER=fake          # or openai_compatible + LLM_API_KEY
```

Create `infra/.env`. It sets the port the app is served on; pick any free port and use the same one in `PUBLIC_APP_URL`:

```ini
WEB_PORT=8088
```

### 4.2 Start

```bash
docker compose -f infra/compose.yml --profile full up -d --build
```

This starts:
- `postgres` and `redis`;
- `api`, which also applies database migrations on start;
- `worker`;
- `bot`, in long-polling mode, so no public URL is needed;
- `web`: the app at `http://localhost:8088`;
- `prometheus` (`http://localhost:9090`) and `grafana` (`http://localhost:3000`, login `admin` / `admin`).

### 4.3 Check

```bash
docker compose -f infra/compose.yml --profile full ps          # all services "Up"
curl http://localhost:8088/api/readyz                          # "ok": true
docker compose -f infra/compose.yml --profile full logs -f bot # "Run polling for bot @<username>"
```

Then try the whole flow:
1. Open `http://localhost:8088` and press «Зарегистрироваться». Telegram opens the bot; press **Start**.
2. The bot answers «Пространство семьи зарегистрировано!», and the browser tab signs in by itself.
3. Forward any message to the bot, press «Сохранить», go back to the tab: the item is on the main screen.

**Local limitation:** the bot's links point to `http://localhost:8088`, so they only open on the same computer. To test on a phone, deploy to a server (section 5).

### 4.4 Stop, update, reset

```bash
docker compose -f infra/compose.yml --profile full down            # stop (data is kept)
docker compose -f infra/compose.yml --profile full up -d --build   # after pulling new code
docker compose -f infra/compose.yml --profile full down -v         # stop and DELETE all local data
```

## 5. Deploy to a server

### 5.1 Prepare the VM

1. Install Docker Engine with the Compose plugin.
2. Open inbound ports **22, 80, 443** only.
3. Create a DNS A record `DOMAIN → <VM IP>`. Wait until `dig +short <DOMAIN>` returns the IP: Caddy needs it to get the TLS certificate.
4. Get the code onto the server:
   ```bash
   git clone <repo> kainem && cd kainem && git checkout <branch or tag>
   ```

### 5.2 Configure

```bash
cp infra/.env.prod.example infra/.env.prod
chmod 600 infra/.env.prod
```

Fill in every setting marked **required** in section 3. Check two things:
- the password in `DATABASE_URL` equals `POSTGRES_PASSWORD`;
- `PUBLIC_APP_URL` is `https://<DOMAIN>`.

### 5.3 Start

```bash
docker compose -f infra/compose.prod.yml --env-file infra/.env.prod up -d --build
```

This starts `caddy` (public, gets the TLS certificate), `web`, `api` (2 workers, migrates on start), `worker`, `postgres`, `redis`, `prometheus` and `grafana`. On the server there is no `bot` container: the bot runs inside the API through a webhook.

### 5.4 One-time setup after the first start

Define a shortcut first:

```bash
DC="docker compose -f infra/compose.prod.yml --env-file infra/.env.prod"
```

1. **Point Telegram at the server.** This registers `https://<DOMAIN>/api/webhooks/telegram` with the webhook secret:
   ```bash
   $DC exec api python -m planner.cli set-webhook
   ```
2. **Check the LLM models exist on the proxy.** This prints the available models and fails if a configured one is missing:
   ```bash
   $DC exec api python -m planner.cli check-models
   ```
   To see a real answer, cost included, run `$DC exec api python -m planner.cli llm-ping "Привет"`. If the proxy times out during the TLS handshake, check for a VPN in TUN mode: route `shared1.multitool.works` directly.
3. **Load LLM prices.** They are the fallback when the proxy doesn't report a cost:
   ```bash
   $DC exec api python -m planner.cli prices-sync --file prices/cloudru-2026-09-30.yaml
   ```
4. **Create the read-only database role for Grafana.** The password must equal `GRAFANA_PG_PASSWORD`:
   ```bash
   $DC exec -T postgres psql -U kainem -d kainem -v password='<GRAFANA_PG_PASSWORD>' < infra/postgres/grafana-reader.sql
   $DC restart grafana
   ```

### 5.5 Check

```bash
$DC ps                                   # everything "Up" / "healthy"
curl https://<DOMAIN>/api/readyz         # "ok": true, llm_models.ok: true
```

- Open `https://<DOMAIN>` on a phone: the welcome screen appears. Register through the prod bot.
- **Dashboards:** Grafana and Prometheus are not public. Use a tunnel:
  ```bash
  ssh -L 3000:127.0.0.1:3000 <user>@<VM>
  ```
  Then open `http://localhost:3000` and sign in as `admin` with `GRAFANA_ADMIN_PASSWORD`. The dashboards are in the "kainem" folder.

### 5.6 Update and back up

```bash
git pull && $DC up -d --build            # new version; migrations run automatically on API start
```

- **Back up** the database daily, e.g. from cron: `$DC exec -T postgres pg_dump -U kainem kainem | gzip > backup-$(date +%F).sql.gz`. Keep copies off the VM.
- **Never** apply `infra/compose.loadtest.yml` on a server: it turns on test endpoints and removes rate limits.

## 6. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| The bot doesn't answer (local) | `BOT_TOKEN` is empty or wrong: check `logs bot`. Or a webhook is set for this token: run `set-webhook` only for the prod bot. The local bot removes the webhook on start. |
| The bot doesn't answer (server) | Check that `set-webhook` ran with `PUBLIC_APP_URL=https://<DOMAIN>`, and that `BOT_WEBHOOK_SECRET` hasn't changed since (re-run `set-webhook` after changing it). |
| «Зарегистрироваться» opens the wrong bot | `BOT_USERNAME` doesn't match the token's bot. |
| Links in bot messages don't open | `PUBLIC_APP_URL` doesn't match the address the app is served at (local: the `WEB_PORT` port; server: `https://<DOMAIN>`). |
| API exits with "JWT_SECRET must be set" | Set `JWT_SECRET` in `infra/.env.prod`. |
| `readyz` shows `llm_models.ok: false` | A configured model was removed from the proxy: pick one from `check-models` output. |
| Caddy can't get a certificate | DNS doesn't point at the VM yet, or ports 80/443 are closed. |
| «Поделиться» does nothing | Inline mode is off in BotFather (step 2.2). |
