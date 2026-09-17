/**
 * #6018 — THE FUTURES CARD'S AGE PIP, READ OFF RENDERED MARKUP.
 *
 * `lib/futuresCardPriceAge` is unit-tested next door
 * (`__tests__/futuresCardPriceAge6018.test.ts`). This file proves the WIRING:
 * that `components/FuturesCard` actually prints the helper's answer and no
 * longer prints `market.updated_at`. A correct helper the card does not call is
 * the silent no-op this guards, and the whole defect was a card reading the
 * wrong field — so the claim has to be read off the markup, not off a function.
 *
 * ── THE TWO PRODUCTION SPECIMENS ─────────────────────────────────────────────
 *
 * `bainluck.com/search?q=WNBA Champion`, 390px, 2026-09-13 22:47Z
 * (`artifacts/lane1b-225/BEFORE-wnba-search-390.png`):
 *
 *     WNBA: 2026 Champion   (9413479)   pip "Jul 21"   prices all 2026-09-13 16:50Z
 *     WNBA Champion         (55254662)  pip "21h ago"  prices all 2026-08-07 23:05Z
 *
 * Wrong in both directions in one result list. Both are replayed below in the
 * exact payload shape each surface serves them in.
 *
 * The clock is FROZEN (`jest.useFakeTimers`) at the minute of the screenshot, so
 * the expected strings are fixed text and not a moving target — notice/gotcha
 * "a test anchor must not branch on the clock".
 */

import { renderToStaticMarkup } from "react-dom/server";
import FuturesCard from "../../components/FuturesCard";
import type { FuturesMarket, FuturesOutcome } from "../../lib/types";
import specimen from "../fixtures/futures114175PricelessTail6803.json";

/** The minute of the screenshot, so every relative string below is fixed. */
const SHOT = new Date("2026-09-13T22:47:00.000Z");

function leg(
  id: number,
  name: string,
  probability: number,
  last_updated: string | null,
): FuturesOutcome {
  return {
    id,
    name,
    probability,
    american_odds: null,
    rank: null,
    rank_change_24h: null,
    probability_change_24h: null,
    movement: null,
    opening_probability: null,
    opening_american_odds: null,
    is_winner: null,
    last_updated,
  } as unknown as FuturesOutcome;
}

function card(over: Partial<FuturesMarket>): FuturesMarket {
  return {
    id: 9413479,
    name: "WNBA: 2026 Champion",
    description: null,
    source: "polymarket",
    category: "basketball",
    sport: null,
    sport_name: null,
    llm_sport_category: "basketball",
    external_id: null,
    mutually_exclusive: true,
    commence_time: null,
    resolution_date: null,
    outcome_count: 5,
    created_at: null,
    status: "open",
    ...over,
  } as unknown as FuturesMarket;
}

/** The card's footer pip, or null when it renders nothing. */
function pip(market: FuturesMarket): string | null {
  const html = renderToStaticMarkup(<FuturesCard market={market} />);
  // The footer is the last `text-micro text-text-muted` span on the card.
  const spans = [...html.matchAll(/class="text-micro text-text-muted"[^>]*>([^<]*)</g)];
  if (spans.length === 0) return null;
  return spans[spans.length - 1][1].trim();
}

beforeAll(() => {
  jest.useFakeTimers().setSystemTime(SHOT);
});

afterAll(() => {
  jest.useRealTimers();
});

describe("#6018 the pip speaks for the prices", () => {
  it("a fresh ladder on a row touched in July no longer prints Jul 21", () => {
    // Search shape: `top_outcomes[]` carries no stamps; the server states the
    // floor in `prices_updated_at`.
    const market = card({
      updated_at: "2026-07-21T17:16:38+00:00",
      prices_updated_at: "2026-09-13T16:50:15+00:00",
      top_outcomes: [
        leg(1, "Minnesota Lynx", 0.475, null),
        leg(2, "Las Vegas Aces", 0.135, null),
      ],
    });

    expect(pip(market)).toBe("5h ago");
    expect(pip(market)).not.toBe("Jul 21");
  });

  it("a five-week-old ladder on a row touched minutes ago no longer prints 13m ago", () => {
    const market = card({
      id: 55254662,
      name: "WNBA Champion",
      updated_at: "2026-09-13T22:16:03+00:00",
      prices_updated_at: "2026-08-07T23:05:24+00:00",
      top_outcomes: [
        leg(1, "Minnesota Lynx", 0.48, null),
        leg(2, "Las Vegas Aces", 0.14, null),
      ],
    });

    expect(pip(market)).toBe("Aug 7");
  });

  it("the detail payload's own per-row stamps carry a pinned card", () => {
    // My Stuff and Preferences fetch `/api/futures/{id}`, which sends
    // `outcomes[]` with `last_updated` and no `prices_updated_at`. Same floor,
    // computed client-side — so a pinned card keeps an age pip on the day this
    // ships, rather than losing one while a second serializer catches up.
    const market = card({
      updated_at: "2026-07-21T17:16:38+00:00",
      outcomes: [
        leg(1, "Minnesota Lynx", 0.475, "2026-09-13T16:50:15+00:00"),
        leg(2, "Las Vegas Aces", 0.135, "2026-09-12T16:50:15+00:00"),
      ],
    });

    // The FLOOR of the two drawn rows, not the fresher one — the card's own
    // vocabulary for a day is "1d ago" (`formatRelativeTime`), not "yesterday".
    expect(pip(market)).toBe("1d ago");
    expect(pip(market)).not.toBe("5h ago"); // the newer of the two rows
  });
});

