/**
 * ux/1442 (#8067) — A PRICE NOBODY QUOTED IS NOT A PRICE OF ZERO.
 *
 * Production `/events/14780545` at 390px, 2026-09-22 19:49Z (web `0896cf4e`).
 * The Rams had beaten the Giants 28–6 and the settled `1st Touchdown` board
 * read:
 *
 *     CJ Daniels                             last quote 0%
 *     Puka Nacua                             last quote 0%
 *     Jordan Whittington                     last quote 0%
 *
 * Those three legs are served `probability: null` — the venue WITHDREW their
 * price — with `is_winner: null` and `resolution_source: null` beside it. The
 * zero was manufactured in the renderer: `mergeOutcomes` wrote
 * `probability ?? 0`, so "nobody quoted this" and "the market priced this at
 * nothing" arrived at `OutcomeBar` as the same number. On a *1st Touchdown*
 * board `0%` reads as "this player had no chance" — a claim nobody made.
 *
 * ── WHY #6138 DID NOT ALREADY COVER IT ───────────────────────────────────────
 * #6138 named this exact string and fixed its 73 rows by giving them a VERDICT:
 * every one was a graded loser, so `Lost` was sitting in the payload beside the
 * invented number. It never touched `?? 0`. #8044 (live the same day) then
 * restored the withheld legs that had been dropped from the payload entirely,
 * and those arrive with no grade — so there is no verdict to fall back on and
 * they fall through to the price path. The residue neither ship could reach.
 *
 * ── REACH, MEASURED ON THE SPECIMEN ──────────────────────────────────────────
 * `GET /api/events/14780545/game-markets`, read 20:20Z 2026-09-22: 184 `other`
 * rows, **86 with a null price**, of which **82 are graded** and already render
 * a verdict through #6138. **4 reach the price path** — the three above plus
 * CJ Daniels again on the `1st Los Angeles Rams Touchdown` board.
 *
 * ── WHY THE ASSERTIONS ARE LABELLED (ux/1201's rule, priceAgeMark4970) ───────
 *   SHIP     red against the parent. This is the change.
 *   GUARD    green against the parent, red against a named mutant of the new
 *            code. It protects a DECISION, not the diff.
 *   CONTROL  green against both. It pins what must not move.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import SpecialEventMarkets from "../../components/SpecialEventMarkets";
import { SETTLED_QUOTE_PREFIX } from "@/lib/settledQuote";
import { buildMarketSection, mergeOutcomes } from "@/lib/otherMarketGroups";
import { SOURCE_STALE_AFTER_MS } from "@/lib/sourceAge";
import type { GameMarketsResponse } from "@/lib/api";

type WireRow = NonNullable<GameMarketsResponse["other"]>[number];

const BOARD = "New York Giants vs Los Angeles Rams: 1st Touchdown";

/**
 * Verbatim wire, `GET /api/events/14780545/game-markets`, read 20:20Z
 * 2026-09-22 — five of the board's 28 rows, chosen because they are the three
 * states this ship has to tell apart:
 *
 *   Davante Adams      priced AND graded   — the answer
 *   Blake Corum        no price, GRADED    — #6138's population, reads `Lost`
 *   the three runners  no price, no grade  — this issue
 *
 * Trimmed to five so the card stays under `MAX_OUTCOMES_PER_CARD` (8) and every
 * row renders in the card body rather than behind the `N more` disclosure; the
 * rows themselves are byte-for-byte the served ones.
 */
const WIRE: WireRow[] = [
  { market_name: BOARD, outcome_name: "Davante Adams", probability: 1.0, source: "kalshi", observed_at: "2026-09-22T03:11:49.354824+00:00", is_winner: true, resolution_source: "api_settlement" },
  { market_name: BOARD, outcome_name: "Blake Corum", probability: null, source: "kalshi", observed_at: "2026-09-22T03:11:49.354824+00:00", is_winner: false, resolution_source: "api_settlement" },
  { market_name: BOARD, outcome_name: "Jordan Whittington", probability: null, source: "kalshi", observed_at: "2026-09-22T03:11:49.354824+00:00", is_winner: null, resolution_source: null },
  { market_name: BOARD, outcome_name: "Puka Nacua", probability: null, source: "kalshi", observed_at: "2026-09-22T03:11:49.354824+00:00", is_winner: null, resolution_source: null },
  { market_name: BOARD, outcome_name: "CJ Daniels", probability: null, source: "kalshi", observed_at: "2026-09-22T03:11:49.354824+00:00", is_winner: null, resolution_source: null },
];

