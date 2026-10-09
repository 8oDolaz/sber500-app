# Deployment guide

How to run kainem: first locally on your computer (with your real Telegram bot), then on a server.

Everything runs in Docker. You never install Python or Node on the server.

## 1. What you need

| | Local run | Server |
|---|---|---|
| Docker with Compose v2 | yes | yes |
| A Telegram bot | yes: a **dev** bot | yes: a **separate prod** bot (see below) |
| Sber500 LLM key | optional (a fake LLM works without it) | yes |
| A Linux VM (2 vCPU, 4 GB RAM is plenty) in a Russian cloud, e.g. Timeweb Cloud | — | yes (152-FZ) |
| A domain with an A record pointing at the VM | — | yes |
| A GitHub `production` environment with the deploy secrets (section 5.4) | — | yes, for the Deploy workflow |
| A VLESS VPN subscription (Telegram is blocked in Russia, ADR 0004) | — | yes |

**Use two different bots.** Only one process can poll a bot token at a time. The server and your computer both poll (the server through a VPN proxy, ADR 0004), so with one shared token they would steal each other's updates.

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
| `TELEGRAM_PROXY` | Proxy for Bot API calls (ADR 0004) | empty (direct) | `socks5://xray:1080` |
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

## 5. Deploy to a server (Timeweb Cloud + GitHub Actions)

Deploys are done by the **Deploy** workflow (`.github/workflows/deploy.yml`). It connects to the VM
over SSH as an unprivileged `deploy` user, syncs the sources, writes `infra/.env.prod` from a GitHub
secret, and runs `infra/deploy/deploy.sh` on the server. The VM only needs Docker: no Python, Node or
git. Until the VM is configured in GitHub, the workflow skips itself on pushes to `main`.

### 5.1 Create the VM

In the Timeweb Cloud panel: **Облачные серверы → Создать**.

- OS: Ubuntu 24.04 (22.04 also works). Region: Russia (152-FZ). 2 vCPU / 4 GB RAM / 40 GB is plenty.
- Add your own SSH key to the server so you can log in as `root` for the one-time setup below.
- In the panel's firewall (if you attach one), allow inbound **22, 80, 443** only.
- Create a DNS A record `DOMAIN → <VM IP>` (Timeweb DNS or your registrar). Caddy needs it to get the
  TLS certificate; check with `dig +short <DOMAIN>`.

### 5.2 Prepare the VM (once)

Generate a key pair for GitHub Actions on your computer. The private key goes to GitHub, the public one to the VM:

```bash
ssh-keygen -t ed25519 -N "" -C kainem-deploy -f ~/.ssh/kainem_deploy
```

Run the bootstrap script as root. It installs Docker + Compose from Ubuntu's repositories, configures a
Docker Hub mirror (Docker Hub throttles Russian IPs), creates the `deploy` user with your public key,
creates `/opt/kainem`, and enables a firewall for 22/80/443:

```bash
scp infra/deploy/bootstrap.sh root@<VM_IP>:/root/
ssh root@<VM_IP> "bash /root/bootstrap.sh \"$(cat ~/.ssh/kainem_deploy.pub)\""
```

Then record the VM's host key for strict checking in the workflow:

```bash
ssh-keyscan <VM_IP>          # copy the output: it goes into DEPLOY_KNOWN_HOSTS below
```

### 5.3 Prepare `infra/.env.prod`

On your computer, not on the server:

```bash
cp infra/.env.prod.example /tmp/kainem.env.prod
```

Fill in every setting marked **required** in section 3. Check three things:
- the password in `DATABASE_URL` equals `POSTGRES_PASSWORD`;
- `PUBLIC_APP_URL` is `https://<DOMAIN>` and `DOMAIN` matches the A record;
- `BOT_TOKEN` / `BOT_USERNAME` are the **prod** bot.

The workflow writes this file to `/opt/kainem/infra/.env.prod` (mode 600) on every deploy, so the
secret in GitHub is the source of truth: to change a setting, update the secret and redeploy.

#### The Xray (VLESS) config

Telegram is blocked in Russia: the server can neither call the Bot API nor receive webhooks reliably.
The `bot` container therefore long-polls Telegram through the `xray` container, a VLESS client of your
VPN servers (ADR 0004). Only the bot's traffic goes through it.

