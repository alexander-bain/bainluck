import { test, expect, measureMainRegion } from "../fixtures/audit";
import { classifyMainRegion } from "../helpers/contentState";
import { RSC_PREFETCH } from "../helpers/navigationAborts";

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
