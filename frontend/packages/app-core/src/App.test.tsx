import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fakeBackend, makeServices, me, memoryStorage, renderApp, sessionBody } from "./test-utils";

afterEach(() => vi.useRealTimers());

describe("session gate", () => {
  it("sends a guest from the splash to the welcome screen", async () => {
    const { fetchImpl } = fakeBackend({ "POST /v1/auth/refresh": () => ({ status: 401, body: { detail: {} } }) });
    renderApp(makeServices(fetchImpl as typeof fetch));
    expect(await screen.findByText("Зарегистрироваться")).toBeTruthy();
  });

  it("sends a returning user who hasn't finished onboarding to onboarding", async () => {
    const { fetchImpl, calls } = fakeBackend({
      "POST /v1/auth/refresh": () => ({ status: 200, body: sessionBody }),
      "GET /v1/me": () => ({ status: 200, body: me() }),
    });
    renderApp(makeServices(fetchImpl as typeof fetch));
    expect(await screen.findByText(/Онбординг появится/)).toBeTruthy();
    expect(calls.find((c) => c.path === "/v1/me")?.headers.get("Authorization")).toBe("Bearer at-1");
  });

  it("sends an onboarded user to home", async () => {
    const { fetchImpl } = fakeBackend({
      "POST /v1/auth/refresh": () => ({ status: 200, body: sessionBody }),
      "GET /v1/me": () => ({ status: 200, body: me({ onboarding_completed: true }) }),
    });
    renderApp(makeServices(fetchImpl as typeof fetch), "/home");
    expect(await screen.findByText(/Главный экран появится/)).toBeTruthy();
  });

  it("shows a retry instead of logging out when the server is unreachable", async () => {
    const { fetchImpl } = fakeBackend({ "POST /v1/auth/refresh": () => ({ status: 502 }) });
    renderApp(makeServices(fetchImpl as typeof fetch));
    expect(await screen.findByText("Повторить")).toBeTruthy();
  });
});

describe("welcome → Telegram login", () => {
  it("opens the bot deep link, polls until Start is pressed, then signs in", async () => {
    let pressed = false;
    const { fetchImpl, calls } = fakeBackend({
      "POST /v1/auth/refresh": () => ({ status: 401, body: { detail: {} } }),
      "POST /v1/auth/tg-handshake": () => ({
        status: 201,
        body: {
          nonce: "N1",
          deep_link: "https://t.me/kainem_bot?start=login_N1",
          expires_at: new Date(Date.now() + 600_000).toISOString(),
          poll_interval_ms: 10,
        },
      }),
      "POST /v1/auth/tg-handshake/{nonce}/exchange": () =>
        pressed ? { status: 200, body: sessionBody } : { status: 202, body: { status: "pending" } },
      "GET /v1/me": () => ({ status: 200, body: me() }),
    });
    const services = makeServices(fetchImpl as typeof fetch);
    renderApp(services);
    await userEvent.click(await screen.findByText("Зарегистрироваться"));

    expect(await screen.findByText("Ждём подтверждения…")).toBeTruthy();
    expect(services.platform.openLink).toHaveBeenCalledWith("https://t.me/kainem_bot?start=login_N1", {
      newTab: false,
    });
    const start = calls.find((c) => c.path === "/v1/auth/tg-handshake")!;
    expect(start.body.challenge).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(start.body.utm).toEqual({ utm_source: "test" });
    expect(start.body.anonymous_id).toBeTruthy();

    await waitFor(() => expect(calls.filter((c) => c.path.endsWith("/exchange")).length).toBeGreaterThan(1));
    act(() => {
      pressed = true;
    });
    expect(await screen.findByText(/Онбординг появится/)).toBeTruthy();
    const exchange = calls.find((c) => c.path.endsWith("/exchange"))!;
    expect(exchange.body.verifier).toHaveLength(43); // the verifier, never sent at start
    expect(exchange.body.verifier).not.toBe(start.body.challenge);
  });

  it("resumes polling a handshake saved before a reload", async () => {
    const storage = memoryStorage({
      "auth.pending_handshake": {
        nonce: "N2",
        verifier: "v".repeat(43),
        deepLink: "https://t.me/kainem_bot?start=login_N2",
        expiresAt: new Date(Date.now() + 600_000).toISOString(),
        pollIntervalMs: 10,
      },
    });
    const { fetchImpl } = fakeBackend({
      "POST /v1/auth/refresh": () => ({ status: 401, body: { detail: {} } }),
      "POST /v1/auth/tg-handshake/{nonce}/exchange": () => ({ status: 200, body: sessionBody }),
      "GET /v1/me": () => ({ status: 200, body: me() }),
    });
    renderApp(makeServices(fetchImpl as typeof fetch, storage));
    expect(await screen.findByText(/Онбординг появится/)).toBeTruthy();
    expect(await storage.get("auth.pending_handshake")).toBeUndefined();
  });

  it("explains an expired handshake and lets the user retry", async () => {
    const { fetchImpl } = fakeBackend({
      "POST /v1/auth/refresh": () => ({ status: 401, body: { detail: {} } }),
      "POST /v1/auth/tg-handshake": () => ({
        status: 201,
        body: { nonce: "N3", deep_link: "https://t.me/x", expires_at: new Date(Date.now() + 1e6).toISOString(), poll_interval_ms: 10 },
      }),
      "POST /v1/auth/tg-handshake/{nonce}/exchange": () => ({ status: 410, body: { detail: { reason: "expired" } } }),
    });
    renderApp(makeServices(fetchImpl as typeof fetch));
    await userEvent.click(await screen.findByText("Зарегистрироваться"));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Ссылка для входа устарела. Попробуйте ещё раз.");
    expect(screen.getByText("Зарегистрироваться")).toBeTruthy();
  });
});

describe("magic link", () => {
  it("signs in once and continues to the gate target", async () => {
    const { fetchImpl, calls } = fakeBackend({
      "POST /v1/auth/refresh": () => ({ status: 401, body: { detail: {} } }),
      "POST /v1/auth/magic": () => ({ status: 200, body: sessionBody }),
      "GET /v1/me": () => ({ status: 200, body: me() }),
    });
    renderApp(makeServices(fetchImpl as typeof fetch), "/auth/tg?token=abcdefghijklmnopqrstuvwxyz");
    expect(await screen.findByText(/Онбординг появится/)).toBeTruthy();
    expect(calls.filter((c) => c.path === "/v1/auth/magic")).toHaveLength(1);
  });

  it("offers Telegram login when the link is used or expired", async () => {
    const { fetchImpl } = fakeBackend({
      "POST /v1/auth/refresh": () => ({ status: 401, body: { detail: {} } }),
      "POST /v1/auth/magic": () => ({ status: 410, body: { detail: { reason: "used" } } }),
    });
    renderApp(makeServices(fetchImpl as typeof fetch), "/auth/tg?token=abcdefghijklmnopqrstuvwxyz");
    expect(await screen.findByText("Войти через Telegram")).toBeTruthy();
  });
});
