/**
 * UX-P115 (#2086) — SETTLED MEANS SETTLED on the event page's Additional Markets.
 *
 * Standing ruling 2: a settled surface shows the result, never a live-looking
 * price. `SpecialEventMarkets` printed one anyway on every finished game, and
 * the reason is the thing this suite is shaped around:
 *
 *   `eventStatus` was DECLARED on the component's props (`:14`) and PASSED by
 *   the event page (`page.tsx:1170`) and DESTRUCTURED BY NOBODY.
 *
 * That defect is invisible to three of the four things that would normally
 * catch it. tsc is happy — an omitted destructure of an optional prop is legal.
 * A grep for `eventStatus` finds the declaration and the call site and reads as
 * handled. A test that renders only the settled case and asserts "it says
 * settled" would pass the moment someone re-adds the word to the subtitle while
 * the rows keep their bars.
 *
 * ── SO THE LOAD-BEARING TEST IS DIFFERENTIAL ─────────────────────────────────
 *
 * Render the SAME payload twice, once settled and once scheduled, and require
 * the two markups to DIFFER. If the prop is ever dropped on the floor again —
 * by deleting the destructure, by shadowing it, by an early return above the
 * branch — the two renders collapse to one string and this reds, without the
 * test having to predict which visual detail was lost. It is the same shape as
 * `settledVocabulary.test.tsx`'s differential census, aimed at a prop instead
 * of a verdict word.
 *
 * ── AND THE OTHER DIRECTION IS ASSERTED TOO ──────────────────────────────────
 *
 * Gotcha #43: a cap's guard must assert BOTH directions. Over-suppression here
 * would mean a LIVE game losing its bars — the exact failure the native side
 * shipped (a price-band filter that deleted rows on finished games). So the
 * scheduled render is pinned byte-for-byte against the pre-change markup.
 *
 * The fixture is the issue's own production payload (event 15177664, captured
 * 2026-08-21 into `artifacts-ux-p115/`), not a hand-written one. UX-P098's
 * lesson: a hand-rolled census can reproduce the bug it is meant to catch.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import SpecialEventMarkets from "../../components/SpecialEventMarkets";
import { SETTLED_QUOTE_PREFIX, SETTLED_QUOTE_SECTION_NOTE } from "@/lib/settledQuote";
import { SETTLED_VOCABULARY } from "@/lib/propGrade";
import type { GameMarketsResponse } from "@/lib/api";

/**
 * Event 15177664, `Roman Andres Burruchaga @ Stan Wawrinka`, verbatim from
 * production. The match finished 2026-07-23; these prices were still being
 * served on 2026-08-21.
 */
const OTHER_ROWS = [
  { market_name: "Wawrinka vs Burruchaga: Set 1 Winner", outcome_name: "Roman Andres Burruchaga", probability: 0.99, source: "kalshi" },
  { market_name: "Wawrinka vs Burruchaga: Set 1 Winner", outcome_name: "Stan Wawrinka", probability: 0.01, source: "kalshi" },
  { market_name: "Wawrinka vs Burruchaga: Set 2 Winner", outcome_name: "Stan Wawrinka", probability: 0.99, source: "kalshi" },
  { market_name: "Wawrinka vs Burruchaga: Set 2 Winner", outcome_name: "Roman Andres Burruchaga", probability: 0.01, source: "kalshi" },
  { market_name: "Wawrinka vs Burruchaga: Exact Match Score", outcome_name: "Roman Andres Burruchaga wins 2-1", probability: 0.99, source: "kalshi" },
  { market_name: "Wawrinka vs Burruchaga: Exact Match Score", outcome_name: "Stan Wawrinka wins 2-0", probability: 0.01, source: "kalshi" },
  { market_name: "Wawrinka vs Burruchaga: Exact Match Score", outcome_name: "Stan Wawrinka wins 2-1", probability: 0.01, source: "kalshi" },
  { market_name: "Wawrinka vs Burruchaga: Exact Match Score", outcome_name: "Roman Andres Burruchaga wins 2-0", probability: 0.01, source: "kalshi" },
];

/**
 * The MODAL settled row, and the reason the fix is not "hide the 99%".
 *
 * Measured over 40 settled events on 2026-08-21: of 158 priced rows, 58 sit in
 * 0.40–0.60 and only 6 sit at 0.90 or above. A 99% on a finished match looks
 * odd; a 47% reads as an ordinary live probability, so it is the case a human
 * will never report and always believe. Native's old filter kept exactly these.
 *
 * Three outcomes, and not a spread/total/moneyline name, ON PURPOSE. The first
 * draft of this fixture used "Total Aces · Over/Under" and a two-way "Tiebreak
 * Played · Yes/No", and `buildMarketSection` dropped BOTH before render —
 * `isRedundantWithMarketMaps` strips total+over/under, and `findWinProbMarkets`
 * strips any two-outcome market summing to ~1. The suite then asserted against
 * an empty string and would have passed had it only checked for absences.
 */
const COIN_FLIP_ROWS = [
  { market_name: "Wawrinka vs Burruchaga: Number of Sets", outcome_name: "2 sets", probability: 0.47, source: "kalshi" },
  { market_name: "Wawrinka vs Burruchaga: Number of Sets", outcome_name: "3 sets", probability: 0.53, source: "kalshi" },
  { market_name: "Wawrinka vs Burruchaga: Number of Sets", outcome_name: "4 sets", probability: 0.05, source: "kalshi" },
];

