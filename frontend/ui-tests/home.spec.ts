import { expect, test, type Page } from "@playwright/test";

const tasks = [
  { id: "t1", title: "Оплатить английский", due_date: "2026-10-11", due_at: null, assignee_hint: "Миша", done: false },
  { id: "t2", title: "Собрать форму", due_date: "2026-10-10", due_at: "2026-10-10T14:00:00Z", assignee_hint: "Маша", done: false },
];
const events = [
  { id: "e1", title: "Футбол", starts_at: "2026-10-10T14:30:00Z", ends_at: null, start_date: null, all_day: false, participants_hint: "Миша" },
  { id: "e2", title: "Родительское собрание", starts_at: "2026-10-13T15:00:00Z", ends_at: null, start_date: null, all_day: false, participants_hint: "Мама" },
];
type Reply = { status?: number; body: unknown };
type Options = { tasks?: () => Reply | Promise<Reply>; events?: () => Reply | Promise<Reply>; patch?: () => Reply | Promise<Reply>; botLink?: string | null; familyId?: string | null };
async function assertSvgGeometry(page: Page) {
  const mismatches = await page.locator("img").evaluateAll(async nodes => {
    const results = await Promise.all(nodes.map(async node => {
      const image = node as HTMLImageElement;
      const svg = new DOMParser().parseFromString(await (await fetch(image.src)).text(), "image/svg+xml").documentElement;
      const width = Number(svg.getAttribute("width")), height = Number(svg.getAttribute("height"));
      const style = getComputedStyle(image), box = image.getBoundingClientRect();
      const matrix = new DOMMatrixReadOnly(style.transform === "none" ? undefined : style.transform);
      const expectedWidth = Math.abs(matrix.a) * width + Math.abs(matrix.c) * height;
      const expectedHeight = Math.abs(matrix.b) * width + Math.abs(matrix.d) * height;
      const valid = width > 0 && height > 0 && Math.abs(parseFloat(style.width) - width) < .1 && Math.abs(parseFloat(style.height) - height) < .1 && Math.abs(box.width - expectedWidth) < .1 && Math.abs(box.height - expectedHeight) < .1;
      return valid ? null : `${image.parentElement?.className}: ${style.width} × ${style.height}, source ${width} × ${height}`;
    }));
    return results.filter(Boolean);
  });
  expect(mismatches).toEqual([]);
}
async function mockApi(page: Page, options: Options = {}) {
  await page.clock.setFixedTime(new Date("2026-10-10T10:00:00Z"));
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    let reply: Reply;
    if (path === "/api/v1/auth/refresh") reply = { body: { access_token: "ui-test", token_type: "bearer", expires_in: 900, user_id: "u1" } };
    else if (path === "/api/v1/me") reply = { body: { user: { id: "u1", first_name: "Мама" }, onboarding_completed: true, active_family_id: options.familyId === undefined ? "f1" : options.familyId, families: options.familyId === null ? [] : [{ id: "f1", name: "Наша семья", role: "owner" }], bot_link: options.botLink === undefined ? "https://t.me/kainem_bot" : options.botLink } };
    else if (path.endsWith("/tasks") && route.request().method() === "GET") reply = options.tasks ? await options.tasks() : { body: tasks };
    else if (path.endsWith("/events")) reply = options.events ? await options.events() : { body: { timezone: "Europe/Moscow", events } };
    else if (path.includes("/tasks/") && route.request().method() === "PATCH") reply = options.patch ? await options.patch() : { body: { ...tasks[0], done: true } };
    else if (path === "/api/v1/analytics/events") reply = { status: 204, body: null };
    else reply = { status: 404, body: {} };
    await route.fulfill({ status: reply.status ?? 200, contentType: "application/json", body: reply.status === 204 ? undefined : JSON.stringify(reply.body) });
  });
}

