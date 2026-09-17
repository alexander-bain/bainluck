/**
 * #6766 — a two-leg dashboard card stops printing a second number the venue
 * never quoted.
 *
 * ═══ WHAT A READER SAW, production 2026-09-17 18:2xZ at 390px ═══
 *
 * `/politics`, "John Thune announces departure as Senate Majority Leader?":
 *
 *     3%  Before Nov 3, 2026            vs  98%  Before Oct 1, 2026
 *
 * The payload prices `Before Oct 1, 2026` at **1.0%**. `BinaryCard` derived the
 * second number as `100 - prob` and then printed a served leg's NAME beside it,
 * so the card said the opposite of the market and drew a nearly full bar to
 * match. `tools/dashboard-two-leg-cards-6766.mjs` measured the class over both
 * dashboards: **19 two-leg cards, 4 disagreeing** — Thune, South Dakota AG
 * (printed 6%, served 4.2%), New York AG (printed 7%, served 4.8%) and
 * `/entertainment`'s MrBeast week-1 views (printed `NO 94%`, served `100M+`
 * 5.1%). Routed by authority, 2026-09-17 1805Z.
 *
 * ═══ WHAT THIS FILE GUARDS, AND WHY IT IS BUILT THIS WAY ═══
 *
 * BOTH DIRECTIONS ARE ASSERTED IN ONE FILE, because the repair is a narrowing
 * and a narrowing's whole risk is what it takes with it. 6 of the 8 two-leg
 * cards authority read are genuine Yes/No binaries whose No side has no quote
 * anywhere and must keep being derived. So the controls here are not decoration:
 * a fix that withheld every second number would pass the Thune arm and fail the
 * page.
 *
 * THE RENDER ARMS MOUNT THE REAL PAGES. `MarketCard`, `BinaryCard`, `MomentCard`
 * and `TechCultureSidebar` are module-locals of Next route files and must stay
 * that way (a page may export only the allowlisted route names — #5953 pays for
 * that lesson in a typecheck error), so this mounts the DEFAULT export and finds
 * the cards in the rendered markup. Nothing in `app/` was rearranged to make the
 * test possible.
 *
 * THE CENTRAL ASSERTION IS NOT A STRING MATCH ON `98%`. It is the probe's rule,
 * run over static markup: EVERY percent a card prints must be a percent the
 * payload carries for that card (within one rounding step), with one licensed
 * exception — the implicit No of a one-outcome contract. A test that only banned
 * the literal `98%` would pass a fix that printed `97%` instead.
 *
 *   TZ=UTC npx jest --testPathPatterns=dashboardCardReadsItsSecondLeg6766
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { twoLegCardPair } from "@/lib/twoLegCardPair";
import type {
  EntertainmentData,
  EntMarketRow,
  PoliticsData,
  PoliticsMarketRow,
} from "@/lib/api";

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

import PoliticsPage from "@/app/politics/page";
import EntertainmentPage from "@/app/entertainment/page";

/* ── Reading the rendered page the way a person reads the screen ─────────── */

/** The entities `renderToStaticMarkup` emits, and what a reader sees instead. */
const ENTITIES: Record<string, string> = {
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&apos;": "'",
  "&#x27;": "'",
};

/**
 * Strip tags so an assertion reads what a READER reads, not what React emitted.
 *
 * 🔴 ONE PASS over an entity table, not a chain of `.replace()` calls. Chained,
 * `&amp;` → `&` runs BEFORE `&gt;` → `>`, so the literal text `&amp;gt;`
 * unescapes twice and comes out as `>` — CodeQL flags exactly this as
 * `js/double-escaping`, HIGH severity, and it flagged this file (alert on the
 * first push of #6766). A single pass cannot feed its own output back in.
 */
