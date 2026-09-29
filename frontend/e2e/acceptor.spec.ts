import { expect, test } from "@playwright/test";

test("acceptor: invite link → bot → magic link → onboarding → the leader's family", async ({ page, request }) => {
  const base = Date.now();
  // Leader registers in the bot (plain /start) and gets an invite link to forward.
  const leader = await (
    await request.post("/api/v1/test/bot-start", { data: { tg_user_id: base, first_name: "Лидер" } })
  ).json();
  expect(leader.kind).toBe("family_registered");
  const token = new URL(leader.invite_link).searchParams.get("start");
  expect(token).toMatch(/^inv_/);

  // The acceptor opens the forwarded link: /start inv_<token> (screen F).
  const acceptor = await (
    await request.post("/api/v1/test/bot-start", { data: { tg_user_id: base + 1, first_name: "Мама", payload: token } })
  ).json();
  expect(acceptor.kind).toBe("invite_accepted");
  expect(acceptor.family_name).toBe("Семья Лидер");

  await page.goto(`/auth/tg?token=${acceptor.magic_token}`);
  await expect(page).toHaveURL(/\/onboarding$/);
  await page.getByRole("button", { name: "В семью" }).click();
  await expect(page).toHaveURL(/\/home$/);

  // Deep link / reload on an inner screen stays there.
  await page.goto("/help");
  await expect(page.getByRole("heading", { name: "Как пользоваться" })).toBeVisible();
  const me = await page.evaluate(async () => {
    const refresh = await fetch("/api/v1/auth/refresh", { method: "POST" });
    const { access_token } = await refresh.json();
    return (await fetch("/api/v1/me", { headers: { Authorization: `Bearer ${access_token}` } })).json();
  });
  expect(me.families).toEqual([expect.objectContaining({ name: "Семья Лидер", role: "adult" })]);
});