for (const width of [320, 402, 768, 1440]) {
  test(`home fits ${width}px, SVGs load, help stays fixed and the final CTA is reachable`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 874 });
    await mockApi(page);
    await page.goto("/home");
    const taskCard = page.locator(".kn-planning-card--tasks");
    await expect(taskCard).toHaveAttribute("data-state", "Content");
    await page.evaluate(() => document.fonts.ready);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const circle = await page.getByRole("checkbox").first().boundingBox();
    expect(circle?.width).toBe(44); expect(circle?.height).toBe(44);
    const help = page.getByRole("button", { name: "Как пользоваться" });
    const before = await help.boundingBox();
    expect(before?.y).toBe(780); expect(before?.height).toBe(44);
    expect(before?.x).toBe((width - 200) / 2);
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    const after = await help.boundingBox();
    expect(after?.y).toBe(before?.y);
    const invite = page.getByRole("button", { name: "Пригласить через бота" });
    const inviteBox = await invite.boundingBox();
    expect(inviteBox!.y + inviteBox!.height).toBeLessThanOrEqual(after!.y - 20);
    await expect(page.locator(".kn-invite-card")).toHaveCSS("background-color", "rgb(230, 227, 227)");
    expect(await page.locator("img").evaluateAll(nodes => nodes.every(n => (n as HTMLImageElement).complete && (n as HTMLImageElement).naturalWidth > 0))).toBe(true);
    await assertSvgGeometry(page);
    if (width === 402) {
      const geometry = await taskCard.boundingBox();
      expect(geometry).toMatchObject({ x: 16, width: 370, height: 216 });
      await page.screenshot({ path: `test-results/${testInfo.project.name}-home-402-bottom.png` });
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: `test-results/${testInfo.project.name}-home-402.png`, fullPage: true });
    }
    if (width === 1440) await page.screenshot({ path: `test-results/${testInfo.project.name}-home-desktop.png`, fullPage: true });
  });
}

test("initial skeletons, partial loading, and genuinely empty lists", async ({ page }) => {
  let release!: (reply: Reply) => void;
  await mockApi(page, { tasks: () => new Promise(resolve => { release = resolve; }), events: () => ({ body: { timezone: "Europe/Moscow", events: [] } }) });
  await page.goto("/home");
  await expect(page.locator(".kn-planning-card--tasks")).toHaveAttribute("data-state", "Loading");
  await expect(page.getByRole("region", { name: "Событий пока нет" })).toBeVisible();
  expect(await page.locator(".kn-home-skeleton img").evaluateAll(nodes => nodes.every(n => (n as HTMLImageElement).naturalWidth > 0))).toBe(true);
  release({ body: [] });
  await expect(page.getByRole("region", { name: "Задач пока нет" })).toBeVisible();
  await expect(page.locator(".kn-today-card")).toHaveCount(0);
  await expect(page.getByRole("checkbox")).toHaveCount(0);
  await page.screenshot({ path: "test-results/home-empty.png", fullPage: true });
});

test("load failure offers retry and does not pretend the family has no tasks", async ({ page }) => {
  let failed = true;
  await mockApi(page, { tasks: () => failed ? { status: 500, body: {} } : { body: tasks } });
  await page.goto("/home");
  const card = page.locator(".kn-planning-card--tasks");
  await expect(card).toHaveAttribute("data-state", "Error");
  await expect(page.getByText("Задач пока нет")).toHaveCount(0);
  failed = false;
  await card.getByRole("button", { name: "Повторить" }).click();
  await expect(card).toHaveAttribute("data-state", "Content");
});

test("stale and offline preserve data; recovery refetches it", async ({ page, context }) => {
  let failed = false;
  let release: ((reply: Reply) => void) | undefined;
  let hold = false;
  await mockApi(page, { tasks: () => hold ? new Promise(resolve => { release = resolve; }) : failed ? { status: 500, body: {} } : { body: tasks } });
  await page.goto("/home");
  const card = page.locator(".kn-planning-card--tasks");
  await expect(card).toHaveAttribute("data-state", "Content");
  hold = true;
  // The same visibility event fired on return from Telegram.
  await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange", { bubbles: true })));
  await expect(card).toHaveAttribute("data-state", "Refreshing");
  await expect(card.getByText("Оплатить английский")).toBeVisible();
  hold = false; failed = true;
  release!({ status: 500, body: {} });
  await expect(card).toHaveAttribute("data-state", "Stale");
  await context.setOffline(true);
  await expect(card).toHaveAttribute("data-state", "Offline");
  await expect(card.getByRole("checkbox").first()).toBeDisabled();
  await expect(card.getByRole("button", { name: "Повторить" })).toBeDisabled();
  failed = false;
  await context.setOffline(false);
  await expect(card).toHaveAttribute("data-state", "Content");
});

