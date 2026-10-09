import type { Analytics } from "@kainem/analytics";
import type { ApiClient } from "@kainem/api-client";
import type { PlatformAdapter } from "@kainem/platform";
import { createContext, useContext, type ReactNode } from "react";
import type { SessionManager } from "./auth/session";

export interface AppServices {
  platform: PlatformAdapter;
  api: ApiClient;
  analytics: Analytics;
  session: SessionManager;
}

const ServicesContext = createContext<AppServices | null>(null);

export function ServicesProvider({ services, children }: { services: AppServices; children: ReactNode }) {
  return <ServicesContext.Provider value={services}>{children}</ServicesContext.Provider>;
}

export function useServices(): AppServices {
  const services = useContext(ServicesContext);
  if (!services) throw new Error("useServices must be used inside <ServicesProvider>");
  return services;
}
