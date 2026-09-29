import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end: real browser → Vite dev server (/api proxy) → FastAPI → Postgres/Redis.
 * Needs `make infra-up`. The Telegram side is simulated with the test-only bind endpoint.
 */
const API_PORT = 8010;
const WEB_PORT = 5180;

export default defineConfig({
  testDir: "e2e",
  timeout: 30_000,
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    ...devices["iPhone 13"],
    browserName: "chromium",
  },
  webServer: [
    {
      command: `sh -c 'PATH=$HOME/.local/bin:$PATH; uv run alembic upgrade head && uv run uvicorn planner.entrypoints.api.app:create_app --factory --port ${API_PORT}'`,
      cwd: "../backend",
      url: `http://127.0.0.1:${API_PORT}/healthz`,
      env: { ENV: "local", ENABLE_TEST_ENDPOINTS: "true", LLM_PROVIDER: "fake", LOG_JSON: "false", BOT_USERNAME: "kainem_e2e_bot" },
      reuseExistingServer: false,
    },
    {
      command: `pnpm --filter @kainem/pwa exec vite --port ${WEB_PORT} --strictPort`,
      url: `http://localhost:${WEB_PORT}`,
      env: { KAINEM_API: `http://127.0.0.1:${API_PORT}` },
      reuseExistingServer: false,
    },
  ],
});
