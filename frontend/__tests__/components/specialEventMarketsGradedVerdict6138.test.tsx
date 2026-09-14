/**
 * ux/1257 (#6138) — A SETTLED GAME'S "OTHER MARKETS" STATE THEIR RESULT.
 *
 * Production, `/events/14780142` at 390px, 2026-09-14 11:20Z. Chicago had beaten
 * Carolina 59–37 four hours earlier and the card read:
 *
 *     Chicago vs Carolina: 1st Half / Fulltime Result
 *       Chicago wins 1H / Chicago wins game      last quote 100%
 *       Carolina wins 1H / Chicago wins game     last quote   0%
 *       ... seven more rows, every one "last quote 0%"
 *
 * Row one is the answer, printed as a price. Rows two onward are worse: their
 * wire `probability` is **null** — no venue quoted them — and `mergeOutcomes`'
 * `?? 0` turned "no price" into a rendered `0%`. All nine rows arrived carrying
 * `is_winner` and `resolution_source: api_settlement`.
 *
 * Alex's standing ruling is *settled means settled*: cards show RESULTS.
 *
 * ── REACH, MEASURED BEFORE THE FIX ───────────────────────────────────────────
 * Four settled NFL pages (`14780142`, `14780147`, `14780145`, `14637256`,
 * 11:25Z): 275 `other` rows, **247 graded (90%)** — 79 winners, 168 losers —
 * and every one of the 247 rendered as a quote. **73 of the 275 (27%) carry a
 * null price and printed `last quote 0%`; all 73 are graded losers**, so the
 * invented number was never the best thing we could say.
 *
 * ── WHY MOST OF THIS SUITE IS ABOUT REFUSING ─────────────────────────────────
 *
 * A frozen quote on a finished game is weak. A row crowned `Lost` that nobody
 * graded is a lie, and it is the exact lie #4788 was filed on — `is_winner` is
 * `boolean NULL DEFAULT false`, so the never-graded cohort is indistinguishable
 * from a called loss on that field alone. The rule is `outcomeRowVerdict` and it
 * is CALLED here, never copied (#6082 exists because the last copy diverged), so
 * five of the tests below are about the doors it closes rather than the ship.
 *
 * The differential test is the load-bearing one. `is_winner`/`resolution_source`
 * are the fourth and fifth optional fields threaded wire → module → component on
 * this surface, and #2086's `eventStatus` shipped declared, passed, and
 * destructured by nobody. A dropped field is invisible to tsc and to a grep, so
 * the same payload is rendered WITH and WITHOUT the two keys and the markups are
 * required to differ.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import SpecialEventMarkets from "../../components/SpecialEventMarkets";
import { SETTLED_QUOTE_PREFIX } from "@/lib/settledQuote";
import { RETRACTED_RESOLUTION_SOURCE } from "@/components/futures/OutcomeRow";
import type { GameMarketsResponse } from "@/lib/api";

type WireRow = NonNullable<GameMarketsResponse["other"]>[number];

/**
 * Verbatim wire, `GET /api/events/14780142/game-markets`, read 2026-09-14
 * 11:22Z — the nine-row `1st Half / Fulltime Result` ladder that produced the
 * screenshot above, plus the three-row `Race to 7 Points` card beside it.
 *
 * The two cards are kept together on purpose: the ladder is graded by
 * `api_settlement` (tier 3) and the race by `clean_resolution` (tier 1), so the
 * fixture exercises both sides of the authority split without a hand-built row.
 */
