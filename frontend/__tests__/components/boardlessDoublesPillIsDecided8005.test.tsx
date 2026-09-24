/**
 * #8005 — THE DOUBLES PILL APOLOGISED TEN DAYS AFTER ALL THREE FINALS.
 *
 * `bainluck.com/tournaments/us-open` → Doubles, production 2026-09-23 11:03Z at
 * 390px (lane1b/399):
 *
 *   We can't show today's schedule
 *   … so a match that is on right now would be missing. We're checking.
 *
 * above 147 finished doubles results including three graded finals, while
 * Men's on the same page said "This draw is done" (#5924).
 *
 * #5924 reads `board.decided`, and the doubles have NO board — boards are built
 * from championship futures and no venue lists a doubles title market — so the
 * pill could never be decided and fell to the tournament-wide
 * `order_of_play_listed` (625). The server now grades each draw's final from
 * the scoreboard and serves `slate.decided_draws`; the pill reads it. Still
 * NOT a client-side count of `results`.
 */

import React from "react";
import fs from "fs";
import path from "path";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentMatches from "@/components/tournament/TournamentMatches";
import { slateEmptyState } from "@/lib/slate";
import { shownBoardsAreDecided, type TournamentBoardData } from "@/lib/tournament";

const DOUBLES = ["mens-doubles", "womens-doubles", "mixed-doubles"];

/** Production 2026-09-23: two singles boards, both decided; no doubles board. */
function board(draw: string, decided: boolean): TournamentBoardData {
  return {
    draw,
    label: draw,
    rows: [],
    contenders: 0,
    unpriced: 0,
    rows_not_live: 0,
    mixed_freshness_rows: 0,
    price_state: "dark",
    newest_observed_at: null,
    age_hours: null,
    ...(decided ? { decided: { winner_entity_key: "x" } } : {}),
  };
}
const BOARDS = [board("mens-singles", true), board("womens-singles", true)];

describe("🔴 a boardless draw the server graded is decided", () => {
  it("production: three doubles finals listed, no doubles board", () => {
    // BEFORE: boards alone could never answer for the Doubles pill.
    expect(shownBoardsAreDecided(BOARDS, DOUBLES)).toBe(false);
    // AFTER: the server's per-draw list answers it.
    expect(shownBoardsAreDecided(BOARDS, DOUBLES, DOUBLES)).toBe(true);
  });

  it("the empty state stops apologising", () => {
    const state = slateEmptyState({
      drawReleased: true,
      orderOfPlayListed: 625,
      drawIsDecided: shownBoardsAreDecided(BOARDS, DOUBLES, DOUBLES),
    });
    expect(state.cause).toBe("decided");
    const html = renderToStaticMarkup(<TournamentMatches entries={[]} empty={state} />);
    expect(html).toContain('data-empty-cause="decided"');
    expect(html).toContain("This draw is done");
    expect(html).not.toContain("would be missing");
    expect(html).not.toContain("We're checking");
  });
});

describe("🟢 it still under-claims", () => {
  it("one ungraded doubles draw keeps the pill undecided", () => {
    // Mid-tournament: men's and women's doubles finals played, mixed still on.
    expect(
      shownBoardsAreDecided(BOARDS, DOUBLES, ["mens-doubles", "womens-doubles"]),
    ).toBe(false);
  });

  it("absent, null or empty list reads exactly as before", () => {
    for (const listed of [undefined, null, []]) {
      expect(shownBoardsAreDecided(BOARDS, DOUBLES, listed)).toBe(false);
      expect(shownBoardsAreDecided(BOARDS, ["mens-singles"], listed)).toBe(true);
    }
  });

  it("a pill showing no draws is never decided", () => {
    expect(shownBoardsAreDecided(BOARDS, [], DOUBLES)).toBe(false);
  });

  it("the list does not speak for a draw it does not name", () => {
    const undecidedSingles = [board("mens-singles", false)];
    expect(shownBoardsAreDecided(undecidedSingles, ["mens-singles"], DOUBLES)).toBe(false);
  });

  it("board and list combine per draw", () => {
    const boards = [board("mens-doubles", true)];
    expect(
      shownBoardsAreDecided(boards, DOUBLES, ["womens-doubles", "mixed-doubles"]),
    ).toBe(true);
    expect(shownBoardsAreDecided(boards, DOUBLES, ["womens-doubles"])).toBe(false);
  });
});

describe("the hub page passes the server's list", () => {
  const PAGE = path.resolve(__dirname, "../../app/tournaments/[slug]/page.tsx");
  it("feeds slate.decided_draws into the pill's decided check", () => {
    const code = fs
      .readFileSync(PAGE, "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, " ")
      .split("\n")
      .map((line) => line.replace(/(^|\s)\/\/.*$/, "$1"))
      .join("\n");
    expect(code).toMatch(
      /shownBoardsAreDecided\(data\?\.boards,\s*drawsShown,\s*data\?\.slate\?\.decided_draws\)/,
    );
  });
});
