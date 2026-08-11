import { test, expect, measureMainRegion } from "../fixtures/audit";
import { classifyMainRegion } from "../helpers/contentState";
import { RSC_PREFETCH } from "../helpers/navigationAborts";
import { findSettledEventWithProps } from "../helpers/settledSpecimen";

/** Backend origin, for the one journey that has to FIND its specimen. */
const API_BASE = (process.env.AUDIT_API_BASE_URL || "https://api.bainluck.com").replace(/\/$/, "");

/**
 * UX-P041 Item 2 — the EVENT-PAGE pack.
 *
 * Why this exists. Four consecutive UX cycles fixed an event-page surface and
 * none of them could photograph it: UX-P036 (#1626, the divergence section),
 * UX-P037 (#1627, Additional Markets), UX-P039 (#1635, market-map ladders) and
 * UX-P040 (#1638, settled prop grades). Every one shipped on unit evidence
 * alone. The rail has had a Discover pack since L2-221 and never grew one for
 * the second-most-walked surface in the product.
 *
 * Under ruling 014 this pack is a tier in its own right: it inherits the usage
 * weight of the four fixes it makes verifiable, rather than scoring zero for
 * having no user of its own.
 *
 * It walks the real north-star journey rather than deep-linking an id — find
 * tonight's game on /sports, open it, read the probability — so a broken link
 * or an empty slate fails here instead of being papered over by a hard-coded
 * event that may not exist tomorrow.
 */

/** The sports feed's game cards. Same stable hook the page ships for its own tests. */
const SPORTS_CARD = '[data-testid="sports-card"]';
/** Any event detail link. The pack must not depend on one event id surviving to tomorrow. */
const EVENT_LINK = 'main a[href^="/events/"]';
/** The hero number — "read the probability" is the whole point of the page. */
const HERO_PROBABILITY = '[data-testid="event-hero-probability"]';
/**
 * The settled hero (UX-P043 / #1649).
 *
 * A finished game shows a winner, not a big number — "settled means settled" is
 * a standing ruling, and the probability testid deliberately does not exist on
 * that branch. The pack's first dispatch (run 31356326468) opened the first
 * game on /sports at 04:43 UTC, got a FINAL, and failed 4/4 on a hero that was
 * working correctly.
 *
 * Evening is exactly when people open this page, so the fix is to prove the
 * settled hero too rather than to hunt for a game that is still in progress.
 * Either hero counts as "the page answered"; which one it was is recorded.
 */
const HERO_SETTLED = '[data-testid="event-hero-settled"]';
const HERO_ANY = `${HERO_PROBABILITY}, ${HERO_SETTLED}`;

/**
 * Next.js prefetches the RSC payload of every `<Link>` on /sports and cancels
 * those prefetches when this spec clicks through. Declared rather than
 * filtered: #1525 rules out widening the rail's network checks and prescribes
 * "a declared, named allowance that fails when it stops firing". The shared
 * evaluator excuses one only if it is genuinely an abort AND not a feed
 * request, so #1525 Shape A stays graded.
 *
 * Measured base rate before declaring: 7-12 per journey, 8 of 8 journeys across
 * two dispatches (31355571532 @ abdcf410, 31356326468 @ f78b8a6d).
 */
// UX-P047 (#1648 P1): imported from the shared module rather than restated —
// `discover-smoke` now declares the same allowance, and two specs owning two
// copies of one token is the drift this cycle exists to end.

/**
 * C229's P1, now enforceable in a real browser.
 *
 * The animation split (UX-P038) left converted call sites painting at
 * `opacity: 0` until an optional chunk resolved, so ready content could be
 * invisible — and permanently invisible if the chunk failed. UX-P041 Item 0
 * repaired it and proved it at the server-render level. This proves it where
 * the user actually is.
 *
 * Deliberately narrow, so it stays a signal rather than noise: an element only
 * counts as wrongly-hidden if it has TEXT, occupies a real box, and still
 * computes to `opacity: 0`. Collapsed menus and unmounted panels carry
 * `display: none` and therefore have no box, so they are excluded by
 * construction rather than by an allowlist someone has to maintain.
 */
async function invisibleTextNodes(page: { evaluate: <T>(fn: () => T) => Promise<T> }) {
  return page.evaluate(() => {
    const main = document.querySelector("main") ?? document.body;
    const bad: Array<{ tag: string; text: string; opacity: string }> = [];
    for (const el of Array.from(main.querySelectorAll<HTMLElement>("*"))) {
      const text = (el.textContent ?? "").trim();
      if (!text) continue;
      const rect = el.getBoundingClientRect();
      if (rect.width < 1 || rect.height < 1) continue;
      const opacity = getComputedStyle(el).opacity;
      if (parseFloat(opacity) === 0) {
        bad.push({ tag: el.tagName.toLowerCase(), text: text.slice(0, 60), opacity });
      }
    }
    // De-duplicate ancestors reporting the same subtree text.
    const seen = new Set<string>();
    return bad.filter((b) => {
      if (seen.has(b.text)) return false;
      seen.add(b.text);
      return true;
    });
  });
}

