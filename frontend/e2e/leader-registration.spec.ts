import { expect, test } from "@playwright/test";

test("leader: welcome → Telegram → back in the PWA with a session that survives reload", async ({ page, request }) => {
  // Without the Telegram app the browser lands on the t.me web page; the user then comes back.
  await page.route("https://t.me/**", (route) =>
    route.fulfill({ contentType: "text/html", body: "<h1>Telegram web stub</h1>" }),
  );

  await page.goto("/?utm_source=e2e");
  await expect(page.getByRole("button", { name: "Зарегистрироваться" })).toBeVisible();
  await page.screenshot({ path: "e2e/screens/B-welcome.png", fullPage: true });

  await page.getByRole("button", { name: "Зарегистрироваться" }).click();
  await expect(page.getByText("Telegram web stub")).toBeVisible();
  await page.goBack();
  // The reloaded app resumes the persisted handshake and keeps polling.
  await expect(page.getByText("Ждём подтверждения…")).toBeVisible();

  // The app persisted the pending handshake (so polling survives the trip to Telegram); read it back.
  const pending = await page.evaluate(
    () =>
      new Promise<{ nonce: string; deepLink: string }>((resolve, reject) => {
        const open = indexedDB.open("kainem");
        open.onerror = () => reject(open.error);
        open.onsuccess = () => {
          const get = open.result.transaction("kv").objectStore("kv").get("auth.pending_handshake");
          get.onsuccess = () => resolve(get.result);
          get.onerror = () => reject(get.error);
        };
      }),
  );
  const { nonce, deepLink: deep_link } = pending;
  expect(deep_link).toBe(`https://t.me/kainem_e2e_bot?start=login_${nonce}`);
  await page.screenshot({ path: "e2e/screens/B-waiting.png", fullPage: true });

  // What the bot does on `/start login_<nonce>` (unique Telegram id per run).
  const bind = await request.post(`/api/v1/test/tg-handshake/${nonce}/bind`, {
    data: { tg_user_id: Date.now(), first_name: "Лидер" },
  });
  expect((await bind.json()).kind).toBe("family_registered");

  await expect(page).toHaveURL(/\/onboarding$/);
  await expect(page.getByText("Семья Лидер")).toBeVisible();

  // The refresh cookie (httpOnly, path /api/v1/auth) restores the session after a reload.
  await page.reload();
  await expect(page).toHaveURL(/\/onboarding$/);
  await expect(page.getByText("Семья Лидер")).toBeVisible();
});

test("magic link from the bot message signs in once", async ({ page, request }) => {
  const bind = await request.post(`/api/v1/test/tg-handshake/unknown-nonce/bind`, {
    data: { tg_user_id: Date.now() + 1, first_name: "Мама" },
  });
  const { magic_token } = await bind.json();

  await page.goto(`/auth/tg?token=${magic_token}`);
  await expect(page).toHaveURL(/\/onboarding$/);
  await expect(page.getByText("Семья Мама")).toBeVisible();

  const other = await page.context().browser()!.newContext();
  const second = await other.newPage();
  await second.goto(`/auth/tg?token=${magic_token}`);
  await expect(second.getByText("Ссылка устарела или уже использована.")).toBeVisible();
  await other.close();
});
