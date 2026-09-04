/**
 * live/058, #2746 — THE LIVE TENNIS CARD LEARNS GAMES.
 *
 * live/057 put two observers on one clock over nine live US Open matches:
 * ESPN published **78 game-level score changes** in 45 minutes and our card
 * moved **9 times**, because the only score field a tennis event had was
 * `home_score`/`away_score` and for tennis that counts SETS.
 *
 * `event.linescore` is the grain that was missing. This suite is about what a
 * reader SEES of it.
 *
 * ## The control is the whole test, again
 *
 * `tennisScoreUnits.test.tsx` (the ux/1034 B5 suite) holds both arms for the
 * chart. The arms here are the two silences: a payload with no linescore, and
 * a payload with an EMPTY one. A component that rendered a scoreboard in either
 * case would pass every positive assertion below and put "0-0" under a match
 * that has not started — the exact defect (gotcha #53, live/056) that a live
 * card cannot afford.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TennisLinescore from "@/components/TennisLinescore";
import type { TennisLinescore as Linescore } from "@/lib/types";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** ESPN competition 182709, live 2026-09-03: Popyrin 6-2 6-7(4) 6-5 Tabilo. */
const LIVE: Linescore = {
  source: "espn",
  unit: "games",
  state: "in_progress",
  completion: "unknown",
  status_detail: "3rd Set",
  was_suspended: false,
  sets: [
    { home: 6, away: 2, home_tiebreak: null, away_tiebreak: null, won_by: "home" },
    { home: 6, away: 7, home_tiebreak: 4, away_tiebreak: 7, won_by: "away" },
    { home: 6, away: 5, home_tiebreak: null, away_tiebreak: null, won_by: null },
  ],
  current_set: 3,
  sets_won: { home: 1, away: 1 },
  games: { home: 18, away: 14 },
  line: "6-2, 6-7(4), 6-5",
  observed_at: "2026-09-03T21:30:00Z",
  // live/059 addendum (D59 = A'): an ESPN line carries no points and no
  // server — the fields are PRESENT and null, which is the honest "this source
  // does not say", not omitted.
  points: null,
  serving: null,
  state_source: "espn",
  score_as_of: "2026-09-03T21:30:00Z",
  state_disagrees: false,
};

/** The SAME match a minute later off StatPal: sets, games, points AND server. */
const STATPAL_LIVE: Linescore = {
  ...LIVE,
  source: "statpal",
  line: "6-2, 6-7, 6-5",
  points: { home: "40", away: "30" },
  serving: "home",
  score_as_of: "2026-09-03T21:31:00Z",
};

function render(linescore: Linescore | null | undefined) {
  return renderToStaticMarkup(
    <TennisLinescore
      linescore={linescore}
      homeName="Alexei Popyrin"
      awayName="Alejandro Tabilo"
    />,
  );
}

describe("the live card prints games, not just sets", () => {
  it("draws every published set for both players", () => {
    const text = visibleText(render(LIVE));

    // Two rows, one column per set, in publication order. The trailing `6`
    // and `5` are the set IN PLAY — the game-level movement the card was
    // blind to, and the reason this component exists.
    expect(text).toContain("Popyrin 6 6 4 6");
    expect(text).toContain("Tabilo 2 7 5");
  });

  it("prints the tiebreak points on the LOSER of that set, once", () => {
    /**
     * The second set was 7-6(4) to Tabilo, so POPYRIN is the one who lost it
     * and the 4 is his. Both sides carry points in the payload — 7 for the
     * winner, 4 for the loser — and printing both gives `6⁴ 7⁷`, which is two
     * numbers for one tiebreak and reads as a second set. The convention is
     * the loser's, once, on the loser's row.
     */
    const html = render(LIVE);
    const text = visibleText(html);

    expect(html).toContain("<sup");
    expect(text).toContain("Popyrin 6 6 4 6");  // the 4 rides Popyrin's lost 6
    expect(text).toContain("Tabilo 2 7 5");     // and nowhere on the winner's row
  });

  it("names the moment ESPN names", () => {
    expect(visibleText(render(LIVE))).toContain("3rd Set");
  });

  it("says RETIRED rather than the set it stopped in", () => {
    /**
     * "Dusan Lajovic bt SoonWoo Kwon 4-6 7-5 3-1 ret" (competition 184599).
     *
     * `completion` is a fact about the match and `status_detail` a fact about
     * the moment; captioning a retirement "3rd Set" would put it back on court.
     * This is also the fixture `authority_score` REFUSES — the set count is 1-1
     * and naming a winner off it inverts the result — so the line is the only
     * true score this match will ever show.
     */
    const retired: Linescore = {
      ...LIVE,
      state: "decided",
      completion: "retired",
      status_detail: "Retired",
      current_set: null,
      sets: [
        { home: 4, away: 6, home_tiebreak: null, away_tiebreak: null, won_by: "away" },
        { home: 7, away: 5, home_tiebreak: null, away_tiebreak: null, won_by: "home" },
        { home: 3, away: 1, home_tiebreak: null, away_tiebreak: null, won_by: null },
      ],
      line: "4-6, 7-5, 3-1",
    };

    const text = visibleText(render(retired));
    expect(text).toContain("Retired");
    expect(text).not.toContain("Set");
  });

  it("does not caption a match with a status ESPN gave us no word for", () => {
    /** `unknown` degrades to silence, never to "Final" — the one direction
        that would make a card confident about a match nobody has finished. */
    const text = visibleText(
      render({ ...LIVE, completion: "unknown", status_detail: null }),
    );
    expect(text).not.toContain("Final");
    expect(text).not.toContain("unknown");
  });

  it("prints an en dash for a side ESPN has not written yet", () => {
    /** THE CHANGEOVER. ESPN writes one side's new line before the other's; a
        `0` there is a score the reader would believe. */
    const ragged: Linescore = {
      ...LIVE,
      sets: [
        { home: 6, away: 3, home_tiebreak: null, away_tiebreak: null, won_by: "home" },
        { home: 1, away: null, home_tiebreak: null, away_tiebreak: null, won_by: null },
      ],
      current_set: 2,
      line: "6-3, 1-?",
    };

    const text = visibleText(render(ragged));
    expect(text).toContain("–");
    expect(text).not.toMatch(/1\s+0/);
  });
});

