# ADR 0004 — Telegram through a VLESS proxy, bot in long-polling mode

- Status: accepted · 2026-10-09

## Context
Telegram is blocked in Russia, and the production VM is in a Russian cloud (152-FZ, ADR 0001). On the
first deploy both directions failed:

- outbound: Bot API calls from the API container (`sendMessage`, `setWebhook`) timed out;
- inbound: Telegram could not deliver webhook updates to the VM (`getWebhookInfo` reported
  `last_error_message: Connection timed out`), so it kept retrying with growing delays and `/start`
  took minutes to answer. Without `/start` nobody can sign in to the PWA (ADR 0002).

A proxy fixes outbound traffic only. Inbound webhook delivery to a Russian IP stays unreliable.

## Decision
- The bot runs in **long-polling mode in production**, as its own `bot` container
  (`python -m planner.entrypoints.bot`, the same entrypoint as `make bot`). On start it deletes the
  webhook. Nothing has to reach the VM from Telegram.
- All Bot API traffic goes through **`TELEGRAM_PROXY`** (`socks5://xray:1080`): an `xray` container
  (Xray-core) that is a VLESS client of an external VPN server. The SOCKS port is only reachable inside
  the compose network. Only the bot's traffic uses it: the LLM proxy, Let's Encrypt and users' requests
  go out directly.
- The Xray config holds the VPN credentials. It is not committed: the `XRAY_CONFIG` secret of the
  GitHub `production` environment is written to `infra/xray/config.json` on every deploy (template:
  `infra/xray/config.example.json`).
- The webhook route (`/api/webhooks/telegram`) and `cli set-webhook` stay, for an environment where
  Telegram can reach the server. Only one mode per token can be active.

## Consequences
- Users notice no difference: long polling returns as soon as an update arrives. Telegram keeps
  undelivered updates for 24 hours, so a bot restart or a short VPN outage delays replies but loses none.
- Only one bot process may poll a token. The bot is not scaled horizontally, which is far beyond MVP needs.
- The VPN is now a dependency of sign-in, invites and capture. The PWA and the API keep working
  without it. `telegram_api_requests_total{status}` counts Bot API calls; the `TelegramUnreachable`
  alert fires when the polling bot has had no successful call for 5 minutes, and `BotDown` when its
  container is gone.
- The Xray config lists every server of the VPN subscription. It health-checks each one every minute
  (`burstObservatory`, probing `api.telegram.org`) and routes through the fastest working one
  (`leastPing` balancer), so one VPN server going down costs about a minute, not an outage.
- Data residency: the VPN provider sees only TLS traffic to `api.telegram.org`, which already leaves
  Russia by nature. No user data goes anywhere it did not go before.
