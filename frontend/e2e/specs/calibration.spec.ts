import { test, expect, readContentRegionText } from "../fixtures/audit";

/**
 * L2-228 — the public calibration journey.
 *
 * `/calibration` is the most-linked non-feed page on the site and it has no
 * browser coverage at all. The whole page is a client-side SWR fetch of
 * `GET /api/calibration` (`frontend/lib/api.ts:1873`), so *every* failure mode
 * lands in the browser rather than in a server log: a slow or 5xx API renders
 * `Failed to load calibration data`, a hung one leaves `Loading calibration
 * data...` mounted forever, and a payload that parses but carries a NaN metric
 * renders `NaNpp` in a stat card and reads as a number to anyone skimming.
 *
 * What this pack answers, at desktop and mobile:
 *
 *   1. Did the calibration API actually get called, and did it succeed?
 *   2. Is the hard error state absent, and the loader unmounted?
 *   3. Do the stat cards carry values that are actually finite numbers?
 *   4. Is the well-traded/thin control present (it governs every table below)?
 *   5. Is the methodology section present?
 *   6. Do the stat cards lay out without collapsing or overlapping?
 *
 * ## What it deliberately does NOT assert
 *
 * Per the queue gate: no assertion that a particular population COUNT or a
 * particular cohort ORDERING is correct. r336 / C111 / Q297 own those facts,
 * and a rail that hard-codes "1,043,221 outcomes" becomes a tripwire for their
 * legitimate repairs instead of a check on rendering. This pack proves the page
 * renders honest, finite, non-collapsed numbers — not which numbers are right.
 *
 * ## On selectors: no test hooks, on purpose
 *
 * The Discover packs bind to `data-testid` hooks that L2-223 added to those
 * components. This pack does not, because `frontend/app/calibration/page.tsx`
 * is Lane 1's active file (Queue 297 Item 1 is rewriting its degraded-state
 * rendering right now) and the Lane-2 gate forbids touching it.
 *
 * So the selectors below are chosen to be **fail-closed**. That is the property
 * that matters, and it is not the same as "stable":
 *
 *   - A fail-OPEN selector matches something it shouldn't and reports green.
 *     `main div.break-inside-avoid` was one — `DiscoverSkeletonGrid` carried the
 *     same Tailwind layout class, so a page stuck on skeletons "found a card".
 *     That is the C96 [P1] false green and it is banned here: no assertion
 *     below is satisfied by a layout class.
 *   - A fail-CLOSED selector stops matching and reports red. An editorial
 *     reword of the stat-card label "Brier Score" breaks this spec loudly. That
 *     is a maintenance cost, not a correctness hole, and it is the correct
 *     trade while the file belongs to another lane.
 *
 * `section#methodology` is a real id and is the one genuinely stable anchor on
 * the page. When Q297 lands and the file is free, the right follow-up is to add
 * `data-testid` hooks plus a `__tests__` guard, exactly as L2-223 did for
 * Discover, and drop the label matching.
 */

/** The declared page budget. The journey waits within this and no longer. */
const PAGE_BUDGET_MS = 45_000;

/** The hard failure copy the page renders when the fetch rejects. */
const ERROR_COPY = "Failed to load calibration data";
/** The loader. Still mounted at the end == the fetch never resolved. */
const LOADING_COPY = "Loading calibration data...";

/**
 * Stat-card labels the page renders (`StatCard` at page.tsx:881). Located by
 * label text, then read positionally WITHIN that card — the card is found
 * semantically, so the positional read cannot wander onto another element.
 */
const STAT_LABELS = [
  "Resolved Outcomes",
  "Calibration Error (ECE)",
  "Brier Score",
  "Sources",
  "Categories",
] as const;

/** The well-traded / thin toggle, which governs every table and curve below. */
const COHORT_CONTROL = /Well-traded only|Include thin\/untraded/;

/** A rendered value that is not a finite number, however it got there. */
const NON_FINITE = /NaN|Infinity|undefined|null/i;

interface StatCard {
  label: string;
  value: string;
  box: { x: number; y: number; width: number; height: number } | null;
}