```bash
cp infra/xray/config.example.json /tmp/kainem.xray.json
```

Keep `inbounds`, `burstObservatory` and `routing` as they are. The template has one outbound per VPN
server (`vless-1`, `vless-2`; add `vless-3`… or delete one, keeping the `vless-` prefix). Every minute
Xray checks each server by opening `https://api.telegram.org` through it, and sends the bot's traffic
through the fastest one that works (`leastPing`). If a server goes down, traffic moves to another one
within about a minute. If all checks fail, Xray falls back to `vless-1`.

Fill each outbound from one server link of your subscription,
`vless://<id>@<address>:<port>?security=…&type=…&sni=…&pbk=…&sid=…&flow=…&fp=…`:

| Link part | Config field |
|---|---|
| `<id>`, `<address>`, `<port>` | `vnext[0].users[0].id`, `vnext[0].address`, `vnext[0].port` |
| `flow` | `users[0].flow` (remove the field if the link has none) |
| `type` | `streamSettings.network` (`tcp`, `ws`, `grpc`, `xhttp`) |
| `security=reality`: `sni`, `pbk`, `sid`, `fp` | `realitySettings.serverName`, `publicKey`, `shortId`, `fingerprint` |

For `security=tls` replace `realitySettings` with `"tlsSettings": {"serverName": "<sni>"}`; for `ws`
or `grpc` add `wsSettings` / `grpcSettings` with the link's `path` / `serviceName`. Many VPN clients
(v2rayN, Hiddify, Nekoray) can also export a ready Xray JSON config for a server: keep its outbound
and rename its tag to `vless-N`; take the other sections from the template.

Check the file before using it (needs Docker):

```bash
docker run --rm -v /tmp/kainem.xray.json:/etc/xray/config.json:ro ghcr.io/xtls/xray-core:26.3.27 \
  run -test -c /etc/xray/config.json     # prints "Configuration OK."
```

The file holds your VPN credentials: it goes only into the `XRAY_CONFIG` secret, and the workflow writes it to
`/opt/kainem/infra/xray/config.json` on every deploy (gitignored).

### 5.4 Configure GitHub

**Settings → Environments → New environment → `production`.** Optionally add yourself as a required
reviewer: every deploy then waits for your approval. Then add:

| Kind | Name | Value |
|---|---|---|
| Variable | `DEPLOY_HOST` | VM IP (or hostname) |
| Variable | `DEPLOY_KNOWN_HOSTS` | the `ssh-keyscan` output from 5.2 (recommended; without it the first connection trusts the host blindly) |
| Variable | `DEPLOY_USER` | optional, default `deploy` |
| Variable | `DEPLOY_PORT` | optional, default `22` |
| Variable | `DEPLOY_PATH` | optional, default `/opt/kainem` |
| Secret | `DEPLOY_SSH_KEY` | contents of `~/.ssh/kainem_deploy` (the private key, all lines) |
| Secret | `PROD_ENV_FILE` | contents of your filled-in `.env.prod` (the whole file) |
| Secret | `XRAY_CONFIG` | contents of your filled-in Xray config (5.3) |

Delete the local copies (`/tmp/kainem.env.prod`, `/tmp/kainem.xray.json`) once the first deploy is green.

### 5.5 Deploy

- **Automatically:** every push to `main` deploys.
- **Manually:** Actions → **Deploy** → *Run workflow* → pick a branch or tag. GitHub only shows this
  button once the workflow file is on the default branch (`main`), so merge `dev` into `main` first.

What a run does, in order (`infra/deploy/deploy.sh`):

1. `pg_dump` of the database into `/opt/kainem/backups/` (last 5 kept), skipped on the first deploy.
2. `docker compose build --pull` for `api`, `worker`, `bot` and `web` with `APP_VERSION` = the git tag or short SHA.
3. `docker compose up -d --remove-orphans`: the API applies migrations on start.
4. Waits until the API container is healthy, then `bot-check` (calls the Bot API through the proxy;
   a failure is a warning, see section 6), `prices-sync --file …`, `check-models` (a missing model is a
   warning, not a failure), and creates or refreshes the `grafana_reader` role.
5. `curl https://<DOMAIN>/api/readyz` from the server, then again from GitHub. Fails if `ok` is not `true`.