test("completion waits for confirmation, retries failures, then shows AllDone", async ({ page }) => {
  let release!: (reply: Reply) => void;
  let done = false, calls = 0;
  await mockApi(page, { tasks: () => ({ body: done ? [] : [tasks[0]] }), patch: () => { calls++; return new Promise(resolve => { release = resolve; }); } });
  await page.goto("/home");
  const card = page.locator(".kn-planning-card--tasks"), checkbox = page.getByRole("checkbox");
  await checkbox.click();
  await expect(checkbox).toBeDisabled(); await expect(checkbox).not.toBeChecked();
  await expect(card.getByText("Сохраняем…")).toBeVisible();
  release({ status: 500, body: {} });
  await expect(card.getByRole("alert")).toContainText("Не сохранено");
  await checkbox.click();
  await expect.poll(() => calls).toBe(2);
  done = true; release({ body: { ...tasks[0], done: true } });
  await expect(checkbox).toBeChecked();
  await expect(card).toHaveAttribute("data-state", "AllDone");
  await expect(page.getByRole("checkbox")).toHaveCount(0);
});

test("today events show their time once; missing fields and explicit all-day remain distinct", async ({ page }) => {
  await mockApi(page, {
    tasks: () => ({ body: [{ ...tasks[0], due_date: null, assignee_hint: null }] }),
    events: () => ({ body: { timezone: "Europe/Moscow", events: [events[0], { ...events[1], id: "e3", title: "Без указанного времени", starts_at: null, start_date: "2026-10-10", participants_hint: null }, { ...events[1], id: "e4", title: "День рождения", starts_at: null, start_date: "2026-10-11", all_day: true, participants_hint: null }] } }),
  });
  await page.goto("/home");
  const eventCard = page.locator(".kn-planning-card--events");
  await expect(eventCard.locator(".kn-home-event")).toHaveCount(3);
  const football = eventCard.locator("li").filter({ hasText: "Футбол" });
  await expect(football.locator(".kn-event-badge__time")).toHaveText("17:30");
  await expect(football.locator(".kn-home-metadata")).not.toContainText("Сегодня");
  await expect(football.locator(".kn-home-metadata")).not.toContainText("17:30");
  await expect(eventCard.getByText("Без времени", { exact: true })).toHaveCount(1);
  await expect(eventCard.getByText("Весь день", { exact: true })).toHaveCount(1);
  await expect(page.locator(".kn-planning-card--tasks").getByText("Без срока")).toBeVisible();
});

test("fixed help is keyboard accessible and navigates to the existing instructions", async ({ page }) => {
  await mockApi(page); await page.goto("/home");
  const help = page.getByRole("button", { name: "Как пользоваться" });
  await help.focus();
  await expect(help).toBeFocused();
  await expect(help).toHaveCSS("outline-style", "solid");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/help$/);
  await expect(page.getByRole("heading", { name: "Перешлите сообщение из чата", exact: true })).toBeVisible();
});

