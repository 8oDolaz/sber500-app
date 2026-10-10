import { defineConfig } from "@playwright/test";

/** Built assets and actual service worker, not the development server. Run pnpm build first. */
export default defineConfig({
  testDir: "pwa-tests",
  outputDir: "test-results/pwa",
  timeout: 30_000,
  use: { baseURL: "http://127.0.0.1:5194", browserName: "chromium", viewport: { width: 402, height: 874 } },
  webServer: {
    command: "pnpm --filter @kainem/pwa exec vite preview --host 127.0.0.1 --port 5194 --strictPort",
    url: "http://127.0.0.1:5194",
    reuseExistingServer: false,
  },
});
