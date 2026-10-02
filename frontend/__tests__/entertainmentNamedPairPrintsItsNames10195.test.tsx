/**
 * #10195 — on /entertainment, a two-answer question that isn't yes/no prints its
 * two answers by name.
 *
 * ═══ WHAT A READER SAW, production 2026-10-02 12:3xZ at 390px ═══
 *
 * "Anne Hathaway baby: Boy or Girl?" (Polymarket, `/futures/61186896`) serves
 * `Boy` 50.5 · `Girl` 49.5. The page showed it twice and named neither answer:
 *
 *     trending hero card     51%  Yes likely
 *     Cultural moments card  YES 51%  NO 49%
 *
 * #6766 already gates the YES/NO bar on the pair being ONE question by its
 * prices, and Boy/Girl is exactly one question — so the prices were right and
 * the WORDS were invented: `YesNoBar` hard-coded YES/NO, and the hero's default
 * (`binary`) branch printed "Yes likely" without looking at the legs.
 *
 * ═══ WHAT THIS FILE GUARDS ═══
 *
 * All three call sites, mounted through the page's DEFAULT export (the cards are
 * module-locals of a route file — see #6766's test for why): the trending hero,
 * the Cultural Moments feed and the Tech & Culture rail. Both directions in one
 * file: the named pair prints its names, AND a real Yes/No market keeps its
 * YES/NO wording — a fix that renamed every bar would pass the first arm alone.
 *
 *   TZ=UTC npx jest --testPathPatterns=entertainmentNamedPairPrintsItsNames10195
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { namedPairLabels } from "@/lib/twoLegCardPair";
import type { EntertainmentData, EntMarketRow } from "@/lib/api";

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({
    data: (global as never as { __PAYLOAD__: unknown }).__PAYLOAD__,
    error: undefined,
  }),
}));
jest.mock("@/hooks", () => ({
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
}));
jest.mock("@/lib/tmdb", () => ({
  hasTMDBToken: () => false,
  searchMovie: async () => null,
  posterUrl: (p: string) => p,
}));

import EntertainmentPage from "@/app/entertainment/page";

const ENTITIES: Record<string, string> = {
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&apos;": "'",
  "&#x27;": "'",
};

/** What a reader reads: tags stripped, entities decoded in ONE pass (CodeQL js/double-escaping). */
function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&(?:amp|lt|gt|quot|apos|#x27);/g, (entity) => ENTITIES[entity] ?? entity)
    .replace(/\s+/g, " ")
    .trim();
}

/** `ProbPct` prints the `%` in its own span, so the reader's "51%" arrives as "51 %". */
function tight(text: string): string {
  return text.replace(/(\d) %/g, "$1%");
}

/** The visible text of EVERY card linking to `/futures/<id>`, in document order. */
function cardTexts(markup: string, marketId: number): string[] {
  const out: string[] = [];
  const needle = `href="/futures/${marketId}"`;
  for (let at = markup.indexOf(needle); at >= 0; at = markup.indexOf(needle, at + 1)) {
    const next = markup.indexOf('href="/futures/', at + 1);
    out.push(tight(visibleText(markup.slice(at, next < 0 ? markup.length : next))));
  }
  return out;
}

function entMarket(over: Partial<EntMarketRow>): EntMarketRow {
  return {
    q: "placeholder",
    prob: 50,
    src: "polymarket",
    market_id: 1,
    external_id: "x",
    kind: "binary",
    top_outcomes: [],
    outcome_count: 1,
    volume_24h: 1000,
    resolution_date: null,
    image_url: null,
    hook: null,
    ...over,
  };
}

/** The specimen, in the shape `/api/entertainment` served it on 2026-10-02. */
const HATHAWAY = entMarket({
  q: "Anne Hathaway baby: Boy or Girl?",
  prob: 50.5,
  market_id: 61186896,
  external_id: "1030960",
  top_outcomes: [
    { name: "Boy", prob: 50.5, delta_24h: 0 },
    { name: "Girl", prob: 49.5, delta_24h: 0 },
  ],
  outcome_count: 2,
});

/** Two named legs that are NOT one question (85.5 + 17.5 = 103): the list, not a split. */
const NAMED_NOT_ONE_QUESTION = entMarket({
  q: "Dune vs Avengers: Highest Rotten Tomatoes Score",
  prob: 85.5,
  market_id: 61186897,
  top_outcomes: [
    { name: "Dune: Part Three", prob: 85.5, delta_24h: 0 },
    { name: "Avengers: Doomsday", prob: 17.5, delta_24h: 0 },
  ],
  outcome_count: 2,
});

/** CONTROL — a one-outcome Kalshi binary: its No is implicit and YES/NO is true. */
const YES_ONLY = entMarket({
  q: "Another GTA VI trailer released by October 31?",
  prob: 52,
  src: "kalshi",
  market_id: 61186898,
  top_outcomes: [{ name: "Yes", prob: 52, delta_24h: 0 }],
  outcome_count: 1,
});

