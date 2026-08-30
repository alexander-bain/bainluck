/**
 * UX-P186 — THE BIGGEST NUMBER ON THE WEATHER PAGE SAYS WHAT IT IS ABOUT.
 *
 * ═══ WHAT THIS IS ═══
 *
 * `/weather` opens on a rotating hero card: a question, one large percentage,
 * a source badge, a resolution date. `GET /api/weather/featured` never told the
 * card WHICH outcome the percentage belonged to, so under a multi-outcome
 * question the number answered nothing:
 *
 *     Featured · Daily rain
 *     Where will it rain on Aug 29, 2026?
 *     78%                                    ← 78% of what? Which city?
 *
 * The answer was Minneapolis, out of twenty-two cities. New York City, on the
 * same market, was at 4.5%.
 *
 * ═══ THE READER COUNT ═══
 *
 * Every load, and not by accident. Captured from production 2026-08-30, ALL
 * FIVE cards the hero rotates were multi-outcome (22, 42, 11, 11 and 11
 * outcomes) — see `_featured_census` in the fixture. That is structural: the
 * featured scorer is `len(m.outcomes) / days`, so it RANKS BY OUTCOME COUNT and
 * systematically promotes exactly the markets whose bare number is least
 * legible. A binary market, whose bare number reads perfectly well, can barely
 * reach the hero at all.
 *
 * The wildcards rail shared the defect with a sharper edge: "Major volcano
 * eruption in 2026?" showed 68%, which is the price of the outcome "At least 2"
 * — not the probability of an eruption, which is what the card reads as.
 *
 * ═══ WHAT EVERY ROW HERE IS MADE OF ═══
 *
 * The BEFORE is the verbatim production body, banked in
 * `backend/tests/fixtures/uxp186_weather_featured.json` before a line of the fix
 * was written. Every assertion renders the SHIPPED `WeatherHero` /`WildCards`
 * and reads the text a PERSON sees. Nothing is drawn by hand and there is no
 * source-level arm — a guard that greps the file stays green when someone
 * deletes the call site.
 *
 *   TZ=UTC npx jest --testPathPatterns=weatherFeaturedLeaderCapture
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
  "uxp186_weather_featured.json",
);

const banked = JSON.parse(fs.readFileSync(FIXTURE, "utf8"));
const SERVED_BEFORE_FEATURED = banked.served_before_featured as Record<
  string,
  unknown
>[];
const SERVED_BEFORE_WILDCARDS = banked.served_before_wildcards as Record<
  string,
  unknown
>[];

/* ── SWR is the only thing between these components and their payload ─── */

let swrPayload: unknown;
let swrError: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: swrError }),
}));

/* eslint-disable @typescript-eslint/no-var-requires */
const WeatherHero = require("@/components/weather/WeatherHero").default;
const WildCards = require("@/components/weather/WildCards").default;
const EventList = require("@/components/weather/EventList").default;
const HurricaneTracker = require("@/components/weather/HurricaneTracker").default;
/* eslint-enable @typescript-eslint/no-var-requires */

