/**
 * #6616 — `/weather` stops printing 100% over a live 99.5¢ book and stops
 * printing nothing at all over a live 0.05¢ one.
 *
 * ═══ WHAT A READER SAW, production 2026-09-16 at 390px ═══
 *
 *   Monthly rainfall   Miami 100% · Seattle 100% · NYC 100% · Houston 100%
 *                      — every one of the four stored `0.995000` on an OPEN
 *                      "Above 1 inch" market. Controls in the same card, same
 *                      code path: Chicago 95, Austin 20, San Francisco 6.
 *   Natural events     "Hurricane Marie category? — Category 1 or above 100%"
 *                      (closes Dec 2), "Number of tornadoes in Sep 2026? —
 *                      Above 25 100%" (closes Oct 1). Both tradeable.
 *   Wild cards         "Lowest daily Arctic sea ice extent in summer 2026"
 *                      served `prob: 100` beside its own `history` of 99.5s.
 *                      One market, one price, two renderings — the card refuted
 *                      itself with no database read.
 *   City ladders       96 `dist` rows across 42 cities served `prob: 0`. Los
 *                      Angeles quotes "63°F or below" AND "64-65°F" at
 *                      `0.000500`; the panel gave each of them no bar, no
 *                      tooltip and no pointer, which tells a reader an outcome
 *                      is impossible by refusing to discuss it.
 *
 * ═══ WHY THIS ONE NEEDED A SERVER CHANGE AND #6610 DID NOT ═══
 *
 * `/entertainment` serves `prob` at one decimal, so its page could divide by 100
 * and call the contract. `weather.py`'s `_highest_prob` was `round(best * 100)`
 * — an `int` — and an integer cannot be un-rounded. The raw probability now
 * travels beside it on every row that prints a percent, and the page reads it
 * through `weatherProbability`, which falls back to `prob / 100` so a payload
 * out of the hourly Redis cache degrades to exactly the old picture rather than
 * to a wrong one.
 *
 * Every assertion renders a SHIPPED component. The percent strings come from
 * `lib/probabilityDisplay`, not from literals retyped here, so this file cannot
 * drift from the rule it is guarding.
 *
 *   TZ=UTC npx jest --testPathPatterns=weatherPercentsJoinTheContract6616
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  ABOVE_NINETY_NINE_PERCENT,
  BELOW_ONE_PERCENT,
} from "@/lib/probabilityDisplay";
import {
  weatherProbability,
  type CityData,
  type EventMarket,
  type MonthlyRain,
  type TempBucket,
} from "@/components/weather/data";
import ProbabilityNumber from "@/components/weather/ProbabilityNumber";
import EventList from "@/components/weather/EventList";
import HurricaneTracker from "@/components/weather/HurricaneTracker";
import DistributionPanel from "@/components/weather/DistributionPanel";

/* ── SWR is the only thing between RainForecast and its payload ─────────── */

let swrPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: undefined }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const RainForecast = require("@/components/weather/RainForecast").default;

/** The half-cent quote behind every `100%` the page printed. */
const NINETY_NINE_FIVE = 0.995;
/** Los Angeles' two coldest buckets, both live, both arriving as `prob: 0`. */
const FIVE_HUNDREDTHS_OF_A_POINT = 0.0005;

/** Strip tags so assertions read what a PERSON reads. */
function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&ldquo;|&rdquo;/g, '"')
    .replace(/&middot;/g, "·")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&gt;/g, ">")
    .replace(/&lt;/g, "<")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

function count(haystack: string, needle: string): number {
  return haystack.split(needle).length - 1;
}

/* ── Specimens, in the shape the route now serves ───────────────────────── */

function monthly(
  city: string,
  prob: number,
  probability?: number,
): MonthlyRain {
  return { city, period: "Sep 2026", prob, probability, src: "kalshi" };
}

function event(q: string, prob: number, probability?: number): EventMarket {
  return { q, prob, probability, src: "kalshi", closes: "Tue, Dec 2" };
}

function bucket(label: string, prob: number, probability?: number): TempBucket {
  return { label, prob, probability };
}

function city(dist: TempBucket[]): CityData {
  return {
    id: "la",
    name: "Los Angeles",
    preferredX: 18.8,
    preferredY: 45.4,
    x: 18.8,
    y: 45.4,
    region: "Americas",
    srcs: ["polymarket"],
    high: { unit: "F", mode: 78, dist },
  };
}

/* ═══ 1. The accessor: one place for the value, one place for the fallback ═ */

