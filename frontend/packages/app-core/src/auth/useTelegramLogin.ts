import type { Session } from "@kainem/api-client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useServices } from "../context";
import { challengeFor, createVerifier } from "./pkce";

/**
 * PWA ↔ bot login (ADR 0002):
 * 1. create a handshake (PKCE challenge) and open t.me/<bot>?start=login_<nonce>;
 * 2. poll the exchange endpoint until the user presses Start in the bot.
 *
 * The pending handshake is persisted, so polling resumes if the page reloads
 * while the user is in Telegram (common on mobile; the only way on iOS standalone PWAs).
 */

const PENDING_KEY = "auth.pending_handshake";

interface PendingHandshake {
  nonce: string;
  verifier: string;
  deepLink: string;
  expiresAt: string;
  pollIntervalMs: number;
}

export type LoginStatus =
  | { kind: "idle" }
  | { kind: "starting" }
  | { kind: "waiting"; deepLink: string }
  | { kind: "error"; reason: "expired" | "failed" | "offline" };

export function useTelegramLogin(onSession: (session: Session) => Promise<void>) {
  const { api, platform, analytics } = useServices();
  const [status, setStatus] = useState<LoginStatus>({ kind: "idle" });
  const pending = useRef<PendingHandshake | null>(null);
  const polling = useRef(false);
  const onSessionRef = useRef(onSession);
  onSessionRef.current = onSession;

  const clearPending = useCallback(async () => {
    pending.current = null;
    await platform.storage.del(PENDING_KEY).catch(() => undefined);
  }, [platform]);

  /** One exchange attempt. Returns true when polling should stop. */
  const pollOnce = useCallback(async (): Promise<boolean> => {
    const hs = pending.current;
    if (!hs) return true;
    if (Date.now() >= Date.parse(hs.expiresAt)) {
      await clearPending();
      setStatus({ kind: "error", reason: "expired" });
      return true;
    }
    try {
      const { data, response } = await api.POST("/v1/auth/tg-handshake/{nonce}/exchange", {
        params: { path: { nonce: hs.nonce } },
        body: { verifier: hs.verifier },
      });
      if (response.status === 202) return false;
      await clearPending();
      if (data && "access_token" in data) {
        setStatus({ kind: "idle" });
        await onSessionRef.current(data);
      } else {
        setStatus({ kind: "error", reason: response.status === 410 ? "expired" : "failed" });
      }
      return true;
    } catch {
      return false; // offline for a moment: keep polling
    }
  }, [api, clearPending]);

  const pollLoop = useCallback(async () => {
    if (polling.current) return;
    polling.current = true;
    try {
      while (pending.current && document.visibilityState === "visible") {
        if (await pollOnce()) return;
        await new Promise((r) => setTimeout(r, pending.current?.pollIntervalMs ?? 2000));
      }
    } finally {
      polling.current = false;
    }
  }, [pollOnce]);

  // Resume a handshake started before a reload; poll again whenever the app comes back to the foreground.
  useEffect(() => {
    let cancelled = false;
    void platform.storage
      .get<PendingHandshake>(PENDING_KEY)
      .catch(() => undefined)
      .then((saved) => {
        if (cancelled || !saved || Date.now() >= Date.parse(saved.expiresAt)) return;
        pending.current = saved;
        setStatus({ kind: "waiting", deepLink: saved.deepLink });
        void pollLoop();
      });
    const onVisible = () => {
      if (document.visibilityState === "visible" && pending.current) void pollLoop();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [platform, pollLoop]);

  const openTelegram = useCallback(
    (deepLink: string) => platform.openLink(deepLink, { newTab: platform.install?.os() === "desktop" }),
    [platform],
  );

  const start = useCallback(async () => {
    analytics.track("register_clicked", {});
    setStatus({ kind: "starting" });
    try {
      const verifier = createVerifier();
      const { data } = await api.POST("/v1/auth/tg-handshake", {
        body: {
          challenge: await challengeFor(verifier),
          anonymous_id: await analytics.getAnonymousId(),
          utm: platform.launchContext().utm ?? {},
        },
      });
      if (!data) {
        setStatus({ kind: "error", reason: "failed" });
        return;
      }
      pending.current = {
        nonce: data.nonce,
        verifier,
        deepLink: data.deep_link,
        expiresAt: data.expires_at,
        pollIntervalMs: data.poll_interval_ms,
      };
      await platform.storage.set(PENDING_KEY, pending.current).catch(() => undefined);
      setStatus({ kind: "waiting", deepLink: data.deep_link });
      openTelegram(data.deep_link);
      void pollLoop();
    } catch {
      setStatus({ kind: "error", reason: "offline" });
    }
  }, [analytics, api, platform, openTelegram, pollLoop]);

  const cancel = useCallback(async () => {
    await clearPending();
    setStatus({ kind: "idle" });
  }, [clearPending]);

  return { status, start, cancel, openTelegram };
}
