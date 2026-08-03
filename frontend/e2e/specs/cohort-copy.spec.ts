import fs from "node:fs";
import path from "node:path";
import { test, expect, type Page, type Route } from "@playwright/test";

/**
 * L2-236 Item 2 — does the calibration page's cohort language agree with the
 * numbers it renders, in a real browser, at both viewports?
 *
 * The defect this grades: `/calibration` defaults to `price_moved !== false`
 * and described that set as "well-traded markets — where real trading moved the
 * price". `price_moved` is a TRI-state — `true`, `false`, and `null` for
 * sportsbook lines where the question does not apply — so on the frozen
 * 2026-08-02 production payload the sentence was false for 40,075 of the
 * 389,385 rows it described, and those rows were named nowhere: the activity
 * section's two cards summed to 612,332 against a stated 652,407.
 *
 * ## Why this pack drives FIXTURES and the production pack does not
 *
 * `specs/calibration.spec.ts` audits the live site and deliberately asserts no
 * population count and no cohort ordering — pinning "1,043,221 outcomes" there
 * would make the rail a tripwire for Lane 1's legitimate repairs. But the
 * claims THIS queue shipped are exactly claims about specific numbers and a
 * specific direction, and production serves one payload at a time: the
 * reversed-direction and unavailable states cannot be observed on demand.
 *
 * So the API is intercepted and four states are driven through the real page:
 *
 *   fresh              the production payload, current
 *   dated-degraded     the same numbers served as a dated last-good snapshot
 *   reversed-direction moved/unchanged swapped, so the ordering flips
 *   unavailable        a typed 503 — no numbers may be rendered at all
 *
 * Same bytes native was graded on (`fixtures/calibration-prod-2026-08-02.json`,
 * ported from L2-231's `CalibrationProdFixture.swift`), so "parity" means the
 * two surfaces agreed about one response rather than each agreeing with itself.
 *
 * ## Why it does NOT use the audit journey fixture
 *
 * The `journey` fixture binds a run to a deployed frontend SHA and refuses to
 * pass without one — correctly, for a production evidence rail. This pack
 * grades a build, not a deployment, and runs against whatever origin is given
 * (a local `next start` before the push, production after it). Borrowing the
 * SHA-bound fixture here would either produce a manifest claiming a deployment
 * this run never touched, or a permanent red. It writes its own per-claim
 * ledger instead, with the same properties that matter: every claim named and
 * graded individually, console errors and failed requests recorded rather than
 * summarised, and a screenshot per state per viewport.
 *
 * Named `cohort-copy` on purpose: `npm run calibration` filters on the token
 * "calibration", which would otherwise select this file into the production
 * pack and fail it for producing no journey record.
 */

const FIXTURE = JSON.parse(
  fs.readFileSync(path.join(__dirname, "..", "fixtures", "calibration-prod-2026-08-02.json"), "utf8")
) as {
  payload: CalibrationPayload;
  cache_stale: Record<string, unknown>;
};

interface FixtureBucket {
  bucket_idx: number;
  source: string;
  category: string;
  price_moved: boolean | null;
  n: number;
  winners: number;
  sum_prob: number;
  sum_sq_err: number;
}
interface CalibrationPayload {
  buckets: FixtureBucket[];
  total_outcomes: number;
  cache?: Record<string, unknown>;
  [k: string]: unknown;
}

/** Deep-ish clone that is enough for a JSON fixture. */
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

/**
 * The production payload with `price_moved` true/false swapped. Every other
 * byte is identical, so what this state changes is the ORDERING and nothing
 * else — which is the point: the prose must follow the numbers, not a constant.
 */
function reversed(): CalibrationPayload {
  const p = clone(FIXTURE.payload);
  for (const b of p.buckets) {
    if (b.price_moved === true) b.price_moved = false;
    else if (b.price_moved === false) b.price_moved = true;
  }
  return p;
}

function dated(): CalibrationPayload {
  const p = clone(FIXTURE.payload);
  p.cache = clone(FIXTURE.cache_stale);
  return p;
}

/** One graded claim. `ok === false` fails the state it belongs to. */
interface Claim {
  id: string;
  ok: boolean;
  detail: string;
}

interface StateEvidence {
  fixture: string;
  project: string;
  viewport: { width: number; height: number } | null;
  base_url: string;
  build_sha: string;
  captured_at_pt: string;
  screenshot: string | null;
  /** How the frame was captured — a clipped shot is not a whole-page shot. */
  screenshot_mode: "full-page" | "viewport" | "none";
  /** Cropped frames of the exact surfaces this queue changed. */
  element_shots: string[];
  console_errors: string[];
  failed_requests: string[];
  declared_allowances: string[];
  unexpected_noise: string[];
  claims: Claim[];
}