describe("#6616 · weatherProbability is the only reader of the raw value", () => {
  test("the served raw value wins", () => {
    expect(weatherProbability({ prob: 100, probability: NINETY_NINE_FIVE })).toBe(
      NINETY_NINE_FIVE,
    );
    expect(
      weatherProbability({ prob: 0, probability: FIVE_HUNDREDTHS_OF_A_POINT }),
    ).toBe(FIVE_HUNDREDTHS_OF_A_POINT);
  });

  test("an absent field falls back to the pre-#6616 rendering, exactly", () => {
    // The hourly Redis cache can serve a payload built before the field
    // existed. `prob / 100` is what the page used to print, so a stale payload
    // degrades to today's picture rather than to a new wrong one.
    expect(weatherProbability({ prob: 83 })).toBe(0.83);
    expect(weatherProbability({ prob: 100 })).toBe(1);
    expect(weatherProbability({ prob: 0 })).toBe(0);
  });

  test("null and a non-number are absence, not a value", () => {
    expect(weatherProbability({ prob: 95, probability: null })).toBe(0.95);
    expect(
      weatherProbability({ prob: 95, probability: NaN as unknown as number }),
    ).toBe(0.95);
  });
});

/* ═══ 2. The split-span number (hero + wild cards) ═════════════════════════ */

/**
 * The digits and the `%` are ADJACENT spans at two sizes — that is why this
 * component takes `probabilityParts` and not the finished string (the #6064
 * shape). So the tags are stripped WITHOUT a separator: a reader sees `>99%`,
 * and `visibleText`'s word-preserving space would read `> 99 %`, which is a
 * fact about the markup and not about the page.
 */
function probabilityNumber(value: number, probability?: number): string {
  return renderToStaticMarkup(
    React.createElement(ProbabilityNumber, { value, probability, size: 64 }),
  )
    .replace(/<[^>]*>/g, "")
    .replace(/&gt;/g, ">")
    .replace(/&lt;/g, "<")
    .trim();
}

describe("#6616 · the 64px hero number obeys the boundary rule", () => {
  test("a 99.5¢ book stops reading as a settled question", () => {
    expect(probabilityNumber(100, NINETY_NINE_FIVE)).toBe(
      ABOVE_NINETY_NINE_PERCENT,
    );
  });

  test("a real price below half a point stops reading as impossible", () => {
    expect(probabilityNumber(0, FIVE_HUNDREDTHS_OF_A_POINT)).toBe(
      BELOW_ONE_PERCENT,
    );
  });

  test("an ACTUAL certainty still prints 100% — the boundaries are real", () => {
    expect(probabilityNumber(100, 1)).toBe("100%");
    expect(probabilityNumber(0, 0)).toBe("0%");
  });

  test("ordinary values are byte-identical to what they printed before", () => {
    expect(probabilityNumber(83, 0.83)).toBe("83%");
    expect(probabilityNumber(6, 0.06)).toBe("6%");
    expect(probabilityNumber(50, 0.5)).toBe("50%");
  });

  test("the server's integer is the digits, the raw value only the rule", () => {
    // `probabilityDisplay.ts:99` — the two rules compose. A card whose server
    // decided 57 prints 57, even though this value rounds to 56 on its own.
    expect(probabilityNumber(57, 0.565)).toBe("57%");
  });

  test("a stale cached payload prints exactly what it printed yesterday", () => {
    expect(probabilityNumber(100)).toBe("100%");
    expect(probabilityNumber(95)).toBe("95%");
  });
});

/* ═══ 3. Natural events — the two live `100%` specimens ════════════════════ */

describe("#6616 · the natural-event rows", () => {
  const TORNADOES = "Number of tornadoes in Sep 2026?";

  function eventList(items: EventMarket[]): string {
    return visibleText(
      renderToStaticMarkup(
        React.createElement(EventList, {
          title: "Tornadoes",
          sub: "Kalshi",
          icon: "🌪️",
          accent: "#6366F1",
          items,
        }),
      ),
    );
  }

  test("an open tornado market stops being reported as settled", () => {
    const text = eventList([event(TORNADOES, 100, NINETY_NINE_FIVE)]);
    expect(text).toContain(ABOVE_NINETY_NINE_PERCENT);
    expect(text).not.toContain(" 100%");
  });

  test("the rows that were already right do not move", () => {
    const text = eventList([
      event("Above 25", 62, 0.62),
      event("Above 50", 20, 0.195),
      event("Above 100", 6, 0.06),
    ]);
    expect(text).toContain("62%");
    expect(text).toContain("20%");
    expect(text).toContain("6%");
    expect(text).not.toContain(ABOVE_NINETY_NINE_PERCENT);
    expect(text).not.toContain(BELOW_ONE_PERCENT);
  });

  test("the hurricane card takes the same medicine", () => {
    const text = visibleText(
      renderToStaticMarkup(
        React.createElement(HurricaneTracker, {
          items: [
            event("Hurricane Marie category?", 100, NINETY_NINE_FIVE),
            event("Hurricane Nadine category?", 44, 0.44),
          ],
        }),
      ),
    );
    expect(text).toContain(ABOVE_NINETY_NINE_PERCENT);
    expect(text).toContain("44%");
    expect(text).not.toContain(" 100%");
  });

  test("a pre-#6616 cached row still prints its integer", () => {
    expect(eventList([event(TORNADOES, 100)])).toContain("100%");
  });
});

