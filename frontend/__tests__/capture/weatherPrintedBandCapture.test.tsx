/**
 * UX-P192 — A LIVE PRICE ON `/weather` STOPS PRINTING AS IMPOSSIBLE.
 *
 * ═══ WHAT THIS IS ═══
 *
 * Since UX-P046 the site has had one home for the decision "what percentage does
 * this probability print", and its rule is one sentence: **rounding may never
 * move a probability across a boundary it is not on.** A value strictly inside
 * (0, 1) is neither impossible nor certain, so it prints `<1%` or `>99%` rather
 * than `0%` or `100%`. Every surface adopted it. `/weather` did not.
 *
 * It could not have. The weather wire carried only `prob`, the rounded integer,
 * and **an integer cannot be un-rounded** — a bucket quoted at 0.0015 arrives as
 * `0` and there is nothing left to tell it apart from a market nobody is making.
 * So the backend now ships the pair (`prob` plus the `probability` it came from,
 * built together by `_printed`), and every printed number on the page goes
 * through `weatherPercent`, this module's adapter onto `formatProbabilityPercent`.
 *
 * ═══ THE READER COUNT ═══
 *
 * Measured on production 2026-08-30, banked in
 * `backend/tests/fixtures/uxp192_printed_band.json`:
 *
 *     571  numbers served across the six weather payloads
 *     130  of them printing `0%`   —  22.8% of the page
 *
 * And in the population those payloads are drawn from: **0 exact zeros, 0
 * unpriced outcomes**, out of 2,663. There is no honest `0%` on this page. Every
 * one of the 130 was printed over a price a market was actively making.
 *
 * Los Angeles (market 59803955), on the served `/cities` payload: four of eleven
 * temperature buckets printed `0%`, priced 0.0015, 0.003, 0.003 and 0.0015, in a
 * distribution whose own favourite is 43.5%. Four impossibilities in a forecast
 * that contains none.
 *
 * ═══ WHAT EVERY ROW HERE IS MADE OF ═══
 *
 * The SHIPPED components, rendered, with the specimens' MEASURED prices. Nothing
 * re-derives a percentage: the expected strings come from the fixture's `after`
 * column, which `test_weather_printed_band_uxp192.py` independently proves is the
 * contract's rule and not a hand-typed guess.
 *
 * ⚠️ `renderToStaticMarkup` EMITS HTML ENTITIES. `<1%` arrives as `&lt;1%`. The
 * `visibleText` helper this repo copies between capture tests unescapes `&amp;`
 * and `&#x27;` but NOT `&lt;`/`&gt;`, so a card printing exactly the right thing
 * reads as one that is not (banked by UX-P191). The helper below unescapes both.
 *
 *   TZ=UTC npx jest --testPathPatterns=weatherPrintedBandCapture
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

const FRONTEND = path.join(__dirname, "..", "..");
const REPO = path.join(FRONTEND, "..");
const FIXTURE = path.join(
  REPO,
  "backend",
  "tests",
  "fixtures",
  "uxp192_printed_band.json",
);

const banked = JSON.parse(fs.readFileSync(FIXTURE, "utf8"));

interface SpecimenOutcome {
  label: string;
  probability: number;
  before: string;
  after: string;
}
interface Specimen {
  market_id: number;
  city: string;
  name: string;
  source: string;
  outcomes: SpecimenOutcome[];
}

const SPECIMENS: Specimen[] = banked.specimens;
const LA = SPECIMENS.find((s) => s.city === "Los Angeles")!;
const BEIJING = SPECIMENS.find((s) => s.city === "Beijing")!;

/* ── SWR is the only thing between a weather component and its payload ── */

let swrPayload: unknown;
let swrError: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: swrError }),
}));

