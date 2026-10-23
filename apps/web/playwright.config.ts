import { defineConfig, devices } from "@playwright/test";

// E2E for the 2-minute demo story, route smoke tests and axe checks.
// Locally: `docker compose up -d db`, then `pnpm --filter web exec playwright test`.
// Servers are reused when already running on these ports (3310 is chosen to avoid other dev apps).
const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 3310);
const API_PORT = Number(process.env.E2E_API_PORT ?? 8000);
const baseURL = process.env.E2E_BASE_URL ?? `http://localhost:${WEB_PORT}`;
const apiURL = process.env.E2E_API_URL ?? `http://localhost:${API_PORT}`;
const databaseURL = process.env.DATABASE_URL ?? "postgres://igs:igs@localhost:5433/igs";
const isCI = !!process.env.CI;
// External servers (e.g. a deployed preview): skip booting anything locally.
const external = !!process.env.E2E_BASE_URL;

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./e2e/.results",
  globalSetup: "./e2e/global-setup.ts",
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 1 : 0,
  workers: isCI ? 2 : undefined,
  reporter: isCI
    ? [["github"], ["html", { outputFolder: "./e2e/.report", open: "never" }]]
    : [["list"], ["html", { outputFolder: "./e2e/.report", open: "never" }]],
  expect: { timeout: 10_000 },
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    locale: "es-AR",
    timezoneId: "America/Argentina/Buenos_Aires",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    {
      name: "mobile",
      use: { ...devices["Pixel 7"] },
      // The demo story and a11y run on desktop; mobile gets the route smoke tests.
      testMatch: /smoke\.spec\.ts/,
    },
  ],
  webServer: external
    ? undefined
    : [
        {
          name: "api",
          command: `uv run uvicorn igs_core.app:create_app --factory --port ${API_PORT}`,
          cwd: "../..",
          url: `${apiURL}/healthz`,
          reuseExistingServer: !isCI,
          timeout: 120_000,
          env: {
            DATABASE_URL: databaseURL,
            IGS_DATABASE_URL: databaseURL,
            // Never spend money from e2e: the copilot/ask paths are mocked in the browser.
            OPENAI_API_KEY: "",
          },
        },
        {
          name: "web",
          command: isCI ? `pnpm start --port ${WEB_PORT}` : `pnpm dev --port ${WEB_PORT}`,
          url: baseURL,
          reuseExistingServer: !isCI,
          timeout: 180_000,
          env: { API_URL: apiURL, NEXT_PUBLIC_API_URL: apiURL },
        },
      ],
});