/* ═══ 4. Monthly rainfall — the four cities, through the shipped card ═════ */

describe("#6616 · the Monthly rainfall card", () => {
  function rain(monthlyRows: MonthlyRain[]): string {
    swrPayload = { daily: [], monthly: monthlyRows };
    return visibleText(renderToStaticMarkup(React.createElement(RainForecast)));
  }

  const FOUR_CITIES = ["Miami", "Seattle", "NYC", "Houston"];

  test("all four 99.5¢ cities stop claiming the month is decided", () => {
    const text = rain([
      ...FOUR_CITIES.map((c) => monthly(c, 100, NINETY_NINE_FIVE)),
      monthly("Chicago", 95, 0.95),
      monthly("Austin", 20, 0.195),
      monthly("San Francisco", 6, 0.06),
    ]);

    expect(count(text, ABOVE_NINETY_NINE_PERCENT)).toBe(4);
    // The controls are the weight of the finding: the same card, the same code
    // path, and not one of them moves.
    expect(text).toContain("95%");
    expect(text).toContain("20%");
    expect(text).toContain("6%");
    for (const c of FOUR_CITIES) expect(text).toContain(c);
  });

  test("the card prints no bare 100% anywhere", () => {
    const text = rain(FOUR_CITIES.map((c) => monthly(c, 100, NINETY_NINE_FIVE)));
    expect(text).not.toContain(" 100%");
  });

  test("a genuinely settled row would still print 100%", () => {
    // Not a hypothetical: `settled means settled`. The rule is about values
    // strictly inside (0, 1), and 1 is not inside it.
    expect(rain([monthly("Miami", 100, 1)])).toContain("100%");
  });

  test("a pre-#6616 cached payload renders exactly as it did before", () => {
    const text = rain([monthly("Miami", 100), monthly("Chicago", 95)]);
    expect(text).toContain("100%");
    expect(text).toContain("95%");
    expect(text).not.toContain(ABOVE_NINETY_NINE_PERCENT);
  });
});

/* ═══ 5. The city ladder — the `<1%` arm, where the lie was silence ═══════ */

describe("#6616 · a priced temperature bucket is a bucket the reader can see", () => {
  const LADDER: TempBucket[] = [
    bucket("63°F or below", 0, FIVE_HUNDREDTHS_OF_A_POINT),
    bucket("64-65°F", 0, FIVE_HUNDREDTHS_OF_A_POINT),
    bucket("78-79°F", 62, 0.62),
    bucket("80-81°F", 38, 0.3795),
  ];

  function panel(dist: TempBucket[]): string {
    return renderToStaticMarkup(
      React.createElement(DistributionPanel, { city: city(dist) }),
    );
  }

  test("the two live cold buckets get a tooltip that says <1%", () => {
    const markup = panel(LADDER);
    expect(count(visibleText(markup), BELOW_ONE_PERCENT)).toBe(2);
  });

  test("they get the minimum bar height, so the ladder shows they exist", () => {
    // `minHeight: 3` is the whole visual difference between "priced at almost
    // nothing" and "not a thing the venue quotes".
    const priced = panel(LADDER);
    const unpriced = panel([
      bucket("63°F or below", 0, 0),
      bucket("64-65°F", 0, 0),
      ...LADDER.slice(2),
    ]);
    expect(count(priced, "min-height:3px")).toBeGreaterThan(
      count(unpriced, "min-height:3px"),
    );
  });

  test("a bucket the venue does NOT price stays silent", () => {
    // Zero is a real price and absence is not zero, but a bucket standing at
    // exactly 0 has nothing to interrogate — it must not gain a `<1%` tooltip.
    const text = visibleText(
      panel([bucket("63°F or below", 0, 0), ...LADDER.slice(2)]),
    );
    expect(text).not.toContain(BELOW_ONE_PERCENT);
  });

  test("the modal bucket and its headline percent are unchanged", () => {
    const text = visibleText(panel(LADDER));
    expect(text).toContain("62%");
    expect(text).toContain("78-79°F is the modal outcome");
  });

  test("a pre-#6616 cached ladder renders exactly as it did before", () => {
    const text = visibleText(
      panel([bucket("63°F or below", 0), bucket("78-79°F", 62)]),
    );
    expect(text).not.toContain(BELOW_ONE_PERCENT);
    expect(text).toContain("62%");
  });
});
