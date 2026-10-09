import { Analytics } from "@kainem/analytics";
import { API_BASE, createApiClient, platformHeaders } from "@kainem/api-client";
import { App, ServicesProvider, SessionManager } from "@kainem/app-core";
import { createWebAdapter } from "@kainem/platform";
import "@kainem/ui-kit";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { registerSW } from "virtual:pwa-register";

const APP_VERSION = import.meta.env.VITE_APP_VERSION ?? "0.1.0";

const platform = createWebAdapter();
const clientCtx = { platform: platform.kind, displayMode: platform.displayMode };
const session = new SessionManager(clientCtx);
const api = createApiClient(clientCtx, session);
const analytics = new Analytics({
  endpoint: `${API_BASE}/v1/analytics/events`,
  appVersion: APP_VERSION,
  storage: platform.storage,
  headers: () => {
    const token = session.getAccessToken();
    return { ...platformHeaders(clientCtx), ...(token ? { Authorization: `Bearer ${token}` } : {}) };
  },
});
analytics.start();
registerSW({ immediate: true });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ServicesProvider services={{ platform, api, analytics, session }}>
      <App showKit={import.meta.env.DEV} />
    </ServicesProvider>
  </StrictMode>,
);