test("public calibration renders finite, non-degraded numbers", async ({ page, journey }) => {
  const path = "/calibration";

  // Capture the calibration API exchange. Installed BEFORE navigation — a
  // listener attached after `goto` misses the request it exists to observe.
  //
  // The shared fixture already fails the journey on any first-party 4xx/5xx,
  // and `api.bainluck.com` is first-party (L2-223 widened that deliberately),
  // so a 500 here fails without this listener. This records the exchange so
  // the manifest says WHICH call and WHAT status, rather than just "a request
  // failed" — and so the absence of the call is itself detectable.
  const apiCalls: Array<{ url: string; status: number }> = [];
  page.on("response", (res) => {
    const url = res.url();
    // The bucket-examples endpoint is a different, lazier call; match the
    // main payload only, not `/api/calibration/examples`.
    if (/\/api\/calibration(\?|$)/.test(url)) {
      apiCalls.push({ url: new URL(url).pathname, status: res.status() });
    }
  });

  await page.goto(path, { waitUntil: "domcontentloaded" });

  const errorLocator = page.getByText(ERROR_COPY, { exact: false }).first();
  const methodology = page.locator("section#methodology").first();

  // Race the two terminal outcomes. A healthy page resolves as soon as the
  // methodology section mounts; a broken one resolves as soon as the error copy
  // appears. A page that does neither burns the budget and fails — which is
  // the correct verdict for a hang, and the reason the wait is bounded here
  // rather than left to the 90s global timeout.
  await Promise.race([
    methodology.waitFor({ state: "visible", timeout: PAGE_BUDGET_MS }).catch(() => null),
    errorLocator.waitFor({ state: "visible", timeout: PAGE_BUDGET_MS }).catch(() => null),
  ]);

  const errorVisible = await errorLocator.isVisible().catch(() => false);
  const loadingVisible = await page
    .getByText(LOADING_COPY, { exact: false })
    .first()
    .isVisible()
    .catch(() => false);
  const methodologyVisible = await methodology.isVisible().catch(() => false);
  const cohortControlVisible = await page
    .getByText(COHORT_CONTROL)
    .first()
    .isVisible()
    .catch(() => false);

  // Read every stat card in one pass: its label, its rendered value, and its
  // box. `StatCard` renders [label, value, detail] as three sibling divs, so
  // the value is child 1 of the card the label lives in.
  const stats: StatCard[] = [];
  for (const label of STAT_LABELS) {
    const labelNode = page.getByText(label, { exact: true }).first();
    if (!(await labelNode.isVisible().catch(() => false))) {
      stats.push({ label, value: "", box: null });
      continue;
    }
    const card = labelNode.locator("xpath=..");
    const value = (
      await card
        .locator("> div")
        .nth(1)
        .innerText()
        .catch(() => "")
    ).trim();
    stats.push({ label, value, box: await card.boundingBox().catch(() => null) });
  }

  const missing = stats.filter((s) => s.box === null);
  // A value must contain a digit AND must not be a non-finite token. "NaNpp"
  // and "Infinity" both render as plausible-looking text in a stat card; this
  // is the assertion that makes them red instead of readable.
  const nonFinite = stats.filter(
    (s) => s.box !== null && (!/\d/.test(s.value) || NON_FINITE.test(s.value)),
  );
  const collapsed = stats.filter((s) => s.box && (s.box.width <= 0 || s.box.height <= 0));

  // Geometric overlap between stat cards. A grid that reflows badly at 390px
  // stacks cards on top of each other while every text assertion still passes,
  // so "the numbers are there" is not the same as "the numbers are readable".
  const overlapping: string[] = [];
  const boxed = stats.filter((s) => s.box && s.box.width > 0 && s.box.height > 0);
  for (let i = 0; i < boxed.length; i++) {
    for (let j = i + 1; j < boxed.length; j++) {
      const a = boxed[i].box!;
      const b = boxed[j].box!;
      // 1px of tolerance for sub-pixel layout rounding.
      const overlapX = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
      const overlapY = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
      if (overlapX > 1 && overlapY > 1) {
        overlapping.push(`${boxed[i].label} ∩ ${boxed[j].label}`);
      }
    }
  }

  const failedApiCalls = apiCalls.filter((c) => c.status >= 400);

  // The blank-page check needs the page's content region. `/calibration`
  // renders NO `<main>` element — unlike the Discover surfaces this rail was
  // built against — so reading `main` here waited on an element that is never
  // going to exist. With Playwright's default unbounded `actionTimeout` that
  // consumed the entire remaining test budget, and the journey died before it
  // could grade a single assertion or take its terminal screenshot: run
  // 30722940887 came back `infra_error` with an empty artifacts array, on both
  // projects, and would have done so even with a perfectly healthy page.
  //
  // `readContentRegionText` falls back to `body` when there is no `main`, and
  // bounds the read either way. (The missing landmark is a real accessibility
  // gap on that page, but the file belongs to another lane — recorded for its
  // owner, not fixed here.)
  const mainText = await readContentRegionText(page);

  await journey.finish({
    journeyId: "calibration.anonymous",
    expectedPath: path,
    // The subject is not the Discover feed, so the shared card check does not
    // apply. The blank-main check below still does, and every assertion that
    // matters for this page is this spec's own.
    contentMode: "none",
    realCardFound: false,
    mainRegionNonBlank: mainText.trim().length > 200 && !loadingVisible && !errorVisible,
  });

  // Ordered most-diagnostic first, so the first red line in the report names
  // the actual failure rather than a downstream symptom of it.
  expect(apiCalls.length, "the page must actually call GET /api/calibration").toBeGreaterThan(0);
  expect(
    failedApiCalls.map((c) => `${c.url} → ${c.status}`),
    "the calibration API must not return an error status",
  ).toEqual([]);
  expect(errorVisible, `"${ERROR_COPY}" must not be rendered`).toBe(false);
  expect(loadingVisible, "the loading state must not still be mounted").toBe(false);
  expect(methodologyVisible, "the methodology section must render").toBe(true);
  expect(cohortControlVisible, "the well-traded/thin control must render").toBe(true);
  expect(
    missing.map((s) => s.label),
    "every stat card must render",
  ).toEqual([]);
  expect(
    nonFinite.map((s) => `${s.label}="${s.value}"`),
    "every stat card value must be a finite number",
  ).toEqual([]);
  expect(
    collapsed.map((s) => s.label),
    "no stat card may collapse to zero width or height",
  ).toEqual([]);
  expect(overlapping, "stat cards must not overlap each other").toEqual([]);
});
