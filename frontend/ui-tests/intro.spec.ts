import { expect, test, type Page } from "@playwright/test";

type Reply = { status?: number; body?: unknown };
type Options = { guest?: boolean; onboarded?: boolean; handshake?: () => Reply | Promise<Reply>; save?: () => Reply | Promise<Reply> };
async function mockApi(page: Page, options: Options = {}) {
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    let reply: Reply;
    if (path.endsWith("/auth/refresh")) reply = options.guest ? { status: 401 } : { body: { access_token: "intro-test", token_type: "bearer", expires_in: 900, user_id: "u1" } };
    else if (path.endsWith("/me") && route.request().method() === "PATCH") reply = options.save ? await options.save() : { status: 500 };
    else if (path.endsWith("/me")) reply = { body: profile(options.onboarded ?? true) };
    else if (path.endsWith("/tg-handshake")) reply = options.handshake ? await options.handshake() : { status: 500 };
    else if (path.endsWith("/exchange")) reply = { status: 202, body: { status: "pending" } };
    else if (path.endsWith("/tasks")) reply = { body: [] };
    else if (path.endsWith("/events")) reply = { body: { timezone: "Europe/Moscow", events: [] } };
    else reply = { status: 204 };
    await route.fulfill({ status: reply.status ?? 200, contentType: "application/json", body: reply.status === 204 ? undefined : JSON.stringify(reply.body ?? {}) });
  });
}
function profile(onboarded: boolean) {
  return { user: { id: "u1", first_name: "Мама" }, onboarding_completed: onboarded, active_family_id: "f1", families: [{ id: "f1", name: "Наша семья", role: "owner" }], bot_link: "https://t.me/kainem_bot" };
}

for (const width of [320, 402, 768, 1440]) {
  for (const screen of ["welcome", "help"] as const) {
    test(`${screen} fits ${width}px and loads the local Figma illustrations`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 874 });
      await mockApi(page, { guest: screen === "welcome" });
      await page.goto(`/${screen}`);
      await expect(page.locator(".kn-screen--intro")).toBeVisible();
      await page.evaluate(async () => {
        await document.fonts.ready;
        await Promise.all(Array.from(document.images).map(async image => { image.loading = "eager"; await image.decode(); }));
      });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      const main = await page.locator("main").boundingBox();
      expect(main?.width).toBe(Math.min(width, 402));
      const broken = await page.locator("img").evaluateAll(images => images.filter(image => !(image as HTMLImageElement).naturalWidth).map(image => (image as HTMLImageElement).src));
      expect(broken).toEqual([]);
      // Figma SVGs keep their root dimensions; rotation is applied to the arrow, not scaling.
      const svgSizes = await page.locator('img[src$=".svg"]').evaluateAll(async images => Promise.all(images.map(async node => {
        const image = node as HTMLImageElement;
        const svg = new DOMParser().parseFromString(await (await fetch(image.src)).text(), "image/svg+xml").documentElement;
        const style = getComputedStyle(image);
        return Math.abs(parseFloat(style.width) - Number(svg.getAttribute("width"))) < .1 && Math.abs(parseFloat(style.height) - Number(svg.getAttribute("height"))) < .1;
      })));
      expect(svgSizes.every(Boolean)).toBe(true);
      const actions = page.locator(".kn-intro-action");
      for (const action of await actions.all()) expect((await action.boundingBox())!.height).toBeGreaterThanOrEqual(52);
      await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
      await expect(page.locator("footer button")).toBeInViewport();
      if (width === 320 || width === 402) {
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({ path: `test-results/${testInfo.project.name}-${screen}-${width}.png`, fullPage: true });
      }
    });
  }
}

test("welcome shares busy state, permits retry and cancels a pending login", async ({ page, context }) => {
  let release: ((reply: Reply) => void) | undefined;
  let calls = 0;
  await page.addInitScript(() => { window.open = () => null; });
  await mockApi(page, { guest: true, handshake: () => { calls++; return new Promise(resolve => { release = resolve; }); } });
  await page.goto("/welcome");
  await page.getByRole("button", { name: "Начать в Telegram" }).first().click();
  await expect(page.getByRole("button", { name: "Открываем Telegram…" })).toHaveCount(2);
  await expect(page.locator("footer button")).toBeDisabled();
  await expect.poll(() => typeof release).toBe("function");
  release!({ status: 500 });
  await expect(page.getByRole("alert")).toContainText("Не получилось войти");
  await page.getByRole("button", { name: "Начать в Telegram" }).last().click();
  await expect.poll(() => calls).toBe(2);
  release!({ status: 201, body: { nonce: "N1", deep_link: "https://t.me/kainem_bot?start=login_N1", expires_at: new Date(Date.now() + 600_000).toISOString(), poll_interval_ms: 2000 } });
  await expect(page.getByRole("button", { name: "Ждём подтверждения…" })).toBeDisabled();
  await expect(page.locator("footer button")).toBeEnabled();
  await page.getByRole("button", { name: "Отмена" }).click();
  await expect(page.getByRole("button", { name: "Начать в Telegram" })).toHaveCount(2);
  await context.setOffline(true);
  await expect(page.getByRole("button", { name: "Нет подключения" })).toHaveCount(2);
  await expect(page.locator("footer button")).toBeDisabled();
  await context.setOffline(false);
  await expect(page.locator("footer button")).toBeEnabled();
});

test("guide starts at the top and returns to the saved home position", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 600 });
  await mockApi(page);
  await page.goto("/home");
  await page.getByRole("button", { name: "Как пользоваться" }).waitFor();
  await page.evaluate(() => window.scrollTo(0, 220));
  const savedY = await page.evaluate(() => scrollY);
  expect(savedY).toBeGreaterThan(0);
  await page.getByRole("button", { name: "Как пользоваться" }).click();
  await expect(page).toHaveURL(/\/help$/);
  await expect.poll(() => page.evaluate(() => scrollY)).toBe(0);
  await page.getByRole("button", { name: "На главную" }).first().click();
  await expect(page).toHaveURL(/\/home$/);
  await expect.poll(() => page.evaluate(() => scrollY)).toBe(savedY);
  await page.goto("/help");
  await page.getByRole("button", { name: "На главную" }).first().click();
  await expect(page).toHaveURL(/\/home$/);
});

test("onboarding retries a failed save and enters the real home", async ({ page }) => {
  let attempts = 0;
  await mockApi(page, { onboarded: false, save: () => ++attempts === 1 ? { status: 500 } : { body: profile(true) } });
  await page.goto("/onboarding");
  await page.getByRole("button", { name: "В семью", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page).toHaveURL(/\/onboarding$/);
  await page.getByRole("button", { name: "В семью", exact: true }).click();
  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByRole("region", { name: "Задач пока нет" })).toBeVisible();
});

test("iOS installation instructions trap focus and restore it when dismissed", async ({ page }) => {
  await page.addInitScript(() => Object.defineProperty(navigator, "userAgent", { get: () => "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)" }));
  await mockApi(page, { onboarded: false });
  await page.goto("/onboarding");
  const install = page.getByRole("button", { name: "Добавить на главный экран" });
  await install.click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("Открыть в Safari");
  const close = dialog.getByRole("button", { name: "Понятно" });
  await expect(close).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(close).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(close).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(install).toBeFocused();
});