/* eslint-disable @typescript-eslint/no-var-requires */
const DistributionPanel = require("@/components/weather/DistributionPanel").default;
const EventList = require("@/components/weather/EventList").default;
const WeatherHero = require("@/components/weather/WeatherHero").default;
const WildCards = require("@/components/weather/WildCards").default;
const ClimateDashboard = require("@/components/weather/ClimateDashboard").default;
const RainForecast = require("@/components/weather/RainForecast").default;
const { weatherPercent, hasPrice } = require("@/components/weather/data");
/* eslint-enable @typescript-eslint/no-var-requires */

/**
 * Strip tags so assertions read what a PERSON reads.
 *
 * `&lt;` and `&gt;` are unescaped FIRST and deliberately: they are the two
 * characters this entire queue is about, and every copy of this helper in the
 * repo omits them.
 */
function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&ldquo;|&rdquo;/g, '"')
    .replace(/&middot;/g, "·")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    // ⚠️ `ProbabilityNumber` renders the `%` in its OWN smaller span, so
    // stripping tags to a space reads the 64px hero as `<1 %` — and would read
    // an ordinary card as `68 %`. No real copy on this page puts a space before
    // a percent sign, so rejoining is unambiguous. Without this line the hero
    // is unassertable, which is how it stayed unasserted.
    .replace(/(\S) %/g, "$1%")
    .trim();
}

/**
 * `0%` is a SUBSTRING of `30%`, `40%`, `100%`… Every "the page no longer says
 * 0%" assertion in the first draft of this file passed or failed on whether the
 * specimen happened to contain a round number — Beijing's `30%` and `40%` made
 * it fail while Los Angeles' identical defect passed.
 */
function printsZeroPercent(text: string): boolean {
  return /(?<![0-9])0%/.test(text);
}
function printsHundredPercent(text: string): boolean {
  return /(?<![0-9])100%/.test(text);
}

function withSwr(payload: unknown, component: unknown, error?: unknown): string {
  swrPayload = payload;
  swrError = error;
  return renderToStaticMarkup(React.createElement(component as never));
}

/** The served `dist` shape for a specimen — the pair, exactly as `_printed` emits it. */
function servedDist(spec: Specimen) {
  return spec.outcomes.map((o) => ({
    label: o.label,
    prob: Math.floor(o.probability * 100 + 0.5),
    probability: o.probability,
  }));
}

function cityPayload(spec: Specimen) {
  return {
    id: spec.city.toLowerCase().replace(/ /g, "_"),
    name: spec.city,
    preferredX: 10,
    preferredY: 10,
    x: 10,
    y: 10,
    region: "Americas" as const,
    srcs: [spec.source] as ("kalshi" | "polymarket")[],
    marketId: spec.market_id,
    high: { unit: "C" as const, mode: 32, dist: servedDist(spec) },
  };
}

/* ═══ 1 · the banked BEFORE is genuinely the broken state ══════════════════ */

describe("UX-P192 · the banked payload really did print impossibilities", () => {
  test("the population contains no honest zero at all", () => {
    expect(banked.population.exact_zero).toBe(0);
    expect(banked.population.unpriced).toBe(0);
    expect(banked.population.interior_prints_zero).toBe(288);
  });

  test("130 of the 571 served numbers printed 0%", () => {
    expect(banked.served.total).toEqual({
      numbers: 571,
      zeros: 130,
      hundreds: 0,
    });
  });

  test("the LA specimen has four zeros over live prices, and seven controls", () => {
    const changed = LA.outcomes.filter((o) => o.before !== o.after);
    expect(changed).toHaveLength(4);
    expect(changed.every((o) => o.before === "0%" && o.after === "<1%")).toBe(true);
    expect(changed.every((o) => o.probability > 0)).toBe(true);
    expect(LA.outcomes.filter((o) => o.before === o.after)).toHaveLength(7);
  });
});

/* ═══ 2 · the adapter itself ═══════════════════════════════════════════════ */

