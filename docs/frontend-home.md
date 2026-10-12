# Home screen and PWA handoff

The home wireframe has been replaced with the audited [Figma home, 9:421](https://www.figma.com/design/IwoVYL8aolHhH1kRNyTvLg/Untitled?node-id=9-421) and its component/state library. The final first-contact screen, signed-in onboarding and guide are documented in [frontend-intro.md](frontend-intro.md).

## Components and layout

- `frontend/packages/ui-kit/src/home.tsx`: header, actions, planning cards, checkbox/task/event rows, today's summary, invitation.
- `frontend/packages/ui-kit/src/home.css`: scoped home tokens, interaction states and responsive rules. It composes the existing `Button` and `Screen`.
- `frontend/packages/ui-kit/src/assets/home/`: downloaded SVGs with their original root dimensions; `manifest.json` records the source and dimensions. No expiring Figma URLs are used by the application.
- `frontend/packages/app-core/src/screens/Home.tsx`: real API queries, actions and state selection.
- `frontend/packages/app-core/src/data/format.ts`: date/time presentation, missing values, overdue status and family timezone.
- `frontend/packages/app-core/src/useHomeRuntime.ts`: online status, clock/return handling and Telegram handoff state.

At 402px the layout follows the 370px Figma cards: 16px page gutters, 28px card corners, 20px padding and gaps. Typography is Inter: title 34/41, card heading 20/24, body 17/22, metadata 13/18. Checkbox hit areas and actions are at least 44px high; the visible checkbox circle is 24px.

Below 361px the large title becomes 28/35 and card padding becomes 16px. Metadata wraps in icon/text groups; long titles wrap. At 768px, tasks/events become two columns; the summary and invitation span both. The page is capped at 1040px. These wider layouts adapt the mobile design without changing its content hierarchy.

Per the requested behavior, [the help button, 54:2854](https://www.figma.com/design/IwoVYL8aolHhH1kRNyTvLg/Untitled?node-id=54-2854) floats above all home cards: centered, 200 × 44px, 50px above the bottom safe area. The document reserves 118px plus the safe area so the last invitation action can be scrolled fully above it. It navigates to `/help`.

## State contracts

| Component | State | Trigger/behavior |
| --- | --- | --- |
| Tasks / events | Content | Successful response with records |
| Tasks / events | Empty | Successful response with no records; no fake rows |
| Tasks / events | Loading | First request without data; skeletons, one loading announcement per section |
| Tasks / events | Refreshing | Keep existing records while refetching |
| Tasks / events | Error | First load failed; section retry |
| Tasks / events | Stale | Refresh failed; keep last response and offer retry |
| Tasks / events | Offline | Keep in-memory records; task writes and retry disabled |
| Tasks / events | OfflineEmpty | No network and no response yet; not an empty-list success |
| Tasks | AllDone | The server confirmed completions and the authoritative open list is empty during this visit |
| Task row | Open / Overdue | Available action; overdue derives from the deadline, never color alone |
| Task row | Saving | One pending PATCH per task; not checked until confirmed |
| Task row | Completed | Blue check and “Выполнено”; remove from open list after 650ms and refetch |
| Task row | Error | Keep original task and show a retry on the same checkbox |
| Task row | Disabled | No offline write queue; no request is sent |
| Today | Tasks / Events / Mixed | Include only known unfinished tasks/events on the current family day |
| Today | Loading | Supported for a known summary whose row details are not yet loaded |
| Today | Refreshing / Stale / Offline | Retain known rows; previous-day rows are filtered out when the clock advances |
| Invitation / bot action | Default / Hover / Pressed / Focus | Native button interactions, visible keyboard focus |
| Invitation / bot action | Opening | Busy, repeat activation blocked across both CTAs |
| Invitation / bot action | Error | Only an actual adapter exception; retry available |
| Invitation / bot action | Disabled | Missing/invalid Telegram link; invitation explains unavailable configuration |
| Help | Default / Hover / Pressed / Focus | Local navigation; no server saving/success state is needed |

The initial home does not invent a Today card before any today records are known. Existing rows use Refreshing rather than replacing known data with skeletons. The development catalogue also exposes the reusable Today Loading variant.

The invitation background stays `#e6e3e3` in every state. No black background or progress-count strip remains. A missing active family shows an explanation and the existing bot entry point instead of endless loading skeletons.

## API and date semantics

The existing generated OpenAPI client and endpoints are unchanged:

| Endpoint | Use |
| --- | --- |
| `GET /v1/me` | Active family and configured `bot_link` |
| `GET /v1/families/{family_id}/tasks` | Open tasks |
| `PATCH /v1/families/{family_id}/tasks/{task_id}` with `{done:true}` | Confirm completion |
| `GET /v1/families/{family_id}/events` | Upcoming events (backend default: 7 days) and family timezone |

Queries are scoped by family, consume cancellation signals, refetch on mount/return to the foreground and recover on reconnect. Signing out clears the query cache; a late task response cannot restore it after the screen unmounts. A cancelled or failed completion is never displayed as confirmed.

- Date-only values remain calendar dates; they are not converted through the browser timezone.
- Aware timestamps are converted to the family's timezone, including midnight and daylight-saving changes.
- Before the events endpoint supplies the timezone, task instants use explicitly labelled UTC and absolute dates. They are not placed in Today using a guessed family day.
- Tasks without a date or time show “Без срока”. The reusable TimeOnly variant shows “Без даты” plus the known time. Missing people are hidden.
- Today events hide the visible date and show start time once in the left badge. The date remains available to assistive technology. Today without a known time shows a clock and “Без времени”.
- Other date-only events omit the time. An unknown date shows “Без даты”; no time is manufactured as `00:00`.
- “Весь день” is shown only for the explicit API `all_day:true` flag. It is not inferred from a missing time.

**Current API boundary:** there is no independent time-only field. `due_at`/`starts_at` contain a date and time together, and event creation requires a start date or instant. TimeOnly and undated-event variants are implemented and previewable in the UI kit, but persisting those combinations requires a separate backend/domain contract change. The frontend does not manufacture a date to simulate them.

Both Telegram CTAs use the configured `me.bot_link`, with an HTTPS Telegram host check. The header opens that link unchanged; “Пригласить через бота” sets `start=share_invite` (on home and in the guide). The bot handles `/start share_invite` like `/invite`: it sends the active family's current invitation with sharing instructions and a “Поделиться” button. This intent neither logs the user in nor joins or creates a family. A revoked invitation is replaced with a valid one. Telegram may show a Start confirmation before delivering the command.

Opening the bot does not mean an invitation was sent. The browser cannot confirm that the native Telegram app opened; the busy state is released on return or after 1.5 seconds without claiming success. Invitation creation/sending remains in the bot. After first registration, the bot sends a separate invitation message without a private login token. Every bot message with a space/login link also includes the family invitation after a blank line, including repeat login, an expired handshake, joining a family and already being a member.

## PWA and branding

[Icon source: Figma 71:5960](https://www.figma.com/design/IwoVYL8aolHhH1kRNyTvLg/Untitled?node-id=71-5960). The website favicon, iOS touch icon and standard/maskable PWA icons use this artwork. Source assets and an optional regeneration script are in [`frontend/branding`](../frontend/branding/README.md); generated files are committed, so production builds need no image tools.

The existing Vite PWA shell includes a standalone manifest, stable app ID, service worker, app icons and installation support. Landscape is allowed for responsive tablet/desktop use. Production needs HTTPS, as in the existing Caddy deployment. iOS installation instructions and Android's install prompt remain in the existing onboarding.

The service worker precaches the shell, fonts and branding assets, never `/api` responses. Home records are kept in the current session's query cache, not a persistent offline database. A cold offline launch can open the shell and show the existing session connection/retry screen; it cannot restore an authenticated profile from a failed refresh request. This avoids persisting another family's private data on a shared device.

## Review and validation

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm typecheck
pnpm test
pnpm build
pnpm exec playwright install chromium webkit
pnpm test:ui
pnpm test:pwa  # uses the production build and actual service worker

# Real FastAPI/Postgres/Redis scenarios (separate from controlled UI replies):
# Start Docker and run `make infra-up` from the repository root first.
pnpm e2e
```

`pnpm dev` → `/_kit` shows the development-only state catalogue, including date/time/person combinations, section states, checkbox states and invitation states. It is excluded from production routing. `/home` always uses real API data.

Browser checks cover 320/402/768/1440px in Chromium and WebKit, loaded SVG geometry, fixed help positioning, the reachable final CTA, loading/empty/error/stale/offline/retry/completion flows and the optional metadata catalogue. Production checks validate the manifest/icons and service-worker offline shell. CI runs these plus the existing real-backend e2e suite. Native Telegram handoff and installation on physical iOS/Android devices are not automated by these browser tests.
