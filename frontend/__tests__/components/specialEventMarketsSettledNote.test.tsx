/**
 * #3752 — the settled section note stops promising a quote the grid refuses to
 * print.
 *
 * ── THE PAGE THIS WAS FILED ON ───────────────────────────────────────────────
 *
 * `/events/15305016` (Ben Shelton d. Stefanos Tsitsipas 6-2 6-3 6-4,
 * `status: completed`), production, 390px, 2026-09-07. The header read:
 *
 *     6 markets grouped by category · settled — showing each market's last quote
 *
 * and the six rows under it were:
 *
 *     Shelton won Set 1                              ← result, no number
 *     Shelton won Set 2                              ← result, no number
 *     Shelton won Set 3                              ← result, no number
 *     Stefanos Tsitsipas 3-2 — no longer possible    ← struck, no number
 *     Stefanos Tsitsipas 3-1 — no longer possible    ← struck, no number
 *     Stefanos Tsitsipas 3-0 — no longer possible    ← struck, no number
 *
 * Zero quotes for a sentence that promised six. Both row treatments are ruled
 * and correct (UX-P115, and the struck-row work on `15304939`); the SENTENCE is
 * the defect, and it became false as those treatments were added around it.
 *
 * ── WHY THE FIXTURE IS THE WIRE ──────────────────────────────────────────────
 *
 * `fixtures/gameMarkets15305016.json` is that event's `/game-markets` payload
 * verbatim, all 27 `other` rows, captured 2026-09-07. Hand-rolling it would
 * have hidden the interesting part: 27 wire rows become 6 rendered ones, and
 * WHICH 6 is decided by `buildMarketSection`'s own filters. UX-P098's lesson,
 * and this suite's older sibling makes the same call.
 *
 * ── THE LOAD-BEARING ASSERTION IS ABOUT THE DOM, NOT THE COUNTER ─────────────
 *
 * The invariant is a biconditional between two things a reader can see:
 *
 *     the note promises a percentage  ⟺  a percentage is on screen
 *
 * so it is asserted against rendered markup in both directions, not against
 * `quotedOutcomes`. A test that checked the counter would go on passing the day
 * a new row shape learns to suppress its number without telling the counter —
 * which is precisely how the original sentence became false.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import SpecialEventMarkets from "../../components/SpecialEventMarkets";
import {
  buildMarketSection,
  completedSetsForTennis,
  decidedSetsWinnerFor,
  tennisSetsWonFor,
} from "@/lib/otherMarketGroups";
import {
  settledSectionNote,
  SETTLED_QUOTE_PREFIX,
  SETTLED_QUOTE_SECTION_NOTE,
  SETTLED_SECTION_NOTE_NO_QUOTES,
} from "@/lib/settledQuote";
import type { GameMarketsResponse } from "@/lib/api";

import WIRE from "../fixtures/gameMarkets15305016.json";

const SPORT = "tennis_atp_us_open";

const payload = (over: Partial<GameMarketsResponse> = {}): GameMarketsResponse =>
  ({
    ...WIRE,
    totals: [],
    player_props: [],
    team_totals: [],
    spreads: [],
    period_markets: [],
    matchups: [],
    pace: null,
    ...over,
  }) as unknown as GameMarketsResponse;

/** Exactly what `app/events/[id]/page.tsx:1586` passes, so the test renders the page's render. */
const render = (data: GameMarketsResponse, status: string | undefined) =>
  renderToStaticMarkup(
    <SpecialEventMarkets
      data={data}
      eventStatus={status}
      completedSets={completedSetsForTennis(SPORT, data)}
      decidedSetsWinner={decidedSetsWinnerFor(SPORT, data)}
      setsWon={tennisSetsWonFor(SPORT, data)}
    />,
  );

/**
 * What a reader sees. React emits the apostrophe in the old note as `&#x27;`,
 * so a raw `toContain` finds nothing — and finds nothing in the PASSING
 * direction for every "must not contain" check below.
 */
const visible = (html: string) =>
  html
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&#x2F;/g, "/")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .replace(/&mdash;/g, "—")
    .replace(/\s+/g, " ");

/** Any percentage in the body of the grid — the thing the note promises. */
const PERCENT_ON_A_ROW = /\d+%/;

describe("the production specimen: six settled rows, no quote among them", () => {
  const finished = payload();

  test("the fixture really is the 0-quote shape (not vacuous)", () => {
    const section = buildMarketSection(finished.other, {
      completedSets: completedSetsForTennis(SPORT, finished),
      decidedSetsWinner: decidedSetsWinnerFor(SPORT, finished),
      setsWon: tennisSetsWonFor(SPORT, finished),
    });
    // 27 wire rows in, 6 rendered out — the page's own numbers.
    expect(section.renderedOutcomes).toBe(6);
    expect(section.quotedOutcomes).toBe(0);
  });

  test("THE FIX: the header does not promise a quote", () => {
    const text = visible(render(finished, "completed"));
    expect(text).toContain(SETTLED_SECTION_NOTE_NO_QUOTES);
    expect(text).not.toContain(SETTLED_QUOTE_SECTION_NOTE);
    expect(text).not.toContain(SETTLED_QUOTE_PREFIX);
  });

  test("THE BICONDITIONAL: no percentage promised, no percentage on screen", () => {
    // Strip the header line itself and check the GRID. `6 markets grouped by
    // category` is a count, not a price, and matching it here would make the
    // assertion trivially about the wrong text.
    const html = render(finished, "completed");
    const grid = html.slice(html.indexOf("grid grid-cols-1"));
    expect(visible(grid)).not.toMatch(PERCENT_ON_A_ROW);
    // ...and the rows are still all there. #2019: a row nobody can price is a
    // refusal, never a blank.
    const text = visible(html);
    for (const row of ["Shelton won Set 1", "Shelton won Set 2", "Shelton won Set 3"]) {
      expect(text).toContain(row);
    }
    expect(text).toContain("no longer possible");
  });
});

