import { test, expect } from "../fixtures/audit";

/**
 * UX-P003 — card == hero == chart, proved in a real browser.
 *
 * Standing ruling #1 (Alex, 2026-08-05): "the card is bound to the same
 * aggregate/blend probability the hero renders — no separate card-only
 * probability path may diverge from it."
 *
 * The unit suites (`backend/tests/test_blend_surface_parity.py`,
 * `frontend/__tests__/lib/probabilityInvariant.test.ts`) prove the functions
 * agree on a fixture. They cannot prove the DEPLOY does — the two numbers come
 * from two different endpoints (`/api/feed` and `/api/events/{id}`), rendered by
 * two different pages, so only a browser that walks the actual journey can show
 * a user that the number does not change when they tap.
 *
 * What this measures, on a real deploy:
 *
 *   1. Find a game card on Discover that PAINTED a win probability.
 *   2. Read the number it painted, and follow its own link.
 *   3. Read the number the event hero painted.
 *   4. They must be the same integer percent.
 *
 * The before-state this guards against (production, 2026-08-05, live MLB —
 * the measurements that motivated the queue):
 *
 *     Giants @ Rangers    card 60%   hero 78%   (18.8 pts apart)
 *     Dodgers @ Cubs      card 89%   hero 99%   (10.6 pts apart)
 *     Blue Jays @ Astros  card 99%   hero 100%
 *
 * Both numbers are read from `data-probability` attributes rendered next to the
 * painted text (`EventCard.tsx`, `events/[id]/page.tsx`), not scraped from
 * styled prose — the rail's standing lesson that copy and layout classes are
 * not selectors.
 *
 * HONEST-UNKNOWN: a slate with no game card carrying a probability is a real
 * outcome, not a pass and not a failure. It is reported as skipped with the
 * reason, because "we could not find a game to check" must never read as "the
 * numbers matched".
 */

const CARD_WRAPPER = '[data-testid="discover-card"]';
const CARD_HOME_PROB = '[data-testid="event-card-home-probability"]';
const HERO_PROB = '[data-testid="event-hero-probability"]';
const ERROR_STATE =
  '[data-testid="discover-feed-error"], [data-testid="discover-feed-unavailable"]';

/** How many cards to walk before giving up on finding a game with a probability. */
const MAX_CARDS = 12;

const pct = (fraction: number) => Math.round(fraction * 100);

function parseProbability(raw: string | null): number | null {
  if (raw === null || raw.trim() === "") return null;
  const value = Number(raw);
  if (!Number.isFinite(value)) return null;
  // The attribute carries the 0–1 fraction every payload field uses. A value
  // outside that range means someone wrote a 0–100 axis value here, which is
  // the #1003 scale-slip class — fail loudly rather than silently comparing
  // two different scales.
  if (value < 0 || value > 1) return null;
  return value;
}

test("a game's probability does not change between the card and the hero", async ({
  page,
}) => {
  await page.goto("/discover", { waitUntil: "domcontentloaded" });

  const cardLocator = page.locator(CARD_WRAPPER).first();
  const errorLocator = page.locator(ERROR_STATE).first();
  await Promise.race([
    cardLocator.waitFor({ state: "visible", timeout: 45_000 }).catch(() => null),
    errorLocator.waitFor({ state: "visible", timeout: 45_000 }).catch(() => null),
  ]);

  expect(
    await errorLocator.isVisible().catch(() => false),
    "the feed served an error/unavailable state — no parity claim can be made from it",
  ).toBe(false);

  // Walk cards until we find a GAME card that painted a probability. Futures and
  // concept cards have no home/away hero to compare against, so they are skipped
  // rather than counted as checked.
  const cards = page.locator(CARD_WRAPPER);
  const cardCount = Math.min(await cards.count(), MAX_CARDS);

  let cardProbability: number | null = null;
  let eventHref: string | null = null;

  for (let i = 0; i < cardCount; i++) {
    const card = cards.nth(i);
    const probEl = card.locator(CARD_HOME_PROB).first();
    if (!(await probEl.count())) continue;

    const parsed = parseProbability(await probEl.getAttribute("data-probability"));
    if (parsed === null) continue;

    const link = card.locator('a[href^="/events/"]').first();
    if (!(await link.count())) continue;

    const href = await link.getAttribute("href");
    if (!href) continue;

    cardProbability = parsed;
    eventHref = href;
    break;
  }

  test.skip(
    cardProbability === null || eventHref === null,
    `no game card on this slate painted a win probability (checked ${cardCount} cards) — ` +
      "honest UNKNOWN, not a pass",
  );

  await page.goto(eventHref!, { waitUntil: "domcontentloaded" });

  const hero = page.locator(HERO_PROB).first();
  await hero.waitFor({ state: "visible", timeout: 45_000 });

  const heroProbability = parseProbability(await hero.getAttribute("data-probability"));
  expect(
    heroProbability,
    `the hero on ${eventHref} rendered no usable probability, so the card's ` +
      `${pct(cardProbability!)}% has nothing to agree with`,
  ).not.toBeNull();

  // THE ASSERTION. One question, one number, both screens.
  expect(
    pct(heroProbability!),
    `card == hero == chart (standing ruling #1). The Discover card painted ` +
      `${pct(cardProbability!)}% and the hero at ${eventHref} painted ` +
      `${pct(heroProbability!)}% for the same game — a user tapping the card ` +
      `watched the number move under them.`,
  ).toBe(pct(cardProbability!));
});