function renderWith(Component: React.ComponentType, payload: unknown): string {
  swrPayload = payload;
  swrError = undefined;
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

/** The hero rotates; `renderToStaticMarkup` never fires the interval, so the
 *  card under test is always index 0. Put the case first. */
function heroText(card: Record<string, unknown>): string {
  return visibleText(renderWith(WeatherHero, [card]));
}

const RAIN_BEFORE = SERVED_BEFORE_FEATURED[0];
const VOLCANO_BEFORE = SERVED_BEFORE_WILDCARDS[0];

/* ═══ 1 · the banked BEFORE really is the broken state ═════════════════ */

describe("UX-P186 · the fixture is genuinely the defect", () => {
  test("not one served card carried a leader", () => {
    for (const card of [
      ...SERVED_BEFORE_FEATURED,
      ...SERVED_BEFORE_WILDCARDS,
    ]) {
      expect(card).not.toHaveProperty("leader");
    }
  });

  test("every hero card was multi-outcome — the scorer guarantees it", () => {
    const census = banked._featured_census as { n_outcomes: number }[];
    expect(census).toHaveLength(5);
    for (const row of census) expect(row.n_outcomes).toBeGreaterThan(2);
    expect(census.map((r) => r.n_outcomes)).toEqual([22, 42, 11, 11, 11]);
  });

  test("the banked rain card is the one from the docstring", () => {
    expect(RAIN_BEFORE.q).toBe("Where will it rain on Aug 29, 2026?");
    expect(RAIN_BEFORE.prob).toBe(78);
    expect((banked._featured_census as { leader: string }[])[0].leader).toBe(
      "Minneapolis",
    );
  });
});

/* ═══ 2 · the ship, rendered ═══════════════════════════════════════════ */

describe("UX-P186 · the hero says which outcome its number belongs to", () => {
  test("BEFORE: the shipped card printed 78% and named nothing", () => {
    const text = heroText(RAIN_BEFORE);
    expect(text).toContain("Where will it rain on Aug 29, 2026?");
    expect(text).toContain("78");
    expect(text).not.toContain("Minneapolis");
  });

  test("AFTER: the same card names Minneapolis", () => {
    const text = heroText({ ...RAIN_BEFORE, leader: "Minneapolis" });
    expect(text).toContain("78");
    expect(text).toContain("Minneapolis");
  });

  test("the name is not hard-coded — it tracks the payload", () => {
    // Vacuity companion. If the render stopped reading `leader` and printed a
    // constant, the assertion above would still pass.
    expect(heroText({ ...RAIN_BEFORE, leader: "Seattle" })).toContain("Seattle");
    expect(heroText({ ...RAIN_BEFORE, leader: "Seattle" })).not.toContain(
      "Minneapolis",
    );
  });

  test("a temperature band reads as one string, not two numbers", () => {
    const text = heroText({
      ...SERVED_BEFORE_FEATURED[2],
      leader: "78-79°F",
    });
    expect(text).toContain("Highest temperature in Los Angeles on August 31?");
    expect(text).toContain("78-79°F");
  });
});

describe("UX-P186 · the wildcards rail, same fix", () => {
  test("BEFORE: 68% under a question that reads as a yes/no", () => {
    const text = visibleText(renderWith(WildCards, [VOLCANO_BEFORE]));
    expect(text).toContain("Major volcano eruption in 2026?");
    expect(text).toContain("68");
    expect(text).not.toContain("At least 2");
  });

  test("AFTER: the 68% is labelled with the outcome it prices", () => {
    const text = visibleText(
      renderWith(WildCards, [{ ...VOLCANO_BEFORE, leader: "At least 2" }]),
    );
    expect(text).toContain("68");
    expect(text).toContain("At least 2");
  });
});

describe("UX-P186 · the natural-events rail, where the sharpest case lives", () => {
  // `EventList` and `HurricaneTracker` take their rows as props, so they render
  // without SWR.
  //
  // Karina's real row, 2026-08-30. The question names no category at all, so a
  // bare 94% reads as "94% likely to be a hurricane". It means "at least a
  // Category 1" — her own ladder puts "Category 4 or above" at 32% and
  // "Category 5 or above" at 9%, which is a completely different forecast.
  const KARINA = {
    q: "Hurricane Karina category?",
    prob: 94,
    src: "kalshi" as const,
    closes: "Wed, Dec 2",
  };

  test("BEFORE: the row printed 95% against a question naming no category", () => {
    const text = visibleText(
      renderToStaticMarkup(
        React.createElement(EventList, {
          title: "Seismic activity",
          sub: "sub",
          icon: "x",
          accent: "#7C3AED",
          items: [KARINA],
        }),
      ),
    );
    expect(text).toContain("Hurricane Karina category?");
    expect(text).toContain("94%");
    expect(text).not.toContain("Category 1");
  });

  test("AFTER: the row says Category 1 or above", () => {
    const text = visibleText(
      renderToStaticMarkup(
        React.createElement(EventList, {
          title: "Seismic activity",
          sub: "sub",
          icon: "x",
          accent: "#7C3AED",
          items: [{ ...KARINA, leader: "Category 1 or above" }],
        }),
      ),
    );
    expect(text).toContain("94%");
    expect(text).toContain("Category 1 or above");
  });

  test("the hurricane tracker's own rows say it too", () => {
    const text = visibleText(
      renderToStaticMarkup(
        React.createElement(HurricaneTracker, {
          items: [{ ...KARINA, leader: "Category 1 or above" }],
        }),
      ),
    );
    expect(text).toContain("Category 1 or above");
  });

  test("both degrade on a row with no leader", () => {
    for (const Component of [EventList, HurricaneTracker]) {
      const text = visibleText(
        renderToStaticMarkup(
          React.createElement(Component as React.ComponentType<never>, {
            title: "t",
            sub: "s",
            icon: "x",
            accent: "#7C3AED",
            items: [KARINA, { ...KARINA, leader: null }],
          } as never),
        ),
      );
      expect(text).not.toMatch(/\bnull\b/);
      expect(text).not.toMatch(/\bundefined\b/);
      expect(text).toContain("94%");
    }
  });
});

/* ═══ 3 · the degradations, which are the risky half ═══════════════════ */

/** The caption's own element, empty or not. Text assertions cannot see this:
 *  React renders `{undefined}` as nothing at all, so an UNGUARDED caption emits
 *  a real, empty, margin-carrying <p> that reads as clean to `visibleText`.
 *  Counting the element is the only way to catch it. */
function captionElements(markup: string): string[] {
  // `truncate` is the caption's own signature — the hero's only other <p> is
  // the page subtitle ("max-w-md mb-6"), which never truncates. If this matcher
  // ever goes blind, "...and exactly one caption element when there is" below
  // fails; the two tests hold each other up.
  return markup.match(/<p[^>]*\btruncate\b[^>]*>.*?<\/p>/g) ?? [];
}

describe("UX-P186 · nothing worth naming prints nothing", () => {
  test("leader: null renders no caption and no stray word", () => {
    const text = heroText({ ...RAIN_BEFORE, leader: null });
    expect(text).toContain("78");
    expect(text).not.toMatch(/\bnull\b/);
    expect(text).not.toMatch(/\bundefined\b/);
  });

  test("NO CAPTION ELEMENT AT ALL when there is nothing to caption", () => {
    // Not "no visible text" — no element. An empty <p class="mt-1"> pushes the
    // pill row down by its margin on every card that has no leader, which is
    // every binary market on the page.
    for (const card of [
      RAIN_BEFORE, // the banked BEFORE: no `leader` key whatsoever
      { ...RAIN_BEFORE, leader: null },
      { ...RAIN_BEFORE, leader: "" },
    ]) {
      swrPayload = [card];
      swrError = undefined;
      const markup = renderToStaticMarkup(React.createElement(WeatherHero));
      expect(captionElements(markup)).toHaveLength(0);
    }
  });

  test("...and exactly one caption element when there is", () => {
    // Vacuity companion: proves the matcher above can actually find one.
    swrPayload = [{ ...RAIN_BEFORE, leader: "Minneapolis" }];
    swrError = undefined;
    const markup = renderToStaticMarkup(React.createElement(WeatherHero));
    const captions = captionElements(markup);
    expect(captions).toHaveLength(1);
    expect(captions[0]).toContain("Minneapolis");
  });

  test("A PAYLOAD WITH NO `leader` KEY AT ALL is not a bug — the hourly Redis " +
    "cache serves one for up to an hour after every deploy", () => {
    // This is the whole reason the frontend type is `leader?:` and not
    // `leader:`. A card that printed "undefined" under the number for an hour
    // after each release would be a worse defect than the one being fixed.
    const text = heroText(RAIN_BEFORE);
    expect(RAIN_BEFORE).not.toHaveProperty("leader");
    expect(text).not.toMatch(/\bundefined\b/);
    expect(text).toContain("78");
  });

  test("the same two degradations on the wildcards rail", () => {
    for (const card of [
      VOLCANO_BEFORE,
      { ...VOLCANO_BEFORE, leader: null },
      { ...VOLCANO_BEFORE, leader: "" },
    ]) {
      const text = visibleText(renderWith(WildCards, [card]));
      expect(text).toContain("68");
      expect(text).not.toMatch(/\bnull\b/);
      expect(text).not.toMatch(/\bundefined\b/);
    }
  });

  test("STILL LOADING is untouched — the skeleton is still the right answer", () => {
    // `leader` must not have turned a loading state into a content state.
    expect(renderWith(WeatherHero, undefined)).toContain("animate-pulse");
    expect(renderWith(WildCards, undefined)).toContain("animate-pulse");
  });
});

/* ═══ 4 · the rest of the card did not move ════════════════════════════ */

describe("UX-P186 · everything else the card says is unchanged", () => {
  test("question, percentage, source and resolution date all survive", () => {
    const before = heroText(RAIN_BEFORE);
    const after = heroText({ ...RAIN_BEFORE, leader: "Minneapolis" });

    for (const fragment of [
      "Where will it rain on Aug 29, 2026?",
      "Featured · Daily rain",
      "78",
      "Resolves Mon, Aug 31",
    ]) {
      expect(before).toContain(fragment);
      expect(after).toContain(fragment);
    }

    // The ONLY difference a reader can see is the new word.
    expect(after.replace(" Minneapolis", "")).toBe(before);
  });
});
