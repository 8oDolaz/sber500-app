import { Analytics } from "@kainem/analytics";
import { createApiClient } from "@kainem/api-client";
import type { KeyValueStorage, PlatformAdapter } from "@kainem/platform";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { vi } from "vitest";
import { AppRoutes } from "./App";
import { SessionManager } from "./auth/session";
import { ServicesProvider, type AppServices } from "./context";

export type Handler = (req: { method: string; path: string; body: any; headers: Headers }) =>
  | { status: number; body?: unknown }
  | Promise<{ status: number; body?: unknown }>;

/** A fake backend: routes "METHOD /path" to handlers and records every call. */
export function fakeBackend(routes: Record<string, Handler>) {
  const calls: Array<{ method: string; path: string; body: any; headers: Headers }> = [];
  const fetchImpl = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const req = input instanceof Request ? input : new Request(new URL(String(input), "http://app.test"), init);
    const path = new URL(req.url).pathname.replace(/^\/api/, "");
    const text = await req.text();
    const call = { method: req.method, path, body: text ? JSON.parse(text) : undefined, headers: req.headers };
    calls.push(call);
    const key = Object.keys(routes).find((k) => {
      const [m, p] = k.split(" ");
      return m === req.method && new RegExp(`^${p!.replace(/\{[^}]+\}/g, "[^/]+")}$`).test(path);
    });
    if (!key) return new Response("{}", { status: 404 });
    const res = await routes[key]!(call);
    return new Response(res.body === undefined ? null : JSON.stringify(res.body), {
      status: res.status,
      headers: { "Content-Type": "application/json" },
    });
  };
  return { fetchImpl, calls };
}

export function memoryStorage(initial: Record<string, unknown> = {}): KeyValueStorage {
  const m = new Map(Object.entries(initial));
  return {
    get: async <T,>(k: string) => m.get(k) as T | undefined,
    set: async <T,>(k: string, v: T) => void m.set(k, v),
    del: async (k: string) => void m.delete(k),
  };
}

export function makeServices(fetchImpl: typeof fetch, storage = memoryStorage()): AppServices {
  const platform: PlatformAdapter = {
    kind: "pwa",
    displayMode: () => "browser",
    launchContext: () => ({ utm: { utm_source: "test" } }),
    storage,
    share: async () => "shared",
    openLink: vi.fn(),
  };
  const ctx = { platform: "pwa", displayMode: () => "browser" };
  const baseUrl = "http://app.test/api";
  const session = new SessionManager(ctx, fetchImpl, baseUrl);
  const api = createApiClient(ctx, session, { baseUrl, baseFetch: (r) => fetchImpl(r) });
  const analytics = new Analytics({
    endpoint: `${baseUrl}/v1/analytics/events`,
    appVersion: "test",
    storage,
    headers: () => ({}),
    fetchImpl: (async () => new Response("{}")) as typeof fetch,
  });
  return { platform, api, analytics, session };
}

export function renderApp(services: AppServices, path = "/"): ReturnType<typeof render> {
  return render(
    <ServicesProvider services={services}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </ServicesProvider>,
  );
}

export const me = (overrides: Partial<{ onboarding_completed: boolean }> = {}) => ({
  user: { id: "u1", first_name: "Лидер" },
  onboarding_completed: false,
  active_family_id: "f1",
  families: [{ id: "f1", name: "Семья Лидер", role: "owner" }],
  ...overrides,
});

export const sessionBody = { access_token: "at-1", token_type: "bearer" as const, expires_in: 900, user_id: "u1" };
