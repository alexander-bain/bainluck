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
// L2-239 Item 1 — this script is now SELF-GRADING.
//
// L2-238 left it printing observations for a human to read, and then no human
// could run it: Chromium cannot spawn a renderer in the authoring sandbox
// (`bootstrap_check_in ... Permission denied (1100)`), so the three states were
// closed on source-level proof. An unrunnable script that reports numbers is
// one `looks right to me` away from certifying a broken render, which is the
// same false green the rest of this rail exists to prevent. So every state now
// carries EXPECTATIONS, each viewport produces an explicit pass/fail, and the
// process exits non-zero if any of them misses. A failed render routes the
// defect; it does not get converted into a source-level pass.
//
// Usage: node scripts/l2238-render-states.js <baseURL> <outDir>

const { chromium, devices } = require("@playwright/test");
const crypto = require("crypto");
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

/**
 * Distinct questions, deliberately.
 *
 * The first run of this script (30836513085) served twelve variants of "Will the
 * Fed cut rates in September? (n)" and Discover rendered ONE card reading
 * "WILL THE FED — 12 markets / Show 11 more". That is the story-grouping working
 * exactly as designed, but it meant a fixture claiming to prove "twelve cards
 * survived" was really proving one did. Cards must differ in subject or the
 * count being asserted is not the count being rendered.
 */
const SUBJECTS = [
  "Will the Fed cut rates in September?",
  "Who wins the Best Picture Oscar?",
  "Will there be a government shutdown this year?",
  "Will SpaceX launch Starship again this quarter?",
  "Will the UK hold a general election before July?",
  "Who wins the Premier League?",
  "Will inflation come in under 3% this month?",
  "Will a hurricane make landfall in Florida this season?",
  "Will OpenAI release a new frontier model this quarter?",
  "Who wins the Nobel Peace Prize?",
  "Will Bitcoin close above its January high?",
  "Will the Supreme Court hear the tariff case?",
];

function cards(n) {
  return Array.from({ length: n }, (_, i) => ({
    ...CARD,
    data: {
      ...CARD.data,
      id: 424242 + i,
      name: SUBJECTS[i % SUBJECTS.length] + (i >= SUBJECTS.length ? ` (${i + 1})` : ""),
    },
  }));
}

const POPULATED = (n, hasMore = false) => ({
  items: cards(n),
  total: n,
  limit: 20,
  offset: 0,
  has_more: hasMore,
  cache: { status: "hit", ttl_seconds: 60, stale_ttl_seconds: 900 },
});

/**
 * Routes this fixture invented. Next prefetches every card's detail route, and
 * a card id that exists only in a stubbed feed body has no page behind it — so
 * `/futures/424242?_rsc=…` aborts or 404s. That is the fixture's own shadow, not
 * a product defect, and it is recorded in the packet rather than dropped.
 *
 * Deliberately narrow: the deploy-smoke rail saw the same ERR_ABORTED shape on a
 * REAL id (`/futures/171`), and nothing here may hide that.
 */
const SYNTHETIC_DETAIL_ROUTE = /\/futures\/4242\d+(\?|$)/;

/** Chromium's own line for any 4xx subresource. Says nothing the network channel does not. */
const CHROMIUM_RESOURCE_404 = "Failed to load resource: the server responded with a status of 404";

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

/**
 * Feed bodies served in order; the last repeats.
 *
 * `trigger` is how the SECOND body is reached, and getting it right is the whole
 * difference between proving the fix and proving nothing. L2-238's script
 * reloaded the page — but a reload is a COLD load, and the web client has no
 * on-disk last-good the way native does, so the "with-last-good" state rendered
 * as the cold unavailable state and the assertion that cards survive could never
 * have passed. Run 30836513085 is that mistake, measured.
 *
 * The two real in-session paths, both of which `page.tsx` handles separately:
 *
 *   `swr-refresh`  — the 120s `refreshInterval` revalidation of page 1. This is
 *                    the path L2-238 fixed: an unavailable body used to walk the
 *                    success path and replace the rendered cards with `[]`.
 *                    `revalidateOnFocus` is false, so waiting out the interval
 *                    is the honest trigger; a synthetic focus event does nothing.
 *   `paginate`     — infinite scroll reaching an unavailable next page
 *                    (`loadNextPage`, page.tsx:612). Cards stay, `hasMore` is
 *                    untouched, and the retry appears inline below them.
 */