/** CONTROL — both legs served AND named Yes/No: still YES/NO, whatever the case. */
const YES_NO_SERVED = entMarket({
  q: "Tom Brady to fight in the WWE before 2028",
  prob: 53.5,
  market_id: 61186899,
  top_outcomes: [
    { name: "Yes", prob: 53.5, delta_24h: 0 },
    { name: "No", prob: 46.5, delta_24h: 0 },
  ],
  outcome_count: 2,
});

/** A trending lead the hero needs (it renders only with 2+), kept off every assertion. */
const LEAD = entMarket({
  q: "Oscar Winner: Best Picture",
  prob: 50,
  kind: "multi",
  src: "kalshi",
  market_id: 61186890,
  top_outcomes: [
    { name: "The Odyssey", prob: 50, delta_24h: 0 },
    { name: "The Black Ball", prob: 27, delta_24h: 0 },
    { name: "Dune: Part Three", prob: 11, delta_24h: 0 },
  ],
  outcome_count: 12,
});

function payload(rows: EntMarketRow[]): EntertainmentData {
  return {
    total_markets: rows.length,
    updated_at: "2026-10-02T12:00:00+00:00",
    trending: [LEAD, ...rows],
    themes: {
      music: {
        count: 0,
        spotify_race: [],
        billboard_watch: [],
        billboard_groups: [],
        album_drops: [],
        artist_streaming: [],
        side_markets: [],
      },
      movies_tv: {
        count: 0,
        rt_groups: [],
        rt_markets: [],
        box_office_groups: [],
        box_office: [],
        reality_tv: [],
        side_markets: [],
      },
      tech_culture: { count: rows.length, markets: rows },
    },
    cultural_moments: rows,
    by_source: { kalshi: 1, polymarket: 1 },
  };
}

function render(rows: EntMarketRow[]): string {
  (global as never as { __PAYLOAD__: unknown }).__PAYLOAD__ = payload(rows);
  return renderToStaticMarkup(React.createElement(EntertainmentPage));
}

const ROWS = [HATHAWAY, NAMED_NOT_ONE_QUESTION, YES_ONLY, YES_NO_SERVED];
const markup = render(ROWS);

describe("namedPairLabels", () => {
  it("returns the served names of a named pair", () => {
    expect(namedPairLabels(HATHAWAY)).toEqual(["Boy", "Girl"]);
  });

  it("returns null for a Yes/No pair in any case, and for a one-outcome contract", () => {
    expect(namedPairLabels(YES_NO_SERVED)).toBeNull();
    expect(
      namedPairLabels({
        prob: 60,
        outcome_count: 2,
        top_outcomes: [
          { name: "no", prob: 60 },
          { name: "YES", prob: 40 },
        ],
      }),
    ).toBeNull();
    expect(namedPairLabels(YES_ONLY)).toBeNull();
  });
});

describe("/entertainment prints a named pair's names on every card", () => {
  it("renders each row on all three call sites (hero, moments, tech rail)", () => {
    for (const row of ROWS) {
      expect(cardTexts(markup, row.market_id)).toHaveLength(3);
    }
  });

  it("names Boy and Girl beside their own prices, and never YES/NO or 'likely'", () => {
    for (const text of cardTexts(markup, HATHAWAY.market_id)) {
      expect(text).toMatch(/\bBoy\b[^%]*51%/);
      // Rounded as ONE question (#2831): 51 + 49, never 51 + 50.
      expect(text).toMatch(/\bGirl\b[^%]*49%/);
      expect(text).not.toMatch(/\bYES\b/i);
      expect(text).not.toMatch(/\bNO\b/i);
      expect(text).not.toMatch(/likely/i);
    }
  });

  it("gives two named legs that are not one question the list, with both names", () => {
    for (const text of cardTexts(markup, NAMED_NOT_ONE_QUESTION.market_id)) {
      expect(text).toContain("Dune: Part Three");
      expect(text).toContain("Avengers: Doomsday");
      expect(text).toMatch(/86%/);
      expect(text).toMatch(/18%/);
      expect(text).not.toMatch(/likely/i);
      // 100 − 85.5 is a number neither leg is quoted at.
      expect(text).not.toMatch(/\b15%/);
    }
  });

  it("CONTROL — a one-outcome contract keeps its YES/NO wording on every card", () => {
    const [hero, moments, rail] = cardTexts(markup, YES_ONLY.market_id);
    expect(hero).toMatch(/Yes likely/);
    expect(moments).toMatch(/YES 52%.*NO 48%/);
    expect(rail).toMatch(/YES 52%.*NO 48%/);
  });

  it("CONTROL — a served Yes/No pair keeps YES/NO, not 'Yes'/'No' as names", () => {
    const [, moments, rail] = cardTexts(markup, YES_NO_SERVED.market_id);
    expect(moments).toMatch(/YES 54% NO 46%/);
    expect(rail).toMatch(/YES 54% NO 46%/);
  });
});
