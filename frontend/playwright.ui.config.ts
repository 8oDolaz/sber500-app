import { defineConfig } from "@playwright/test";

/** Browser UI contracts with controlled API replies; the existing e2e suite uses the real backend. */
export default defineConfig({
  testDir: "ui-tests",
  outputDir: "test-results/home-ui",
  timeout: 30_000,
  workers: 2,
  use: {
    baseURL: "http://127.0.0.1:5193",
    viewport: { width: 402, height: 874 },
    serviceWorkers: "block",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { browserName: "chromium" } },
    { name: "webkit", use: { browserName: "webkit" } },
  ],
  webServer: {
    command: "pnpm --filter @kainem/pwa exec vite --host 127.0.0.1 --port 5193 --strictPort",
    url: "http://127.0.0.1:5193",
    reuseExistingServer: false,
  },
});
