/**
 * #4171 item 3 — THE GRID ALWAYS SCROLLED, IT JUST NEVER SAID SO.
 *
 * ═══ 🔴 THE FILING'S CONCLUSION IS WRONG, AND THAT MATTERS TO THE FIX ═══
 *
 * #4171 item 3 says the grid *"overflows horizontally at 390px … the TITLE
 * column is clipped … a reader on a phone cannot see the column the whole grid
 * builds to."* The clip is real and reproduces on production. The conclusion
 * does not follow, and building to it would have produced the wrong fix
 * (narrower columns, or a dropped column).
 *
 * Five columns is
 *
 *     2*GRID_ROW_PADDING_PX + GRID_NAME_WIDTH_PX
 *       + 5*GRID_COLUMN_WIDTH_PX + 5*GRID_GAP_PX
 *     = 28 + 118 + 270 + 30 = 446px
 *
 * inside a `GRID_CARD_CONTENT_PX` of 332. So `gridScrolls` is true, and this
 * container has carried `overflow-x-auto`, snap points and a rounded scroll
 * floor since #3072 and #3087. **TITLE is one swipe away and always has been.**
 *
 * What was missing is the AFFORDANCE: nothing on screen distinguished "the
 * table ends here" from "there is more to the right", so a reader with no
 * reason to attempt a horizontal swipe never learns the column exists — which
 * produces exactly the complaint that got filed. The arithmetic above is
 * asserted below rather than trusted, because it is the whole argument for
 * treating this as an affordance bug.
 *
 * ═══ SAME FIX AS #4261, ON PURPOSE ═══
 *
 * `TournamentProgressionTable` had the identical defect and latency/282b fixed
 * it in `aa22d84c` with a right-edge fade drawn only while there is more to
 * reach. Notice 35 — one family everywhere — so this is that treatment ported,
 * not a second invention.
 *
 * 🔴 Including the trap they paid for: their first cut faded the FULL HEIGHT
 * and washed out the last 32px of every cell, which on that table is precisely
 * where the bars differ, so the affordance erased the encoding it shipped
 * beside. This grid has a `SparkBar` under every numeric cell for the same
 * reason. The cue is therefore clamped to the header row's MEASURED height, and
 * that clamp is asserted here rather than left as a comment.
 *
 * ═══ WHY jsdom CAN ONLY TAKE THIS SO FAR ═══
 *
 * `scrollWidth`, `clientWidth` and `getBoundingClientRect()` are all 0 in jsdom,
 * so the cue's RUNTIME visibility cannot be exercised here and pretending
 * otherwise would be the "guard that never passed" failure. What is provable
 * without a browser is asserted: the overflow arithmetic, the scroller's own
 * attributes, and — the part that would actually regress — that the cue is
 * absent when it must be. The visible-state proof is the production screenshot
 * on the issue.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import PlayoffGrid from "@/components/tournament/PlayoffGrid";
import {
  GRID_CARD_CONTENT_PX,
  GRID_COLUMN_WIDTH_PX,
  GRID_GAP_PX,
  GRID_NAME_WIDTH_PX,
  GRID_ROW_PADDING_PX,
  gridScrolls,
  gridWidthPx,
  readPlayoffGrid,
  type PlayoffGrid as GridModel,
} from "@/lib/playoffGrid";
import type { TournamentPayload } from "@/lib/tournament";

const PAYLOAD = JSON.parse(
  fs.readFileSync(
    path.join(__dirname, "..", "..", "..", "docs", "mocks", "us-open", "payload-2026-08-27.json"),
    "utf8"
  )
) as TournamentPayload;

function mensGrid(): GridModel {
  const grid = readPlayoffGrid(PAYLOAD.grids?.["mens-singles"]);
  if (grid === null) throw new Error("the committed payload carries no men's grid");
  return grid;
}

describe("#4171 item 3 — the premise, checked rather than taken on trust", () => {
  it("the US Open grid really does overflow a phone card", () => {
    const grid = mensGrid();
    const columns = grid.columns.length;
    // The arithmetic the whole diagnosis rests on, spelled out so a change to
    // any constant that quietly removes the overflow also removes this ship's
    // reason to exist — loudly.
    expect(gridWidthPx(columns)).toBe(
      2 * GRID_ROW_PADDING_PX +
        GRID_NAME_WIDTH_PX +
        columns * GRID_COLUMN_WIDTH_PX +
        columns * GRID_GAP_PX
    );
    expect(gridWidthPx(columns)).toBeGreaterThan(GRID_CARD_CONTENT_PX);
    expect(gridScrolls(columns)).toBe(true);
  });

  it("...and the clipped column is REACHABLE, which is why this is not a layout fix", () => {
    // The correction to the filing, as an assertion. If TITLE were genuinely
    // unreachable the answer would be to narrow or drop a column; it is not.
    const grid = mensGrid();
    const html = renderToStaticMarkup(<PlayoffGrid grid={grid} initialExpanded />);
    expect(html).toContain('data-testid="grid-scroller"');
    expect(html).toContain("overflow-x-auto");
    expect(html).toContain("snap-start");
    // And the column the reader is being sent to is really in the markup.
    expect(html).toContain('data-kind="title"');
  });

  it("a grid narrow enough to fit does NOT become a scroller", () => {
    // The positive control for `gridScrolls`. Without it, "the grid scrolls"
    // could be a constant rather than a measurement, and the cue below would be
    // guarding a condition that is always true.
    const narrow = { ...mensGrid(), columns: mensGrid().columns.slice(0, 1) };
    expect(gridScrolls(narrow.columns.length)).toBe(false);
    const html = renderToStaticMarkup(<PlayoffGrid grid={narrow} initialExpanded />);
    expect(html).not.toContain("overflow-x-auto");
  });
});

describe("#4171 item 3 — the cue is absent until a browser says otherwise", () => {
  it("server render draws no fade, because it cannot know there is more to reach", () => {
    // 🔴 THIS IS THE ASSERTION THAT WOULD ACTUALLY CATCH A REGRESSION, and it is
    // the opposite of what it looks like. `canScrollRight` starts false and only
    // a real measurement flips it, so the cue must NOT be in the server markup.
    // If someone "simplifies" the gate to `scrolls &&` — which renders on the
    // server and looks correct in a screenshot — every grid would wear a
    // permanent fade, including one already scrolled to its end. That is the
    // regression, and this line is what reds on it.
    const html = renderToStaticMarkup(<PlayoffGrid grid={mensGrid()} initialExpanded />);
    expect(html).not.toContain('data-testid="grid-scroll-affordance"');
  });

  it("the cue's height is bound to the header, never hard-coded", () => {
    // The #4261 trap, as a source assertion rather than a comment. jsdom cannot
    // measure, so this checks the thing that goes wrong: a literal height. The
    // cue must take its height from the header ref's measurement.
    const source = fs.readFileSync(
      path.join(__dirname, "..", "..", "components", "tournament", "PlayoffGrid.tsx"),
      "utf8"
    );
    const cue = source.slice(source.indexOf('data-testid="grid-scroll-affordance"'));
    const block = cue.slice(0, cue.indexOf("/>"));
    expect(block).toContain("height: headerHeight");
    // ...and it is scoped to the phone, where the grid scrolls at all: above
    // `lg` the container is `overflow-x-visible` and there is nothing to cue.
    expect(block).toContain("lg:hidden");
    // A full-height fade is the exact thing #4261 had to undo.
    expect(block).not.toContain("inset-0");
    expect(block).not.toContain("h-full");
  });
});
