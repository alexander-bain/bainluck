// L2-238 Item 1 — rendered proof of the three Discover terminal states, at
// mobile and desktop widths, through the real browser rail.
//
// These states are states of the SERVER, so no screenshot of production can
// show them on demand — `/api/feed` serves whatever it happens to be serving.
// The feed request is therefore intercepted and answered with the EXACT bodies
// backend/app/routes/feed.py returns, and the page under test is the real
// production build (`next start`), not a story or a mock component.
//
//   unavailable-with-last-good     — cards render, then a revalidation comes
//                                    back typed-unavailable. Cards must stay.
//   unavailable-without-last-good  — the first load is unavailable. Must show
//                                    the retry state, never "all caught up".
//   genuine-exhaustion             — a complete, empty build. Must still show
//                                    the end-of-feed card.
//   normal                         — the adjacent regression journey.
//
// Usage: node scripts/l2238-render-states.js <baseURL> <outDir>

const { chromium, devices } = require("@playwright/test");
const fs = require("fs");
const path = require("path");

const BASE = process.argv[2] || "http://localhost:3199";
const OUT = process.argv[3] || "/tmp/l2-238-proof/web";

const CARD = {
  type: "futures",
  score: 90,
  data: {
    id: 424242,
    name: "Will the Fed cut rates in September?",
    llm_sport_category: "economics",
    sport: null,
    sport_name: null,
    source: "kalshi",
    source_count: 2,
    market_tier: 1,
    status: "open",
    resolution_date: "2030-09-30T00:00:00Z",
    outcome_count: 2,
    canonical_market_key: null,
    top_outcomes: [
      { id: 1, name: "Yes", probability: 0.62, rank: 1, movement: 0.04 },
      { id: 2, name: "No", probability: 0.38, rank: 2, movement: -0.04 },
    ],
  },
};

function cards(n) {
  return Array.from({ length: n }, (_, i) => ({
    ...CARD,
    data: {
      ...CARD.data,
      id: 424242 + i,
      name: `Will the Fed cut rates in September? (${i + 1})`,
    },
  }));
}

const POPULATED = (n) => ({
  items: cards(n),
  total: n,
  limit: 20,
  offset: 0,
  has_more: false,
  cache: { status: "hit", ttl_seconds: 60, stale_ttl_seconds: 900 },
});

/** Byte-for-byte the waiter-unavailable body from routes/feed.py. */
const UNAVAILABLE = {
  items: [],
  total: 0,
  limit: 20,
  offset: 0,
  has_more: false,
  cache: {
    status: "unavailable",
    ttl_seconds: 60,
    stale_ttl_seconds: 900,
    reason: "leader_unavailable",
  },
};

const EXHAUSTED = {
  items: [],
  total: 0,
  limit: 20,
  offset: 0,
  has_more: false,
  cache: { status: "hit", ttl_seconds: 60, stale_ttl_seconds: 900 },
};

const VIEWPORTS = [
  { name: "mobile", viewport: { width: 390, height: 844 }, ...devices["iPhone 13"] },
  { name: "desktop", viewport: { width: 1440, height: 900 } },
];

/** Feed bodies served in order; the last repeats. */
const STATES = {
  normal: [POPULATED(12)],
  "genuine-exhaustion": [EXHAUSTED],
  "unavailable-without-last-good": [UNAVAILABLE],
  "unavailable-with-last-good": [POPULATED(12), UNAVAILABLE],
};