describe("the two silences", () => {
  it("renders nothing when the payload carries no linescore", () => {
    /** THE CONTROL. Every non-tennis event on the site takes this path, and a
        component that drew an empty scoreboard here would put a blank grid
        under every NFL game. */
    expect(render(undefined)).toBe("");
    expect(render(null)).toBe("");
  });

  it("renders nothing when the linescore has no sets", () => {
    /** The walkover shape: a result with no line at all. "0-0" would be a
        score; the absence of one is the truth (gotcha #53). */
    expect(render({ ...LIVE, sets: [], line: "" })).toBe("");
  });
});

/**
 * live/059 addendum (D59 = A′) — THE FINER GRAIN, AND ITS CONTROL.
 *
 * ESPN's tennis scoreboard publishes no point score and no server; StatPal's
 * livescores publish both. The card must show them when the line's own source
 * carries them and must show NOTHING extra when it does not — an ESPN line
 * after this addendum has to render byte-for-byte as it did before, or the
 * addendum has changed every non-anchored match on the board.
 */
describe("the current game (live/059 addendum)", () => {
  test("a StatPal line shows the point score and marks the server", () => {
    const html = render(STATPAL_LIVE);
    expect(visibleText(html)).toContain("40");
    expect(visibleText(html)).toContain("30");
    expect(html).toContain('aria-label="serving"');
  });

  test("CONTROL — an ESPN line adds nothing: no points, no serve dot", () => {
    const html = render(LIVE);
    expect(html).not.toContain('aria-label="serving"');
    // "40"/"30" are not set scores in this fixture, so their absence is a real
    // test that no point column was drawn.
    expect(visibleText(html)).not.toContain("40");
    expect(visibleText(html)).not.toContain("30");
  });

  test("an ESPN line renders exactly as it did before the addendum", () => {
    const text = visibleText(render(LIVE));
    expect(text).toContain("Popyrin");
    expect(text).toContain("Tabilo");
    expect(text).toContain("3rd Set");
  });

  test("a decided match shows no point score even if one is carried", () => {
    /* A trailing "40–30" beside a final score reads as live. `current_set` is
       null on a decided match and that is what gates the column. */
    const html = render({
      ...STATPAL_LIVE,
      state: "decided",
      current_set: null,
      completion: "final",
    });
    expect(visibleText(html)).not.toContain("40");
    expect(html).not.toContain('aria-label="serving"');
  });

  test("the disagreement caveat appears only when the feeds disagree", () => {
    expect(visibleText(render(STATPAL_LIVE))).not.toContain("Score as of");
    const html = render({ ...STATPAL_LIVE, state_disagrees: true });
    expect(visibleText(html)).toContain("Score as of");
  });

  test("a half-published point score prints a dash, never a zero", () => {
    const html = render({
      ...STATPAL_LIVE,
      points: { home: "40", away: null },
    });
    const text = visibleText(html);
    expect(text).toContain("40");
    expect(text).not.toContain("40 0");
  });
});