describe("#6018 what it refuses to say", () => {
  it("renders no pip at all when the payload cannot date its prices", () => {
    // The window of every deploy in which Vercel is ahead of Heroku: search
    // sends `top_outcomes[]` with no stamps and no `prices_updated_at`. The
    // corner goes empty rather than falling back to the row's write time.
    const market = card({
      updated_at: "2026-09-13T22:16:03+00:00",
      top_outcomes: [leg(1, "Minnesota Lynx", 0.475, null)],
    });

    const printed = pip(market);
    expect(printed).not.toBe("31m ago"); // what `updated_at` would have given
    expect(printed === null || printed === "").toBe(true);
  });

  it("an `updated_at` alone can never reach the footer", () => {
    // The strongest form of the claim: the ONLY field that used to feed the pip
    // is present and recent, everything else is absent, and nothing is printed.
    const market = card({
      updated_at: "2026-09-13T22:46:00+00:00",
    });

    const printed = pip(market);
    expect(printed === null || printed === "").toBe(true);
  });
});

/**
 * #6803 — THE SAME WIRING, ONE DOOR FURTHER IN.
 *
 * Appended here rather than given its own file because it is the same claim
 * about the same span: the card prints the helper's answer. The unit rule lives
 * in `__tests__/futuresCardPricelessRowFloor6803.test.ts`; this proves a reader
 * of a PINNED card sees it, which is the surface #6803 was filed about
 * (`/api/futures/{id}` — My Stuff and Preferences). That surface is auth-gated,
 * so under notice 49 this rendered-output read is what closes it in place of a
 * LOOK no lane can take.
 *
 * Its own frozen clock: the minute the fixture was captured, so "3h ago" is
 * fixed text rather than a moving target.
 */
describe("#6803 a priceless rung does not date the pinned card", () => {
  /** `/api/futures/114175`, captured 2026-09-17T23:05Z. */
  const CAPTURE = new Date("2026-09-17T23:05:00.000Z");

  beforeAll(() => {
    jest.setSystemTime(CAPTURE);
  });

  afterAll(() => {
    jest.setSystemTime(SHOT);
  });

  const ladder = (): FuturesOutcome[] =>
    (specimen.outcomes as Array<{
      id: number;
      name: string;
      probability: number | null;
      last_updated: string;
    }>).map((o) => leg(o.id, o.name, o.probability as number, o.last_updated));

  it("prints the age of the fourteen prices, not of the five placeholders", () => {
    const market = card({
      id: 114175,
      name: "Who will be UFC Heavyweight champion at the end of 2026?",
      outcome_count: 19,
      // The row's own write time is irrelevant and present on purpose.
      updated_at: "2026-09-17T19:50:18+00:00",
      outcomes: ladder(),
    });

    expect(pip(market)).toBe("3h ago");
    // What the reader actually saw: 128 days of understatement, bought from
    // five rungs that display no number at all.
    expect(pip(market)).not.toBe("May 12");
  });

  it("a ladder of nothing but placeholders prints no pip rather than May 12", () => {
    // The floor is withheld (notice 34), not recovered from the rows the helper
    // just refused to count. A card drawing no prices has no price age.
    const market = card({
      id: 114175,
      outcome_count: 5,
      updated_at: "2026-09-17T19:50:18+00:00",
      outcomes: (specimen.outcomes as Array<{
        id: number;
        name: string;
        probability: number | null;
        last_updated: string;
      }>)
        .filter((o) => o.probability == null)
        .map((o) => leg(o.id, o.name, o.probability as number, o.last_updated)),
    });

    const printed = pip(market);
    expect(printed).not.toBe("May 12");
    expect(printed === null || printed === "").toBe(true);
  });
});
