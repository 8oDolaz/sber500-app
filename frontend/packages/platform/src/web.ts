import { createStore, del, get, set } from "idb-keyval";
import type { DeviceOs, DisplayMode, InstallApi, KeyValueStorage, LaunchContext, PlatformAdapter } from "./types";

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

export function detectOs(ua: string = navigator.userAgent, maxTouchPoints: number = navigator.maxTouchPoints): DeviceOs {
  if (/android/i.test(ua)) return "android";
  // iPadOS 13+ reports itself as Macintosh; touch support gives it away.
  if (/iphone|ipad|ipod/i.test(ua) || (/macintosh/i.test(ua) && maxTouchPoints > 1)) return "ios";
  if (/windows|macintosh|linux|cros/i.test(ua)) return "desktop";
  return "other";
}

export function detectDisplayMode(): DisplayMode {
  const standalone =
    window.matchMedia?.("(display-mode: standalone)").matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true;
  return standalone ? "standalone" : "browser";
}

export function parseLaunchContext(search: string): LaunchContext {
  const params = new URLSearchParams(search);
  const utm: Record<string, string> = {};
  params.forEach((value, key) => {
    if (key.startsWith("utm_")) utm[key] = value.slice(0, 200);
  });
  const startParam = params.get("start") ?? undefined;
  return { ...(startParam ? { startParam } : {}), ...(Object.keys(utm).length ? { utm } : {}) };
}

function idbStorage(): KeyValueStorage {
  const store = createStore("kainem", "kv");
  return {
    get: (key) => get(key, store),
    set: (key, value) => set(key, value, store),
    del: (key) => del(key, store),
  };
}

function createInstallApi(): InstallApi {
  let deferred: BeforeInstallPromptEvent | null = null;
  let installed = detectDisplayMode() === "standalone";
  const listeners = new Set<() => void>();
  const notify = () => listeners.forEach((l) => l());

  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault(); // we show our own card (screen C) instead of the mini-infobar
    deferred = e as BeforeInstallPromptEvent;
    notify();
  });
  window.addEventListener("appinstalled", () => {
    installed = true;
    deferred = null;
    notify();
  });

  const os = detectOs();
  return {
    os: () => os,
    isInstalled: () => installed,
    canPrompt: () => deferred !== null,
    needsManualInstructions: () => os === "ios" && !installed,
    async prompt() {
      if (!deferred) return "unavailable";
      const event = deferred;
      deferred = null;
      await event.prompt();
      const { outcome } = await event.userChoice;
      notify();
      return outcome;
    },
    onChange(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

export function createWebAdapter(): PlatformAdapter {
  const launch = parseLaunchContext(window.location.search);
  return {
    kind: "pwa",
    displayMode: detectDisplayMode,
    launchContext: () => launch,
    storage: idbStorage(),
    async share(payload) {
      if (navigator.share) {
        try {
          await navigator.share(payload);
          return "shared";
        } catch {
          return "cancelled";
        }
      }
      await navigator.clipboard?.writeText(payload.url ?? payload.text ?? "");
      return "copied";
    },
    openLink(url, opts) {
      // t.me links: same-tab navigation lets iOS/Android hand off to the Telegram app.
      if (opts?.newTab) window.open(url, "_blank", "noopener");
      else window.location.href = url;
    },
    install: createInstallApi(),
  };
}
