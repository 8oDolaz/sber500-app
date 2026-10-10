# First contact, onboarding and guide

The placeholder welcome and help screens now use the final [welcome, 92:6999](https://www.figma.com/design/IwoVYL8aolHhH1kRNyTvLg/Untitled?node-id=92-6999) and [guide, 90:4273](https://www.figma.com/design/IwoVYL8aolHhH1kRNyTvLg/Untitled?node-id=90-4273). The existing signed-in onboarding uses the same components while retaining its installation and completion logic. The [home handoff](frontend-home.md) covers planning data, component states and branding.

## Implementation

- `frontend/packages/ui-kit/src/intro.tsx` and `intro.css`: shared brand, hero, Telegram action, tutorial examples, cards and navigation. They compose the existing `Screen`, `Button` and `InviteCard`.
- `frontend/packages/ui-kit/src/assets/intro/`: local Figma assets; `manifest.json` records their source nodes. SVG root dimensions are preserved. The decorative blue hero background is a native static export with the Figma shader baked in; no GPU or experimental shader runtime is required.
- `frontend/packages/app-core/src/screens/Welcome.tsx`: guest entry and the existing PKCE Telegram login.
- `frontend/packages/app-core/src/screens/Onboarding.tsx`: authenticated introduction, optional PWA installation and server-confirmed onboarding completion.
- `frontend/packages/app-core/src/screens/Help.tsx`: guide, bot/invitation actions, back navigation, family selection and sign-out.

The mobile layout is capped at 402px and centered on larger screens. At 402px the welcome follows the Figma proportions: 24px gutters, 84px brand icon, Inter 34/41 heading and 17/22 body, 52px primary actions, 28px white cards. Narrow screens wrap text and scale the tutorial figures proportionally. The guide has 44px back buttons at both ends. Safe areas are reserved, and the installation sheet can scroll in a short landscape viewport. Image captions remain accessible HTML/figure labels; screenshot examples do not replace interactive UI.

The grey invitation remains `#e6e3e3`. Future Alice/calendar features retain the planned wording and have no misleading active controls. The existing family selector and sign-out remain available in a collapsed “Семья и аккаунт” section below the guide; this adds a row beyond the Figma tutorial.

## Routes and state behavior

| Route / action | Behavior |
| --- | --- |
| `/welcome` | Two “Начать в Telegram” actions share a single handshake; repeated requests are blocked while starting or waiting. |
| Login starting | Both actions show “Открываем Telegram…” and are disabled. |
| Login waiting | Header shows busy “Ждём подтверждения…”; reopen and cancel are available. The footer reopens the same link. |
| Login reload / return | The persisted handshake resumes polling. A late exchange after cancellation cannot sign the user in. |
| Login expired / failed | An adjacent alert explains the error, clears the pending handshake and permits a fresh attempt. An adapter exception during handoff is handled as failure. |
| Login offline | Both start actions are disabled; reconnect enables them. A pending handshake is retained while polling retries. |
| `/onboarding` | The existing session gate sends authenticated users here until onboarding is complete. |
| “В семью” / “Перейти к делам” | `PATCH /v1/me` with `{onboarding_completed:true}`. Both actions become busy during saving; failure stays on the page and permits retry. Offline saving is disabled. Only a successful response opens home. |
| Install offered | Native Chromium prompt, iOS Safari instructions, or Android manual instructions, according to the existing platform adapter. |
| Install hidden | Already installed, or a desktop without a native install offer. Installation is optional; opening the instructions is not treated as successful installation. |
| Install pending / failed | Busy action prevents duplicate invocation; failure offers another attempt. Instructions trap focus, support Escape and restore focus to their trigger. |
| `/home` → `/help` → back | The fixed home button opens the guide at its top; its back buttons restore the prior home scroll position. A direct guide visit falls back to `/home`. |
| Guide bot / invitation | Both actions use the configured, validated `me.bot_link`; opening blocks duplicate handoff across actions. Missing links disable them with an explanation. Actual adapter errors show a retry; opening Telegram never claims an invitation was sent. |
| Family selector | Shown for multiple families; active family is marked. `PUT /v1/me/active-family` saves the choice; pending/offline states disable switches, failure permits retry. |
| Sign-out | Uses the existing logout/session cleanup, including clearing family query data. |

The login protocol, API schema, authentication cookies and magic-link flow are retained. No production bot username is hardcoded into the UI. Physical-device Telegram handoff and native installation still depend on the browser/OS; the app cannot detect whether the external Telegram application opened successfully.

## PWA and validation

The existing standalone manifest, branded icons and service worker also serve these screens. Fonts and tutorial/brand images are local and included in the production precache. API responses are never precached. As documented for home, a cold offline launch shows the session connection/retry screen rather than persisting private family data.

Run from `frontend`:

```bash
pnpm install --frozen-lockfile
pnpm typecheck
pnpm test
pnpm build
pnpm exec playwright install chromium webkit
pnpm test:ui
pnpm test:pwa
# With Postgres/Redis available via `make infra-up`:
pnpm e2e
```

Unit checks cover login, reload/resume, expiration, handoff failure, cancellation of a late response, installation, onboarding completion, family switching and sign-out. Browser checks cover 320/402/768/1440px in Chromium and WebKit, local image decoding and SVG dimensions, both login actions, offline/retry/cancel, guide return navigation and keyboard operation of installation instructions. PWA checks use the production build and real service worker, verify the tutorial image precache and check that API data is excluded. The existing real-backend e2e login → Telegram → onboarding → home → guide → sign-out scenario uses the final UI labels.