const STATES = {
  normal: { bodies: [POPULATED(12)] },
  "genuine-exhaustion": { bodies: [EXHAUSTED] },
  "unavailable-without-last-good": { bodies: [UNAVAILABLE] },
  "unavailable-with-last-good": { bodies: [POPULATED(12), UNAVAILABLE], trigger: "swr-refresh" },
  "unavailable-next-page": { bodies: [POPULATED(12, true), UNAVAILABLE], trigger: "paginate" },
};

/** The page's own `refreshInterval`, plus room for the request to land. */
const SWR_REFRESH_MS = 120_000;

/**
 * What each state MUST look like on screen. `seen` is the observation record
 * built below; a predicate returning a string is a failure with its reason.
 *
 * These are the queue's acceptance criteria, restated as executable claims:
 * last-good cards stay visible, a cold unavailable offers a retry, genuine
 * exhaustion alone says caught up, and no state silently borrows another's UI.
 */
const EXPECTATIONS = {
  // A complete build of 12 markets legitimately ENDS with the caught-up card —
  // `has_more: false` means there is genuinely no more. Asserting its absence
  // here was wrong, and run 30836513085 said so at both viewports. What the
  // adjacent journey actually regression-guards is that a healthy feed renders
  // cards and reaches for neither error surface.
  normal: [
    ["cards render", (s) => (s.cards > 0 ? null : `expected cards, saw ${s.cards}`)],
    [
      "every card rendered, none lost",
      (s) => (s.cards === 12 ? null : `served 12 distinct markets, rendered ${s.cards}`),
    ],
    ["no unavailable notice", (s) => (s.unavailable ? "the retry state appeared on a healthy feed" : null)],
    ["no error state", (s) => (s.error ? "the error state appeared on a healthy feed" : null)],
    ["skeleton resolved", (s) => (s.skeleton ? "the loading skeleton never resolved" : null)],
  ],
  "genuine-exhaustion": [
    ["no cards", (s) => (s.cards === 0 ? null : `expected an empty build, saw ${s.cards} cards`)],
    ["says caught up", (s) => (s.endOfFeed ? null : "genuine exhaustion did not render the end-of-feed card")],
    [
      "does NOT claim unavailable",
      (s) => (s.unavailable ? "an exhausted feed rendered the retry state — the two are not the same screen" : null),
    ],
    ["no error state", (s) => (s.error ? "an exhausted feed rendered the error state" : null)],
  ],
  "unavailable-without-last-good": [
    ["no cards", (s) => (s.cards === 0 ? null : `nothing should have rendered, saw ${s.cards} cards`)],
    ["offers the retry state", (s) => (s.unavailable ? null : "a cold unavailable feed did not render the retry state")],
    [
      "does NOT say caught up",
      (s) => (s.endOfFeed ? 'an unavailable feed told the reader "all caught up" — the L2-238 defect' : null),
    ],
    [
      "the retry control is reachable and named",
      (s) => (s.retryAccessibleNameVisible ? null : 'no visible control named "Try again to load the feed"'),
    ],
    ["announced as an alert", (s) => (s.alertText ? null : "the unavailable state carries no role=alert text")],
    ["no overlapping text or controls", (s) => s.overlapFailure],
  ],
  "unavailable-with-last-good": [
    [
      "last-good cards stay visible",
      (s) => (s.cards === 12 ? null : `an unavailable revalidation left ${s.cards} of 12 cards`),
    ],
    [
      "raises the retry state beside them",
      (s) => (s.unavailable ? null : "an unavailable revalidation was rendered as success"),
    ],
    [
      "does NOT say caught up",
      (s) => (s.endOfFeed ? 'last-good cards were followed by "all caught up" on an unavailable feed' : null),
    ],
    ["no overlapping text or controls", (s) => s.overlapFailure],
  ],
  "unavailable-next-page": [
    [
      "loaded cards stay visible",
      (s) => (s.cards === 12 ? null : `an unavailable next page left ${s.cards} of 12 cards`),
    ],
    [
      "offers the retry inline",
      (s) => (s.unavailable ? null : "an unavailable next page did not raise the retry state"),
    ],
    [
      "does NOT end the feed",
      (s) => (s.endOfFeed ? "an unavailable next page was rendered as the end of the feed" : null),
    ],
    ["no overlapping text or controls", (s) => s.overlapFailure],
  ],
};