test("an unavailable bot link disables both CTAs and explains why", async ({ page }) => {
  await mockApi(page, { botLink: null }); await page.goto("/home");
  await expect(page.getByRole("button", { name: "В бота" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Пригласить через бота" })).toBeDisabled();
  await expect(page.getByText("Ссылка на бота пока недоступна.")).toBeVisible();
});

test("offline before the first planning reply shows OfflineEmpty, not Empty", async ({ page, context }) => {
  let release!: (reply: Reply) => void;
  await mockApi(page, { tasks: () => new Promise(resolve => { release = resolve; }) });
  await page.goto("/home");
  const card = page.locator(".kn-planning-card--tasks");
  await expect(card).toHaveAttribute("data-state", "Loading");
  await expect.poll(() => typeof release).toBe("function");
  await context.setOffline(true);
  await expect(card).toHaveAttribute("data-state", "OfflineEmpty");
  await expect(card.getByRole("button", { name: "Повторить" })).toBeDisabled();
  release({ body: [] });
});

test("a missing active family offers a way forward without endless skeletons", async ({ page }) => {
  await mockApi(page, { familyId: null, tasks: () => { throw new Error("must not request unscoped tasks"); } });
  await page.goto("/home");
  await expect(page.getByRole("heading", { name: "Семья пока не выбрана" })).toBeVisible();
  await expect(page.locator(".kn-home-skeleton")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "В бота" })).toBeEnabled();
});

test("state catalogue covers optional metadata, row states and invitation states without broken assets", async ({ page }) => {
  await mockApi(page); await page.goto("/_kit");
  const taskCard = page.locator(".kn-planning-card--tasks"), eventCard = page.locator(".kn-planning-card--events");
  for (const person of [true, false]) {
    await page.getByLabel("Указан человек").setChecked(person);
    for (const timing of ["DateTime", "DateOnly", "TimeOnly", "None"]) {
      await page.getByRole("combobox", { name: "Данные задачи", exact: true }).selectOption(timing);
      const row = taskCard.locator("li").first();
      await expect(row.locator(".kn-home-icon--clock")).toHaveCount(timing.includes("Time") ? 1 : 0);
      await expect(row.locator(".kn-home-icon--person")).toHaveCount(person ? 1 : 0);
      if (timing === "None") await expect(row).toContainText("Без срока");
      if (timing === "TimeOnly") await expect(row).toContainText("Без даты");
    }
    for (const timing of ["DateTime", "DateOnly", "TimeOnly", "None", "TodayTime", "TodayNoTime"]) {
      await page.getByRole("combobox", { name: "Данные события", exact: true }).selectOption(timing);
      const row = eventCard.locator("li").first();
      await expect(row.locator(".kn-home-icon--person")).toHaveCount(person ? 1 : 0);
      if (timing === "TodayTime") {
        await expect(row.locator(".kn-event-badge__time")).toHaveText("19:00");
        await expect(row.locator(".kn-home-metadata")).not.toContainText("Сегодня");
      }
      if (timing === "TodayNoTime") await expect(row).toContainText("Без времени");
    }
  }
  for (const state of ["Open", "Saving", "Completed", "Error", "Disabled", "Overdue"]) {
    await page.getByRole("combobox", { name: "Состояние задачи", exact: true }).selectOption(state);
    await expect(taskCard.locator("li").first()).toHaveAttribute("data-state", state);
    await expect.poll(() => page.locator("img").evaluateAll(nodes => nodes.every(n => (n as HTMLImageElement).naturalWidth > 0))).toBe(true);
    // A spinning saving indicator has a changing transform; other states keep exact source geometry.
    if (state !== "Saving") await assertSvgGeometry(page);
  }
  for (const state of ["Content", "Empty", "Loading", "Error", "OfflineEmpty", "Refreshing", "Stale", "Offline", "AllDone"]) {
    await page.getByRole("combobox", { name: "Состояние списка", exact: true }).selectOption(state);
    await expect(taskCard).toHaveAttribute("data-state", state);
    if (state === "Loading") {
      await expect.poll(() => page.locator(".kn-today-skeleton-row img").evaluateAll(nodes => nodes.length === 2 && nodes.every(n => (n as HTMLImageElement).naturalWidth === 330 && n.getBoundingClientRect().width === 330))).toBe(true);
      await assertSvgGeometry(page);
    }
  }
  for (const state of ["Default", "Opening", "Error", "Disabled"]) {
    await page.getByRole("combobox", { name: "Приглашение", exact: true }).selectOption(state);
    await expect(page.locator(".kn-invite-card")).toHaveCSS("background-color", "rgb(230, 227, 227)");
    if (state === "Opening" || state === "Disabled") await expect(page.locator(".kn-invite-card button")).toBeDisabled();
    if (state === "Error") await expect(page.locator(".kn-invite-card [role=alert]")).toBeVisible();
  }
});
