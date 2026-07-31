import { defineConfig, devices } from "@playwright/test";

/**
 * L2-221 — browser-audit rail configuration.
 *
 * Isolated from the main frontend project (own package.json/tsconfig, and the
 * main tsconfig excludes `e2e`) so it never enters Vercel/CI installs or
 * `next build`. GitHub Actions is orchestration only — every command below
 * runs identically on a laptop:
 *
 *   cd frontend/e2e
 *   npm run contract                       # node --test; no browser, no install
 *   npm ci
 *   npx playwright install --with-deps chromium
 *   AUDIT_REQUESTED_SHA=<40-hex> \
 *   AUDIT_OBSERVED_FRONTEND_SHA=<40-hex> \
 *   TRACE_BASE_URL=https://www.bainluck.com npm run smoke
 *
 * The contract fixtures deliberately do NOT run here — they run on
 * `node --test` (`npm run contract`), with no Playwright and no browser
 * download. A gate that only runs once a package install succeeds is a gate
 * that gets skipped on the day it matters, so the false-green fixtures are
 * kept dependency-free. This config owns only the real browser journeys:
 * `desktop` and `mobile`.
 */
export default defineConfig({
  testDir: ".",
  timeout: 90_000,
  // Retries hide flakiness in an evidence rail. The manifest records the
  // attempt number, so if retries are ever enabled a retry can still never be
  // mistaken for a first-pass green.
  retries: 0,
  forbidOnly: true,
  reporter: [
    ["list"],
    ["html", { open: "never", outputFolder: process.env.AUDIT_REPORT_DIR || "playwright-report" }],
    ["./reporters/auditReporter.ts"],
  ],
  outputDir: process.env.AUDIT_RESULTS_DIR || "test-results",
  use: {
    baseURL: process.env.TRACE_BASE_URL || "https://www.bainluck.com",
    trace: "on",
    screenshot: "only-on-failure",
    // Video and HAR stay OFF by default: an authenticated trace can retain
    // cookies and tokens, and phase 1 publishes artifacts unconditionally.
    video: "off",
  },
  projects: [
    {
      name: "desktop",
      testDir: "./specs",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    {
      name: "mobile",
      testDir: "./specs",
      use: { ...devices["Pixel 5"], viewport: { width: 390, height: 844 } },
    },
  ],
});
