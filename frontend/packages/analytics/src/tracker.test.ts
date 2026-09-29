import { describe, expect, it, vi } from "vitest";
import { Analytics } from "./tracker";

function memoryStorage() {
  const m = new Map<string, unknown>();
  return {
    get: async <T,>(k: string) => m.get(k) as T | undefined,
    set: async <T,>(k: string, v: T) => void m.set(k, v),
  };
}

function setup(responses: Array<number | Error>) {
  const bodies: any[] = [];
  const fetchImpl = vi.fn(async (_url: string, init: RequestInit) => {
    bodies.push(JSON.parse(init.body as string));
    const next = responses.shift() ?? 200;
    if (next instanceof Error) throw next;
    return new Response("{}", { status: next });
  }) as unknown as typeof fetch;
  const storage = memoryStorage();
  const a = new Analytics({
    endpoint: "/api/v1/analytics/events",
    appVersion: "0.1.0",
    storage,
    headers: () => ({ "X-Client-Platform": "pwa" }),
    fetchImpl,
  });
  return { a, bodies, storage, fetchImpl };
}

describe("Analytics", () => {
  it("sends batched events with a stable anonymous id", async () => {
    const { a, bodies, storage } = setup([200]);
    a.track("screen_viewed", { screen: "welcome" });
    a.track("register_clicked", {});
    await a.flush();
    expect(bodies).toHaveLength(1);
    expect(bodies[0].events.map((e: any) => e.name)).toEqual(["screen_viewed", "register_clicked"]);
    expect(bodies[0].anonymous_id).toBe(await storage.get("analytics.anonymous_id"));
  });

  it("re-queues on network errors and 5xx, keeping event ids for dedupe", async () => {
    const { a, bodies } = setup([new Error("offline"), 503, 200]);
    a.track("register_clicked", {});
    await a.flush();
    await a.flush();
    await a.flush();
    expect(bodies).toHaveLength(3);
    expect(new Set(bodies.map((b) => b.events[0].id)).size).toBe(1);
  });

  it("drops batches the server rejects as invalid", async () => {
    const { a, fetchImpl } = setup([422]);
    a.track("register_clicked", {});
    await a.flush();
    await a.flush();
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("reuses the persisted anonymous id across instances", async () => {
    const first = setup([]);
    const id = await first.a.getAnonymousId();
    const second = new Analytics({
      endpoint: "/x",
      appVersion: "0",
      storage: first.storage,
      headers: () => ({}),
      fetchImpl: first.fetchImpl,
    });
    expect(await second.getAnonymousId()).toBe(id);
  });
});