describe("UX-P192 · weatherPercent is the single home, not a second rule", () => {
  test("every specimen price prints the fixture's `after` string", () => {
    for (const spec of SPECIMENS) {
      for (const o of spec.outcomes) {
        expect([spec.city, o.label, weatherPercent({
          prob: Math.floor(o.probability * 100 + 0.5),
          probability: o.probability,
        })]).toEqual([spec.city, o.label, o.after]);
      }
    }
  });

  test("a served integer with NO probability degrades to exactly the old number", () => {
    // The hourly Redis cache can serve a payload built before `probability` was
    // on the wire. For that hour the page must print what it printed yesterday —
    // NOT invent a `<1%` it has no evidence for.
    for (const o of LA.outcomes) {
      const prob = Math.floor(o.probability * 100 + 0.5);
      expect(weatherPercent({ prob })).toBe(o.before);
    }
    expect(weatherPercent({ prob: 0 })).toBe("0%");
    expect(weatherPercent({ prob: 100 })).toBe("100%");
  });

  test("the override cannot buy a boundary the value is not on", () => {
    // The composition that makes the pair worth shipping: `prob` decides the
    // INTEGER, the probability decides the BAND. A server-decided 100 over a
    // probability of 0.996 is still `>99%`.
    expect(weatherPercent({ prob: 100, probability: 0.996 })).toBe(">99%");
    expect(weatherPercent({ prob: 0, probability: 0.004 })).toBe("<1%");
    expect(weatherPercent({ prob: 100, probability: 1 })).toBe("100%");
    expect(weatherPercent({ prob: 0, probability: 0 })).toBe("0%");
  });

  test("the server's integer WINS where it differs from a naive re-round", () => {
    // ⚠️ Every other assertion in this file passes with the `{ rendered }`
    // option deleted, because the server rounds by the same rule and the two
    // agree. They diverge only where the CARD-level decision moved the integer
    // (#2060): `0.075` renders to 8 on its own and to 7 as the trailing side of
    // a normalized pair, and only the pair's answer keeps the card at 100.
    //
    // Weather does not use the card-sum rule TODAY, so this row is about the
    // adapter's contract rather than about a number now on the page — said
    // plainly, because a guard whose population is empty should say so.
    expect(weatherPercent({ prob: 7, probability: 0.075 })).toBe("7%");
    expect(weatherPercent({ prob: 93, probability: 0.925 })).toBe("93%");
  });

  test("hasPrice asks the value, not the rounded integer", () => {
    expect(hasPrice({ prob: 0, probability: 0.0015 })).toBe(true);
    expect(hasPrice({ prob: 0, probability: 0 })).toBe(false);
    expect(hasPrice({ prob: 0 })).toBe(false);
    expect(hasPrice({ prob: 44, probability: 0.435 })).toBe(true);
  });
});

/* ═══ 3 · the shipped components, rendered ═════════════════════════════════ */

