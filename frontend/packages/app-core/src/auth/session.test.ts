import { describe, expect, it } from "vitest";
import { createApiClient } from "@kainem/api-client";
import { fakeBackend, sessionBody } from "../test-utils";
import { SessionManager } from "./session";

const ctx = { platform: "pwa", displayMode: () => "browser" };

describe("SessionManager + API client", () => {
  it("refreshes once on 401 and retries the request with the new token", async () => {
    let meCalls = 0;
    const { fetchImpl, calls } = fakeBackend({
      "POST /v1/auth/refresh": () => ({ status: 200, body: { ...sessionBody, access_token: "fresh" } }),
      "GET /v1/me": ({ headers }) => {
        meCalls += 1;
        return headers.get("Authorization") === "Bearer fresh" ? { status: 200, body: {} } : { status: 401 };
      },
    });
    const session = new SessionManager(ctx, fetchImpl as typeof fetch, "http://app.test/api");
    session.accept({ ...sessionBody, access_token: "stale" });
    const api = createApiClient(ctx, session, { baseUrl: "http://app.test/api", baseFetch: (r) => fetchImpl(r) });
    const { response } = await api.GET("/v1/me");
    expect(response.status).toBe(200);
    expect(meCalls).toBe(2);
    expect(calls.filter((c) => c.path === "/v1/auth/refresh")).toHaveLength(1);
  });

  it("shares one refresh between concurrent callers (the cookie rotates)", async () => {
    const { fetchImpl, calls } = fakeBackend({
      "POST /v1/auth/refresh": () => ({ status: 200, body: sessionBody }),
    });
    const session = new SessionManager(ctx, fetchImpl as typeof fetch, "http://app.test/api");
    await Promise.all([session.restore(), session.restore(), session.refresh()]);
    expect(calls).toHaveLength(1);
  });

  it("forgets the token when the refresh cookie is rejected", async () => {
    const { fetchImpl } = fakeBackend({ "POST /v1/auth/refresh": () => ({ status: 401 }) });
    const session = new SessionManager(ctx, fetchImpl as typeof fetch, "http://app.test/api");
    session.accept(sessionBody);
    expect(await session.restore()).toBe("unauthenticated");
    expect(session.isAuthenticated()).toBe(false);
  });
});