/** Pacific time, because that is the clock the report is read on. */
function nowPT(): string {
  return new Date().toLocaleString("en-US", {
    timeZone: "America/Los_Angeles",
    dateStyle: "medium",
    timeStyle: "medium",
  });
}

const BUILD_SHA =
  process.env.AUDIT_CHECKOUT_SHA || process.env.AUDIT_REQUESTED_SHA || "uncommitted-working-tree";

/**
 * Noise the HOST environment creates, not the page.
 *
 * On a sandboxed developer machine the outbound allowlist blocks the nav
 * search bar's trending prefetch to `api.bainluck.com`, which surfaces as one
 * `net::ERR_ACCESS_DENIED`. That is the sandbox, not the build — but it must
 * not be silently tolerated either, so it is declared only when the runner says
 * it is running under those conditions. A CI run sets nothing, declares
 * nothing, and would fail on the same line if the request really did break.
 */
const SANDBOX_ALLOWANCES: RegExp[] =
  process.env.AUDIT_SANDBOXED_NETWORK === "1"
    ? [/ERR_ACCESS_DENIED/, /events\/search\/trending/]
    : [];

/** The copy that must never come back, in any state. */
const BANNED = [
  { id: "copy.no_false_trading_claim", re: /where real trading moved the price/i },
  { id: "copy.no_well_traded", re: /well[- ]traded/i },
  { id: "copy.no_thin_untraded", re: /thinly[- ]traded|thin\/untraded|thin markets/i },
  { id: "copy.no_superiority", re: /more accurately calibrated|dramatically better/i },
];

/**
 * Intercept the calibration payload only. `/api/calibration/examples` is a
 * different, lazier call and must reach the network untouched — routing it here
 * too would make a drill-in failure look like a cohort failure.
 */
async function stubCalibration(
  page: Page,
  responder: (route: Route) => Promise<void> | void
): Promise<void> {
  await page.route("**/api/calibration**", async (route) => {
    const { pathname } = new URL(route.request().url());
    if (!/\/api\/calibration\/?$/.test(pathname)) return route.fallback();
    await responder(route);
  });
}

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({
    status,
    contentType: "application/json",
    headers: { "access-control-allow-origin": "*" },
    body: JSON.stringify(body),
  });

/**
 * Run one fixture state through the page and write its evidence.
 *
 * Assertions are collected as claims and graded at the END, so a first failure
 * cannot abort the run before the screenshot and the ledger exist — the L2-229
 * lesson: an unbounded or early-aborting step eats the proof it was gathering.
 */