function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&(?:amp|lt|gt|quot|apos|#x27);/g, (entity) => ENTITIES[entity] ?? entity)
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * The visible text of EVERY card linking to `/futures/<id>`, in document order.
 *
 * Each card is cut from its own anchor to the next anchor, which is what bounds
 * a card on both dashboards: every card on both pages is a `<Link>` wrapper.
 *
 * 🔴 ALL of them, not the first. `/entertainment` renders the same market in the
 * Cultural Moments feed AND in the Tech & Culture rail, which are two different
 * call sites with two different copies of the decision. A helper that returned
 * the first match let a mutation of the rail survive the whole battery — it was
 * asserting the moments card twice. An empty list means the card is not on the
 * page, which every caller asserts on rather than on an empty string: "absent"
 * and "printed nothing" are different facts.
 */
function cardTexts(markup: string, marketId: number): string[] {
  const out: string[] = [];
  const needle = `href="/futures/${marketId}"`;
  for (let at = markup.indexOf(needle); at >= 0; at = markup.indexOf(needle, at + 1)) {
    const next = markup.indexOf('href="/futures/', at + 1);
    out.push(visibleText(markup.slice(at, next < 0 ? markup.length : next)));
  }
  return out;
}

/** Every whole-or-one-decimal percent the card prints, in order. */
function printedPercents(text: string): number[] {
  return (text.match(/(?<!\d)(\d{1,3}(?:\.\d)?)%/g) || []).map(parseFloat);
}

/**
 * THE RULE, as the probe states it: a printed percent is either a served leg or
 * the implicit No of a one-outcome contract. Anything else is invented.
 *
 * A percent may differ from its leg by a rounding step; 1.5 points is the same
 * tolerance `tools/dashboard-two-leg-cards-6766.mjs` uses against production, so
 * the two arms of this ship cannot drift apart on what counts as a match.
 */
function unsupportedPercents(
  text: string,
  row: { prob: number; outcome_count: number; top_outcomes: { name: string; prob: number }[] },
): number[] {
  const supported = row.top_outcomes.map((o) => o.prob);
  if (row.outcome_count <= 1) supported.push(100 - row.prob);
  return printedPercents(text).filter(
    (p) => !supported.some((s) => Math.abs(s - p) <= 1.5),
  );
}

/* ── Specimens, in the shape the two routes actually serve ───────────────── */

/** The Thune ladder: two NESTED date rungs summing to 3.5, the defect's own specimen. */
const THUNE: PoliticsMarketRow = {
  q: "John Thune announces departure as Senate Majority Leader?",
  prob: 2.5,
  src: "kalshi",
  market_id: 52756060,
  top_outcomes: [
    { name: "Before Nov 3, 2026", prob: 2.5 },
    { name: "Before Oct 1, 2026", prob: 1.0 },
  ],
  outcome_count: 2,
};

/** A genuine two-candidate race: two served legs that ARE one question (100.0). */
const CALIFORNIA_AG: PoliticsMarketRow = {
  q: "California Attorney General winner?",
  prob: 94.5,
  src: "polymarket",
  market_id: 60473187,
  top_outcomes: [
    { name: "Rob Bonta", prob: 94.5 },
    { name: "Michael E. Gates", prob: 5.5 },
  ],
  outcome_count: 2,
};

/** A Kalshi Yes/No: ONE outcome, and its No side exists nowhere but this card. */
const IMPLICIT_NO: PoliticsMarketRow = {
  q: "Real Madrid: Florentino Perez Out as President",
  prob: 2.0,
  src: "kalshi",
  market_id: 25924737,
  top_outcomes: [{ name: "Yes", prob: 2.0 }],
  outcome_count: 1,
};

function entMarket(over: Partial<EntMarketRow>): EntMarketRow {
  return {
    q: "placeholder",
    prob: 50,
    src: "polymarket",
    market_id: 1,
    external_id: "x",
    kind: "internet",
    top_outcomes: [],
    outcome_count: 1,
    volume_24h: 1000,
    resolution_date: null,
    image_url: null,
    hook: null,
    ...over,
  };
}

/** Two BUCKETS, neither of which is a "yes" or a "no". */
const MRBEAST = entMarket({
  q: "# of views of next MrBeast video on week 1?",
  prob: 6.0,
  market_id: 61300898,
  top_outcomes: [
    { name: "90-100M", prob: 6.0, delta_24h: 0 },
    { name: "100M+", prob: 5.1, delta_24h: 0 },
  ],
  outcome_count: 2,
});

/** The control on the same rail: a real Yes/No, which must keep its YES/NO bar. */
const ENT_BINARY = entMarket({
  q: "Will Dune: Part Three be delayed?",
  prob: 12,
  market_id: 61300899,
  top_outcomes: [{ name: "Yes", prob: 12, delta_24h: 0 }],
  outcome_count: 1,
});

function politicsPayload(markets: PoliticsMarketRow[]): PoliticsData {
  return {
    total_markets: markets.length,
    updated_at: "2026-09-17T18:00:00+00:00",
    themes: {
      presidential: {
        count: 0,
        headline_q: null,
        candidates: [],
        has_dual_source: false,
        kalshi_market_id: null,
        poly_market_id: null,
        side_markets: [],
      },
      congressional: {
        count: 0,
        markets: [],
        chamber_control: { senate: null, house: null },
        senate_map: null,
      },
      gubernatorial: { count: 0, markets: [] },
      policy: { count: markets.length, markets },
      scotus: { count: 0, markets: [] },
      international: { count: 0, markets: [] },
      other: { count: 0, markets: [] },
    },
    cross_source: [],
    by_source: { kalshi: 1, polymarket: 1 },
  };
}

function entertainmentPayload(
  sidebar: EntMarketRow[],
  moments: EntMarketRow[],
): EntertainmentData {
  return {
    total_markets: sidebar.length + moments.length,
    updated_at: "2026-09-17T18:00:00+00:00",
    trending: [],
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
      tech_culture: { count: sidebar.length, markets: sidebar },
    },
    cultural_moments: moments,
    by_source: { kalshi: 1, polymarket: 1 },
  };
}

