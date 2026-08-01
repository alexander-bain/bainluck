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
    // L2-229: no single action may consume the whole test budget.
    //
    // Playwright's default `actionTimeout` is 0 — meaning UNBOUNDED, capped
    // only by the 90s test timeout above. That is a false-green hazard in an
    // evidence rail, and the calibration pack's first real run proved it: the
    // spec read `page.locator("main").innerText()`, `/calibration` renders no
    // `<main>` at all, and that one auto-waiting call sat there until the test
    // died. The journey never reached `journey.finish()`, so no assertion was
    // graded and the terminal screenshot fired against an already-torn-down
    // context — producing `infra_error` with an EMPTY artifacts array.
    //
    // An evidence-free red is the exact shape this rail exists to prevent: it
    // is indistinguishable from a rail that never ran, and it tells you
    // nothing about the page. Bounding actions means a hung or missing element
    // fails as a NAMED assertion with a screenshot attached, while the journey
    // still has budget left to record and photograph what it saw.
    //
    // 10s is far above any healthy interaction and far below the 90s budget,
    // so several bounded failures can stack and the journey still finishes.
    actionTimeout: 10_000,
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