const WIRE: WireRow[] = [
  { market_name: "Chicago vs Carolina: 1st Half / Fulltime Result", outcome_name: "Chicago wins 1H / Chicago wins game", probability: 1.0, source: "kalshi", observed_at: "2026-09-13T20:26:13.247902+00:00", is_winner: true, resolution_source: "api_settlement" },
  { market_name: "Chicago vs Carolina: 1st Half / Fulltime Result", outcome_name: "Carolina wins 1H / Chicago wins game", probability: null, source: "kalshi", observed_at: "2026-09-13T20:26:13.247902+00:00", is_winner: false, resolution_source: "api_settlement" },
  { market_name: "Chicago vs Carolina: 1st Half / Fulltime Result", outcome_name: "Carolina wins 1H / Game ends in a tie", probability: null, source: "kalshi", observed_at: "2026-09-13T20:26:13.247902+00:00", is_winner: false, resolution_source: "api_settlement" },
  { market_name: "Chicago vs Carolina: 1st Half / Fulltime Result", outcome_name: "Tie 1H / Chicago wins game", probability: null, source: "kalshi", observed_at: "2026-09-13T20:26:13.247902+00:00", is_winner: false, resolution_source: "api_settlement" },
  { market_name: "Chicago vs Carolina: 1st Half / Fulltime Result", outcome_name: "Chicago wins 1H / Carolina wins game", probability: null, source: "kalshi", observed_at: "2026-09-13T20:26:13.247902+00:00", is_winner: false, resolution_source: "api_settlement" },
  { market_name: "Chicago vs Carolina: 1st Half / Fulltime Result", outcome_name: "Tie 1H / Carolina wins game", probability: null, source: "kalshi", observed_at: "2026-09-13T20:26:13.247902+00:00", is_winner: false, resolution_source: "api_settlement" },
  { market_name: "Chicago vs Carolina: 1st Half / Fulltime Result", outcome_name: "Chicago wins 1H / Game ends in a tie", probability: null, source: "kalshi", observed_at: "2026-09-13T20:26:13.247902+00:00", is_winner: false, resolution_source: "api_settlement" },
  { market_name: "Chicago vs Carolina: 1st Half / Fulltime Result", outcome_name: "Carolina wins 1H / Carolina wins game", probability: null, source: "kalshi", observed_at: "2026-09-13T20:26:13.247902+00:00", is_winner: false, resolution_source: "api_settlement" },
  { market_name: "Chicago vs Carolina: 1st Half / Fulltime Result", outcome_name: "Tie 1H / Game ends in a tie", probability: null, source: "kalshi", observed_at: "2026-09-13T20:26:13.247902+00:00", is_winner: false, resolution_source: "api_settlement" },
  { market_name: "Chicago vs Carolina: Race to 7 Points", outcome_name: "Carolina reaches 7 points first", probability: 0.99, source: "kalshi", observed_at: "2026-09-13T20:34:13.264517+00:00", is_winner: true, resolution_source: "clean_resolution" },
  { market_name: "Chicago vs Carolina: Race to 7 Points", outcome_name: "Chicago reaches 7 points first", probability: 0.01, source: "kalshi", observed_at: "2026-09-13T20:34:13.264517+00:00", is_winner: false, resolution_source: "clean_resolution" },
  { market_name: "Chicago vs Carolina: Race to 7 Points", outcome_name: "Neither team reaches 7 points", probability: 0.01, source: "kalshi", observed_at: "2026-09-13T20:34:13.264517+00:00", is_winner: false, resolution_source: "clean_resolution" },
];

function payload(other: WireRow[] = WIRE, overrides: Partial<GameMarketsResponse> = {}): GameMarketsResponse {
  return {
    event_id: 14780142,
    home_team: "Carolina Panthers",
    away_team: "Chicago Bears",
    home_score: 37,
    away_score: 59,
    status: "completed",
    totals: [],
    player_props: [],
    team_totals: [],
    spreads: [],
    period_markets: [],
    matchups: [],
    other,
    pace: null,
    ...overrides,
  } as unknown as GameMarketsResponse;
}

const render = (data: GameMarketsResponse, eventStatus = data.status) =>
  renderToStaticMarkup(<SpecialEventMarkets data={data} eventStatus={eventStatus} />);

const visible = (html: string) =>
  html
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&#x2F;/g, "/")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ");

/**
 * The text of each verdict row, read off the ROW ELEMENT.
 *
 * Not a window of characters after the label: `specialEventMarketsDecidedSet`
 * records that a window silently captured a SIBLING row's percentage the moment
 * the card's order changed. A verdict row renders its label and its one word and
 * nothing else, so the element is the honest boundary and the row's whole text
 * can be asserted exactly.
 */
