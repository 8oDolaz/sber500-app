import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  // Keep shell/branding checks independent of a running API; no session is restored.
  await page.route("**/api/**", route => route.fulfill({ status: 401, contentType: "application/json", body: "{}" }));
});

test("production manifest, site favicon and install icons reference the new brand assets", async ({ page, request }) => {
  const manifestReply = await request.get("/manifest.webmanifest");
  expect(manifestReply.ok()).toBe(true);
  const manifest = await manifestReply.json();
  expect(manifest).toMatchObject({ id: "/", name: "kainem", display: "standalone", start_url: "/", scope: "/", orientation: "any" });
  expect(manifest.icons).toEqual(expect.arrayContaining([
    expect.objectContaining({ src: "pwa-192x192.png", sizes: "192x192" }),
    expect.objectContaining({ src: "pwa-512x512.png", sizes: "512x512" }),
    expect.objectContaining({ src: "maskable-icon-512x512.png", sizes: "512x512", purpose: "maskable" }),
  ]));
  await page.goto("/");
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute("href", "/manifest.webmanifest");
  await expect(page.locator('link[rel="apple-touch-icon"]')).toHaveAttribute("href", "/apple-touch-icon-180x180.png");
  await expect(page.locator('link[rel="icon"][type="image/png"]')).toHaveAttribute("href", "/favicon-32x32.png");
  const icons = await page.evaluate(async () => {
    const sources = ["/pwa-192x192.png", "/pwa-512x512.png", "/maskable-icon-512x512.png", "/apple-touch-icon-180x180.png", "/favicon-32x32.png"];
    return Promise.all(sources.map(async src => { const icon = new Image(); icon.src = src; await icon.decode(); return [icon.naturalWidth, icon.naturalHeight]; }));
  });
  expect(icons).toEqual([[192, 192], [512, 512], [512, 512], [180, 180], [32, 32]]);
  expect((await request.get("/favicon.ico")).ok()).toBe(true);
});

test("the installed service worker opens the shell offline and never caches family API data", async ({ page, context }) => {
  await page.goto("/");
  await page.evaluate(async () => { await navigator.serviceWorker.ready; });
  await page.reload();
  expect(await page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true);
  const cached = await page.evaluate(async () => {
    const names = await caches.keys();
    const requests = await Promise.all(names.map(async name => (await (await caches.open(name)).keys()).map(r => new URL(r.url).pathname)));
    return requests.flat();
  });
  expect(cached).toContain("/index.html");
  expect(cached.some(path => path.startsWith("/api/"))).toBe(false);
  await page.unroute("**/api/**");
  await context.setOffline(true);
  await page.goto("/home");
  await expect(page.getByText("Нет соединения с сервером.")).toBeVisible();
  expect(await page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true);
});