describe("the other direction: a quote on screen keeps the promise", () => {
  /**
   * The same match with the score withheld, which is what the page has before
   * the scoreboard lands. No completed sets means no row is decided, so every
   * row prices — the shape the original sentence was written for.
   */
  const scoreless = payload({ home_score: null, away_score: null });

  test("the fixture really is the all-quoted shape (not vacuous)", () => {
    const section = buildMarketSection(scoreless.other, {
      completedSets: completedSetsForTennis(SPORT, scoreless),
      decidedSetsWinner: decidedSetsWinnerFor(SPORT, scoreless),
      setsWon: tennisSetsWonFor(SPORT, scoreless),
    });
    expect(section.quotedOutcomes).toBe(section.renderedOutcomes);
    expect(section.quotedOutcomes).toBeGreaterThan(0);
  });

  test("the header promises a quote, and a quote is on screen", () => {
    const text = visible(render(scoreless, "completed"));
    expect(text).toContain(SETTLED_QUOTE_SECTION_NOTE);
    expect(text).toContain(SETTLED_QUOTE_PREFIX);
    expect(text).toMatch(PERCENT_ON_A_ROW);
  });

  test("the promise never says 'each' again", () => {
    // The specific wording that was false. Pinned so a later edit that restores
    // a universal claim has to argue with this line.
    expect(SETTLED_QUOTE_SECTION_NOTE).not.toMatch(/\beach\b/);
    expect(SETTLED_QUOTE_SECTION_NOTE).not.toMatch(/\bevery\b/);
  });
});

describe("the MIXED section — #3645's acceptance criterion, and the hard case", () => {
  /**
   * The same match stopped at two sets to love. Sets 1 and 2 are decided AND
   * the score can name who took them, so those rows state results; set 3 is
   * still open, so its row quotes. On the exact-score ladder `Tsitsipas 3-2` is
   * still reachable from 0-2 and prices, while `3-1` and `3-0` are struck.
   *
   * One section, both row shapes at once. This is the state a match spends real
   * time in, and it is why the replacement sentence is quantified as "any"
   * rather than "each": neither a universal claim nor silence is true here.
   */
  const twoSetsToLove = payload({ home_score: 2, away_score: 0 });

  test("the fixture really is mixed (not vacuous)", () => {
    const section = buildMarketSection(twoSetsToLove.other, {
      completedSets: completedSetsForTennis(SPORT, twoSetsToLove),
      decidedSetsWinner: decidedSetsWinnerFor(SPORT, twoSetsToLove),
      setsWon: tennisSetsWonFor(SPORT, twoSetsToLove),
    });
    expect(section.quotedOutcomes).toBeGreaterThan(0);
    expect(section.quotedOutcomes).toBeLessThan(section.renderedOutcomes);
  });

  test("both shapes are on screen, and the sentence is true of both", () => {
    const text = visible(render(twoSetsToLove, "completed"));
    // a stated result...
    expect(text).toMatch(/won Set [12]/);
    // ...and a quote, under one header.
    expect(text).toContain(SETTLED_QUOTE_PREFIX);
    expect(text).toContain(SETTLED_QUOTE_SECTION_NOTE);
    // The old sentence would have been false here too: it promised a quote for
    // EVERY market, and the result rows are markets with none.
    expect(text).not.toContain("showing each market's last quote");
  });
});

describe("the chooser is total, and settlement still gates the whole clause", () => {
  test.each([0, 1, 6, 99])("%i quoted outcomes maps to a sentence", (n) => {
    const note = settledSectionNote(n);
    expect(typeof note).toBe("string");
    expect(note.length).toBeGreaterThan(0);
    expect(note).toBe(n > 0 ? SETTLED_QUOTE_SECTION_NOTE : SETTLED_SECTION_NOTE_NO_QUOTES);
  });

  test.each([undefined, "scheduled", "live", "in_progress"])(
    "%s says nothing about settlement at all",
    (status) => {
      // Gotcha #43, both directions: the note must not leak onto a live match
      // merely because its rows happen to have results (tennis decides sets
      // mid-match). `SETTLED_SECTION_NOTE_NO_QUOTES` is the bare word "settled",
      // so it is checked with a word boundary rather than `toContain` — the
      // markup is full of class names, and a substring check would be a false
      // red waiting for a restyle.
      const text = visible(render(payload(), status));
      expect(text).not.toMatch(/(^|[^A-Za-z])settled([^A-Za-z]|$)/);
      expect(text).not.toContain(SETTLED_QUOTE_SECTION_NOTE);
    },
  );
});