function renderWith(payload: unknown, page: React.ComponentType): string {
  (global as never as { __PAYLOAD__: unknown }).__PAYLOAD__ = payload;
  return renderToStaticMarkup(React.createElement(page));
}

/* ═══ ARM 1 — the rule itself ═════════════════════════════════════════════ */

describe("twoLegCardPair: the second number is read, and derived only where that is true", () => {
  it("reads the served second leg of a two-rung market rather than the complement", () => {
    const pair = twoLegCardPair(THUNE);
    expect(pair.second).toEqual({ name: "Before Oct 1, 2026", prob: 1.0 });
    // The number the card used to print, named so this cannot pass by accident.
    expect(pair.second?.prob).not.toBeCloseTo(100 - THUNE.prob, 5);
    expect(pair.oneQuestion).toBe(false);
  });

  it("reads the served leg even when the pair IS one question", () => {
    // 93.5 + 6.4 = 99.9 — inside the complement band, yet 6.4 ≠ 100 − 93.5.
    // So this arm fails for a fix that only re-derives when the sum looks wrong.
    const pair = twoLegCardPair({
      prob: 93.5,
      outcome_count: 2,
      top_outcomes: [
        { name: "Letitia James (D)", prob: 93.5 },
        { name: "Saritha Komatireddy (R)", prob: 6.4 },
      ],
    });
    expect(pair.second?.prob).toBe(6.4);
    expect(pair.oneQuestion).toBe(true);
  });

  it("keeps deriving the implicit No of a ONE-outcome contract", () => {
    const pair = twoLegCardPair(IMPLICIT_NO);
    expect(pair.first).toEqual({ name: "Yes", prob: 2.0 });
    expect(pair.second).toEqual({ name: "No", prob: 98.0 });
    expect(pair.oneQuestion).toBe(true);
  });

  it("states NO second number when a multi-outcome market served only one price", () => {
    // The #6255 population — an unpriced rung is dropped from the slice while
    // `outcome_count` keeps the ladder's true arity. Draws 0 cards today; it is
    // asserted because inventing a price is the class this ship closes.
    const pair = twoLegCardPair({
      prob: 62,
      outcome_count: 2,
      top_outcomes: [{ name: "Yes", prob: 62 }],
    });
    expect(pair.second).toBeNull();
    expect(pair.oneQuestion).toBe(false);
  });
});

/* ═══ ARM 2 — /politics, rendered ═════════════════════════════════════════ */

