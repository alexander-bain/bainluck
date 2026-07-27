import { defineConfig, devices } from "@playwright/test";

/**
 * L2-189 Item 2 — repeatable Discover latency trace harness.
 *
 * Isolated from the main frontend project (own package.json/tsconfig) so it
 * never enters Vercel/CI installs or `next build`. Run:
 *
 *   cd frontend/e2e
 *   npm install
 *   npx playwright install chromium
 *   TRACE_BASE_URL=https://www.bainluck.com npm run trace:discover
 *
 * Two projects give the desktop + 375px comparison the queue asks for.
 */
export default defineConfig({
  testDir: ".",
  timeout: 60_000,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.TRACE_BASE_URL || "https://www.bainluck.com",
    trace: "on",
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } },
    },
    {
      name: "mobile-375",
      use: { ...devices["Pixel 5"], viewport: { width: 375, height: 812 } },
    },
  ],
});
