import { expect, test } from "@playwright/test";

/** SPEC G → H → D: a message forwarded to the bot, confirmed, shows up on the main screen. */
test("forwarded message → «Сохранить» → task on the main screen → done", async ({ page, request }) => {
  const tg = Date.now() + 7;
  const start = await (await request.post("/api/v1/test/bot-start", { data: { tg_user_id: tg, first_name: "Дима" } })).json();

  await page.goto(`/auth/tg?token=${start.magic_token}`);
  await page.getByRole("button", { name: "В семью" }).click();
  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByText(/Перешлите боту сообщение/)).toBeVisible();

  // In the bot: forward a message, get a draft card, press «Сохранить» (the fake LLM makes it a task).
  const captured = await (
    await request.post("/api/v1/test/capture", { data: { tg_user_id: tg, text: "забрать посылку на почте" } })
  ).json();
  expect(captured.failure).toBeNull();
  const [draft] = captured.drafts;
  expect(draft.summary).toBe("Задача: забрать посылку на почте");
  const confirmed = await (
    await request.post(`/api/v1/test/drafts/${draft.id}/confirm`, { data: { tg_user_id: tg } })
  ).json();
  expect(confirmed.status).toBe("done");

  // Back in the app: returning to the tab refetches immediately.
  await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange", { bubbles: true })));
  await expect(page.getByText("забрать посылку на почте")).toBeVisible();
  await page.screenshot({ path: "e2e/screens/D-home-items.png", fullPage: true });

  await page.getByRole("button", { name: "Отметить выполненной" }).click();
  await expect(page.getByRole("button", { name: "Вернуть в работу" })).toBeVisible();
  await page.reload();
  await expect(page.getByText("забрать посылку на почте")).toHaveCount(0);
});
