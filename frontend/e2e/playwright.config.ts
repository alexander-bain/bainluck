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
 *   AUDIT_CHECKOUT_SHA=$(git rev-parse HEAD) \
 *   AUDIT_CHECKOUT_ANCESTRY=requested-is-ancestor-of-checkout \
 *   TRACE_BASE_URL=https://www.bainluck.com npm run smoke
 *
 * `AUDIT_CHECKOUT_SHA` is required (L2-223): the manifest binds the commit
 * that GRADED the run alongside the commit it audited, and a manifest missing
 * it is rejected. Set the ancestry only when it is actually true — the point
 * of the field is that nobody has to take the relationship on trust.
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
    // Trace, video and HAR are ALL off in phase 1 (L2-223).
    //
    // L2-221 shipped `trace: "on"` directly beneath a comment explaining why
    // an authenticated trace is dangerous — the reasoning was right and the
    // setting contradicted it. A Playwright trace is a zip of the whole
    // session: request and response bodies, storage, and every cookie and
    // authorization header the page sent. The manifest's redaction pass
    // scrubs JSON FIELDS; it cannot touch those bytes, so calling the run
    // "redacted" while uploading a raw trace for 90 days was not true.
    //
    // Turning this back on requires a reviewed containment policy (short
    // retention, restricted download, or a scrubbing step that operates on the
    // trace zip itself) — not just an edit here. The manifest validator
    // rejects a declared trace artifact, and the workflow no longer uploads
    // `test-results/`, so this is one of three locks rather than the only one.
    trace: "off",
    screenshot: "only-on-failure",
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
