import type { ClientContext, Session } from "@kainem/api-client";
import { API_BASE, platformHeaders } from "@kainem/api-client";

export type RefreshResult = "ok" | "unauthenticated" | "offline";

/**
 * Holds the short-lived access token in memory only (never in storage).
 * The refresh token is an httpOnly cookie scoped to /api/v1/auth, invisible to JS.
 */
export class SessionManager {
  private accessToken: string | null = null;
  private refreshing: Promise<RefreshResult> | null = null;
  private listeners = new Set<() => void>();

  constructor(
    private readonly ctx: ClientContext,
    private readonly baseFetch: typeof fetch = (input, init) => fetch(input, init),
    private readonly baseUrl: string = API_BASE,
  ) {}

  getAccessToken = (): string | null => this.accessToken;

  isAuthenticated(): boolean {
    return this.accessToken !== null;
  }

  /** Called with the body of a successful login (handshake exchange or magic link). */
  accept(session: Session): void {
    this.accessToken = session.access_token;
    this.emit();
  }

  /** For the API client: true when a fresh access token is available. */
  refresh = async (): Promise<boolean> => (await this.restore()) === "ok";

  /** Concurrent callers share one refresh request (the server rotates the cookie on each call). */
  restore(): Promise<RefreshResult> {
    this.refreshing ??= this.doRefresh().finally(() => {
      this.refreshing = null;
    });
    return this.refreshing;
  }

  async logout(): Promise<void> {
    try {
      await this.post("/v1/auth/logout");
    } finally {
      this.clear();
    }
  }

  clear(): void {
    this.accessToken = null;
    this.emit();
  }

  onChange(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private async doRefresh(): Promise<RefreshResult> {
    try {
      const res = await this.post("/v1/auth/refresh");
      if (res.ok) {
        this.accept((await res.json()) as Session);
        return "ok";
      }
      if (res.status === 401) {
        this.clear();
        return "unauthenticated";
      }
      return "offline"; // 5xx / proxy errors: treat like a network problem, don't log the user out
    } catch {
      return "offline";
    }
  }

  private post(path: string): Promise<Response> {
    return this.baseFetch(`${this.baseUrl}${path}`, {
      method: "POST",
      credentials: "same-origin",
      headers: platformHeaders(this.ctx),
    });
  }

  private emit(): void {
    this.listeners.forEach((l) => l());
  }
}