/**
 * UX-P049 / UX-P053 (#1650) — the settled-props specimen search now lives in
 * `helpers/settledSpecimen`, whose header carries the full measurement.
 *
 * WHY IT IS A SEARCH AT ALL. The journeys below deliberately walk the real
 * north-star journey: open /sports, click whatever game is first. That is the
 * right shape for "can a reader get to a game and read the probability", and
 * exactly the wrong shape for #1650, whose defect only appears on a SETTLED game
 * that PUBLISHES PLAYER PROPS. The obvious alternative — a workflow input
 * carrying an event id — was rejected twice over: it needs
 * `.github/workflows/browser-audit.yml`, a barred file, and a pinned id rots,
 * which is the failure this pack's own header warns about.
 *
 * WHY IT MOVED OUT OF THIS FILE. The search is pure logic over an injected
 * fetch, and while it sat here the only way to exercise it was to dispatch a run
 * against whatever slate happened to exist. That slate is what defeated it: at
 * 18:10 PT the completed window contains no props-bearing game at all, so a live
 * dispatch could neither prove nor disprove a change to the finder. The contract
 * suite now pins the behaviour against fixtures.
 */

/**
 * #1650's contradiction, stated as the browser sees it.
 *
 * The Player Props header claims one of exactly two things about a finished
 * game: "Final · graded results", or "Final · per-player grading unavailable
 * for this game". The bug was the first sentence printed above a list in which
 * NOTHING was graded — every row reading "Resolved · grading unavailable" under
 * a header asserting the opposite, with WHAT HIT adding a third phrasing
 * ("grading pending") for the same backend state.
 *
 * Note what is NOT asserted: a mixed page is legitimate. "graded results" over
 * a list where SOME rows are ungraded is honest, so the check is the narrow one
 * — a header claiming grades must be able to point at one.
 */
const GRADED_HEADER = "Final · graded results";
const NO_GRADE_HEADER = "Final · per-player grading unavailable for this game";
const NO_GRADE_ROW = "Resolved · grading unavailable";

test("settled props are described one way, not three", async ({ page, journey }) => {
  const startedAt = Date.now();

  const specimen = await findSettledEventWithProps((url) => page.request.get(url), API_BASE);

  // Navigate first, so a failed search still produces a terminal screenshot of
  // *something* rather than an empty artifact.
  if (specimen) {
    await page.goto(`/events/${specimen.id}`, { waitUntil: "domcontentloaded" });
    await page
      .getByText(/Player Props/i)
      .first()
      .waitFor({ state: "visible", timeout: 45_000 })
      .catch(() => null);
  } else {
    await page.goto("/sports", { waitUntil: "domcontentloaded" });
  }

  // Explicitly bounded: an unguarded landmark read hangs for the whole
  // actionTimeout if `main` never mounts, and the rail has already been bitten
  // once by an unbounded wait eating the evidence it was collecting.
  const body = specimen
    ? ((await page.locator("main").first().textContent({ timeout: 15_000 }).catch(() => "")) ?? "")
    : "";
  const claimsGraded = body.includes(GRADED_HEADER);
  const claimsNoGrade = body.includes(NO_GRADE_HEADER);
  const ungradedRows = body.split(NO_GRADE_ROW).length - 1;

  const mainRegion = await measureMainRegion(page, '[data-testid="discover-skeleton"]');

  await journey.finish({
    journeyId: "event.page.settled_props_verdict",
    realCardFound: !!specimen && (claimsGraded || claimsNoGrade),
    firstCardMs: specimen ? Date.now() - startedAt : null,
    mainRegion,
    allowedNavigationAborts: [RSC_PREFETCH],
  });

  expect(
    specimen,
    "no recently-completed event published any player props — the #1650 surface " +
      "could not be reached, so this run collected no evidence about it",
  ).not.toBeNull();

  expect(
    claimsGraded || claimsNoGrade,
    `event ${specimen?.id} has ${specimen?.propCount} player props but rendered neither ` +
      `settled Player Props header — the surface under test did not appear`,
  ).toBe(true);

  /**
   * The oracle is the PAYLOAD, not a second reading of the screen.
   *
   * Counting verdict words in the rendered text would be scraping the same
   * surface the header is on, so a wrong header and a wrong row would agree and
   * pass. The backend's own `hit` field is the independent input both are
   * supposed to be describing — which is precisely the shape of the bug: one
   * backend state, three vocabularies.
   *
   * Both directions, per gotcha #43. A page with SOME graded rows is honest
   * under the graded header, so the check is not "no ungraded rows" — it is
   * that the header agrees with whether anything was graded at all.
   */
  if (specimen && specimen.gradedCount === 0) {
    expect(
      claimsGraded,
      `#1650: event ${specimen.id} has ${specimen.propCount} props and the backend graded ` +
        `NONE of them, yet the page claims "${GRADED_HEADER}" (${ungradedRows} row(s) say ` +
        `"${NO_GRADE_ROW}" underneath it)`,
    ).toBe(false);
  } else if (specimen) {
    expect(
      claimsNoGrade,
      `#1650 inverted: the backend graded ${specimen.gradedCount} of ${specimen.propCount} props, ` +
        `yet the page claims "${NO_GRADE_HEADER}" — the contradiction has changed sides, not gone`,
    ).toBe(false);
  }
});

