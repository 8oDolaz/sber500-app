import type { ReactNode } from "react";
import { Navigate } from "react-router";
import { homeRouteFor, useAuth } from "./auth/AuthProvider";
import { Splash } from "./screens/Splash";

/** Screens for signed-in users. While the session is being restored the splash shows,
 * so reloading or deep-linking into /help or /home keeps the user on that screen. */
export function RequireSession({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  if (state.status === "authenticated") return children;
  if (state.status === "anonymous") return <Navigate to="/" replace />;
  return <Splash />;
}

/** Screens for guests (welcome); a signed-in user is sent to where they belong. */
export function GuestOnly({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  if (state.status === "anonymous") return children;
  const target = homeRouteFor(state);
  return <Navigate to={target && target !== "/welcome" ? target : "/"} replace />;
}
