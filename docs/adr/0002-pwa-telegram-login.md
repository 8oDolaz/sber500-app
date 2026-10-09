# ADR 0002 — PWA login through the Telegram bot

- Status: accepted · 2026-09-29
- Context: SPEC flow 1–3 ("Регистрация пройдет в телеграмме"), ARCHITECTURE §5.1

## Context
Registration happens in the Telegram bot, but screens A–D live in a standalone PWA. On iOS a PWA
added to the home screen has **its own storage, separate from Safari**. Links opened from Telegram
land in Safari or the in-app browser, never in the installed app. A link-only login would therefore
never reach the installed PWA, and screen C asks users to install it.

## Decision
Two ways to sign in, both issued by the bot:

1. **Handshake with polling** (works everywhere, including the installed PWA):
   - The PWA creates `verifier` (random, kept on the device) and sends
     `POST /v1/auth/tg-handshake {challenge = base64url(sha256(verifier)), anonymous_id, utm}`.
   - The response is `{nonce, deep_link: t.me/<bot>?start=login_<nonce>}`; the PWA opens the link.
   - The user presses Start. The bot creates the user, their family space and invite, then binds the nonce.
   - The PWA polls `POST /v1/auth/tg-handshake/{nonce}/exchange {verifier}` (202 until bound) and
     gets a session exactly once. The nonce travels through a public URL, so it is useless without the verifier.
   - The pending handshake is persisted on the device, so polling resumes after a reload
     (the browser may navigate to t.me when the Telegram app isn't installed).
2. **Magic link** in the bot message ("Вот пространство семьи — <link>"): `/auth/tg?token=…`,
   single use, 10-minute TTL, stored hashed. When it fails, the page offers the handshake.

**Sessions:**
- The access JWT (15 min) is kept in memory only.
- The refresh token is an httpOnly, SameSite=Lax cookie scoped to `/api/v1/auth`. It lasts 30 days and rotates on every use.
- Reusing a rotated refresh token revokes the whole login chain (theft detection).

**Analytics:**
- `anonymous_id` from the handshake flows into `user_signed_up` and `login_handshake_completed`, joining the pre-login funnel to the account.
- UTM tags carry over the same way.

## Consequences
- No passwords or OTP providers. Telegram is the only identity for now; the `identities` table leaves room for more.
- The PWA needs a secure context (https or localhost) for WebCrypto (PKCE).
- Test-only `POST /v1/test/tg-handshake/{nonce}/bind` simulates the bot in e2e tests. It is enabled only
  with `ENABLE_TEST_ENDPOINTS=true` in `local`/`test` environments, and users created through it are flagged `is_test`.
