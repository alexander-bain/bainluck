/**
 * The slate row draws the set line, and stays quiet without one (live/061, #2746).
 *
 * `tennisLinescore.test.tsx` guards the FULL variant, which the match page
 * draws. This guards the COMPACT one, which the tournament hub's slate row
 * draws — thirty of them under each other, where a two-row grid per fixture
 * would turn a scannable card into a wall of tables.
 *
 * ## Both directions, because only one of them fails loudly (gotcha #43)
 *
 *  - A live row must SHOW `6-2 6-7 6-5`. If it does not, the ship is missing
 *    and somebody notices on day one.
 *  - An upcoming row must show NOTHING. If it grows an empty strip or a row of
 *    dashes, every fixture on a card that has not started acquires a scoreboard
 *    reading `0-0` — and nobody notices, because it looks like a design choice.
 *
 * The absence arms therefore outnumber the presence arms, deliberately. Same
 * posture, and for the same stated reason, as the suite for the full variant.
 *
 * ## The cadence this row inherits, stated rather than claimed
 *
 * The slate refreshes on `sync-tournament-results`' **180-second** beat. This
 * suite does not assert a 30-second SLA and the ship does not claim one: the
 * two fields the compact variant REFUSES to draw — the point score and the
 * serving dot — are refused precisely because they are the two that a
 * three-minute-old read cannot keep true.
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
  points: null,
  serving: null,
  state_source: "espn",
  score_as_of: "2026-09-03T21:30:00Z",
  state_disagrees: false,
};

/**
 * The set pairs with the tiebreak superscripts and all layout whitespace
 * removed — `6-26-76-5`.
 *
 * Each `<span>` boundary becomes a space under `visibleText`, so `6-2` arrives
 * as `6 - 2` and a naive `toContain("6-2")` fails on markup rather than on
 * meaning. Dropping the superscripts first matters too: they sit BETWEEN the
 * two halves of a pair, so `6-7(4)` reads as `6 4 - 7` unstripped.
 */
function setPairs(html: string): string {
  return visibleText(html.replace(/<sup[^>]*>.*?<\/sup>/g, "")).replace(/\s+/g, "");
}

function compact(linescore: Linescore | null | undefined): string {
  return renderToStaticMarkup(
    <TennisLinescore
      variant="compact"
      linescore={linescore}
      homeName="Alexei Popyrin"
      awayName="Alejandro Tabilo"
    />,
  );
}

describe("the slate row shows the set line", () => {
  it("prints every published set as a pair, in play order", () => {
    // The whole ship in one assertion: a reader scanning the hub sees how the
    // match has gone, not just the words "3rd Set". Order matters as much as
    // presence — a set list out of play order is a different match.
    expect(setPairs(compact(LIVE))).toBe("6-26-76-5");
  });

  it("labels the line for a screen reader with the score itself", () => {
    expect(compact(LIVE)).toContain('aria-label="Set scores: 6-2, 6-7(4), 6-5"');
  });

  it("puts the tiebreak superscript on the LOSER of the set, and on nobody else", () => {
    const html = compact(LIVE);
    const sups = html.match(/<sup[^>]*>(\d+)<\/sup>/g) ?? [];

    // Set two went 6-7(4) — Popyrin lost it, so his 4 is the superscript.
    // Showing both would print `6⁴-7⁷`, two numbers for one tiebreak.
    expect(sups).toHaveLength(1);
    expect(sups[0]).toContain(">4<");
  });

  it("shows no superscript while the tiebreak is still being played", () => {
    const html = compact({
      ...LIVE,
      sets: [
        { home: 6, away: 6, home_tiebreak: 5, away_tiebreak: 4, won_by: null },
      ],
      current_set: 1,
    });
    // Either number could be the loser's, and guessing puts a 7-5 result on
    // the wrong side.
    expect(html).not.toContain("<sup");
  });

  it("marks a retirement, so a stopped match is not read as a final score", () => {
    const text = visibleText(
      compact({
        ...LIVE,
        state: "decided",
        completion: "retired",
        current_set: null,
      }),
    ).toLowerCase();

    expect(text).toContain("ret.");
  });
});

describe("the slate row stays quiet without a line", () => {
  it("renders nothing at all for a missing linescore", () => {
    expect(compact(null)).toBe("");
    expect(compact(undefined)).toBe("");
  });

  it("renders nothing for a linescore whose set list is empty", () => {
    // NOT an empty strip. A blank scoreboard beside a match reads as 0-0 —
    // gotcha #53, and live/056's rule that a quiet rail beats a lying one.
    expect(compact({ ...LIVE, sets: [], current_set: null })).toBe("");
  });

  it("never prints a zero for a set neither side has published", () => {
    const text = visibleText(
      compact({
        ...LIVE,
        sets: [
          {
            home: null,
            away: null,
            home_tiebreak: null,
            away_tiebreak: null,
            won_by: null,
          },
        ],
        current_set: 1,
      }),
    );
    // ESPN writes the two sides a fraction apart, so the side it has not
    // written yet is UNPUBLISHED — a `0` there is a score a reader believes.
    expect(text).not.toContain("0");
  });
});

describe("compact refuses what belongs to the match page", () => {
  const STATPAL_LIVE: Linescore = {
    ...LIVE,
    source: "statpal",
    points: { home: "40", away: "30" },
    serving: "home",
  };

  it("omits the point score, which a 180-second list cannot keep true", () => {
    expect(visibleText(compact(STATPAL_LIVE))).not.toContain("40");
  });

  it("omits the serving dot, for the same reason", () => {
    expect(compact(STATPAL_LIVE)).not.toContain('aria-label="serving"');
  });

  it("has not replaced the full variant, which still draws both", () => {
    // The match page is the surface that wants names, points and the server —
    // and it refreshes fast enough for them to be true.
    const full = renderToStaticMarkup(
      <TennisLinescore
        linescore={STATPAL_LIVE}
        homeName="Alexei Popyrin"
        awayName="Alejandro Tabilo"
      />,
    );

    expect(full).toContain("<table");
    expect(visibleText(full)).toContain("40");
    expect(full).toContain('aria-label="serving"');
    // ...and the compact one is not a table at all.
    expect(compact(LIVE)).not.toContain("<table");
  });
});