async function run() {
  fs.mkdirSync(OUT, { recursive: true });
  // Playwright's bundled Chromium cannot start here: launching a child process
  // fails at `bootstrap_check_in ... Permission denied (1100)`, the Mach-port
  // rendezvous a restricted launchd session denies. `--single-process` gets past
  // the launch and then loses the page target. The installed Google Chrome has a
  // signed, registered bootstrap identity and does start, so prefer it and fall
  // back to the bundled build wherever that works (CI runners, ordinary shells).
  let browser;
  const args = ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"];
  try {
    browser = await chromium.launch({ channel: "chrome", args });
  } catch (e) {
    console.error("system chrome unavailable, falling back to bundled chromium:", e.message);
    browser = await chromium.launch({ args });
  }
  const results = [];

  for (const [state, bodies] of Object.entries(STATES)) {
    for (const vp of VIEWPORTS) {
      const context = await browser.newContext({
        viewport: vp.viewport,
        userAgent: vp.userAgent,
        deviceScaleFactor: vp.deviceScaleFactor || 2,
        isMobile: vp.isMobile || false,
        hasTouch: vp.hasTouch || false,
      });
      const page = await context.newPage();
      const consoleErrors = [];
      const requestFailures = [];
      page.on("console", (m) => {
        if (m.type() === "error") consoleErrors.push(m.text());
      });
      page.on("requestfailed", (r) => {
        // Third-party analytics/pixel blocks are not this page's failures.
        if (/bainluck|localhost/.test(r.url())) {
          requestFailures.push(`${r.url()} ${r.failure()?.errorText}`);
        }
      });

      let feedCalls = 0;
      await page.route("**/api/feed*", async (route) => {
        const body = bodies[Math.min(feedCalls, bodies.length - 1)];
        feedCalls += 1;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          headers: { "X-Feed-Cache": body.cache?.status || "hit" },
          body: JSON.stringify(body),
        });
      });
      // Keep every other API call off the network so the render is deterministic.
      await page.route("**/api/discover/resolutions*", (r) =>
        route_json(r, { resolutions: [] }),
      );

      await page.goto(`${BASE}/discover`, { waitUntil: "domcontentloaded" });
      await page
        .locator('[data-testid="discover-card"], [data-testid="discover-empty-state"], [data-testid="discover-feed-unavailable"], [data-testid="discover-feed-error"]')
        .first()
        .waitFor({ state: "visible", timeout: 30_000 })
        .catch(() => null);

      if (state === "unavailable-with-last-good") {
        // Force the background revalidation that returns unavailable, exactly
        // as SWR's refreshInterval would, and prove the cards survive it.
        await page.evaluate(() => window.dispatchEvent(new Event("focus")));
        await page.evaluate(() =>
          fetch("/api/feed?limit=20&offset=0&event_pct=0.15").catch(() => {}),
        );
        // SWR's own 120s interval is too slow for a render pass; re-mounting the
        // route re-runs the SWR fetcher against the now-unavailable stub while
        // the client keeps the generation it already rendered.
        await page.waitForTimeout(500);
        await page.reload({ waitUntil: "domcontentloaded" });
        await page.waitForTimeout(2500);
      }

      await page.waitForTimeout(1200);

      const seen = {
        cards: await page.locator('[data-testid="discover-card"]').count(),
        unavailable: await page
          .locator('[data-testid="discover-feed-unavailable"]')
          .first()
          .isVisible()
          .catch(() => false),
        endOfFeed: await page
          .locator('[data-testid="discover-empty-state"]')
          .first()
          .isVisible()
          .catch(() => false),
        error: await page
          .locator('[data-testid="discover-feed-error"]')
          .first()
          .isVisible()
          .catch(() => false),
        skeleton: await page
          .locator('[data-testid="discover-skeleton"]')
          .first()
          .isVisible()
          .catch(() => false),
      };

      // Accessibility: the retry control's accessible name and its alert role.
      const retry = page.getByRole("button", { name: "Try again to load the feed" });
      const retryVisible = await retry.first().isVisible().catch(() => false);
      const alertText = seen.unavailable
        ? await page.locator('[role="alert"]').first().innerText().catch(() => null)
        : null;

      const file = path.join(OUT, `${state}-${vp.name}.png`);
      await page.screenshot({ path: file, fullPage: false });

      results.push({
        state,
        viewport: vp.name,
        size: vp.viewport,
        feedCalls,
        ...seen,
        retryAccessibleNameVisible: retryVisible,
        alertText,
        consoleErrors,
        requestFailures,
        screenshot: file,
      });
      await context.close();
    }
  }

  await browser.close();
  const manifest = path.join(OUT, "manifest.json");
  fs.writeFileSync(manifest, JSON.stringify({ base: BASE, results }, null, 2));
  console.log(JSON.stringify(results, null, 2));
}

function route_json(route, body) {
  return route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

run().catch((e) => {
  console.error(e);
  process.exit(1);
});
