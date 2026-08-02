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
 * ## On selectors: `data-testid` hooks (L2-231 Item 1)
 *
 * This pack originally bound to stat-card LABEL TEXT and then read the value
 * positionally as `> div` index 1 of the label's parent, because
 * `app/calibration/page.tsx` was Lane 1's active file and the Lane-2 gate
 * forbade touching it. Q297 landed and the file is free, so the hooks are in
 * and the prose selectors are out. Two things improve:
 *
 *   - An editorial reword no longer breaks the rail. That was a maintenance
 *     tax, not a correctness hole — but it was a real one.
 *   - The positional read is gone, and that one WAS a correctness hole:
 *     `> div` index 1 is satisfied by whatever sits second, so a reshuffle
 *     inside `StatCard` would have moved the read onto the DETAIL line — a
 *     string that also contains digits and would therefore still have passed
 *     the finite-number assertion. Fail-open, on a wrong number. Exactly the
 *     C96 [P1] class. `[data-testid="<card>-value"]` names the number itself.
 *
 * `frontend/__tests__/components/calibrationAuditHooks.test.tsx` is the
 * tripwire: it fails in CI if a hook is dropped, renamed, or duplicated, so a
 * missing anchor surfaces there rather than as a mystery red here.
 *
 * The page also publishes machine-readable state the rail grades on instead of
 * parsing prose: `data-population-version`, `data-cache-status`,
 * `data-cohort-n`, `data-activity-direction`, `data-disposition`.
 */

/** The declared page budget. The journey waits within this and no longer. */
const PAGE_BUDGET_MS = 45_000;

/** The hard failure copy the page renders when the fetch rejects. */
const ERROR_COPY = "Failed to load calibration data";
/** The loader. Still mounted at the end == the fetch never resolved. */
const LOADING_COPY = "Loading calibration data...";

/**
 * The five headline stat cards, by hook. Each renders its number under
 * `<hook>-value`, so the value is addressed directly rather than by position.
 */
const STAT_HOOKS = [
  "calibration-stat-outcomes",
  "calibration-stat-ece",
  "calibration-stat-brier",
  "calibration-stat-sources",
  "calibration-stat-categories",
] as const;

/** The well-traded / thin toggle, which governs every table and curve below. */
const COHORT_CONTROL = '[data-testid="calibration-cohort-toggle"]';

/** A rendered value that is not a finite number, however it got there. */
const NON_FINITE = /NaN|Infinity|undefined|null/i;

/**
 * L2-230 / C111 [P1]. Copy that asserts one cohort is SUPERIOR. The page used
 * to print "outcomes where the price moved are dramatically better calibrated"
 * unconditionally, and `unchangedECE / movedECE` labelled "more accurately
 * calibrated" — which on 2026-08-02 rendered "0.6x more accurately calibrated"
 * beside stat cards reading 1.7pp and 1.0pp. These strings must never come back.
 */
const SUPERIORITY_COPY = /more accurately calibrated|dramatically better calibrated/i;

