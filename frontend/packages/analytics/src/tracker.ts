import type { ClientEventName, ClientEvents } from "./events";

interface QueuedEvent {
  id: string;
  name: string;
  occurred_at: string;
  properties: Record<string, unknown>;
}

export interface AnalyticsStorage {
  get<T>(key: string): Promise<T | undefined>;
  set<T>(key: string, value: T): Promise<void>;
}

export interface AnalyticsOptions {
  endpoint: string;
  appVersion: string;
  storage: AnalyticsStorage;
  headers(): Record<string, string>;
  fetchImpl?: typeof fetch;
  flushIntervalMs?: number;
  maxBatch?: number;
  maxQueue?: number;
}

const ANON_KEY = "analytics.anonymous_id";

/**
 * Batched, failure-tolerant tracking (ARCHITECTURE §9.1: analytics never breaks the product).
 * `anonymousId` is stable per install; it joins pre-login funnel steps to the account (plan §Analytics).
 */
export class Analytics {
  private queue: QueuedEvent[] = [];
  private anonymousId: Promise<string>;
  private readonly sessionId = crypto.randomUUID();
  private timer: ReturnType<typeof setInterval> | undefined;
  private flushing: Promise<void> | null = null;
  private readonly fetchImpl: typeof fetch;

  constructor(private readonly opts: AnalyticsOptions) {
    this.fetchImpl = opts.fetchImpl ?? fetch.bind(globalThis);
    this.anonymousId = this.loadAnonymousId();
  }

  start(): void {
    this.timer = setInterval(() => void this.flush(), this.opts.flushIntervalMs ?? 5000);
    document.addEventListener("visibilitychange", this.onHide);
    window.addEventListener("pagehide", this.onHide);
  }

  stop(): void {
    clearInterval(this.timer);
    document.removeEventListener("visibilitychange", this.onHide);
    window.removeEventListener("pagehide", this.onHide);
  }

  getAnonymousId(): Promise<string> {
    return this.anonymousId;
  }

  track<N extends ClientEventName>(name: N, properties: ClientEvents[N]): void {
    this.queue.push({
      id: crypto.randomUUID(),
      name,
      occurred_at: new Date().toISOString(),
      properties: properties as Record<string, unknown>,
    });
    const maxQueue = this.opts.maxQueue ?? 500;
    if (this.queue.length > maxQueue) this.queue.splice(0, this.queue.length - maxQueue);
    if (this.queue.length >= (this.opts.maxBatch ?? 20)) void this.flush();
  }

  flush(keepalive = false): Promise<void> {
    if (this.flushing) return this.flushing;
    this.flushing = this.send(keepalive).finally(() => {
      this.flushing = null;
    });
    return this.flushing;
  }

  private onHide = () => {
    if (document.visibilityState === "hidden") void this.flush(true);
  };

  private async send(keepalive: boolean): Promise<void> {
    const batch = this.queue.splice(0, this.opts.maxBatch ?? 20);
    if (batch.length === 0) return;
    try {
      const res = await this.fetchImpl(this.opts.endpoint, {
        method: "POST",
        keepalive,
        headers: { "Content-Type": "application/json", ...this.opts.headers() },
        body: JSON.stringify({
          anonymous_id: await this.anonymousId,
          session_id: this.sessionId,
          app_version: this.opts.appVersion,
          events: batch,
        }),
      });
      // 4xx other than 401/429 means the batch is invalid: drop it (server counts rejects).
      // 401: the access token expired; it is refreshed by the next API call, so retry later.
      if (res.status === 401 || res.status === 429 || res.status >= 500) this.queue.unshift(...batch);
    } catch {
      this.queue.unshift(...batch); // offline: keep for the next flush (ids make retries idempotent)
    }
  }

  private async loadAnonymousId(): Promise<string> {
    try {
      const existing = await this.opts.storage.get<string>(ANON_KEY);
      if (existing) return existing;
      const id = crypto.randomUUID();
      await this.opts.storage.set(ANON_KEY, id);
      return id;
    } catch {
      return crypto.randomUUID();
    }
  }
}
