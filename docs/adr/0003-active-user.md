# ADR 0003 — Definition of an active user and reporting day

- Status: accepted · 2026-09-29 (ARCHITECTURE §9.4, §14 decision #9)

## Decision
A user is **active on day D** if they performed at least one *user-initiated* action on D:

| Surface | Counts | Does not count |
|---|---|---|
| PWA / Mini App | any authenticated API request with status < 500 | `/v1/analytics/events`, `/v1/auth/refresh`, `/healthz`, `/readyz`, `/metrics` |
| Telegram bot | messages, commands, callback button presses | `my_chat_member`, `chosen_inline_result`, deliveries to the user |

Passive things never count: receiving a notification, background sync, digests.

- **Reporting day** is computed in `REPORTING_TZ` (default `Europe/Moscow`); timestamps are stored in UTC.
- **Platform** comes from the `X-Client-Platform` header (validated enum: `pwa`, `telegram_mini_app`)
  or is `telegram_bot` for bot updates.
- Storage: `user_activity_daily (user_id, activity_date, platform)`, one row per user/day/platform,
  deduped with Redis `SET NX` and `ON CONFLICT DO NOTHING`.
- Test accounts (`users.is_test`, introduced in M1) are excluded in every dashboard view.

This definition must not change silently: any change is a new ADR and a dashboard annotation.