A failed run leaves the previous containers running only if it failed before step 3; after that, fix
and redeploy. Logs: `ssh deploy@<VM_IP>` then `cd /opt/kainem && docker compose -f infra/compose.prod.yml --env-file infra/.env.prod logs -f api`.

### 5.6 Check

- Open `https://<DOMAIN>` on a phone: the welcome screen appears. Register through the prod bot.
- **Dashboards:** Grafana and Prometheus are not public. Use a tunnel:
  ```bash
  ssh -L 3000:127.0.0.1:3000 deploy@<VM_IP>
  ```
  Then open `http://localhost:3000` and sign in as `admin` with `GRAFANA_ADMIN_PASSWORD`. The dashboards are in the "kainem" folder.

### 5.7 Manual operation on the server

Everything the workflow does can be done by hand as the `deploy` user:

```bash
cd /opt/kainem
DC="docker compose -f infra/compose.prod.yml --env-file infra/.env.prod"
APP_VERSION=manual bash infra/deploy/deploy.sh   # the same steps as the workflow
$DC ps                                            # everything "Up" / "healthy"
$DC logs -f api
$DC exec api python -m planner.cli check-models
```

- **Back up** the database daily, e.g. from cron: `$DC exec -T postgres pg_dump -U kainem kainem | gzip > backup-$(date +%F).sql.gz`. Keep copies off the VM. The pre-deploy dumps in `backups/` are a safety net, not a backup strategy.
- **Restore:** `gunzip -c backups/<file>.sql.gz | $DC exec -T postgres psql -U kainem kainem` (stop `api` and `worker` first).
- **Never** apply `infra/compose.loadtest.yml` on a server: it turns on test endpoints and removes rate limits.
- Rotating `JWT_SECRET`: update the `PROD_ENV_FILE` secret and redeploy.
- Changing VPN servers: update the `XRAY_CONFIG` secret and redeploy. Then `$DC exec bot python -m planner.cli bot-check` should print the bot's username.

## 6. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| The bot doesn't answer (local) | `BOT_TOKEN` is empty or wrong: check `logs bot`. Or a webhook is set for this token: run `set-webhook` only for the prod bot. The local bot removes the webhook on start. |
| The bot doesn't answer (server) | The proxy is down or misconfigured: `$DC logs xray bot` and `$DC exec bot python -m planner.cli bot-check`. Check `TELEGRAM_PROXY=socks5://xray:1080` in `PROD_ENV_FILE` and the VLESS fields in `XRAY_CONFIG`. Updates are kept by Telegram for 24 h and arrive once the proxy works. |
| The bot answers only after minutes | A webhook is still set for the prod token, or the bot isn't polling through the proxy. The `bot` container deletes the webhook on start; `bot-check` shows `webhook: none (long polling)`. |
| «Зарегистрироваться» opens the wrong bot | `BOT_USERNAME` doesn't match the token's bot. |
| Links in bot messages don't open | `PUBLIC_APP_URL` doesn't match the address the app is served at (local: the `WEB_PORT` port; server: `https://<DOMAIN>`). |
| API exits with "JWT_SECRET must be set" | Set `JWT_SECRET` in `infra/.env.prod`. |
| `readyz` shows `llm_models.ok: false` | A configured model was removed from the proxy: pick one from `check-models` output. |
| Caddy can't get a certificate | DNS doesn't point at the VM yet, or ports 80/443 are closed. |
| «Поделиться» does nothing | Inline mode is off in BotFather (step 2.2). |
| Deploy workflow is "skipped" | `DEPLOY_HOST`, `DEPLOY_SSH_KEY`, `PROD_ENV_FILE` or `XRAY_CONFIG` is missing in the `production` environment (section 5.4). |
| Deploy fails at "Set up SSH" | Wrong `DEPLOY_SSH_KEY` (paste the whole private key), the public key isn't in `/home/deploy/.ssh/authorized_keys`, or `DEPLOY_KNOWN_HOSTS` is from another host. |
| Deploy fails at "Smoke test" but `$DC ps` is healthy | DNS or 80/443 (Caddy has no certificate yet). Fix and re-run the workflow. |
| `docker compose build` is slow or pulls fail on the VM | Docker Hub throttling. `bootstrap.sh` sets registry mirrors in `/etc/docker/daemon.json`; check they are still reachable. |
