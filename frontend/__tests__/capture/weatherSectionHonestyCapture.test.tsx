/**
 * UX-P205 — THE LAST THREE WEATHER SECTIONS STOP PRETENDING TO LOAD.
 *
 * PILLAR: TRUTH.  SHIP: on /weather, a section that has nothing to show says so,
 * instead of shimmering as though data were still on the way.
 *
 * ═══ WHAT THIS IS ═══
 *
 * UX-P170 fixed this exact defect in `RainForecast` and wrote, correctly at the
 * time, "five of them have data". Two of that five (`TemperatureMap`,
 * `ClimateDashboard`) were fixed later under #995. THREE were never fixed, and
 * park UX-P186-3 named all three:
 *
 *   WeatherHero    `items = payload?.length ? payload : null`
 *   WildCards      `cards = payload?.length ? payload : null`
 *   NaturalEvents  the same collapse, three times over — hurricane, earthquake,
 *                  tornadoes
 *
 * Each collapses "still loading" (`undefined`) and "loaded, and there is
 * nothing" (`[]`) into one `null`, and every render path maps that `null` to a
 * pulsing SKELETON. The 200 arrives, the list is empty, and the section pulses
 * forever. Gotcha #53: an empty 200 is not an absence, it is a response shape.
 *
 * `WeatherHero` carried a second, sharper defect. Its dots rendered under
 * `!loading`, where `loading = !items && !error`. On a fetch error that reads
 * FALSE while `items` is null, so `items.map` ran on `null` and threw a
 * TypeError mid-render — the error card it was trying to show could never paint.
 *
 * ═══ THE READER COUNT ═══
 *
 * LATENT on all three, deliberately reported as such. `GET /api/weather/`
 * {featured, events, wildcards} were all non-empty when captured (5 / 45+4+2 /
 * 3 rows — banked in the fixture). What makes this worth fixing rather than
 * parking is that the identical collapse IS firing one section away in the same
 * capture: `/api/weather/rain` serves `daily: []`, and that is the section that
 * already had to be fixed. The crash arm of `WeatherHero` needs no lull at all —
 * any 5xx or dropped connection reaches it.
 *
 * ═══ WHAT IS *NOT* FIXED HERE, DELIBERATELY ═══
 *
 * Nothing conjures data. Emptiness is upstream and is not routed here. And a
 * `WeatherHero` payload that HAS rows but whose `src` is absent from `SOURCES`
 * still falls to the skeleton — pre-existing, out of scope, parked as UX-P205-1.
 *
 * ═══ WHAT EVERY ROW HERE IS MADE OF ═══
 *
 * Every assertion renders the SHIPPED component through `renderToStaticMarkup`,
 * with `swr` mocked as the only thing between the component and its payload.
 * The healthy-path rows use the verbatim production bodies banked in
 * `backend/tests/fixtures/uxp205_weather_sections.json`. There is no
 * source-level arm anywhere: a guard that greps the file stays green when
 * someone deletes the call site.
 *
 *   TZ=UTC npx jest --testPathPatterns=weatherSectionHonestyCapture
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
  "uxp205_weather_sections.json",
);

const banked = JSON.parse(fs.readFileSync(FIXTURE, "utf8"));
const SERVED_FEATURED = banked.served_featured;
const SERVED_EVENTS = banked.served_events;
const SERVED_WILDCARDS = banked.served_wildcards;

/* ── SWR is the only thing between the component and its payload ──────── */

let swrPayload: unknown;
let swrError: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: swrError }),
}));

/* eslint-disable @typescript-eslint/no-var-requires */
const WeatherHero = require("@/components/weather/WeatherHero").default;
const WildCards = require("@/components/weather/WildCards").default;
const NaturalEvents = require("@/components/weather/NaturalEvents").default;
/* eslint-enable @typescript-eslint/no-var-requires */

function render(
  Component: React.ComponentType,
  payload: unknown,
  error: unknown = undefined,
): string {
  swrPayload = payload;
  swrError = error;
  return renderToStaticMarkup(React.createElement(Component));
}

/** Strip tags so assertions read what a PERSON reads, not what React emitted. */
function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&ldquo;|&rdquo;/g, '"')
    .replace(/&middot;/g, "·")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

const SKELETON = "animate-pulse";

const EMPTY_EVENTS = { hurricane: [], earthquake: [], tornadoes: [] };

/* ═══════════════════════════════════════════════════════════════════════ */

describe("UX-P205 · the banked payloads are what production actually served", () => {
  test("all three sections were NON-empty — this is a latent fix, and says so", () => {
    expect(banked._population.featured_rows).toBe(5);
    expect(banked._population.events_hurricane).toBe(45);
    expect(banked._population.events_earthquake).toBe(4);
    expect(banked._population.events_tornadoes).toBe(2);
    expect(banked._population.wildcards_rows).toBe(3);
  });

  test("the live witness for the class is banked alongside them", () => {
    // /api/weather/rain served `daily: []` in the same capture. That is the
    // same collapse, already firing, in the section UX-P170 had to fix.
    expect(banked._population.rain_daily_rows).toBe(0);
    expect(banked._population.rain_daily_is_empty).toBe(true);
  });
});

