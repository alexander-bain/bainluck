// #6018 — A FUTURES CARD STOPS STAMPING ITS PRICES WITH THE MOMENT WE TOUCHED THE ROW.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// `bainluck.com/search?q=WNBA Champion`, 390px, 2026-09-13 22:47Z
// (`artifacts/lane1b-225/BEFORE-wnba-search-390.png`). Two cards in one result
// list, both headlining Minnesota at 48%:
//
//     WNBA: 2026 Champion              Minnesota Lynx 48% …      Jul 21
//     Women's Pro Basketball Champion  Minnesota 48% …           21h ago
//
// Read against the rows the same minute:
//
//     9413479   row touched 2026-07-21 17:16Z   top five all written 2026-09-13 16:50Z
//     55254662  row touched 2026-09-13 22:16Z   all twelve legs frozen 2026-08-07
//
// Wrong in both directions on one screen — eight weeks of decay claimed over a
// six-hour-old ladder, thirteen minutes claimed over five-week-old prices — and
// the flattering label sat on the older market.
//
// ── THE MECHANISM ────────────────────────────────────────────────────────────
//
// The footer pip was `formatRelativeTime(market.updated_at)`. `updated_at` is
// the MARKET ROW's write time; prices live in `futures_outcomes.last_updated`.
// Metadata/tier/volume/image passes bump the row without moving a price, and the
// pollers move prices on rows whose metadata has not changed in months. Neither
// column is broken — the card read the wrong one.
//
// ── THE RULE ─────────────────────────────────────────────────────────────────
//
// `renderedPricesAsOf` returns the OLDEST stamp among the rows the card draws.
// Oldest because one pip over five rows is read as covering all five, so the
// only claim honest for every row is a floor. Scoped to the drawn rows because
// 9413479 carries an `Other` rung from May that the card never shows. `null`
// when unknowable, and the card then renders nothing (notice 34: if a number
// cannot be shown honestly, leave the space empty) — never a fall back to
// `updated_at`, which is why `PriceAgeSource` does not include it at all.

import { renderedPricesAsOf } from "@/lib/futuresCardPriceAge";
import type { FuturesOutcome } from "@/lib/types";

const leg = (last_updated: string | null, over: Partial<FuturesOutcome> = {}): FuturesOutcome =>
  ({
    id: 1,
    name: "Leg",
    probability: 0.5,
    american_odds: null,
    rank: null,
    rank_change_24h: null,
    probability_change_24h: null,
    movement: null,
    opening_probability: null,
    opening_american_odds: null,
    is_winner: false,
    last_updated,
    ...over,
  }) as FuturesOutcome;

describe("#6018 the two production specimens", () => {
  it("dates a fresh ladder on a stale row by its prices, not by the row", () => {
    // 9413479: the card printed "Jul 21" over prices from that afternoon.
    const asOf = renderedPricesAsOf({
      prices_updated_at: "2026-09-13T16:50:15+00:00",
      top_outcomes: undefined,
      outcomes: undefined,
    });
    expect(asOf).toBe("2026-09-13T16:50:15+00:00");
  });

  it("dates a stale ladder on a fresh row by its prices", () => {
    // 55254662: the card printed "21h ago" over legs frozen five weeks.
    const asOf = renderedPricesAsOf({
      prices_updated_at: "2026-08-07T23:05:24+00:00",
      top_outcomes: undefined,
      outcomes: undefined,
    });
    expect(asOf).toBe("2026-08-07T23:05:24+00:00");
  });
});

describe("#6018 the floor, over the rows the card draws", () => {
  it("takes the OLDEST drawn row, so one stale rung ages the card", () => {
    const asOf = renderedPricesAsOf({
      outcomes: [
        leg("2026-09-13T16:50:00.000Z", { id: 1 }),
        leg("2026-08-01T09:00:00.000Z", { id: 2 }),
        leg("2026-09-13T16:50:00.000Z", { id: 3 }),
      ],
      top_outcomes: undefined,
    });
    expect(asOf).toBe("2026-08-01T09:00:00.000Z");
  });

  it("reads `top_outcomes` when present — the same rows the card renders", () => {
    // The card's own pick is `market.top_outcomes || market.outcomes`. A helper
    // that folded `outcomes` here would age the card to a set it never draws.
    const asOf = renderedPricesAsOf({
      top_outcomes: [leg("2026-09-13T16:50:00.000Z", { id: 1 })],
      outcomes: [leg("2026-05-12T16:17:37.000Z", { id: 99, name: "Other" })],
    });
    expect(asOf).toBe("2026-09-13T16:50:00.000Z");
  });

  it("prefers the server's own arithmetic when it is served", () => {
    // `/api/events/search` computes the floor over the rows IT chose to serve,
    // which is by construction what the card draws.
    const asOf = renderedPricesAsOf({
      prices_updated_at: "2026-09-13T16:50:15+00:00",
      top_outcomes: [leg("2026-01-01T00:00:00.000Z", { id: 1 })],
      outcomes: undefined,
    });
    expect(asOf).toBe("2026-09-13T16:50:15+00:00");
  });
});

describe("#6018 it withholds rather than guesses", () => {
  it("returns null when no drawn row carries a stamp", () => {
    // `/api/events/search`'s `top_outcomes[]` has never carried `last_updated`,
    // so this is the shape served for the whole window of every deploy in which
    // Vercel is ahead of Heroku. Nothing is claimed.
    expect(
      renderedPricesAsOf({
        top_outcomes: [leg(null, { id: 1 }), leg(null, { id: 2 })],
        outcomes: undefined,
      }),
    ).toBeNull();
  });

  it("returns null for a card with no rows at all", () => {
    expect(renderedPricesAsOf({ top_outcomes: undefined, outcomes: undefined })).toBeNull();
    expect(renderedPricesAsOf({ top_outcomes: [], outcomes: [] })).toBeNull();
  });

  it("skips an unstamped row instead of dating the card to the epoch", () => {
    const asOf = renderedPricesAsOf({
      outcomes: [leg(null, { id: 1 }), leg("2026-09-13T16:50:00.000Z", { id: 2 })],
      top_outcomes: undefined,
    });
    expect(asOf).toBe("2026-09-13T16:50:00.000Z");
  });

  it("ignores an unparseable stamp rather than rendering `Invalid Date`", () => {
    expect(
      renderedPricesAsOf({
        prices_updated_at: "not a date",
        top_outcomes: [leg("2026-09-13T16:50:00.000Z", { id: 1 })],
        outcomes: undefined,
      }),
    ).toBe("2026-09-13T16:50:00.000Z");

    expect(
      renderedPricesAsOf({
        prices_updated_at: "",
        top_outcomes: [leg("also not a date", { id: 1 })],
        outcomes: undefined,
      }),
    ).toBeNull();
  });
});