test("event page opens from the sports feed and shows a probability", async ({ page, journey }) => {
  const startedAt = Date.now();

  await page.goto("/sports", { waitUntil: "domcontentloaded" });

  // The slate has to produce a game before the pack can say anything about an
  // event page. An empty slate is a legitimate state of /sports but NOT a pass
  // for this journey — it means no evidence was collected, and the rail's whole
  // rule is that a run with no evidence is not green.
  const link = page.locator(EVENT_LINK).first();
  await Promise.race([
    link.waitFor({ state: "visible", timeout: 45_000 }).catch(() => null),
    page.locator(SPORTS_CARD).first().waitFor({ state: "visible", timeout: 45_000 }).catch(() => null),
  ]);

  const linkFound = await link.isVisible().catch(() => false);
  const href = linkFound ? await link.getAttribute("href") : null;

  if (linkFound) {
    await link.click();
    await page.waitForURL(/\/events\//, { timeout: 45_000 }).catch(() => null);
  }

  const heroLocator = page.locator(HERO_ANY).first();
  await heroLocator.waitFor({ state: "visible", timeout: 45_000 }).catch(() => null);
  const heroVisible = await heroLocator.isVisible().catch(() => false);
  const heroText = heroVisible ? ((await heroLocator.textContent()) ?? "").trim() : null;

  // Which hero answered is evidence, not a detail: a run that only ever sees
  // settled games has not proven the live path, and vice versa.
  const settledHero = await page.locator(HERO_SETTLED).first().isVisible().catch(() => false);

  const realCardFound = heroVisible && !!heroText;
  const firstCardMs = realCardFound ? Date.now() - startedAt : null;

  const mainRegion = await measureMainRegion(page, '[data-testid="discover-skeleton"]');

  await journey.finish({
    journeyId: "event.page.probability",
    realCardFound,
    firstCardMs,
    mainRegion,
    allowedNavigationAborts: [RSC_PREFETCH],
  });

  const region = classifyMainRegion(mainRegion);
  expect(
    region.nonBlank,
    `the event page must render content, not a loading shell — ${region.state}: ${region.detail}`,
  ).toBe(true);
  expect(linkFound, "the sports feed must offer at least one event link to open").toBe(true);
  expect(page.url(), `expected an event detail URL after clicking ${href}`).toMatch(/\/events\//);
  expect(
    realCardFound,
    settledHero
      ? "the event page must show its settled hero (winner treatment)"
      : "the event page must show its hero probability",
  ).toBe(true);
});

test("event page content is never painted invisible", async ({ page, journey }) => {
  const startedAt = Date.now();

  await page.goto("/sports", { waitUntil: "domcontentloaded" });
  const link = page.locator(EVENT_LINK).first();
  await link.waitFor({ state: "visible", timeout: 45_000 }).catch(() => null);
  const linkFound = await link.isVisible().catch(() => false);
  if (linkFound) {
    await link.click();
    await page.waitForURL(/\/events\//, { timeout: 45_000 }).catch(() => null);
  }

  const heroLocator = page.locator(HERO_ANY).first();
  await heroLocator.waitFor({ state: "visible", timeout: 45_000 }).catch(() => null);
  const heroVisible = await heroLocator.isVisible().catch(() => false);

  const hidden = await invisibleTextNodes(page);
  const mainRegion = await measureMainRegion(page, '[data-testid="discover-skeleton"]');

  await journey.finish({
    journeyId: "event.page.paints_visible",
    realCardFound: heroVisible,
    firstCardMs: heroVisible ? Date.now() - startedAt : null,
    mainRegion,
    allowedNavigationAborts: [RSC_PREFETCH],
  });

  expect(linkFound, "the sports feed must offer at least one event link to open").toBe(true);
  expect(
    hidden,
    `content is rendered but painted at opacity 0 — the C229 P1 class. ` +
      `Offenders: ${JSON.stringify(hidden)}`,
  ).toEqual([]);
});