/** The three legs of this issue, by name. */
const WITHHELD = ["Jordan Whittington", "Puka Nacua", "CJ Daniels"];

function payload(
  other: WireRow[] = WIRE,
  overrides: Partial<GameMarketsResponse> = {},
): GameMarketsResponse {
  return {
    event_id: 14780545,
    home_team: "Los Angeles Rams",
    away_team: "New York Giants",
    home_score: 28,
    away_score: 6,
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

/** Tags stripped, entities decoded — what a reader actually sees. */
const visible = (html: string) =>
  html
    .replace(/<span class="sr-only">.*?<\/span>/g, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&#x2F;/g, "/")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();

/**
 * The whole text of each row rendered by a given `data-testid`, read off the
 * ROW ELEMENT.
 *
 * Not a window of characters after the label: `specialEventMarketsDecidedSet`
 * records that a window silently captured a SIBLING row's percentage the moment
 * the card's order changed. Each of these rows renders its own content and
 * nothing else, so the element is the honest boundary.
 */
const rowsByTestId = (html: string, testId: string): string[] => {
  const rows: string[] = [];
  const open = new RegExp(`<div[^>]*data-testid="${testId}"[^>]*>`, "g");
  for (let m = open.exec(html); m !== null; m = open.exec(html)) {
    // Walk forward balancing `<div>`s. A lazy `(.*?)</div></div>` cannot do
    // this: a verdict row closes on `</span></div>` and the scan then runs on
    // into the NEXT row — measured, it returned all three rows as one string.
    let depth = 1;
    let i = m.index + m[0].length;
    const start = i;
    const tag = /<\/?div\b[^>]*>/g;
    tag.lastIndex = i;
    for (let t = tag.exec(html); t !== null && depth > 0; t = tag.exec(html)) {
      depth += t[0].startsWith("</") ? -1 : 1;
      i = t.index;
    }
    rows.push(visible(html.slice(start, i)));
  }
  return rows;
};

const noPriceRows = (html: string) => rowsByTestId(html, "special-markets-no-price");
const verdictRows = (html: string) => rowsByTestId(html, "special-markets-verdict");

// ─────────────────────────────────────────────────────────────────────────────
// SHIP — red against the parent, where all three of these printed `0%`.
// ─────────────────────────────────────────────────────────────────────────────

describe("SHIP: a runner nobody priced is not a runner priced at nothing", () => {
  test("the three withheld legs print their name and NO number", () => {
    const html = render(payload());
    const rows = noPriceRows(html);
    expect(rows.sort()).toEqual([...WITHHELD].sort());
    // The whole text of each row is the name. Not a dash, not "no price", not a
    // parenthetical: notice 34's remedy for a number we cannot show honestly is
    // to leave the space empty rather than explain the emptiness.
    for (const row of rows) expect(WITHHELD).toContain(row);
  });

  test("no row on the settled board says `last quote 0%`", () => {
    const seen = visible(render(payload()));
    expect(seen).toContain("CJ Daniels");
    expect(seen).not.toContain(`${SETTLED_QUOTE_PREFIX} 0%`);
    // And the three names are never followed by a quote of any size.
    for (const name of WITHHELD) {
      expect(seen).not.toMatch(new RegExp(`${name} ${SETTLED_QUOTE_PREFIX}`));
    }
  });

  /* CONTROL, and it was labelled SHIP until the parent run graded it. A SETTLED
     board draws no outcome bars in either state — the frozen branch dropped
     them for #2086 — so this pins that and nothing more. The discriminating
     half (a LIVE board, where the parent draws a zero-width bar for a price
     nobody quoted) is asserted in the live block at the foot of this file. */
  test("a settled board draws no outcome bars at all", () => {
    const html = render(payload());
    expect(html).not.toContain("bg-violet-400");
    expect(html).not.toMatch(/style="width:0%"/);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// THE DIFFERENTIAL — the whole issue in one pair.
// ─────────────────────────────────────────────────────────────────────────────

describe("SHIP: `null` and `0` stop reaching the renderer as the same fact", () => {
  /* `probabilityDisplay`'s own words: "Exact `0` and exact `1` are printed
     plainly — those ARE the boundaries, and a caller that wants to distinguish
     'no data' from 'genuinely zero' does so before calling." Until this ship
     no caller on this surface COULD: the merge had already spent the
     distinction. So the same payload is rendered with the price withheld and
     with a genuine zero, and the two markups are required to differ.

     ⚠️ HONEST SCOPE: the specimen page serves no exact zero (0 of 184 rows; the
     smallest real price on it is 0.001, which prints `<1%`). The rows below are
     the served rows with one field changed, which is exactly the control this
     needs — the two payloads differ in nothing else.

     TWO ROWS AND NOT ONE, and the reason is worth keeping. Davante Adams at
     1.0 is this board's only served price, so zeroing exactly one withheld row
     leaves the market with TWO non-null probabilities summing to 1.0 —
     `findWinProbMarkets`' signature for "this is the hero's own question,
     already answered above" — and the whole section is correctly stripped. The
     first draft of this test asserted against an empty string for that reason.
     Zeroing two rows keeps the fixture clear of a filter that has nothing to do
     with this ship. */
  const zeroed = WIRE.map((r) =>
    r.outcome_name === "CJ Daniels" || r.outcome_name === "Puka Nacua"
      ? { ...r, probability: 0 }
      : r,
  );

  test("a genuine zero still prints `last quote 0%`", () => {
    const seen = visible(render(payload(zeroed)));
    expect(seen).toContain(`CJ Daniels ${SETTLED_QUOTE_PREFIX} 0%`);
    expect(seen).toContain(`Puka Nacua ${SETTLED_QUOTE_PREFIX} 0%`);
    // …and the row that is still withheld still says nothing.
    expect(noPriceRows(render(payload(zeroed)))).toEqual(["Jordan Whittington"]);
  });

  test("the two payloads render differently", () => {
    expect(render(payload(zeroed))).not.toEqual(render(payload()));
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// GUARD — the decisions, each dying to a named mutant.
// ─────────────────────────────────────────────────────────────────────────────

describe("GUARD: a verdict still outranks silence", () => {
  /* Mutant: hoist the `outcome.prob === null` branch ABOVE the verdict branch
     in `OutcomeBar`. Every row #6138 fixed carries a null price, so the new
     branch would swallow all 73 of them and `Lost` would vanish from a settled
     board — a fix for an invented zero that deletes the answer beside it. */
  test("Blake Corum — no price, graded loser — still reads `Lost`", () => {
    const html = render(payload());
    expect(verdictRows(html)).toContain("Blake Corum Lost");
    expect(noPriceRows(html)).not.toContain("Blake Corum");
  });

  test("Davante Adams — priced and graded — still reads `Won`", () => {
    expect(verdictRows(render(payload()))).toContain("Davante Adams Won");
  });
});

describe("SHIP: silence is not disagreement", () => {
  /* Mutant: revert the agreement test to `r.probability ?? 0`. A withheld row
     beside a quoted 0.62 then spreads 0.62, blows `AGREEMENT_TOLERANCE`, and
     the label is WITHHELD — an outcome one venue is actively pricing vanishes
     off the card because a second venue stopped quoting it.

     ⚠️ HONEST SCOPE: 0 of 184 rows on the specimen page are in this state, so
     this arm is forward-looking. It is guarded because it is the same coercion
     on the same line, not because anyone has seen it. */
  test("a null row beside a quoted one keeps the label, at the quoted price", () => {
    const { outcomes, withheld } = mergeOutcomes([
      { label: "Puka Nacua", probability: null, source: "kalshi" },
      { label: "Puka Nacua", probability: 0.62, source: "polymarket" },
    ]);
    expect(withheld).toBe(0);
    expect(outcomes).toHaveLength(1);
    expect(outcomes[0].prob).toBe(0.62);
  });

  /* Mutant: `prob: group[0].probability ?? null`. The null row is FIRST in the
     fixture above precisely so taking the group's first row instead of its
     first QUOTED row returns null and loses a price we were served. */
  test("the price comes from the row that carried one, not from row zero", () => {
    const { outcomes } = mergeOutcomes([
      { label: "Puka Nacua", probability: null, source: "kalshi" },
      { label: "Puka Nacua", probability: 0.62, source: "polymarket" },
    ]);
    expect(outcomes[0].prob).not.toBeNull();
  });

  /* Mutant: leave `sourceCount: group.length`. The badge's own words are "how
     many wire rows AGREED on this price", and a venue that quoted nothing
     agreed to nothing — two sources claimed over one venue's number. */
  test("a row that quoted nothing is not counted as a source that agreed", () => {
    const { outcomes } = mergeOutcomes([
      { label: "Puka Nacua", probability: null, source: "kalshi" },
      { label: "Puka Nacua", probability: 0.62, source: "polymarket" },
    ]);
    expect(outcomes[0].sourceCount).toBe(1);
  });

  /* CONTROL: two venues that both quote and agree are untouched — the merge's
     ordinary case, and the one the badge exists for. */
  test("two agreeing quotes still merge and still count two", () => {
    const { outcomes } = mergeOutcomes([
      { label: "Puka Nacua", probability: 0.61, source: "kalshi" },
      { label: "Puka Nacua", probability: 0.62, source: "polymarket" },
    ]);
    expect(outcomes[0].sourceCount).toBe(2);
    expect(outcomes[0].prob).toBe(0.61);
  });

  /* CONTROL: and two venues that genuinely disagree are still withheld. The
     ship must not have turned the agreement test off. */
  test("a real disagreement is still withheld", () => {
    const { outcomes, withheld } = mergeOutcomes([
      { label: "Puka Nacua", probability: 0.09, source: "kalshi" },
      { label: "Puka Nacua", probability: 0.91, source: "polymarket" },
    ]);
    expect(withheld).toBe(1);
    expect(outcomes).toHaveLength(0);
  });
});

describe("SHIP: an unpriced row has no place in a price order", () => {
  /* Mutant: drop the `quotedOrder` clause and let `b.prob - a.prob` coerce the
     absence to 0. A withheld row would then sort exactly where a worthless one
     does — last, which is the one position that reads as a price — and against
     a genuinely zero-priced sibling the comparison ties and the order falls
     through to the alphabet. The labels below are chosen so alphabetical order
     ("A quoted zero" first) and the wire order both disagree with the answer
     this asserts only if the clause is live... so the assertion is the PAIR:
     the priced row precedes the unpriced one however they arrive. */
  const order = (rows: { label: string; probability: number | null }[]) =>
    buildMarketSection(
      rows.map((r) => ({
        market_name: BOARD,
        outcome_name: r.label,
        probability: r.probability,
        source: "kalshi",
      })) as WireRow[],
    ).categories[0].cards[0].outcomes.map((o) => o.label);

  test("a priced zero outranks a withheld price, whichever way they arrive", () => {
    expect(
      order([
        { label: "Zeta unpriced", probability: null },
        { label: "Alpha priced zero", probability: 0 },
        { label: "Mid priced", probability: 0.4 },
      ]),
    ).toEqual(["Mid priced", "Alpha priced zero", "Zeta unpriced"]);
    expect(
      order([
        { label: "Alpha unpriced", probability: null },
        { label: "Zeta priced zero", probability: 0 },
      ]),
    ).toEqual(["Zeta priced zero", "Alpha unpriced"]);
  });

  /* CONTROL: two unpriced rows still fall through to the label tiebreak, which
     is what keeps the board's order independent of a payload that reorders
     itself between loads (#3861's finding). */
  test("two unpriced rows are ordered by label, not by the wire", () => {
    expect(
      order([
        { label: "Zeta unpriced", probability: null },
        { label: "Alpha unpriced", probability: null },
      ]),
    ).toEqual(["Alpha unpriced", "Zeta unpriced"]);
  });
});

describe("SHIP: the section counts quotes it can actually show", () => {
  /* Mutant: leave `quotedOutcomes` as `!o.result`. The counter's own note says
     it exists because the settled note promises the reader a last quote and the
     promise has to be COUNTED rather than assumed — and a row printing no
     number is exactly a row that promise may not include. On this board four of
     the five rows show no percentage and the unmutated counter says so. */
  test("only the one row with a price is counted as a quote", () => {
    const section = buildMarketSection(WIRE);
    expect(section.renderedOutcomes).toBe(5);
    expect(section.quotedOutcomes).toBe(1);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// GUARD — the age mark's denominator (#4970 card half).
// ─────────────────────────────────────────────────────────────────────────────

describe("SHIP: a row with no price cannot vouch for the card's prices", () => {
  /* `isLivePriced` is the denominator for "may the card state its age once?".
     Mutant: drop the `outcome.prob === null` early return. A withheld row
     carries an `observed_at` — that is when WE looked, not when anyone priced
     it — so a fresh one would make a card of uniformly stale prices read as
     MIXED, and the card's stamp would silently move onto the rows. Both
     directions are asserted, per gotcha #43. */
  const NOW = Date.parse("2026-09-22T03:30:00.000Z");
  const ago = (ms: number) => new Date(NOW - ms).toISOString();
  const STALE = ago(SOURCE_STALE_AFTER_MS + 60_000);
  const FRESH = ago(60_000);

  let clock: jest.SpyInstance;
  beforeEach(() => {
    clock = jest.spyOn(Date, "now").mockReturnValue(NOW);
  });
  afterEach(() => clock.mockRestore());

  const liveBoard = (withheldStamp: string): WireRow[] =>
    [
      { market_name: BOARD, outcome_name: "Davante Adams", probability: 0.4, source: "kalshi", observed_at: STALE },
      { market_name: BOARD, outcome_name: "Kyren Williams", probability: 0.3, source: "kalshi", observed_at: STALE },
      { market_name: BOARD, outcome_name: "CJ Daniels", probability: null, source: "kalshi", observed_at: withheldStamp },
    ] as WireRow[];

  const cardMarks = (html: string) => html.match(/data-scope="card"/g)?.length ?? 0;
  const rowMarks = (html: string) => html.match(/data-scope="row"/g)?.length ?? 0;

  test("the card still speaks once for two uniformly stale prices", () => {
    const html = render(payload(liveBoard(FRESH), { status: "live" }), "live");
    expect(cardMarks(html)).toBe(1);
    expect(rowMarks(html)).toBe(0);
  });

  /* The other direction: two prices that genuinely DISAGREE about their age
     still refuse the card mark and mark themselves. Green against the parent —
     this is the behaviour the guard above must not have traded away. */
  test("a genuinely mixed card still refuses to speak for its rows", () => {
    const mixed = [
      { market_name: BOARD, outcome_name: "Davante Adams", probability: 0.4, source: "kalshi", observed_at: STALE },
      { market_name: BOARD, outcome_name: "Kyren Williams", probability: 0.3, source: "kalshi", observed_at: FRESH },
      { market_name: BOARD, outcome_name: "CJ Daniels", probability: null, source: "kalshi", observed_at: FRESH },
    ] as WireRow[];
    const html = render(payload(mixed, { status: "live" }), "live");
    expect(cardMarks(html)).toBe(0);
    expect(rowMarks(html)).toBe(1);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// SHIP — a live board, where the same row must also show nothing, and where the
// parent drew the invented zero as a BAR as well as printing it.
// ─────────────────────────────────────────────────────────────────────────────

describe("SHIP: the rule is the same before the game ends", () => {
  /* `last quote` would be a second lie on top of the first — there was no quote
     to be last — so the withheld row shows its name in both states, and the
     priced rows around it keep their live bars. */
  test("a live board shows the withheld leg's name and no number", () => {
    const live = [
      { market_name: BOARD, outcome_name: "Davante Adams", probability: 0.4, source: "kalshi" },
      { market_name: BOARD, outcome_name: "Kyren Williams", probability: 0.3, source: "kalshi" },
      { market_name: BOARD, outcome_name: "CJ Daniels", probability: null, source: "kalshi" },
    ] as WireRow[];
    const html = render(payload(live, { status: "live" }), "live");
    expect(noPriceRows(html)).toEqual(["CJ Daniels"]);
    expect(visible(html)).toContain("40%");
    // A standalone zero, not the `0%` inside `30%` — which is how the first
    // draft of this line failed against a correct render.
    expect(visible(html)).not.toMatch(/(^|[^0-9])0%/);
    expect(visible(html)).not.toContain(SETTLED_QUOTE_PREFIX);
  });

  /* The bar is the half a reader takes in first (#5984), so the invented zero
     was drawn as well as written: on a live board the parent gives the withheld
     row a track and a zero-width fill. Two priced rows draw two bars here, and
     the third row draws none. */
  test("the withheld row draws no bar, and the priced rows still draw theirs", () => {
    const live = [
      { market_name: BOARD, outcome_name: "Davante Adams", probability: 0.4, source: "kalshi" },
      { market_name: BOARD, outcome_name: "Kyren Williams", probability: 0.3, source: "kalshi" },
      { market_name: BOARD, outcome_name: "CJ Daniels", probability: null, source: "kalshi" },
    ] as WireRow[];
    const html = render(payload(live, { status: "live" }), "live");
    expect(html.match(/max-w-\[140px\]/g)).toHaveLength(2);
    expect(html).not.toMatch(/style="width:0%"/);
  });
});

/* ── THE RUNS THIS FILE'S LABELS ARE MEASURED FROM ───────────────────────────
   PARENT (`e856ccb32` + this file, both source files reverted): 11 failed /
   7 passed of 18. Every assertion labelled SHIP above is in that 11 — four of
   them were labelled GUARD until this run graded them and said otherwise, and
   one labelled SHIP (a settled board's bars) turned out to be green against
   the parent and is now a CONTROL. A label nobody measured is a wish.

   MUTANTS (`artifacts/ux-1442/mutants.py`, re-runnable): 7 named, 7 KILLED,
   0 survived, 0 anchor misses — the branch order, the agreement test's
   coercion, the price's provenance, the source count, the sort clause, the
   quote counter and the age-mark denominator. */
