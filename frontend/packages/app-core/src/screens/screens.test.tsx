import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { installModeOf } from "../useInstall";
import { fakeBackend, fakeInstall, makeServices, me, memoryStorage, renderApp, sessionBody } from "../test-utils";

function signedIn(extra: Record<string, Parameters<typeof fakeBackend>[0][string]> = {}, onboarded = false) {
  return fakeBackend({
    "POST /v1/auth/refresh": () => ({ status: 200, body: sessionBody }),
    "GET /v1/me": () => ({ status: 200, body: me({ onboarding_completed: onboarded }) }),
    "GET /v1/families/{id}/tasks": () => ({ status: 200, body: [] }),
    "GET /v1/families/{id}/events": () => ({ status: 200, body: { timezone: "Europe/Moscow", events: [] } }),
    ...extra,
  });
}

describe("installModeOf", () => {
  it.each([
    [fakeInstall({ isInstalled: () => true, canPrompt: () => true }), "hidden"],
    [fakeInstall({ canPrompt: () => true }), "prompt"],
    [fakeInstall({ os: () => "ios", needsManualInstructions: () => true }), "ios"],
    [fakeInstall({ os: () => "android" }), "manual"],
    [fakeInstall({ os: () => "desktop" }), "hidden"],
    [undefined, "hidden"],
  ] as const)("%#", (install, mode) => {
    expect(installModeOf(install)).toBe(mode);
  });
});

describe("onboarding (screen C)", () => {
  it("uses the native install prompt when the browser offers one", async () => {
    const prompt = vi.fn(async () => "accepted" as const);
    const services = makeServices(signedIn().fetchImpl as typeof fetch, memoryStorage(), fakeInstall({ canPrompt: () => true, prompt }));
    const track = vi.spyOn(services.analytics, "track");
    renderApp(services, "/onboarding");
    await userEvent.click(await screen.findByText("Добавить на главный экран"));
    expect(prompt).toHaveBeenCalledOnce();
    expect(track).toHaveBeenCalledWith("a2hs_prompted", { os: "android" });
    expect(track).toHaveBeenCalledWith("a2hs_accepted", { os: "android" });
  });

  it("shows Safari steps on iOS, including leaving Telegram's in-app browser", async () => {
    const install = fakeInstall({ os: () => "ios", needsManualInstructions: () => true });
    const services = makeServices(signedIn().fetchImpl as typeof fetch, memoryStorage(), install);
    const track = vi.spyOn(services.analytics, "track");
    renderApp(services, "/onboarding");
    await userEvent.click(await screen.findByText("Добавить на главный экран"));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/Открыть в Safari/)).toBeTruthy();
    expect(track).toHaveBeenCalledWith("a2hs_instructions_shown", { os: "ios" });
    await userEvent.click(within(dialog).getByText("Понятно"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("hides the card when the app is already installed", async () => {
    const install = fakeInstall({ isInstalled: () => true });
    renderApp(makeServices(signedIn().fetchImpl as typeof fetch, memoryStorage(), install), "/onboarding");
    await screen.findByText("В семью");
    expect(screen.queryByText("Добавить на главный экран")).toBeNull();
  });

  it("«В семью» completes onboarding and opens the main screen", async () => {
    const { fetchImpl, calls } = signedIn({
      "PATCH /v1/me": () => ({ status: 200, body: me({ onboarding_completed: true }) }),
    });
    renderApp(makeServices(fetchImpl as typeof fetch), "/onboarding");
    await userEvent.click(await screen.findByText("В семью"));
    expect(await screen.findByText("Задачи")).toBeTruthy();
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ onboarding_completed: true });
  });

  it("keeps the user on onboarding with an error when saving fails", async () => {
    const { fetchImpl } = signedIn({ "PATCH /v1/me": () => ({ status: 500 }) });
    renderApp(makeServices(fetchImpl as typeof fetch), "/onboarding");
    await userEvent.click(await screen.findByText("В семью"));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText("В семью")).toBeTruthy();
  });
});

describe("main screen (D) and help", () => {
  it("shows real empty states without placeholder rows", async () => {
    renderApp(makeServices(signedIn({}, true).fetchImpl as typeof fetch), "/home");
    expect(await screen.findByText("Задачи")).toBeTruthy();
    expect(screen.getByText("События")).toBeTruthy();
    expect(await screen.findByText("Задач пока нет")).toBeTruthy();
    expect(await screen.findByText("Событий пока нет")).toBeTruthy();
    expect(screen.queryByText(/третья категор/)).toBeNull();
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });

  it("«Как пользоваться» opens help, which opens the bot and signs out", async () => {
    const { fetchImpl, calls } = signedIn({ "POST /v1/auth/logout": () => ({ status: 204 }) }, true);
    const services = makeServices(fetchImpl as typeof fetch);
    const track = vi.spyOn(services.analytics, "track");
    renderApp(services, "/home");
    await userEvent.click(await screen.findByText("Как пользоваться"));
    expect(track).toHaveBeenCalledWith("how_to_clicked", {});
    expect(await screen.findByText("Перешлите сообщение из чата")).toBeTruthy();

    await userEvent.click(screen.getByText("Открыть бота"));
    expect(services.platform.openLink).toHaveBeenCalledWith("https://t.me/kainem_bot");

    await userEvent.click(screen.getByText("Семья и аккаунт"));
    await userEvent.click(screen.getByText("Выйти"));
    await waitFor(() => expect(calls.some((c) => c.path === "/v1/auth/logout")).toBe(true));
    expect((await screen.findAllByRole("button", { name: "Начать в Telegram" }))[0]!).toBeTruthy();
  });

  it("the guide invitation opens the bot with the invitation start payload", async () => {
    const services = makeServices(signedIn({}, true).fetchImpl as typeof fetch);
    renderApp(services, "/help");
    await userEvent.click(await screen.findByRole("button", { name: "Пригласить через бота" }));
    expect(services.platform.openLink).toHaveBeenCalledWith("https://t.me/kainem_bot?start=share_invite");
  });
});

describe("family switcher (help)", () => {
  it("is shown only with several families and switches the active one", async () => {
    const two = {
      ...me({ onboarding_completed: true }),
      families: [
        { id: "f1", name: "Семья Лидер", role: "owner" },
        { id: "f2", name: "Семья Мама", role: "adult" },
      ],
    };
    const { fetchImpl, calls } = fakeBackend({
      "POST /v1/auth/refresh": () => ({ status: 200, body: sessionBody }),
      "GET /v1/me": () => ({ status: 200, body: two }),
      "PUT /v1/me/active-family": ({ body }) => ({ status: 200, body: { ...two, active_family_id: body.family_id } }),
    });
    renderApp(makeServices(fetchImpl as typeof fetch), "/help");
    await userEvent.click(await screen.findByText("Семья и аккаунт"));
    expect(screen.getByText("Ваши семьи")).toBeTruthy();
    expect(screen.getByText("Семья Лидер — сейчас открыта")).toBeTruthy();
    await userEvent.click(screen.getByText("Семья Мама"));
    expect(await screen.findByText("Семья Мама — сейчас открыта")).toBeTruthy();
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ family_id: "f2" });
  });

  it("is hidden with a single family", async () => {
    renderApp(makeServices(signedIn({}, true).fetchImpl as typeof fetch), "/help");
    await screen.findByText("Перешлите сообщение из чата");
    expect(screen.queryByText("Ваши семьи")).toBeNull();
  });
});
