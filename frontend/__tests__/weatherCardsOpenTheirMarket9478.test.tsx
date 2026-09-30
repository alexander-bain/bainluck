/**
 * #9478 — a /weather market card opens that market's page.
 *
 * ═══ WHAT A READER SAW, production 2026-09-28 3:19 PM PT at 390px ═══
 *
 *   The featured card "Where will it rain on September 28? 99% Philadelphia,
 *   PA" looks like every tappable card on the site. Tapping it only moved the
 *   carousel. Same for every hurricane, earthquake, tornado, climate and wild
 *   card row. The one link on the page was the temperature panel's "View
 *   probability timeline"; `/futures/62786086` rendered the market fine.
 *   `/api/weather/featured` already served `market_id` on every row.
 *
 * Every assertion renders a SHIPPED component with a row in the served shape.
 * The strawman arm of each section renders the same row WITHOUT an id and
 * asserts no link at all: a payload out of the hourly Redis cache, or a route
 * that does not serve the id yet, keeps the card it always had and never
 * links to `/futures/undefined`.
 *
 *   TZ=UTC npx jest --testPathPatterns=weatherCardsOpenTheirMarket9478
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type {
  ClimateMarket,
  EventMarket,
  FeaturedMarket,
  WildCard,
} from "@/components/weather/data";
import EventList from "@/components/weather/EventList";
import HurricaneTracker from "@/components/weather/HurricaneTracker";
import { marketHref } from "@/components/weather/MarketLink";

let swrPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: undefined }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const WeatherHero = require("@/components/weather/WeatherHero").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const ClimateDashboard = require("@/components/weather/ClimateDashboard").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const WildCards = require("@/components/weather/WildCards").default;

/** Every `href` the markup carries, in order. */
function hrefs(markup: string): string[] {
  return Array.from(markup.matchAll(/<a\b[^>]*\bhref="([^"]*)"/g), (m) => m[1]);
}

/* ── Specimens, in the shape the route serves (production, 22:19Z 9/28) ── */

const FEATURED: FeaturedMarket = {
  q: "Where will it rain on September 28?",
  prob: 99,
  probability: 0.99,
  src: "kalshi",
  tag: "Rain",
  closes: "Tue, Sep 29",
  leader: "Philadelphia, PA",
  history: [90, 95, 99],
  market_id: 62786086,
};

function event(q: string, market_id?: number | null): EventMarket {
  return { q, prob: 40, probability: 0.4, src: "kalshi", closes: "Tue, Dec 2", leader: "Category 3", market_id };
}

function climate(q: string, market_id?: number | null): ClimateMarket {
  return { q, prob: 84, probability: 0.84, src: "kalshi", scale: "2030", leader: "Above 10%", market_id };
}

function wild(q: string, market_id?: number | null): WildCard {
  return { q, prob: 3, probability: 0.03, src: "polymarket", tag: "Wild card", market_id };
}

beforeEach(() => {
  swrPayload = undefined;
});

describe("marketHref — the one rule every section uses", () => {
  it("links a real id and refuses every absent or malformed one", () => {
    expect(marketHref(62786086)).toBe("/futures/62786086");
    for (const bad of [undefined, null, 0, -4, 1.5, Number.NaN]) {
      expect(marketHref(bad as number | null | undefined)).toBeNull();
    }
  });
});

describe("the featured card", () => {
  it("opens the market it shows", () => {
    swrPayload = [FEATURED];
    expect(hrefs(renderToStaticMarkup(<WeatherHero />))).toEqual(["/futures/62786086"]);
  });

  it("strawman: a cached row with no id is the plain card, not a dead link", () => {
    swrPayload = [{ ...FEATURED, market_id: undefined }];
    const markup = renderToStaticMarkup(<WeatherHero />);
    expect(markup).toContain("Where will it rain on September 28?");
    expect(hrefs(markup)).toEqual([]);
  });
});

describe("natural-event rows (earthquakes, tornadoes, hurricanes)", () => {
  it("each row with an id opens its own market; a row without one stays a row", () => {
    const items = [event("Hurricane Polo category?", 63100001), event("Number of tornadoes in Sep 2026?")];
    const list = renderToStaticMarkup(<EventList title="Earthquakes" sub="" icon="~" accent="#000" items={items} />);
    expect(hrefs(list)).toEqual(["/futures/63100001"]);
    const tracker = renderToStaticMarkup(<HurricaneTracker items={items} />);
    expect(hrefs(tracker)).toEqual(["/futures/63100001"]);
    // The row without an id still renders, as a row.
    expect(list).toContain("Number of tornadoes in Sep 2026?");
    expect(tracker).toContain("Number of tornadoes in Sep 2026?");
  });
});

describe("climate rows", () => {
  it("each row with an id opens its own market", () => {
    swrPayload = [climate("EV market share in 2030?", 63200002), climate("Global temp record in 2030?", null)];
    const markup = renderToStaticMarkup(<ClimateDashboard />);
    expect(hrefs(markup)).toEqual(["/futures/63200002"]);
    expect(markup).toContain("Global temp record in 2030?");
  });
});

describe("wild cards", () => {
  it("each card with an id opens its own market", () => {
    swrPayload = [wild("Will a supervolcano erupt before 2050?", 63300003), wild("Snow in Miami this year?")];
    const markup = renderToStaticMarkup(<WildCards />);
    expect(hrefs(markup)).toEqual(["/futures/63300003"]);
    expect(markup).toContain("Snow in Miami this year?");
  });
});
