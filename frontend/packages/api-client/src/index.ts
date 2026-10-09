import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export type { components, paths } from "./schema";
export type Me = components["schemas"]["Me"];
export type Session = components["schemas"]["Session"];

export interface ClientContext {
  platform: string;
  displayMode(): string;
}

export interface AuthHooks {
  getAccessToken(): string | null;
  /** Obtain a fresh access token (refresh cookie). Resolves false when the user must log in again. */
  refresh(): Promise<boolean>;
}

type RequestFetch = (request: Request) => Promise<Response>;

/** Same-origin API: the reverse proxy (and the Vite dev server) maps /api → backend. */
export const API_BASE = "/api";

const AUTH_PATH = /\/v1\/auth\//;

export function platformHeaders(ctx: ClientContext): Record<string, string> {
  return { "X-Client-Platform": ctx.platform, "X-Display-Mode": ctx.displayMode() };
}

/**
 * fetch with auth: adds the bearer token and, on a 401 outside /v1/auth/*, refreshes once and retries.
 * Exported for non-OpenAPI callers (analytics) and tests.
 */
export function createAuthFetch(ctx: ClientContext, auth?: AuthHooks, baseFetch: RequestFetch = (r) => fetch(r)) {
  return async (input: Request): Promise<Response> => {
    const retry = input.clone();
    const send = (req: Request) => {
      for (const [k, v] of Object.entries(platformHeaders(ctx))) req.headers.set(k, v);
      const token = auth?.getAccessToken();
      if (token) req.headers.set("Authorization", `Bearer ${token}`);
      return baseFetch(req);
    };
    const res = await send(input);
    if (res.status !== 401 || !auth || AUTH_PATH.test(new URL(input.url).pathname)) return res;
    return (await auth.refresh()) ? send(retry) : res;
  };
}

export function createApiClient(
  ctx: ClientContext,
  auth?: AuthHooks,
  { baseUrl = API_BASE, baseFetch }: { baseUrl?: string; baseFetch?: RequestFetch } = {},
) {
  return createClient<paths>({
    baseUrl,
    credentials: "same-origin",
    fetch: createAuthFetch(ctx, auth, baseFetch),
  });
}

export type ApiClient = ReturnType<typeof createApiClient>;
