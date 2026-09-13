/**
 * #5924 — A FINISHED DRAW APOLOGISED FOR AN EMPTY SCHEDULE.
 *
 * `bainluck.com/tournaments/us-open` → Women's, production 2026-09-13 14:40Z at
 * 390px, where the day's matches sit:
 *
 *   We can't show today's schedule
 *   The schedule feed has this tournament on today's board, but none of it
 *   reached this list — so a match that is on right now would be missing.
 *   We're checking.
 *
 * Every clause is false. The women's draw finished at 20:15Z the night before;
 * today's only match is the MEN'S final, and the Men's tab rendered it fine.
 *
 * THE MECHANISM, both halves measured (live/201, and the payload read here in
 * the same minute): `order_of_play_listed` is TOURNAMENT-wide —
 * `len(order_of_play)` = 625, `tournament_slate.py:1685` — while the list it
 * explains is PER-DRAW. `slate.matches` held exactly one row and its draw was
 * `mens-singles`. So `slateEmptyState`'s `listed > 0` branch, which exists to
 * stop the page reporting its own empty output as a fact about the world
 * (#2707), fired on a draw that is simply over — the mirror of the defect it
 * was written for, and notice-34 prose on the marquee surface.
 *
 * IT HITS THE MEN'S TAB TONIGHT: when the 18:00Z final ends the slate drops it,
 * 625 stays, and the same false alarm lands on the tab everyone is watching.
 *
 * The input is `board.decided` — the grading that live/200's #5917 half
 * publishes (`f6668f077`) — and deliberately NOT a client-side count of
 * `results`, which would be this file's own sin one level down: inferring a
 * fact about the world from the shape of what we happened to render.
 */

import React from "react";
import fs from "fs";
import path from "path";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentMatches from "@/components/tournament/TournamentMatches";
import { slateEmptyState } from "@/lib/slate";
import { shownBoardsAreDecided, type TournamentBoardData } from "@/lib/tournament";

/** The production arguments, verbatim: 625 listed, nothing for this draw. */
const PRODUCTION = { drawReleased: true, orderOfPlayListed: 625 };

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
    ...(decided ? { decided: { winner_entity_key: "elena-rybakina" } } : {}),
  };
}

describe("🔴 a draw that is over is not a rendering failure", () => {
  it("says the draw is done instead of blaming the feed", () => {
    const state = slateEmptyState({ ...PRODUCTION, drawIsDecided: true });
    expect(state.cause).toBe("decided");
    expect(state.headline).toBe("This draw is done");
    expect(state.detail).toBe("The final has been played.");
  });

  it("the apology is GONE, not appended", () => {
    const state = JSON.stringify(slateEmptyState({ ...PRODUCTION, drawIsDecided: true }));
    expect(state).not.toContain("can't show today's schedule");
    expect(state).not.toContain("would be missing");
    expect(state).not.toContain("We're checking");
  });

  it("beats the tournament-wide count, which is the whole bug", () => {
    // 625 is the number that made the page apologise. Passing it alongside a
    // decided draw is the production case, not a hypothetical.
    expect(slateEmptyState({ ...PRODUCTION, drawIsDecided: true }).cause).toBe("decided");
    expect(slateEmptyState({ ...PRODUCTION, drawIsDecided: false }).cause).toBe("unrendered");
  });

  it("renders with no diagnostic prose and says which state it is", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches
        entries={[]}
        empty={slateEmptyState({ ...PRODUCTION, drawIsDecided: true })}
      />,
    );
    expect(html).toContain('data-empty-cause="decided"');
    expect(html).toContain("This draw is done");
    expect(html).not.toContain("We're checking");
  });
});

describe("🟢 every other empty state keeps the words it had", () => {
  it("an undecided draw with a live board still names OUR failure", () => {
    const state = slateEmptyState(PRODUCTION);
    expect(state.cause).toBe("unrendered");
    expect(state.headline).toBe("We can't show today's schedule");
  });

  it("pre-draw is unchanged", () => {
    const state = slateEmptyState({
      drawReleased: false,
      mainDrawLabel: "on Monday",
      orderOfPlayListed: 625,
    });
    expect(state.cause).toBe("pre-draw");
    expect(state.detail).toContain("on Monday");
  });

  it("the hedged zero case is unchanged", () => {
    expect(slateEmptyState({ drawReleased: true, orderOfPlayListed: 0 }).cause).toBe(
      "unlisted",
    );
  });

  it("omitting the new argument entirely changes nothing", () => {
    expect(slateEmptyState(PRODUCTION)).toEqual(
      slateEmptyState({ ...PRODUCTION, drawIsDecided: false }),
    );
  });
});

describe("which boards the question is asked of", () => {
  const WOMENS = board("womens-singles", true);
  const MENS = board("mens-singles", false);

  it("a singles pill reads its own draw", () => {
    expect(shownBoardsAreDecided([WOMENS, MENS], ["womens-singles"])).toBe(true);
    expect(shownBoardsAreDecided([WOMENS, MENS], ["mens-singles"])).toBe(false);
  });

  it("DOUBLES IS THREE DRAWS BEHIND ONE PILL — one graded final is not the day", () => {
    // #4124. `boards.find(...)` — the page's existing `board` memo — returns the
    // FIRST match, so a graded men's doubles final would have spoken for the
    // mixed draw still being played.
    const shown = ["mens-doubles", "womens-doubles", "mixed-doubles"];
    const boards = [
      board("mens-doubles", true),
      board("womens-doubles", true),
      board("mixed-doubles", false),
    ];
    expect(shownBoardsAreDecided(boards, shown)).toBe(false);
    expect(
      shownBoardsAreDecided(
        boards.map((b) => board(b.draw, true)),
        shown,
      ),
    ).toBe(true);
  });

  it("no board for this pill is NOT a finished draw", () => {
    // `[].every(...)` is true. On a page that would announce a final nobody
    // played, off a payload that knows nothing about the draw.
    expect(shownBoardsAreDecided([MENS], ["womens-singles"])).toBe(false);
    expect(shownBoardsAreDecided([], ["womens-singles"])).toBe(false);
    expect(shownBoardsAreDecided(undefined, ["womens-singles"])).toBe(false);
  });
});

describe("the hub page asks the right question", () => {
  // No render harness for the hub page (client page behind SWR); source scan
  // with comments stripped, since this file and the page both name the helper
  // in prose.
  const PAGE = path.resolve(__dirname, "../../app/tournaments/[slug]/page.tsx");
  const executable = () =>
    fs
      .readFileSync(PAGE, "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, " ")
      .split("\n")
      .map((line) => line.replace(/(^|\s)\/\/.*$/, "$1"))
      .join("\n");

  it("computes it from the pill's draws and feeds it to the empty state", () => {
    const code = executable();
    expect(code).toMatch(/shownBoardsAreDecided\(data\?\.boards,\s*drawsShown\)/);
    expect(code).toMatch(/drawIsDecided,/);
    // The wrong input, explicitly: `board` is the first matching board.
    expect(code).not.toMatch(/drawIsDecided:\s*Boolean\(board\?\.decided\)/);
  });
});