/** The activity section — the anchor for the pixels-vs-prose check. */
const ACTIVITY_SECTION = '[data-testid="calibration-activity-section"]';
/** The two cohort stat cards inside that section, moved side first. */
const ACTIVITY_MOVED = "calibration-activity-moved";
const ACTIVITY_UNCHANGED = "calibration-activity-unchanged";

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
  const pageRoot = page.locator('[data-testid="calibration-page"]').first();

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
    .locator(COHORT_CONTROL)
    .first()
    .isVisible()
    .catch(() => false);

  // The payload contract the page says it rendered. Recorded, never asserted to
  // a literal: pinning "q299" here would make the rail a tripwire for Lane 1's
  // legitimate population bumps. Its VALUE is the parity evidence — the native
  // proof compares against this, and a blank means the page rendered a payload
  // that would not name its own contract.
  const populationVersion = (await pageRoot.getAttribute("data-population-version")) ?? "";
  const cacheStatus = (await pageRoot.getAttribute("data-cache-status")) ?? "";
  const cohortN = await page
    .locator('[data-testid="calibration-population-count"]')
    .first()
    .getAttribute("data-cohort-n")
    .catch(() => null);

  // Read every stat card in one pass, by hook. The value element is addressed
  // directly (`<hook>-value`) rather than by sibling position, so a reshuffle
  // inside StatCard cannot silently move the read onto the detail line.
  const stats: StatCard[] = [];
  for (const hook of STAT_HOOKS) {
    const card = page.locator(`[data-testid="${hook}"]`).first();
    if (!(await card.isVisible().catch(() => false))) {
      stats.push({ label: hook, value: "", box: null });
      continue;
    }
    const value = (
      await page
        .locator(`[data-testid="${hook}-value"]`)
        .first()
        .innerText()
        .catch(() => "")
    ).trim();
    stats.push({ label: hook, value, box: await card.boundingBox().catch(() => null) });
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

  // ── L2-230: does the trading-activity PROSE agree with the NUMBERS beside it?
  //
  // This is deliberately NOT an assertion about which cohort ought to win —
  // that stays out of the rail, per the gate above. It is the weaker, strictly
  // mechanical property the shipped bug violated: the sentence named a winner
  // that its own two stat cards contradicted. So read both values and the
  // sentence, and require they point the same way.
  //
  // The section is conditional (it renders only when both cohorts have
  // outcomes), so its absence is not a failure — but a present section with
  // reversed prose is.
  // Same check as before, now read from hooks instead of prose. The page states
  // its own computed direction in `data-activity-direction`, so this compares
  // the page's CLAIM against the page's own two rendered NUMBERS — no regex over
  // a sentence, and no dependence on how that sentence is worded.
  const activitySection = page.locator(ACTIVITY_SECTION).first();
  const activityPresent = await activitySection.isVisible().catch(() => false);
  const activityValues: Record<string, number> = {};
  let activityDirection: string | null = null;

  const readActivityValue = async (hook: string): Promise<void> => {
    const raw = (
      await page
        .locator(`[data-testid="${hook}-value"]`)
        .first()
        .innerText()
        .catch(() => "")
    ).trim();
    const parsed = Number.parseFloat(raw.replace(/pp$/, ""));
    if (Number.isFinite(parsed)) activityValues[hook] = parsed;
  };

  if (activityPresent) {
    activityDirection = await activitySection.getAttribute("data-activity-direction");
    await readActivityValue(ACTIVITY_MOVED);
    await readActivityValue(ACTIVITY_UNCHANGED);
  }

  // Which cohort the RENDERED numbers say is worse. "Active Trading" is the
  // price-moved side; "Opening Price Only" is price-unchanged.
  const moved = activityValues[ACTIVITY_MOVED];
  const unchanged = activityValues[ACTIVITY_UNCHANGED];
  // The page rounds both to 1dp before comparing (that is what the reader sees),
  // so the rail must too — otherwise two cards both showing "1.0pp" would be
  // graded as ordered here and reported as a contradiction of an honest tie.
  const round1 = (v: number) => Math.round(v * 10) / 10;
  const numbersSayHigher =
    Number.isFinite(moved) && Number.isFinite(unchanged)
      ? round1(moved) === round1(unchanged)
        ? "tied"
        : round1(moved) > round1(unchanged)
          ? "moved_higher"
          : "unchanged_higher"
      : null;

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

  // L2-231. The hooks themselves are evidence: if the page root is absent, every
  // hook-based read above degraded to "" and the run must not be read as green.
  expect(
    await pageRoot.isVisible().catch(() => false),
    "the calibration page root hook must render",
  ).toBe(true);
  // Not a literal version — the value is recorded, its PRESENCE is asserted. A
  // payload that will not name its own population contract is exactly what
  // C111 P2 / Q297 §3 made un-serveable, so a blank here is a real regression.
  expect(
    populationVersion,
    "the page must declare the payload's population version",
  ).not.toBe("");
  expect(cohortN, "the population count must publish its cohort n").not.toBeNull();
  // A stale snapshot is legitimate and must be BANNERED; what is not legitimate
  // is a stale payload rendered with no banner at all.
  if (cacheStatus === "stale") {
    expect(
      await page.locator('[data-testid="calibration-stale-banner"]').first().isVisible().catch(() => false),
      "a stale payload must render the dated last-good banner",
    ).toBe(true);
  }
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

  // L2-230. Ordered least-to-most specific so the first red line is the blunt one.
  expect(
    SUPERIORITY_COPY.test(mainText),
    'no cohort may be sold as "more accurately calibrated" / "dramatically better"',
  ).toBe(false);
  if (activityPresent) {
    expect(
      Object.keys(activityValues).sort(),
      "both activity cohort values must render as finite numbers",
    ).toEqual([ACTIVITY_MOVED, ACTIVITY_UNCHANGED].sort());
  }
  if (numbersSayHigher && activityDirection) {
    expect(
      activityDirection,
      `the page claims "${activityDirection}", but its own cards read ` +
        `moved=${moved}pp / unchanged=${unchanged}pp`,
    ).toBe(numbersSayHigher);
  }
});