/** Two boxes overlap by more than a hairline of both their areas. */
function overlaps(a, b) {
  const w = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
  const h = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
  if (w <= 1 || h <= 1) return false;
  const area = w * h;
  return area > 0.1 * Math.min(a.width * a.height, b.width * b.height);
}

/**
 * "No text/control overlaps", measured rather than eyeballed.
 *
 * Only the unavailable notice's own leaves are compared: a page-wide scan would
 * flag every legitimately-nested element. Off-viewport is failed too — a retry
 * button pushed past the right edge at 390px is unreachable, not merely ugly.
 */
async function findOverlap(page, viewportWidth) {
  const boxes = await page
    .locator('[data-testid="discover-feed-unavailable"] p, [data-testid="discover-feed-unavailable"] button')
    .evaluateAll((nodes) =>
      nodes.map((n) => {
        const r = n.getBoundingClientRect();
        return { tag: n.tagName.toLowerCase(), x: r.x, y: r.y, width: r.width, height: r.height };
      })
    )
    .catch(() => []);

  for (const box of boxes) {
    if (box.width <= 0 || box.height <= 0) return `<${box.tag}> rendered with zero size`;
    if (box.x < -1 || box.x + box.width > viewportWidth + 1) {
      return `<${box.tag}> extends outside the ${viewportWidth}px viewport (x=${Math.round(box.x)}, w=${Math.round(box.width)})`;
    }
  }
  for (let i = 0; i < boxes.length; i += 1) {
    for (let j = i + 1; j < boxes.length; j += 1) {
      if (overlaps(boxes[i], boxes[j])) {
        return `<${boxes[i].tag}> overlaps <${boxes[j].tag}>`;
      }
    }
  }
  return null;
}