describe("UX-P205 · WeatherHero", () => {
  test("STILL LOADING (undefined) keeps the skeleton — that part was right", () => {
    const markup = render(WeatherHero, undefined);
    expect(markup).toContain(SKELETON);
    expect(visibleText(markup)).not.toContain("No live weather markets right now");
  });

  test("LOADED-AND-EMPTY says so instead of pulsing", () => {
    const markup = render(WeatherHero, []);
    expect(markup).not.toContain(SKELETON);
    const text = visibleText(markup);
    expect(text).toContain("No live weather markets right now");
    expect(text).toContain("This is where the featured weather question sits.");
  });

  test("a fetch error reads as an error, not as emptiness", () => {
    const text = visibleText(render(WeatherHero, undefined, new Error("boom")));
    expect(text).toContain("Failed to load featured markets");
    expect(text).not.toContain("No live weather markets right now");
  });

  test("a fetch error RENDERS AT ALL — the dots no longer map over null", () => {
    // The defect: `loading = !items && !error` is FALSE under an error with no
    // items, so `!loading` was true and `items.map` threw. Rendering at all is
    // the assertion; the error copy above is what should be reachable.
    expect(() => render(WeatherHero, undefined, new Error("boom"))).not.toThrow();
    expect(() => render(WeatherHero, [], new Error("boom"))).not.toThrow();
  });

  test("the healthy production payload still renders its featured card", () => {
    const markup = render(WeatherHero, SERVED_FEATURED);
    const text = visibleText(markup);
    expect(markup).not.toContain(SKELETON);
    expect(text).toContain(SERVED_FEATURED[0].q);
    expect(text).not.toContain("No live weather markets right now");
  });

  test("the dots appear only when there are markets to dot", () => {
    const withData = render(WeatherHero, SERVED_FEATURED);
    expect(withData).toContain('aria-label="Featured market 1"');
    expect(render(WeatherHero, [])).not.toContain("aria-label=\"Featured market");
    expect(render(WeatherHero, undefined)).not.toContain("aria-label=\"Featured market");
  });
});

describe("UX-P205 · WildCards", () => {
  test("STILL LOADING (undefined) keeps the skeletons", () => {
    const markup = render(WildCards, undefined);
    expect(markup).toContain(SKELETON);
    expect(visibleText(markup)).not.toContain("No live wild card markets right now");
  });

  test("LOADED-AND-EMPTY says so instead of pulsing", () => {
    const markup = render(WildCards, []);
    expect(markup).not.toContain(SKELETON);
    const text = visibleText(markup);
    expect(text).toContain("No live wild card markets right now");
    expect(text).toContain("This is where the offbeat weather questions sit.");
  });

  test("a fetch error still reads as an error", () => {
    const text = visibleText(render(WildCards, undefined, new Error("boom")));
    expect(text).toContain("Failed to load wild cards");
    expect(text).not.toContain("No live wild card markets right now");
  });

  test("the healthy production payload still renders its cards", () => {
    const markup = render(WildCards, SERVED_WILDCARDS);
    expect(markup).not.toContain(SKELETON);
    expect(visibleText(markup)).toContain(SERVED_WILDCARDS[0].q);
  });
});

describe("UX-P205 · NaturalEvents", () => {
  test("STILL LOADING (undefined) keeps all three skeletons", () => {
    const markup = render(NaturalEvents, undefined);
    expect(markup).toContain(SKELETON);
    const text = visibleText(markup);
    expect(text).not.toContain("No live hurricane markets right now");
    expect(text).not.toContain("No live earthquake markets right now");
    expect(text).not.toContain("No live tornado markets right now");
  });

  test("A FULLY EMPTY 200 gives all three sections an honest state", () => {
    const markup = render(NaturalEvents, EMPTY_EVENTS);
    expect(markup).not.toContain(SKELETON);
    const text = visibleText(markup);
    expect(text).toContain("No live hurricane markets right now");
    expect(text).toContain("No live earthquake markets right now");
    expect(text).toContain("No live tornado markets right now");
  });

  test("each section is judged on ITS OWN list, not on the payload as a whole", () => {
    // The one that matters: earthquake and tornadoes are the thin lists (4 and 2
    // rows in production). Either can empty out while hurricane stays healthy.
    const markup = render(NaturalEvents, {
      hurricane: SERVED_EVENTS.hurricane,
      earthquake: [],
      tornadoes: [],
    });
    expect(markup).not.toContain(SKELETON);
    const text = visibleText(markup);
    expect(text).toContain("Atlantic season tracker");
    expect(text).not.toContain("No live hurricane markets right now");
    expect(text).toContain("No live earthquake markets right now");
    expect(text).toContain("No live tornado markets right now");
  });

  test("an empty section keeps its own heading, so the page still reads", () => {
    const text = visibleText(render(NaturalEvents, EMPTY_EVENTS));
    expect(text).toContain("Seismic activity");
    expect(text).toContain("Tornadoes");
    expect(text).toContain("Atlantic season tracker");
    expect(text).toContain("Bigger picture. Rarer events.");
  });

  test("a fetch error still reads as an error, not as emptiness", () => {
    const text = visibleText(render(NaturalEvents, undefined, new Error("boom")));
    expect(text).toContain("Failed to load natural events data");
    expect(text).not.toContain("No live hurricane markets right now");
  });

  test("the healthy production payload still renders all three populated", () => {
    const markup = render(NaturalEvents, SERVED_EVENTS);
    expect(markup).not.toContain(SKELETON);
    const text = visibleText(markup);
    expect(text).toContain(SERVED_EVENTS.earthquake[0].q);
    expect(text).toContain(SERVED_EVENTS.tornadoes[0].q);
    expect(text).not.toContain("No live earthquake markets right now");
  });

  test("no empty section invents a number", () => {
    const markup = render(NaturalEvents, EMPTY_EVENTS);
    expect(markup).not.toContain("NaN");
    expect(visibleText(markup)).not.toMatch(/\d+%/);
  });
});