describe("/politics prints no percent the payload does not carry", () => {
  const markup = renderWith(
    politicsPayload([THUNE, CALIFORNIA_AG, IMPLICIT_NO]),
    PoliticsPage,
  );

  it("renders all three specimens (so the arms below cannot pass on an empty page)", () => {
    for (const row of [THUNE, CALIFORNIA_AG, IMPLICIT_NO]) {
      expect(cardTexts(markup, row.market_id)).toHaveLength(1);
    }
  });

  it("gives the Thune rungs their own served prices, and never 98%", () => {
    const [text] = cardTexts(markup, THUNE.market_id);
    expect(text).toContain("Before Oct 1, 2026");
    expect(unsupportedPercents(text, THUNE)).toEqual([]);
    expect(text).not.toContain("98%");
    expect(text).not.toContain("97%");
  });

  it("does not put two nested rungs on the two ends of one `vs`", () => {
    // The numbers are only half of it. `A% name vs B% name` over one full bar is
    // a claim that the two are opposite ends of one question, and `Before Nov 3`
    // and `Before Oct 1` are nested rather than opposed. A pair outside the
    // complement band takes this page's own rung render instead — which is also
    // the arm that says the routing decision, not just the arithmetic, shipped.
    const [thune] = cardTexts(markup, THUNE.market_id);
    expect(thune).not.toContain(" vs ");
    const [race] = cardTexts(markup, CALIFORNIA_AG.market_id);
    expect(race).toContain(" vs ");
  });

  it("CONTROL — a real two-candidate race keeps both sides, summing to 100", () => {
    const [text] = cardTexts(markup, CALIFORNIA_AG.market_id);
    expect(text).toContain("Rob Bonta");
    expect(text).toContain("Michael E. Gates");
    expect(unsupportedPercents(text, CALIFORNIA_AG)).toEqual([]);
    // #2831's pair contract: rounded once, together — 95/6 was 101 on production.
    const printed = printedPercents(text);
    expect(printed).toHaveLength(2);
    expect(printed[0] + printed[1]).toBe(100);
  });

  it("CONTROL — a one-outcome contract still shows its implicit No", () => {
    const [text] = cardTexts(markup, IMPLICIT_NO.market_id);
    expect(text).toContain("No");
    expect(printedPercents(text)).toContain(98);
    expect(unsupportedPercents(text, IMPLICIT_NO)).toEqual([]);
  });
});

/* ═══ ARM 3 — /entertainment, rendered ════════════════════════════════════ */

describe("/entertainment prints no percent the payload does not carry", () => {
  const markup = renderWith(
    entertainmentPayload([MRBEAST, ENT_BINARY], [MRBEAST, ENT_BINARY]),
    EntertainmentPage,
  );

  it("renders each specimen TWICE — the moments feed and the tech rail", () => {
    // Both rails are in the payload deliberately: they are two call sites with
    // two copies of the decision, and a battery run against only the first let a
    // mutation of the second survive.
    expect(cardTexts(markup, MRBEAST.market_id)).toHaveLength(2);
    expect(cardTexts(markup, ENT_BINARY.market_id)).toHaveLength(2);
  });

  it("gives the MrBeast buckets their own names and prices, and no YES/NO", () => {
    for (const text of cardTexts(markup, MRBEAST.market_id)) {
      expect(text).toContain("90-100M");
      expect(text).toContain("100M+");
      expect(unsupportedPercents(text, MRBEAST)).toEqual([]);
      expect(text).not.toContain("94%");
      // The words themselves: neither bucket is a yes or a no.
      expect(text).not.toMatch(/\bYES\b/);
      expect(text).not.toMatch(/\bNO\b/);
    }
  });

  it("CONTROL — a real Yes/No market keeps its YES/NO bar and its derived No", () => {
    for (const text of cardTexts(markup, ENT_BINARY.market_id)) {
      expect(text).toMatch(/\bYES\b/);
      expect(text).toMatch(/\bNO\b/);
      expect(printedPercents(text)).toContain(88);
      expect(unsupportedPercents(text, ENT_BINARY)).toEqual([]);
    }
  });
});