async function grade(
  page: Page,
  testInfo: { project: { name: string }; outputPath: (n: string) => string; attach: Function },
  fixtureName: string,
  responder: (route: Route) => Promise<void> | void,
  claimsFor: (text: string, page: Page) => Promise<Claim[]>,
  /**
   * Noise this state EXPECTS, declared one pattern at a time. Anything
   * undeclared still fails the state, and a declared allowance that matches
   * nothing fails too — an allowance nobody needs is an allowance that will
   * one day hide a real error (the rail's own rule, in `helpers/journey.js`).
   */
  allowances: RegExp[] = []
): Promise<void> {
  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") consoleErrors.push(m.text().slice(0, 300));
  });
  page.on("requestfailed", (r) => failedRequests.push(`${r.method()} ${r.url()} — ${r.failure()?.errorText}`));
  page.on("response", (r) => {
    if (r.status() >= 400 && /bainluck|localhost/.test(r.url()) && !/\/api\/calibration\/?$/.test(new URL(r.url()).pathname)) {
      failedRequests.push(`${r.request().method()} ${r.url()} → ${r.status()}`);
    }
  });

  await stubCalibration(page, responder);
  await page.goto("/calibration", { waitUntil: "domcontentloaded" });

  // Either terminal state is fine to wait for — the claims decide which one
  // was correct for this fixture.
  await Promise.race([
    page.locator('[data-testid="calibration-page"]').first().waitFor({ state: "visible", timeout: 30_000 }).catch(() => null),
    page.locator('[data-testid="calibration-error"]').first().waitFor({ state: "visible", timeout: 30_000 }).catch(() => null),
  ]);

  const text = await page.locator("body").innerText({ timeout: 10_000 }).catch(() => "");
  const claims = await claimsFor(text, page);

  // Declared allowances, applied to console errors and failed requests alike.
  const noise = [...consoleErrors, ...failedRequests];
  const unexpected = noise.filter((n) => !allowances.some((a) => a.test(n)));
  const unusedAllowances = allowances
    .filter((a) => !noise.some((n) => a.test(n)))
    .map((a) => a.source);

  const evidence: StateEvidence = {
    fixture: fixtureName,
    project: testInfo.project.name,
    viewport: page.viewportSize(),
    base_url: page.url(),
    build_sha: BUILD_SHA,
    captured_at_pt: nowPT(),
    screenshot: null,
    screenshot_mode: "none",
    element_shots: [],
    console_errors: consoleErrors,
    failed_requests: failedRequests,
    declared_allowances: allowances.map((a) => a.source),
    unexpected_noise: unexpected,
    claims,
  };
  // Written to a FILE, not only inlined as an attachment body: an inline
  // attachment lives inside the HTML report's blob and cannot be read with
  // `cat` from the results directory, which is where a reader looks first.
  //
  // Written BEFORE the screenshot, and rewritten after. A full-page capture is
  // the single most fragile call in this function — it is where a browser under
  // a relaxed sandbox actually dies — and the L2-229 lesson is that the step
  // which eats the proof is the step nobody bounded. The graded claims survive
  // the capture failing; the capture failing is then its own named assertion.
  const ledger = testInfo.outputPath(`${fixtureName}-${testInfo.project.name}.claims.json`);
  fs.writeFileSync(ledger, JSON.stringify(evidence, null, 2));

  // WHAT gets photographed, and why it is not a full-page capture by default.
  //
  // A full-page shot of this surface at Pixel-5 scale is a ~390 x 10,000 CSS
  // frame at deviceScaleFactor 2.625 — tens of millions of pixels composed into
  // one bitmap. A browser running with its process isolation relaxed (see
  // AUDIT_CHROMIUM_ARGS) does not merely fail that call: it DIES, taking the
  // shared browser with it, so the next test cannot even open a page. Chasing
  // the whole page cost three states their evidence.
  //
  // So the default capture is the viewport plus an element shot of each surface
  // this queue actually changed — which is the better artifact anyway: a
  // 10,000px-tall thumbnail is unreadable, and these frame the sentence being
  // graded. `AUDIT_FULL_PAGE_SCREENSHOT=1` asks for the whole page where the
  // environment can survive it.
  const shot = testInfo.outputPath(`${fixtureName}-${testInfo.project.name}.png`);
  const wantFull = process.env.AUDIT_FULL_PAGE_SCREENSHOT === "1";
  const captured = await page
    .screenshot({ path: shot, fullPage: wantFull })
    .then(() => (wantFull ? ("full-page" as const) : ("viewport" as const)))
    .catch(() => "none" as const);
  if (captured !== "none" && fs.existsSync(shot)) {
    evidence.screenshot = path.basename(shot);
    evidence.screenshot_mode = captured;
  }

  for (const [name, selector] of [
    ["cohort", '[data-testid="calibration-cohort-toggle"]'],
    ["activity", '[data-testid="calibration-activity-section"]'],
    ["error", '[data-testid="calibration-error"]'],
  ] as const) {
    const el = page.locator(selector).first();
    if (!(await el.isVisible().catch(() => false))) continue;
    const p = testInfo.outputPath(`${fixtureName}-${testInfo.project.name}.${name}.png`);
    if (await el.screenshot({ path: p }).then(() => true).catch(() => false)) {
      evidence.element_shots.push(path.basename(p));
      await testInfo.attach(`cohort-copy-${fixtureName}-${name}.png`, { path: p, contentType: "image/png" });
    }
  }
  fs.writeFileSync(ledger, JSON.stringify(evidence, null, 2));

  await testInfo.attach(`cohort-copy-${fixtureName}.json`, { path: ledger, contentType: "application/json" });
  if (fs.existsSync(shot)) {
    await testInfo.attach(`cohort-copy-${fixtureName}.png`, { path: shot, contentType: "image/png" });
  }

  // Graded last, all at once, so the ledger above exists whatever happens.
  const failed = claims.filter((c) => !c.ok);
  expect(failed.map((c) => `${c.id}: ${c.detail}`), `${fixtureName} claims`).toEqual([]);
  expect(unexpected, `${fixtureName} undeclared console errors / failed requests`).toEqual([]);
  expect(unusedAllowances, `${fixtureName} allowances that matched nothing`).toEqual([]);
  expect(evidence.screenshot_mode, `${fixtureName} terminal screenshot`).not.toBe("none");
  expect(evidence.element_shots.length, `${fixtureName} framed the surface it graded`).toBeGreaterThan(0);
}

