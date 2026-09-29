import type { Me, Session } from "@kainem/api-client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useServices } from "../context";

export type AuthState =
  | { status: "loading" }
  | { status: "offline" }
  | { status: "anonymous" }
  | { status: "authenticated"; me: Me };

interface AuthApi {
  state: AuthState;
  /** After a successful login response: keep the token and load the profile. */
  signedIn(session: Session): Promise<void>;
  signOut(): Promise<void>;
  reload(): Promise<void>;
}

const AuthContext = createContext<AuthApi | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const { api, session } = useServices();
  const [state, setState] = useState<AuthState>({ status: "loading" });

  const loadMe = useCallback(async () => {
    try {
      const { data, response } = await api.GET("/v1/me");
      if (data) setState({ status: "authenticated", me: data });
      else setState({ status: response.status === 401 ? "anonymous" : "offline" });
    } catch {
      setState({ status: "offline" });
    }
  }, [api]);

  const reload = useCallback(async () => {
    setState({ status: "loading" });
    const restored = session.isAuthenticated() ? "ok" : await session.restore();
    if (restored === "ok") await loadMe();
    else setState({ status: restored === "unauthenticated" ? "anonymous" : "offline" });
  }, [session, loadMe]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(
    () =>
      session.onChange(() => {
        if (!session.isAuthenticated()) setState({ status: "anonymous" });
      }),
    [session],
  );

  const value = useMemo<AuthApi>(
    () => ({
      state,
      reload,
      async signedIn(body) {
        session.accept(body);
        await loadMe();
      },
      async signOut() {
        await session.logout();
      },
    }),
    [state, reload, loadMe, session],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthApi {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

/** Where a user in this state belongs (the "session gate" from the plan). */
export function homeRouteFor(state: AuthState): string | null {
  switch (state.status) {
    case "anonymous":
      return "/welcome";
    case "authenticated":
      return state.me.onboarding_completed ? "/home" : "/onboarding";
    default:
      return null;
  }
}
