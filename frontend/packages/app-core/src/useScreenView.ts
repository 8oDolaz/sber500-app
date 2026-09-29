import type { ClientEvents } from "@kainem/analytics";
import { useEffect } from "react";
import { useServices } from "./context";

export function useScreenView(screen: ClientEvents["screen_viewed"]["screen"]): void {
  const { analytics } = useServices();
  useEffect(() => {
    analytics.track("screen_viewed", { screen });
  }, [analytics, screen]);
}
