import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fakeBackend, makeServices, me, renderApp, sessionBody } from "../test-utils";
import { sectionState } from "../useHomeRuntime";

const task = { id: "t1", title: "Собрать форму", due_date: null, due_at: null, assignee_hint: null, done: false };
function backend(extra: Parameters<typeof fakeBackend>[0] = {}) {
  return fakeBackend({
    "POST /v1/auth/refresh": () => ({ status: 200, body: sessionBody }),
    "GET /v1/me": () => ({ status: 200, body: me({ onboarding_completed: true }) }),
    "GET /v1/families/{id}/tasks": () => ({ status: 200, body: [task] }),
    "GET /v1/families/{id}/events": () => ({ status: 200, body: { timezone: "Europe/Moscow", events: [] } }),
    ...extra,
  });
}
afterEach(() => { vi.restoreAllMocks(); window.dispatchEvent(new Event("online")); });

describe("home data states", () => {
  it("preserves an open task until the server confirms, then removes it", async () => {
    let confirm!: (value: { status: number; body: unknown }) => void;
    let done = false;
    const { fetchImpl, calls } = backend({
      "GET /v1/families/{id}/tasks": () => ({ status: 200, body: done ? [] : [task] }),
      "PATCH /v1/families/{id}/tasks/{task}": () => new Promise(resolve => { confirm = value => { done = true; resolve(value); }; }),
    });
    renderApp(makeServices(fetchImpl as typeof fetch), "/home");
    const checkbox = await screen.findByRole("checkbox", { name: /Отметить выполненной/ });
    await userEvent.click(checkbox);
    expect(checkbox.getAttribute("aria-checked")).toBe("false");
    expect(checkbox.hasAttribute("disabled")).toBe(true);
    expect(screen.getByText("Сохраняем…")).toBeTruthy();
    await userEvent.click(checkbox);
    await waitFor(() => expect(calls.filter(c => c.method === "PATCH")).toHaveLength(1));
    confirm({ status: 200, body: { ...task, done: true } });
    await screen.findByText("Выполнено");
    expect(checkbox.getAttribute("aria-checked")).toBe("true");
    expect(await screen.findByText("Все задачи выполнены.", { exact: false })).toBeTruthy();
    expect(screen.queryByRole("checkbox")).toBeNull();
  });
  it("retains the task on failure and retries on the same checkbox", async () => {
    let attempts = 0;
    const { fetchImpl } = backend({ "PATCH /v1/families/{id}/tasks/{task}": () => ++attempts === 1 ? { status: 500 } : { status: 200, body: { ...task, done: true } } });
    renderApp(makeServices(fetchImpl as typeof fetch), "/home");
    await userEvent.click(await screen.findByRole("checkbox"));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText("Собрать форму")).toBeTruthy();
    const retry = screen.getByRole("checkbox", { name: /Повторить выполнение/ });
    expect(retry.getAttribute("aria-checked")).toBe("false");
    await userEvent.click(retry);
    expect(await screen.findByText("Выполнено")).toBeTruthy();
    expect(attempts).toBe(2);
  });
  it("shows request errors separately from an empty list", async () => {
    renderApp(makeServices(backend({ "GET /v1/families/{id}/tasks": () => ({ status: 500 }) }).fetchImpl as typeof fetch), "/home");
    expect(await screen.findByText(/Не удалось загрузить задачи/, {}, { timeout: 3000 })).toBeTruthy();
    expect(screen.queryByText("Задач пока нет")).toBeNull();
    expect(screen.getByRole("button", { name: "Повторить" })).toBeTruthy();
  });
  it("disables completion offline while retaining cached rows", async () => {
    const { fetchImpl, calls } = backend();
    renderApp(makeServices(fetchImpl as typeof fetch), "/home");
    const checkbox = await screen.findByRole("checkbox");
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    window.dispatchEvent(new Event("offline"));
    await waitFor(() => expect(checkbox.hasAttribute("disabled")).toBe(true));
    await userEvent.click(checkbox);
    expect(calls.some(c => c.method === "PATCH")).toBe(false);
    expect(screen.getByText("Собрать форму")).toBeTruthy();
  });
  it("renders today's event with the time once and no visible date", async () => {
    const localToday = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Moscow", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
    const { fetchImpl } = backend({ "GET /v1/families/{id}/events": () => ({ status: 200, body: { timezone: "Europe/Moscow", events: [{ id: "e1", title: "Футбол", starts_at: `${localToday}T17:30:00+03:00`, ends_at: null, start_date: null, all_day: false, participants_hint: "Миша" }] } }) });
    renderApp(makeServices(fetchImpl as typeof fetch), "/home");
    const card = await screen.findByRole("region", { name: "События" });
    await within(card).findByText("Футбол");
    expect(card.querySelectorAll(".kn-event-badge__time")).toHaveLength(1);
    expect(within(card).queryByText("Сегодня")).toBeNull();
    expect(within(card).queryByText("Без даты")).toBeNull();
  });
  it("uses the configured bot link and reports only actual adapter failures", async () => {
    const services = makeServices(backend().fetchImpl as typeof fetch);
    vi.mocked(services.platform.openLink).mockImplementationOnce(() => { throw new Error("blocked"); });
    renderApp(services, "/home");
    await userEvent.click(await screen.findByRole("button", { name: "Пригласить через бота" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Попробовать ещё раз" }));
    expect(services.platform.openLink).toHaveBeenCalledWith("https://t.me/kainem_bot?start=share_invite");
    expect(screen.queryByText("Приглашение отправлено")).toBeNull();
  });
  it("uses the invitation start payload with the configured bot and leaves the header action unchanged", async () => {
    const services = makeServices(backend({ "GET /v1/me": () => ({ status: 200, body: { ...me({ onboarding_completed: true }), bot_link: "https://telegram.me/family_staging_bot?start=old&ref=pwa" } }) }).fetchImpl as typeof fetch);
    renderApp(services, "/home");
    await userEvent.click(await screen.findByRole("button", { name: "Пригласить через бота" }));
    expect(services.platform.openLink).toHaveBeenLastCalledWith("https://telegram.me/family_staging_bot?start=share_invite&ref=pwa");
    window.dispatchEvent(new Event("focus"));
    const header = screen.getByRole("button", { name: "В бота" });
    await waitFor(() => expect(header.hasAttribute("disabled")).toBe(false));
    await userEvent.click(header);
    expect(services.platform.openLink).toHaveBeenLastCalledWith("https://telegram.me/family_staging_bot?start=old&ref=pwa");
  });
  it("blocks duplicate bot handoffs and restores the buttons on return without a false missing-link error", async () => {
    let finish!: () => void;
    const services = makeServices(backend().fetchImpl as typeof fetch);
    vi.mocked(services.platform.openLink).mockImplementationOnce(() => new Promise<void>(resolve => { finish = resolve; }));
    renderApp(services, "/home");
    const bot = await screen.findByRole("button", { name: "В бота" });
    await userEvent.click(bot);
    expect(bot.hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: "Пригласить через бота" }).hasAttribute("disabled")).toBe(true);
    expect(screen.queryByText("Ссылка на бота пока недоступна.")).toBeNull();
    await userEvent.click(bot);
    expect(services.platform.openLink).toHaveBeenCalledOnce();
    window.dispatchEvent(new Event("focus"));
    await waitFor(() => expect(bot.hasAttribute("disabled")).toBe(false));
    finish();
  });
});

describe("section state contract", () => {
  const loaded = { data: [], isPending: false, isError: false, isFetching: false };
  it.each([
    [{ ...loaded, data: undefined, isPending: true }, 0, true, false, "Loading"],
    [{ ...loaded, data: undefined, isError: true }, 0, true, false, "Error"],
    [{ ...loaded, data: undefined }, 0, false, false, "OfflineEmpty"],
    [loaded, 1, false, false, "Offline"],
    [{ ...loaded, isError: true }, 1, true, false, "Stale"],
    [{ ...loaded, isFetching: true }, 1, true, false, "Refreshing"],
    [loaded, 1, true, false, "Content"], [loaded, 0, true, false, "Empty"], [loaded, 0, true, true, "AllDone"],
  ] as const)("%#", (query, count, online, done, expected) => { expect(sectionState(query, count, online, done)).toBe(expected); });
});