/** Pacific time, because that is the clock the evidence is read against. */
function pacificStamp() {
  return new Date().toLocaleString("en-US", {
    timeZone: "America/Los_Angeles",
    hour12: false,
  });
}

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

  for (const [state, { bodies, trigger }] of Object.entries(STATES)) {
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
      const httpErrors = [];
      /** Failures whose only cause is a card id this fixture invented. */
      const syntheticFailures = [];
      page.on("console", (m) => {
        if (m.type() === "error") consoleErrors.push(m.text());
      });
      page.on("requestfailed", (r) => {
        // Third-party analytics/pixel blocks are not this page's failures.
        if (!/bainluck|localhost/.test(r.url())) return;
        const entry = `${r.url()} ${r.failure()?.errorText}`;
        if (SYNTHETIC_DETAIL_ROUTE.test(r.url())) syntheticFailures.push(entry);
        else requestFailures.push(entry);
      });
      page.on("response", (res) => {
        // Named, so the next reader does not have to guess what a bare
        // "Failed to load resource: … 404" in the console channel referred to.
        if (res.status() < 400 || !/bainluck|localhost/.test(res.url())) return;
        const entry = `${res.url()} ${res.status()}`;
        if (SYNTHETIC_DETAIL_ROUTE.test(res.url())) syntheticFailures.push(entry);
        else httpErrors.push(entry);
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

      if (trigger === "swr-refresh") {
        // Wait out the page's own `refreshInterval`. Slow, and the only honest
        // trigger available: `revalidateOnFocus` is false on this SWR key, so a
        // synthetic focus event revalidates nothing, and a reload is a COLD load
        // — the web client has no on-disk last-good, so reloading renders the
        // cold unavailable state and could never prove the cards survived.
        // Run 30836513085 is that mistake, measured at both viewports.
        const feedCallsBefore = feedCalls;
        const deadline = Date.now() + SWR_REFRESH_MS + 20_000;
        while (feedCalls === feedCallsBefore && Date.now() < deadline) {
          await page.waitForTimeout(2_000);
        }
        if (feedCalls === feedCallsBefore) {
          console.error(`::warning::${state}: no background revalidation fired within the bound`);
        }
        await page.waitForTimeout(2_000);
      }

      if (trigger === "paginate") {
        // Drive the infinite-scroll sentinel into view so `loadNextPage` runs
        // against the unavailable body (page.tsx:612) — the other half of the
        // "keep the cards" contract, and the fast one.
        for (let i = 0; i < 12; i += 1) {
          await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
          await page.waitForTimeout(600);
          if (feedCalls > 1) break;
        }
        await page.waitForTimeout(2_000);
        // Screenshot the retry where it renders, not the top of the page.
        await page
          .locator('[data-testid="discover-feed-unavailable"]')
          .first()
          .scrollIntoViewIfNeeded()
          .catch(() => null);
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

      const overlapFailure = seen.unavailable ? await findOverlap(page, vp.viewport.width) : null;

      const file = path.join(OUT, `${state}-${vp.name}.png`);
      await page.screenshot({ path: file, fullPage: false });

      // Chromium logs its own line for every 4xx subresource, and it names
      // nothing. Suppressed ONLY when the sole 4xx observed was a route this
      // fixture invented (`/futures/424242`), and never when a real one failed —
      // otherwise the allowance would outlive its reason and mute the next
      // genuine 404. Same rule L2-235 put on the journey evaluator's allowances.
      const only404sAreSynthetic = httpErrors.length === 0 && syntheticFailures.length > 0;
      const gradedConsole = only404sAreSynthetic
        ? consoleErrors.filter((text) => !text.includes(CHROMIUM_RESOURCE_404))
        : consoleErrors;

      const observation = {
        state,
        url: `${BASE}/discover`,
        viewport: vp.name,
        size: vp.viewport,
        feedCalls,
        trigger: trigger || "none",
        ...seen,
        retryAccessibleNameVisible: retryVisible,
        alertText,
        overlapFailure,
        consoleErrors,
        requestFailures,
        httpErrors,
        // Recorded, never graded, never dropped: the fixture's own shadow.
        syntheticFailures,
        screenshot: file,
        screenshot_sha256: sha256File(file),
        observed_at_pt: pacificStamp(),
        observed_at_utc: new Date().toISOString(),
      };

      // --- The grade. Every claim named, every failure kept.
      const checks = (EXPECTATIONS[state] || []).map(([name, predicate]) => {
        const reason = predicate(observation) || null;
        return { check: name, ok: reason === null, reason };
      });
      // Console errors and first-party request failures are graded for every
      // state, not just the ones with expectations of their own.
      checks.push({
        check: "no console errors",
        ok: gradedConsole.length === 0,
        reason: gradedConsole.length === 0 ? null : gradedConsole.slice(0, 3).join("; "),
      });
      checks.push({
        check: "no first-party request failures",
        ok: requestFailures.length === 0,
        reason: requestFailures.length === 0 ? null : requestFailures.slice(0, 3).join("; "),
      });
      checks.push({
        check: "no first-party 4xx/5xx",
        ok: httpErrors.length === 0,
        reason: httpErrors.length === 0 ? null : httpErrors.slice(0, 3).join("; "),
      });

      observation.checks = checks;
      observation.result = checks.every((c) => c.ok) ? "pass" : "fail";

      console.log(
        `${observation.result === "pass" ? "PASS" : "FAIL"}  ${state} @ ${vp.name} ` +
          `(${vp.viewport.width}x${vp.viewport.height})` +
          checks
            .filter((c) => !c.ok)
            .map((c) => `\n        ✗ ${c.check}: ${c.reason}`)
            .join("")
      );

      results.push(observation);
      await context.close();
    }
  }

  await browser.close();

  const failed = results.filter((r) => r.result !== "pass");
  const packet = {
    base: BASE,
    commit: process.env.RENDER_STATES_SHA || null,
    build: process.env.RENDER_STATES_BUILD || null,
    browser_version: process.env.RENDER_STATES_BROWSER || null,
    generated_at_pt: pacificStamp(),
    generated_at_utc: new Date().toISOString(),
    result: failed.length === 0 ? "pass" : "fail",
    total: results.length,
    failed: failed.length,
    results,
  };
  const manifest = path.join(OUT, "manifest.json");
  fs.writeFileSync(manifest, JSON.stringify(packet, null, 2));

  // A run that graded NOTHING must never read as green — the retired
  // provider's `success` with 0 of 3 modules collected is the shape being
  // refused here.
  if (results.length !== Object.keys(STATES).length * VIEWPORTS.length) {
    console.error(
      `::error::expected ${Object.keys(STATES).length * VIEWPORTS.length} observations, produced ${results.length}`
    );
    process.exit(1);
  }
  if (failed.length > 0) {
    console.error(`::error::${failed.length}/${results.length} rendered states failed`);
    process.exit(1);
  }
  console.log(`\nAll ${results.length} rendered states passed. Packet: ${manifest}`);
}

function sha256File(file) {
  try {
    return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
  } catch {
    return null;
  }
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
