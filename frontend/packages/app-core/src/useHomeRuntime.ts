import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { SectionState } from "@kainem/ui-kit";
import { useServices } from "./context";

function subscribeOnline(listener: () => void) {
  window.addEventListener("online", listener); window.addEventListener("offline", listener);
  return () => { window.removeEventListener("online", listener); window.removeEventListener("offline", listener); };
}
export function useOnline() { return useSyncExternalStore(subscribeOnline, () => navigator.onLine, () => true); }
export function useFamilyClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const tick = () => setNow(new Date());
    const interval = setInterval(tick, 30_000);
    document.addEventListener("visibilitychange", tick); window.addEventListener("pageshow", tick);
    return () => { clearInterval(interval); document.removeEventListener("visibilitychange", tick); window.removeEventListener("pageshow", tick); };
  }, []);
  return now;
}
export function sectionState(query: { data: unknown; isPending: boolean; isError: boolean; isFetching: boolean }, count: number, online: boolean, allDone = false): SectionState {
  const cached = query.data !== undefined;
  if (!online) return cached ? "Offline" : "OfflineEmpty";
  if (!cached) return query.isError ? "Error" : "Loading";
  if (query.isError) return "Stale";
  if (query.isFetching) return "Refreshing";
  return count ? "Content" : allDone ? "AllDone" : "Empty";
}
export function useBotAction(link: string | null | undefined, familyId: string) {
  const { platform } = useServices();
  const [state, setState] = useState<{ origin: "header" | "invite"; status: "Opening" | "Error" } | null>(null);
  const active = useRef(false);
  const generation = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const available = (() => { try { const u = new URL(link || ""); return u.protocol === "https:" && ["t.me", "telegram.me"].includes(u.hostname); } catch { return false; } })();
  const reset = useCallback(() => { generation.current++; active.current = false; clearTimeout(timer.current); setState(null); }, []);
  useEffect(() => { reset(); }, [familyId, link, reset]);
  useEffect(() => {
    const returned = () => { if (document.visibilityState === "visible" && active.current) reset(); };
    window.addEventListener("focus", returned); window.addEventListener("pageshow", returned); document.addEventListener("visibilitychange", returned);
    return () => { generation.current++; clearTimeout(timer.current); window.removeEventListener("focus", returned); window.removeEventListener("pageshow", returned); document.removeEventListener("visibilitychange", returned); };
  }, [reset]);
  return { available, state, async open(origin: "header" | "invite") {
    if (!available || active.current) return;
    const request = ++generation.current;
    active.current = true; setState({ origin, status: "Opening" });
    try {
      const destination = new URL(link!);
      if (origin === "invite") destination.searchParams.set("start", "share_invite");
      await platform.openLink(origin === "invite" ? destination.toString() : link!);
      // The browser cannot confirm the Telegram handoff. Only release the busy state.
      if (generation.current === request) timer.current = setTimeout(reset, 1500);
    } catch { if (generation.current === request) { active.current = false; setState({ origin, status: "Error" }); } }
  } };
}