describe("UX-P192 · the temperature histogram", () => {
  test("no bucket over a live price prints 0%", () => {
    for (const spec of SPECIMENS) {
      const text = visibleText(
        renderToStaticMarkup(
          React.createElement(DistributionPanel, { city: cityPayload(spec) }),
        ),
      );
      expect([spec.city, printsZeroPercent(text)]).toEqual([spec.city, false]);
    }
  });

  test("each of LA's four sub-1% buckets is reachable and reads `<1%`", () => {
    const markup = renderToStaticMarkup(
      React.createElement(DistributionPanel, { city: cityPayload(LA) }),
    );
    const text = visibleText(markup);
    const changed = LA.outcomes.filter((o) => o.after === "<1%");
    expect(changed).toHaveLength(4);
    // Four tooltips, one per bucket — the bars share one string, so count the
    // OCCURRENCES rather than merely asserting the substring appears once.
    expect(text.split("<1%").length - 1).toBe(4);
  });

  test("CONTROL — every bucket NOT on a boundary is byte-identical", () => {
    const text = visibleText(
      renderToStaticMarkup(
        React.createElement(DistributionPanel, { city: cityPayload(LA) }),
      ),
    );
    for (const o of LA.outcomes.filter((x) => x.before === x.after)) {
      expect([o.label, text.includes(o.after)]).toEqual([o.label, true]);
    }
    // And the peak headline still names the market's own favourite.
    expect(text).toContain("44%");
  });

  test("a genuinely unpriced bucket is not given an invented `<1%`", () => {
    // The direction the band must NOT invent. The population has no such row
    // today, which is why this is constructed rather than banked — and why the
    // backend test asserts `exact_zero == 0` separately, so the two claims stay
    // distinguishable.
    //
    // The 0-priced bucket prints NOTHING here rather than `0%`: the histogram
    // shows a number only for the peak and on hover, and `hasPrice` withholds
    // the hover from a bucket with no price. That is the honest answer — but it
    // means this component cannot demonstrate the `0%` half, so `EventList`,
    // which prints its number unconditionally, carries that assertion below.
    const city = cityPayload(BEIJING);
    city.high.dist = [
      { label: "20°C or below", prob: 0, probability: 0 },
      { label: "30°C", prob: 100, probability: 1 },
    ];
    const text = visibleText(
      renderToStaticMarkup(React.createElement(DistributionPanel, { city })),
    );
    expect(text).toContain("100%");
    expect(text).not.toContain("<1%");
    expect(text).not.toContain(">99%");
  });

  test("an unconditional printer shows the two BOUNDARIES plainly", () => {
    // Exactly 0 and exactly 1 are the boundaries, so they print as themselves.
    // A band that fired here would be the same error UX-P046 exists to prevent,
    // arriving from the other side — and it is what native's threshold-shaped
    // copy of this rule did until UX-P192 (contract rows 0.0 and 1.0).
    const text = visibleText(
      renderToStaticMarkup(
        React.createElement(EventList, {
          title: "Boundaries",
          sub: "control",
          icon: "\u26A0",
          items: [
            { q: "Settled no", prob: 0, probability: 0, src: "kalshi", closes: "Tue, Sep 29", leader: null },
            { q: "Settled yes", prob: 100, probability: 1, src: "kalshi", closes: "Tue, Sep 29", leader: null },
          ],
          accent: "#B91C1C",
        }),
      ),
    );
    expect(printsZeroPercent(text)).toBe(true);
    expect(printsHundredPercent(text)).toBe(true);
    expect(text).not.toContain("<1%");
    expect(text).not.toContain(">99%");
  });
});

describe("UX-P192 · the hero, the wild cards and the event lists", () => {
  const featured = [
    {
      q: "Will a supervolcano erupt before 2050?",
      prob: 0,
      probability: 0.0005,
      src: "kalshi" as const,
      tag: "Wild card",
      closes: "Sat, Jan 8",
      leader: null,
    },
  ];

  test("the 64px hero number reads `<1%`, not a giant 0%", () => {
    const text = visibleText(withSwr(featured, WeatherHero));
    expect(text).toContain("<1%");
    expect(printsZeroPercent(text)).toBe(false);
  });

  test("the hero prints the `%` sign exactly once", () => {
    // `ProbabilityNumber` splits the trailing `%` into its own smaller span. A
    // band string must not lose it, nor gain a second one.
    const markup = withSwr(featured, WeatherHero);
    const text = visibleText(markup);
    expect(text.split("%").length - 1).toBe(1);
  });

  test("a wild card at a hair above zero reads `<1%`", () => {
    const text = visibleText(
      withSwr(
        [
          {
            q: "Min Arctic sea ice extent this summer?",
            prob: 0,
            probability: 0.0025,
            src: "polymarket",
            tag: "Wild card",
            closes: "Thu, Oct 1",
            leader: "4.0-4.2m sq km",
          },
        ],
        WildCards,
      ),
    );
    expect(text).toContain("<1%");
    expect(printsZeroPercent(text)).toBe(false);
  });

  test("the natural-events list bands both ends", () => {
    const items = [
      { q: "Category 5 landfall?", prob: 0, probability: 0.0025, src: "kalshi", closes: "Tue, Sep 29", leader: null },
      { q: "Any named storm?", prob: 100, probability: 0.996, src: "kalshi", closes: "Tue, Sep 29", leader: null },
      { q: "Two landfalls?", prob: 62, probability: 0.62, src: "kalshi", closes: "Tue, Sep 29", leader: null },
    ];
    const text = visibleText(
      renderToStaticMarkup(
        React.createElement(EventList, {
          title: "Hurricanes",
          sub: "Atlantic",
          icon: "🌀",
          items,
          accent: "#B91C1C",
        }),
      ),
    );
    expect(text).toContain("<1%");
    expect(text).toContain(">99%");
    expect(text).toContain("62%");
    expect(printsZeroPercent(text)).toBe(false);
    expect(printsHundredPercent(text)).toBe(false);
  });

  test("the climate dashboard bands too", () => {
    const text = visibleText(
      withSwr(
        [
          { q: "Hottest year on record by 2050?", prob: 100, probability: 0.995, src: "kalshi", scale: "2050" },
        ],
        ClimateDashboard,
      ),
    );
    expect(text).toContain(">99%");
    expect(printsHundredPercent(text)).toBe(false);
  });

  test("the rain cards band both lists", () => {
    const text = visibleText(
      withSwr(
        {
          daily: [{ day: "Mon", date: "Sep 1", prob: 0, probability: 0.003, icon: "🌧" }],
          monthly: [
            { city: "Denver", period: "Dec 2026", prob: 0, probability: 0.0015, src: "kalshi", delta24h: 0 },
          ],
        },
        RainForecast,
      ),
    );
    expect(text.split("<1%").length - 1).toBe(2);
    expect(printsZeroPercent(text)).toBe(false);
  });
});