const verdictRows = (html: string): string[] =>
  [...html.matchAll(/<div[^>]*data-testid="special-markets-verdict"[\s\S]*?<\/span><\/div>/g)].map(
    (m) => visible(m[0]).trim(),
  );

/** Strip the two grading keys — the payload an older serialiser sends. */
const ungraded = (rows: WireRow[]): WireRow[] =>
  rows.map(({ is_winner: _w, resolution_source: _s, ...rest }) => rest);

describe("#6138 — a graded row states its verdict instead of a price", () => {
  test("THE SHIP: the winner reads `Won`, and no percentage survives on the row", () => {
    const html = render(payload());
    const row = verdictRows(html).find((r) =>
      r.includes("Chicago wins 1H / Chicago wins game"),
    );
    expect(row).toBeDefined();
    expect(row).toBe("Chicago wins 1H / Chicago wins game Won");
    // Both halves of what it replaced: the number and the caption that framed it.
    expect(row).not.toMatch(/\d+%/);
    expect(row).not.toContain(SETTLED_QUOTE_PREFIX);
  });

  test("THE 0% WE INVENTED IS GONE: a null-priced loser reads `Lost`", () => {
    // This row's wire `probability` is null. It printed `last quote 0%` — a
    // number no venue ever quoted, standing where the answer was.
    const row = verdictRows(render(payload())).find((r) =>
      r.includes("Tie 1H / Game ends in a tie"),
    );
    expect(row).toBe("Tie 1H / Game ends in a tie Lost");
    expect(row).not.toContain("0%");
  });

  test("the whole section: every graded row states a verdict, none prints a number", () => {
    const html = render(payload());
    const rows = verdictRows(html);
    // 12 wire rows, 12 graded, 2 winners. The count is asserted so a change that
    // renders ONE verdict and leaves eleven quotes cannot pass the two tests above.
    expect(rows).toHaveLength(12);
    expect(rows.filter((r) => r.endsWith(" Won"))).toHaveLength(2);
    expect(rows.filter((r) => r.endsWith(" Lost"))).toHaveLength(10);
    for (const row of rows) expect(row).not.toMatch(/\d+%/);
    // And the section as a whole no longer quotes anything, so the words the
    // quotes were wrapped in are gone too.
    expect(visible(html)).not.toContain(SETTLED_QUOTE_PREFIX);
  });

  test("DIFFERENTIAL: strip the two keys and the same payload renders as it did before", () => {
    // The old-payload case, which is also the mid-deploy case: Vercel ships
    // ahead of Heroku, so this component runs against a serialiser with neither
    // key for the length of every release. It must render exactly today's page,
    // not a blackout.
    const before = render(payload(ungraded(WIRE)));
    const after = render(payload());

    expect(verdictRows(before)).toHaveLength(0);
    expect(visible(before)).toContain(SETTLED_QUOTE_PREFIX);
    expect(visible(before)).toContain("100%");
    // The fields are load-bearing: an optional one dropped mid-thread is
    // invisible to tsc and to a grep, and this is the assertion that sees it.
    expect(after).not.toBe(before);
  });

  test("REFUSES the never-graded cohort: `is_winner: false` with a null source keeps its price", () => {
    // #4788. `is_winner` is `boolean NULL DEFAULT false`, so a row nobody graded
    // is served as exactly this. Crowning it `Lost` is the confident-red lie the
    // whole rule exists to prevent, and `resolution_source` is the only field
    // that separates the two cases.
    const rows = WIRE.map((r) => ({ ...r, is_winner: false, resolution_source: null }));
    const html = render(payload(rows));
    expect(verdictRows(html)).toHaveLength(0);
    expect(visible(html)).toContain(SETTLED_QUOTE_PREFIX);
  });

  test("REFUSES a retraction: `ungradeable_result` keeps its price", () => {
    // CAL-P056/#1852. The one `resolution_source` that asserts NO winner — it
    // exists to take a fabricated loss OUT of the curve. A row we have declared
    // unknowable is the last row entitled to a verdict.
    const rows = WIRE.map((r) => ({ ...r, resolution_source: RETRACTED_RESOLUTION_SOURCE }));
    const html = render(payload(rows));
    expect(verdictRows(html)).toHaveLength(0);
    expect(visible(html)).toContain(SETTLED_QUOTE_PREFIX);
  });

  test("ON A LIVE GAME only a tier-3 winner crosses the line, and no loser does", () => {
    // #6082. A first-half market settles while the game is still being played,
    // and saying so is right. But a defaulted `false` on a game in progress is
    // not a called loss, so the LOST arm waits for the event to finish.
    const html = render(payload(WIRE, { status: "live" }), "live");
    const rows = verdictRows(html);
    // `api_settlement` is authoritative; `clean_resolution` is not, so the
    // `Race to 7 Points` winner keeps its price and the ladder's winner does not.
    expect(rows).toEqual(["Chicago wins 1H / Chicago wins game Won"]);
    expect(visible(html)).toContain("Carolina reaches 7 points first");
    expect(visible(html)).toMatch(/Carolina reaches 7 points first[\s\S]*?99%/);
  });

  test("REFUSES a contradiction: two venues disagreeing on the winner keep the price", () => {
    // `mergeOutcomes` collapses rows sharing a label, so one rendered row can
    // inherit two settlements. Two graded rows that disagree about who won are a
    // truth defect upstream and the honest render for a contradiction is the
    // live one.
    const [first, ...rest] = WIRE;
    const contradicted: WireRow[] = [
      first,
      { ...first, source: "polymarket", is_winner: false, resolution_source: "clob_authoritative" },
      ...rest,
    ];
    const html = render(payload(contradicted));
    const rows = verdictRows(html);
    expect(rows.some((r) => r.includes("Chicago wins 1H / Chicago wins game"))).toBe(false);
    // Its eleven uncontradicted siblings are untouched — a contradiction on one
    // label may not blank the card.
    expect(rows).toHaveLength(11);
  });

  test("ABSTAINS rather than refusing: one venue grades, the other has not yet", () => {
    // The other direction of the same merge. A question Kalshi has settled and
    // Polymarket has not is still settled; dropping the grade because a second
    // venue is slow is the false-negative half of the same mistake.
    const [first, ...rest] = WIRE;
    const partial: WireRow[] = [
      first,
      { ...first, source: "polymarket", is_winner: null, resolution_source: null },
      ...rest,
    ];
    const rows = verdictRows(render(payload(partial)));
    expect(rows).toContain("Chicago wins 1H / Chicago wins game Won");
  });

  test("#4970's denominator: a verdict row is not counted when the card dates itself", () => {
    /* The card states its price age ONCE when its live rows agree about being
       stale, and falls back to per-row marks when they disagree — one row quoted
       four minutes ago beside one quoted three days ago cannot be summarised by
       a single number without the summary being false about one of them.
       A row stating `Won` has no live price for an age to be ABOUT, so counting
       it in that denominator is how a card of stale rows comes to read as mixed.

       Built as the sharp case rather than the easy one: the graded row is the
       FRESH one and every live row around it is stale. Excluded (correct) the
       card speaks once; counted, the card sees 1 fresh + 8 stale, calls itself
       mixed, drops its own mark and puts eight per-row marks up instead.

       Offset from `Date.now()` FIRST and never from a literal, so the fixture
       cannot drift across the 30-minute bar as the suite ages (gotcha #44). */
    const minutesAgo = (m: number) => new Date(Date.now() - m * 60_000).toISOString();
    const ladder = WIRE.filter((r) => r.market_name.includes("Fulltime")).map((r, i) => ({
      ...r,
      observed_at: i === 0 ? minutesAgo(2) : minutesAgo(90),
      // Only the fresh row keeps its grade; the rest are live, stale and
      // ungraded, which is the population the card is summarising.
      ...(i === 0 ? {} : { is_winner: null, resolution_source: null }),
    }));
    const html = render(payload(ladder, { status: "live" }), "live");

    expect(verdictRows(html)).toEqual(["Chicago wins 1H / Chicago wins game Won"]);
    expect(html).toMatch(/data-testid="price-age-mark" data-scope="card"/);
    expect(html).not.toMatch(/data-testid="price-age-mark" data-scope="row"/);
  });
});