function payload(rows = OTHER_ROWS): GameMarketsResponse {
  return {
    event_id: 15177664,
    home_team: "Stan Wawrinka",
    away_team: "Roman Andres Burruchaga",
    home_score: null,
    away_score: null,
    status: "closed",
    totals: [],
    player_props: [],
    team_totals: [],
    spreads: [],
    period_markets: [],
    matchups: [],
    other: rows,
    pace: null,
  } as unknown as GameMarketsResponse;
}

const render = (status: string | undefined, rows = OTHER_ROWS) =>
  renderToStaticMarkup(<SpecialEventMarkets data={payload(rows)} eventStatus={status} />);

/** The bar is a `<div>` whose inline width encodes the probability. */
const BAR = /style="width:\s*\d/;

/**
 * What a reader actually sees: tags stripped, entities decoded.
 *
 * Needed because `SETTLED_QUOTE_SECTION_NOTE` contains an apostrophe and React
 * emits it as `&#x27;`, so a raw `toContain` on the phrase silently finds
 * nothing — an assertion that is not merely wrong but wrong in the passing
 * direction for every "must NOT contain" check in this file.
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
    .replace(/\s+/g, " ");

describe("Additional Markets: a settled game states quotes, not chances", () => {
  test("THE REGRESSION GUARD: settled and scheduled must not render identically", () => {
    // If `eventStatus` is ever ignored again — the original defect — these two
    // become the same string and this fails without naming a single pixel.
    expect(render("closed")).not.toEqual(render("scheduled"));
  });

  test.each(["closed", "completed", "settled", "final", "resolved", "CLOSED"])(
    "%s drops every probability bar",
    (status) => {
      expect(render(status)).not.toMatch(BAR);
    },
  );

  test("a settled row says what its number IS", () => {
    const text = visible(render("closed"));
    expect(text).toContain(`${SETTLED_QUOTE_PREFIX} 99%`);
    expect(text).toContain(`${SETTLED_QUOTE_PREFIX} 1%`);
  });

  test("the settled note is said ONCE, not once per row", () => {
    const text = visible(render("closed"));
    const occurrences = text.split(SETTLED_QUOTE_SECTION_NOTE).length - 1;
    expect(occurrences).toBe(1);
    // Eight outcomes are on screen, so a per-row label would have said it 8x.
    expect(text.split(`${SETTLED_QUOTE_PREFIX} `).length - 1).toBeGreaterThan(1);
  });

  test("the coin-flip band is suppressed too, not just the conspicuous 99%", () => {
    // The band native's old `p > 0.01 && p < 0.99` filter kept in full.
    const html = render("closed", COIN_FLIP_ROWS);
    // The fixture must actually reach the screen — see its comment; an earlier
    // draft was filtered out upstream and this suite asserted against "".
    expect(visible(html)).toContain("2 sets");
    expect(html).not.toMatch(BAR);
    expect(visible(html)).toContain(`${SETTLED_QUOTE_PREFIX} 47%`);
  });

  test("NOTHING IS DELETED — every settled outcome keeps its place", () => {
    // #2019: a row nobody can read honestly is a refusal, not a blank. Native
    // used to drop these rows entirely; the count must survive the treatment.
    const text = visible(render("closed"));
    for (const row of OTHER_ROWS) {
      expect(text).toContain(row.outcome_name);
    }
  });

  test("NO VERDICT IS STATED — the grade is not on this payload to state", () => {
    // The grade for these rows EXISTS and is authoritative (`api_settlement`),
    // but the game-markets endpoint does not serialize it, so this surface may
    // not claim a winner AND may not claim grading is unavailable. It says
    // neither. See `lib/settledQuote.ts` for the measurement behind that call.
    //
    // Word-boundary matched against VISIBLE text, not raw markup: the registry
    // holds sentence forms like `hit`, and `hit` is a substring of the class
    // name `bg-white`. A raw substring check here would be a false red waiting
    // for an unrelated restyle.
    const text = visible(render("closed"));
    for (const word of SETTLED_VOCABULARY) {
      const pattern = new RegExp(`(^|[^A-Za-z])${word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}([^A-Za-z]|$)`);
      expect(text).not.toMatch(pattern);
    }
  });
});

describe("the other direction: a game in play is untouched", () => {
  test.each([undefined, "scheduled", "live", "in_progress", "halftime", ""])(
    "%s keeps its bars and says nothing about settlement",
    (status) => {
      const html = render(status);
      expect(html).toMatch(BAR);
      expect(visible(html)).not.toContain(SETTLED_QUOTE_SECTION_NOTE);
      expect(visible(html)).not.toContain(SETTLED_QUOTE_PREFIX);
    },
  );

  test("a live render is byte-identical to the pre-change markup", () => {
    // Over-suppression must be UNREPRESENTABLE, not merely unintended. This
    // pins the untouched path: the settled branch may only ADD a state.
    const before = render("scheduled");
    const after = render(undefined);
    expect(after).toEqual(before);
    expect(before).toContain("99%");
    expect(before).toMatch(BAR);
  });
});