/** Assert a literal string is present, as a named claim. */
const has = (id: string, text: string, needle: string): Claim => ({
  id,
  ok: text.includes(needle),
  detail: text.includes(needle) ? `found "${needle}"` : `MISSING "${needle}"`,
});

const attr = async (page: Page, sel: string, name: string): Promise<string | null> =>
  page.locator(sel).first().getAttribute(name, { timeout: 5_000 }).catch(() => null);

/** The claims every rendered (non-error) state must satisfy. */
async function commonRenderedClaims(text: string, page: Page): Promise<Claim[]> {
  const claims: Claim[] = [];
  for (const b of BANNED) {
    const hit = b.re.exec(text);
    claims.push({ id: b.id, ok: !hit, detail: hit ? `rendered "${hit[0]}"` : "absent" });
  }
  const reconciles = await attr(page, '[data-testid="calibration-cohort-toggle"]', "data-partition-reconciles");
  claims.push({
    id: "partition.reconciles",
    ok: reconciles === "true",
    detail: `data-partition-reconciles=${reconciles}`,
  });
  const moved = await attr(page, '[data-testid="calibration-cohort-toggle"]', "data-moved-n");
  const unchanged = await attr(page, '[data-testid="calibration-cohort-toggle"]', "data-unchanged-n");
  const na = await attr(page, '[data-testid="calibration-cohort-toggle"]', "data-not-applicable-n");
  const cohortN = await attr(page, '[data-testid="calibration-population-count"]', "data-cohort-n");
  const fullN = await attr(page, '[data-testid="calibration-population-count"]', "data-full-n");
  const sum = Number(moved) + Number(unchanged) + Number(na);
  claims.push({
    id: "partition.sums_to_population",
    ok: sum === Number(fullN) && Number.isFinite(sum),
    detail: `${moved} + ${unchanged} + ${na} = ${sum} vs full ${fullN}`,
  });
  claims.push({
    id: "partition.cohort_is_moved_plus_not_applicable",
    ok: Number(cohortN) === Number(moved) + Number(na),
    detail: `cohort ${cohortN} vs moved+na ${Number(moved) + Number(na)}`,
  });
  claims.push({
    id: "cohort.denominator_named_separately",
    ok: Number(cohortN) !== Number(fullN) && text.includes(Number(fullN).toLocaleString("en-US")),
    detail: `cohort ${cohortN}, denominator ${fullN} present in copy`,
  });
  return claims;
}

/** The claims tied to the production numbers, in their un-swapped orientation. */
async function productionNumberClaims(text: string, page: Page): Promise<Claim[]> {
  const claims = await commonRenderedClaims(text, page);
  claims.push(
    has("copy.headline_names_both_halves", text, "Showing markets whose price moved, plus sportsbook lines (389,385)"),
    has("copy.moved_half_counted", text, "349,310 outcomes whose price real trading moved"),
    has("copy.not_applicable_half_named", text, "40,075 sportsbook lines where that test doesn't apply"),
    has("copy.excluded_side_counted", text, "Excluded: 263,022 outcomes whose price never moved off its opening line."),
    has("copy.toggle_names_what_it_adds", text, "Include never-moved (+263,022)"),
    has(
      "copy.activity_partition_reconciles_on_screen",
      text,
      "349,310 + 263,022 + 40,075 = 652,407 resolved outcomes"
    )
  );
  const direction = await attr(page, '[data-testid="calibration-activity-section"]', "data-activity-direction");
  claims.push({
    id: "direction.moved_is_the_higher_error",
    ok: direction === "moved_higher",
    detail: `data-activity-direction=${direction}`,
  });

  // One ADJACENT section, unchanged by this queue. The per-source table is
  // computed over the same cohort filter, so its Combined row is the cheapest
  // proof that renaming the cohort did not move the population underneath it —
  // and it would catch a copy edit that accidentally became a filter edit.
  const combined = await page
    .locator("tr", { hasText: "Combined" })
    .first()
    .innerText()
    .catch(() => "");
  claims.push({
    id: "adjacent.source_table_combined_is_the_cohort",
    ok: combined.includes("389,385"),
    detail: `combined row = ${combined.replace(/\s+/g, " ").trim().slice(0, 120)}`,
  });
  const publishedCats = await attr(page, '[data-testid="calibration-category-breakdown"]', "data-published-categories");
  claims.push({
    id: "adjacent.category_breakdown_still_publishes",
    ok: Number(publishedCats) > 0,
    detail: `data-published-categories=${publishedCats}`,
  });
  claims.push(
    has("direction.sentence_names_the_higher_cohort", text, "price-moved cohort carries the higher calibration error")
  );
  return claims;
}

