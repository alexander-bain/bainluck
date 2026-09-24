/**
 * #2243 FOLLOW-THROUGH — THE THREE SECTIONS THAT STILL PRETEND TO LOAD.
 *
 * UX-P170 fixed the "Rain & rainfall" section's loading/empty collapse
 * (`daily?.length ? daily : null` renders a pulsing skeleton forever on a 200
 * carrying `[]` — gotcha #53) and parked the finding that WeatherHero,
 * NaturalEvents and WildCards share the identical guard while their endpoints
 * happen to be non-empty. This test banks that parked defect: each of the
 * three components rendered against a loaded-and-empty payload must show an
 * honest empty card in the module's existing dialect
 * ("No live X markets right now" + what the card tracks), never a skeleton.
 *
 * Every assertion renders the SHIPPED component with SWR mocked at the seam —
 * the same pattern as weatherRainHonestyCapture.test.tsx. No source-level arm.
 *
 *   TZ=UTC npx jest --testPathPatterns=weatherHonestEmpty2243
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

let swrPayload: unknown;
let swrError: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: swrError }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const WeatherHero = require("@/components/weather/WeatherHero").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const NaturalEvents = require("@/components/weather/NaturalEvents").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const WildCards = require("@/components/weather/WildCards").default;

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

const FEATURED = [
  {
    prob: 78,
    q: "Where will it rain this weekend?",
    src: "kalshi",
    tag: "Rain",
    closes: "Sep 6",
  },
];

const EVENT_ROW = { prob: 10, q: "A major hurricane landfall?", src: "kalshi", closes: "Nov 30" };
const EVENTS_FULL = {
  hurricane: [EVENT_ROW],
  earthquake: [EVENT_ROW],
  tornadoes: [EVENT_ROW],
};
const EVENTS_EMPTY = { hurricane: [], earthquake: [], tornadoes: [] };

const WILDCARD = [
  { prob: 16, q: "Record low Arctic sea ice?", src: "kalshi", tag: "Climate" },
];

describe("#2243 · WeatherHero stops pretending to load", () => {
  test("STILL LOADING (undefined) keeps the skeleton — that part was right", () => {
    const markup = render(WeatherHero, undefined);
    expect(markup).toContain(SKELETON);
    expect(visibleText(markup)).not.toContain("No live featured markets right now");
  });

  test("LOADED-AND-EMPTY renders no skeleton anywhere", () => {
    const markup = render(WeatherHero, []);
    expect(markup).not.toContain(SKELETON);
    expect(visibleText(markup)).toContain("No live featured markets right now");
  });

  test("LOADED-WITH-ROWS still renders the featured card, not the empty branch", () => {
    const markup = render(WeatherHero, FEATURED);
    expect(markup).not.toContain(SKELETON);
    expect(visibleText(markup)).toContain("Where will it rain this weekend?");
    expect(visibleText(markup)).not.toContain("No live featured markets right now");
  });
});

describe("#2243 · NaturalEvents stops pretending to load", () => {
  test("STILL LOADING (undefined) keeps the skeletons — that part was right", () => {
    const markup = render(NaturalEvents, undefined);
    expect(markup).toContain(SKELETON);
    expect(visibleText(markup)).not.toContain("No live hurricane markets right now");
  });

  test("LOADED-AND-EMPTY renders no skeleton anywhere", () => {
    const markup = render(NaturalEvents, EVENTS_EMPTY);
    expect(markup).not.toContain(SKELETON);
    const text = visibleText(markup);
    expect(text).toContain("No live hurricane markets right now");
    expect(text).toContain("No live earthquake markets right now");
    expect(text).toContain("No live tornado markets right now");
  });

  test("PARTIAL emptiness is honest per subsection, not whole-section", () => {
    const markup = render(NaturalEvents, {
      hurricane: [],
      earthquake: [EVENT_ROW],
      tornadoes: [EVENT_ROW],
    });
    expect(markup).not.toContain(SKELETON);
    const text = visibleText(markup);
    expect(text).toContain("No live hurricane markets right now");
    expect(text).not.toContain("No live earthquake markets right now");
    expect(text).toContain("Seismic activity");
    expect(text).toContain("Tornadoes");
  });

  test("LOADED-WITH-ROWS still renders all three trackers", () => {
    const markup = render(NaturalEvents, EVENTS_FULL);
    expect(markup).not.toContain(SKELETON);
    expect(visibleText(markup)).not.toContain("No live hurricane markets right now");
  });
});

describe("#2243 · WildCards stops pretending to load", () => {
  test("STILL LOADING (undefined) keeps the skeletons — that part was right", () => {
    const markup = render(WildCards, undefined);
    expect(markup).toContain(SKELETON);
    expect(visibleText(markup)).not.toContain("No live wild cards right now");
  });

  test("LOADED-AND-EMPTY renders no skeleton anywhere", () => {
    const markup = render(WildCards, []);
    expect(markup).not.toContain(SKELETON);
    expect(visibleText(markup)).toContain("No live wild cards right now");
  });

  test("LOADED-WITH-ROWS still renders the cards, not the empty branch", () => {
    const markup = render(WildCards, WILDCARD);
    expect(markup).not.toContain(SKELETON);
    expect(visibleText(markup)).toContain("Record low Arctic sea ice?");
    expect(visibleText(markup)).not.toContain("No live wild cards right now");
  });
});

/*
 * Review caveat (Codex, 2026-09-23): undefined-vs-empty is scoped to the typed
 * endpoint contract. Only an ARRAY with no rows is a proved absence — a missing
 * subsection or a non-array body must never print "No live X markets".
 */
describe("#2243 · a malformed payload is not a proved absence", () => {
  test("NaturalEvents: a MISSING subsection keeps its skeleton, not an empty verdict", () => {
    const markup = render(NaturalEvents, { earthquake: [EVENT_ROW], tornadoes: [] });
    const text = visibleText(markup);
    expect(markup).toContain(SKELETON);
    expect(text).not.toContain("No live hurricane markets right now");
    expect(text).toContain("No live tornado markets right now");
  });

  test("NaturalEvents: a non-array subsection keeps its skeleton", () => {
    const markup = render(NaturalEvents, { hurricane: {}, earthquake: [EVENT_ROW], tornadoes: [EVENT_ROW] });
    expect(markup).toContain(SKELETON);
    expect(visibleText(markup)).not.toContain("No live hurricane markets right now");
  });

  test("WeatherHero and WildCards: a non-array body keeps the skeleton", () => {
    for (const [Component, phrase] of [
      [WeatherHero, "No live featured markets right now"],
      [WildCards, "No live wild cards right now"],
    ] as const) {
      const markup = render(Component, { detail: "unexpected" });
      expect(markup).toContain(SKELETON);
      expect(visibleText(markup)).not.toContain(phrase);
    }
  });

  test("the empty cards paint with design tokens, never a raw hex", () => {
    const markups = [
      render(WeatherHero, []),
      render(NaturalEvents, EVENTS_EMPTY),
      render(WildCards, []),
    ];
    for (const markup of markups) {
      expect(markup).toContain("bg-surface-card");
      expect(markup).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    }
  });
});
