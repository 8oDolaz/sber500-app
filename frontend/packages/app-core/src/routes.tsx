import type { ReactNode } from "react";
import { Navigate } from "react-router";
import { homeRouteFor, useAuth } from "./auth/AuthProvider";

/** Screens for signed-in users; anyone else goes through the splash/gate. */
export function RequireSession({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  if (state.status === "authenticated") return children;
  return <Navigate to="/" replace />;
}

/** Screens for guests (welcome); a signed-in user is sent to where they belong. */
export function GuestOnly({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  if (state.status === "anonymous") return children;
  const target = homeRouteFor(state);
  return <Navigate to={target && target !== "/welcome" ? target : "/"} replace />;
}