test.describe("calibration cohort copy", () => {
  test("fresh production payload: the words match the numbers", async ({ page }, testInfo) => {
    await grade(page, testInfo, "fresh", (r) => json(r, FIXTURE.payload), productionNumberClaims, [
      ...SANDBOX_ALLOWANCES,
    ]);
  });

  test("dated last-good payload: same cohort language, plus the stale banner", async ({ page }, testInfo) => {
    await grade(page, testInfo, "dated-degraded", (r) => json(r, dated()), async (text, p) => {
      const claims = await productionNumberClaims(text, p);
      const banner = await p.locator('[data-testid="calibration-stale-banner"]').first().isVisible().catch(() => false);
      claims.push({
        id: "degraded.dated_banner_rendered",
        ok: banner,
        detail: `stale banner visible=${banner}`,
      });
      claims.push({
        id: "degraded.cache_status_published",
        ok: (await attr(p, '[data-testid="calibration-page"]', "data-cache-status")) === "stale",
        detail: "data-cache-status",
      });
      return claims;
    }, [...SANDBOX_ALLOWANCES]);
  });

  test("reversed ordering: the prose follows the numbers, not a constant", async ({ page }, testInfo) => {
    await grade(page, testInfo, "reversed-direction", (r) => json(r, reversed()), async (text, p) => {
      const claims = await commonRenderedClaims(text, p);
      // Swapped: the moved side is now the 263,022-row cohort.
      claims.push(
        has("copy.headline_follows_the_swap", text, "Showing markets whose price moved, plus sportsbook lines (303,097)"),
        has("copy.moved_half_counted", text, "263,022 outcomes whose price real trading moved"),
        has("copy.excluded_side_counted", text, "Excluded: 349,310 outcomes whose price never moved off its opening line."),
        has(
          "copy.activity_partition_reconciles_on_screen",
          text,
          "263,022 + 349,310 + 40,075 = 652,407 resolved outcomes"
        ),
        has("direction.sentence_names_the_other_cohort", text, "price-unchanged cohort carries the higher calibration error")
      );
      const direction = await attr(p, '[data-testid="calibration-activity-section"]', "data-activity-direction");
      claims.push({
        id: "direction.flips_with_the_data",
        ok: direction === "unchanged_higher",
        detail: `data-activity-direction=${direction}`,
      });
      return claims;
    }, [...SANDBOX_ALLOWANCES]);
  });

  test("unavailable: no cohort language is rendered over data that is not there", async ({ page }, testInfo) => {
    await grade(
      page,
      testInfo,
      "unavailable",
      (r) =>
        json(
          r,
          {
            detail: {
              status: "unavailable",
              reason: "rebuilding",
              message: "Calibration data is temporarily unavailable. It is rebuilt hourly — please retry shortly.",
            },
          },
          503
        ),
      async (text, p) => {
        const claims: Claim[] = [];
        for (const b of BANNED) {
          const hit = b.re.exec(text);
          claims.push({ id: b.id, ok: !hit, detail: hit ? `rendered "${hit[0]}"` : "absent" });
        }
        const named = await attr(p, '[data-testid="calibration-error"]', "data-error-state-name");
        claims.push({
          id: "unavailable.state_names_itself",
          ok: named === "rebuilding",
          detail: `data-error-state-name=${named}`,
        });
        const pageRoot = await p.locator('[data-testid="calibration-page"]').first().isVisible().catch(() => false);
        claims.push({
          id: "unavailable.no_numbers_rendered",
          ok: !pageRoot,
          detail: `calibration-page visible=${pageRoot}`,
        });
        claims.push({
          id: "unavailable.no_cohort_toggle",
          ok: !(await p.locator('[data-testid="calibration-cohort-toggle"]').first().isVisible().catch(() => false)),
          detail: "cohort toggle must not render without a payload",
        });
        return claims;
      },
      // The 503 IS the fixture: a browser logs every failed response as a
      // console error, so this state cannot be clean and must not pretend to be.
      [/503 \(Service Unavailable\)/, ...SANDBOX_ALLOWANCES]
    );
  });
});