/* ═══ 4 · the rule cannot come back ════════════════════════════════════════ */

describe("UX-P192 · no weather component prints a served integer raw", () => {
  const DIR = path.join(FRONTEND, "components", "weather");

  // Comments stripped: this module's own prose quotes `{item.prob}%` in the
  // sentence explaining why it was removed, and a source scan that reads its
  // own docstring is a scan of the wrong thing (UX-P190, UX-P191).
  const codeOf = (file: string) =>
    fs
      .readFileSync(path.join(DIR, file), "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .split("\n")
      .filter((l) => !l.trim().startsWith("//"))
      .join("\n");

  const FILES = fs.readdirSync(DIR).filter((f) => f.endsWith(".tsx"));

  test("the scan is non-vacuous — it finds the components at all", () => {
    expect(FILES.length).toBeGreaterThanOrEqual(10);
    expect(FILES).toContain("DistributionPanel.tsx");
    expect(FILES).toContain("WeatherHero.tsx");
  });

  test.each(FILES)("%s interpolates no `.prob` directly into text", (file) => {
    // `{x.prob}%` — the shape every one of these files used. A CSS width
    // (`` `${x.prob}%` `` inside a style object) is a length, not a printed
    // percentage, and stays: the backtick before `$` is what tells them apart.
    const offenders = [
      ...codeOf(file).matchAll(/(.?)\{[a-zA-Z.]*\bprob\b\}%/g),
    ].filter((m) => m[1] !== "$");
    expect(offenders.map((m) => m[0])).toEqual([]);
  });

  test("every file that prints a percentage imports the adapter", () => {
    // Vacuity companion: without this, deleting every number from the page
    // would satisfy the scan above.
    const adopters = FILES.filter((f) => codeOf(f).includes("weatherPercent"));
    expect(adopters.sort()).toEqual(
      [
        "ClimateDashboard.tsx",
        "DistributionPanel.tsx",
        "EventList.tsx",
        "HurricaneTracker.tsx",
        "ProbabilityNumber.tsx",
        "RainForecast.tsx",
      ].sort(),
    );
  });

  test("the adapter is the site's formatter, not a local re-implementation", () => {
    const data = codeOf("data.ts".replace(".ts", ".ts"));
    expect(data).toContain("formatProbabilityPercent");
    expect(data).not.toMatch(/[<>]=?\s*(0\.01|99)\b/);
  });
});
