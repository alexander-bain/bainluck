/**
 * #7192 — THE GRID IS SORTED BY THE ONE COLUMN A PHONE NEVER SHOWS.
 *
 * At 390px `bainluck.com/playoffs/mlb` ranked 30 teams by `World Series ▼` and
 * put that column 263px past the right edge. What the reader saw, top to
 * bottom, was the leading column instead:
 *
 *     100  100  99  89  65  77  44  10        <- rank 5 below rank 6
 *
 * So the table asserted an order and showed a number that visibly contradicts
 * it, with nothing on screen to explain either. Measured with the #6722 probe,
 * `tools/progression-col-fit-6722.mjs <url> 390`, on 2026-09-19 (the numbers in
 * PRODUCTION below are that run, verbatim):
 *
 *     grid  cols  clientW  scrollW  overflow  sort column       visible
 *     mlb    4     316      587      271      `World Series ▼`  false
 *     nfl    4     316      556      240      `Super Bowl ▼`    false
 *     mls    2     316      367       51      `MLS Cup ▼`       false
 *
 * NOT a regression of #6722, which deleted the table's `min-w-[500px]` and
 * repaired the one-column grids. That floor is gone (`minWidth: 0px` on all
 * three rows above) and these grids still overflow: four columns genuinely need
 * 587px and no allocation of them fits in 316. There is no layout to be found —
 * the only question is WHERE THE SCROLLER OPENS, and it opened at 0.
 *
 * ═══ WHY THE FIX IS A SCROLL OFFSET AND NOT A COLUMN ORDER ═══
 *
 * The rejected alternative was to move the sort column next to `Team` at phone
 * width. It reads well on the first screen and breaks the thing the grid is:
 * the stages NEST (make playoffs ⊇ division ⊇ conference ⊇ title), so a row is
 * a funnel and reordering it mid-funnel makes the sequence meaningless — and
 * the order would then change under the reader every time they sorted.
 * Scrolling costs nothing here because `#` and `Team` are `position: sticky`:
 * the reader keeps the row's identity and gains the number that ranks it.
 *
 * ═══ TWO ARMS, BECAUSE EITHER HALF ALONE LEAVES THE READER WHERE THEY WERE ═══
 *
 * A. the arithmetic (`sortColumnScrollLeft`) — where the scroller must rest;
 * B. the wiring — that the component calls A, keeps calling it while the layout
 *    is still settling, stops the moment the reader scrolls for themselves, and
 *    marks the columns that are now behind the sticky cells.
 *
 * Arm B is a comment-stripped source scan for the same reason #3035's is: this
 * repo's jest environment is `node`, the component renders here through
 * `renderToStaticMarkup`, and effects never run — an effect-level assertion
 * would be a guard that never executes. jsdom would not save it either: #6722's
 * suite records that every rect, `clientWidth` and `scrollWidth` reads 0 there,
 * so the effect would be handed a zero box and asked to prove it scrolled. That
 * is why the decision is hoisted out of the effect into a pure function at all.
 */

import { readFileSync } from "fs";
import { join } from "path";
import { sortColumnScrollLeft } from "@/components/TournamentProgressionTable";

/**
 * Measured production geometry, in the scroller's client box — the coordinates
 * `progression-col-fit-6722.mjs` prints. `stickyRight` is the right edge of the
 * sticky `Team` header (188px on every grid in the fleet: `#` is 32px wide at
 * `left-0`, `Team` is 148px at `left-8`, plus the scroller's 8px padding).
 */
const PRODUCTION = {
  mlb: {
    clientWidth: 316,
    scrollWidth: 587,
    stickyRight: 188,
    sortColumn: { colLeft: 467.4, colRight: 578.9 }, // World Series ▼
    firstStage: { colLeft: 177.3, colRight: 285.3 }, // Make Playoffs
  },
  nfl: {
    clientWidth: 316,
    scrollWidth: 556,
    stickyRight: 188,
    sortColumn: { colLeft: 446, colRight: 548.5 }, // Super Bowl ▼
  },
  mls: {
    clientWidth: 316,
    scrollWidth: 367,
    stickyRight: 188,
    sortColumn: { colLeft: 271.5, colRight: 358.9 }, // MLS Cup ▼
  },
} as const;

type Grid = { clientWidth: number; stickyRight: number; scrollWidth: number };
type Column = { colLeft: number; colRight: number };

/** Ask the shipped arithmetic where a grid should rest, at a given offset. */
function restFor(grid: Grid, column: Column, scrollLeft: number): number | null {
  return sortColumnScrollLeft({
    colLeft: column.colLeft - scrollLeft,
    colRight: column.colRight - scrollLeft,
    clientWidth: grid.clientWidth,
    scrollLeft,
    stickyRight: grid.stickyRight,
  });
}

/** The probe's own definition of readable, applied to the post-scroll box. */
function readableAfter(
  grid: { clientWidth: number; stickyRight: number },
  column: { colLeft: number; colRight: number },
  scrolled: number,
): boolean {
  return column.colLeft - scrolled >= grid.stickyRight && column.colRight - scrolled <= grid.clientWidth + 0.5;
}

describe("#7192 arm A — the scroller rests on the column the order comes from", () => {
  test.each(["mlb", "nfl", "mls"] as const)(
    "%s: the sort column is off-screen at rest and readable after the move",
    (key) => {
      const grid = PRODUCTION[key];
      // The defect, restated as the precondition. If this ever stops holding,
      // the rest of the test is measuring nothing.
      expect(readableAfter(grid, grid.sortColumn, 0)).toBe(false);

      const next = restFor(grid, grid.sortColumn, 0);
      expect(next).not.toBeNull();
      expect(readableAfter(grid, grid.sortColumn, next as number)).toBe(true);
    },
  );

  test("it is the MINIMUM move, not a jump to the end of the table", () => {
    // 🔴 THE MUTANT THIS EXISTS FOR: `return maxScrollLeft`. It satisfies every
    // assertion above on all three grids — the sort column is the rightmost, so
    // slamming to the end does make it visible — and it is wrong, because it
    // throws away the columns that would still have fitted beside it and lands
    // the reader somewhere no measurement predicted. mlb's max is 271; the
    // correct rest is 262.9, where `World Series` ends exactly at the edge.
    const grid = PRODUCTION.mlb;
    const next = restFor(grid, grid.sortColumn, 0) as number;
    expect(next).toBeCloseTo(262.9, 1);
    expect(next).not.toBe(grid.scrollWidth - grid.clientWidth);
    expect(grid.sortColumn.colRight - next).toBeCloseTo(grid.clientWidth, 1);
  });

  test("a desktop grid that does not overflow is left exactly where it is", () => {
    // 1280px: the whole table fits, so there is nothing to align and no scroll
    // to perform. `null` is not `0` — returning 0 here would be a write to
    // scrollLeft on every desktop render.
    expect(
      sortColumnScrollLeft({
        colLeft: 900,
        colRight: 1010,
        clientWidth: 1200,
        scrollLeft: 0,
        stickyRight: 188,
      }),
    ).toBeNull();
  });

  test("jsdom's all-zero layout asks for no scroll", () => {
    // Not hypothetical: this is what the arithmetic is handed in any test that
    // renders the component, and a fix that scrolled on it would be untestable
    // noise rather than a no-op.
    expect(
      sortColumnScrollLeft({
        colLeft: 0,
        colRight: 0,
        clientWidth: 0,
        scrollLeft: 0,
        stickyRight: 0,
      }),
    ).toBeNull();
  });

  test("a column already readable is not nudged", () => {
    const grid = PRODUCTION.mlb;
    const rest = restFor(grid, grid.sortColumn, 0) as number;
    // Re-measured AFTER the move — rects are viewport-relative, so both edges
    // come back by `rest`. Feeding that state in must be a fixed point, or the
    // effect and the ResizeObserver chase each other across the table.
    expect(restFor(grid, grid.sortColumn, rest)).toBeNull();
  });

  test("sorting by an EARLY stage scrolls back, and never past the start", () => {
    // Tapping `Make Playoffs` while resting on `World Series`. The column is
    // hidden on the other side — underneath the sticky `Team` cell, not past
    // the right edge — and the same call has to come back for it.
    const grid = PRODUCTION.mlb;
    const next = restFor(grid, grid.firstStage, 262.9);
    expect(next).toBe(0);
    // 0 and not -10.7: `Make Playoffs` starts at 177.3, which is 10.7px behind
    // the sticky cell even at the very start of the table. The clamp is the
    // difference between "as close as the table allows" and a scrollLeft the
    // browser silently rejects.
    expect(next).not.toBeLessThan(0);
  });

  test("sorting by the first stage AT REST asks for no scroll at all", () => {
    // The lower clamp eats this move whole: `Make Playoffs` starts 10.7px behind
    // the sticky cell and the table is already at its start. The answer must be
    // `null` — "nothing to do" — and not the offset we are already sitting at,
    // or every sort of the leading column writes scrollLeft and marks the grid
    // aligned for a move that never happened.
    expect(restFor(PRODUCTION.mlb, PRODUCTION.mlb.firstStage, 0)).toBeNull();
  });

  test("sub-pixel overhang does not move the table", () => {
    // Fractional layout widths leave a column a hair past the edge. Acting on
    // that produces a visible half-pixel lurch on every resize for nothing.
    expect(
      sortColumnScrollLeft({
        colLeft: 200,
        colRight: 316.4,
        clientWidth: 316,
        scrollLeft: 0,
        stickyRight: 188,
      }),
    ).toBeNull();
    // ...and a real overhang still moves it, so the tolerance is a tolerance
    // and not a floor that swallows the defect.
    expect(
      sortColumnScrollLeft({
        colLeft: 200,
        colRight: 330,
        clientWidth: 316,
        scrollLeft: 0,
        stickyRight: 188,
      }),
    ).toBeCloseTo(14, 1);
  });
});

describe("#7192 arm B — the component wires the alignment and marks the hidden side", () => {
  // Comment-stripped, per #3035: this fix's own comments quote `scrollLeft`,
  // `sortColumnScrollLeft` and the testids, so an un-stripped scan reads the
  // prose as code and passes on a component that renders none of it.
  const CODE = readFileSync(
    join(__dirname, "../../components/TournamentProgressionTable.tsx"),
    "utf8",
  )
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");

  test("the scroller's offset is assigned from the arithmetic, not from a literal", () => {
    expect(CODE).toMatch(/const next = sortColumnScrollLeft\(\{/);
    expect(CODE).toMatch(/el\.scrollLeft = next;/);
    // The null contract is honoured at the call site. Without this line the
    // "leave a desktop alone" test above is true of the function and false of
    // the page, because `scrollLeft = null` writes 0.
    expect(CODE).toMatch(/if \(next === null\) return;/);
  });

  test("the sort column is the subject, and every stage header can be found", () => {
    // The effect looks the column up by the key it is sorted on; if the headers
    // are not registered it has nothing to measure and silently does nothing.
    expect(CODE).toContain("stageThRefs.current.get(key)");
    expect(CODE).toContain("stageThRefs.current.set(stage.key, node)");
    expect(CODE).toContain("stageThRefs.current.delete(stage.key)");
    // And the sticky cell whose edge decides what "hidden" means.
    expect(CODE).toContain("ref={nameThRef}");
  });

  test("it realigns when the reader sorts, and it does not realign for free", () => {
    expect(CODE).toMatch(/\[sort\.stageKey,/);
    // 🔴 THE TWO HALVES OF "DO NOT FIGHT THE READER". Alignment is re-run on
    // every layout change — a font swap moved the settled rest by 4px on the
    // local build, and a mount-only rule cannot see that — so the guard cannot
    // be "have we ever aligned". It is: the reader has not taken over, OR they
    // have just asked for a different column.
    expect(CODE).toContain("if (!readerScrolled.current) alignSortColumn();");
    expect(CODE).toContain("if (alignedStageKey.current === sort.stageKey) return;");
    expect(CODE).toContain("alignedStageKey.current = key;");
  });

  test("the component does not mistake its own scroll for the reader's", () => {
    // Without the claim, the very first alignment fires a scroll event, the
    // handler records "the reader has taken over", and every later realignment
    // is suppressed — the fix would disable itself on the way in.
    const claim = CODE.indexOf("selfScroll.current = true;");
    const assign = CODE.indexOf("el.scrollLeft = next;");
    expect(claim).toBeGreaterThan(-1);
    expect(assign).toBeGreaterThan(claim); // claimed BEFORE the move, or the event beats it
    expect(CODE).toContain("if (selfScroll.current) selfScroll.current = false;");
    expect(CODE).toContain("else readerScrolled.current = true;");
  });

  test("the header row is observed, not only the scroller", () => {
    // The scroller is `w-full`: its own box does not change when the table
    // inside it grows, so observing it alone is blind to exactly the late
    // content change the realignment exists for.
    expect(CODE).toContain("observer.observe(el)");
    expect(CODE).toContain("observer.observe(headRef.current)");
  });

  test("both edges have a cue, recomputed on scroll rather than frozen at mount", () => {
    expect(CODE).toContain('data-testid="progression-scroll-affordance"');
    expect(CODE).toContain('data-testid="progression-scroll-affordance-left"');
    expect(CODE).toContain("onScroll={handleScroll}");
    // The left cue's condition is the cue: a grid resting at 0 has nothing
    // behind the sticky cells and must not claim otherwise.
    expect(CODE).toContain("setCanScrollLeft(el.scrollLeft > 4)");
    expect(CODE).toContain("setCanScrollRight(el.scrollWidth - el.clientWidth - el.scrollLeft > 4)");
  });

  test("the left cue sits at the sticky seam, because the container's edge is covered", () => {
    // 🔴 THE MISTAKE THIS PINS, which was made and measured on the way here: the
    // obvious mirror of the right cue is `-left-2`, and it is invisible. The
    // `#` and `Team` cells are `sticky`, `z-10` and opaque `bg-surface-card`,
    // and they cover the container's left edge entirely — a fade there paints
    // underneath them and no reader ever sees it. The hidden columns disappear
    // at the RIGHT edge of the sticky block, so that is where the cue goes.
    expect(CODE).toContain("left: stickyEdge");
    // And it must not also carry a container-edge offset class that would
    // fight the measured one.
    //
    // SCOPE NARROWED BY #7246, intent unchanged. This was a file-wide
    // `not.toContain("-left-2")`, which was a true statement about the CUE
    // written as a statement about the FILE — safe only while nothing else
    // could legitimately sit at the container's edge. #7246 put something
    // there: an opaque 8px cover for the strip the sticky block does not
    // reach, whose whole job is to be at `-left-2`. The claim being made here
    // has always been "this cue is positioned by measurement, not by a
    // container offset", so it is now asked of the cue's own JSX block.
    const leftCue = (() => {
      const at = CODE.indexOf('data-testid="progression-scroll-affordance-left"');
      return CODE.slice(CODE.lastIndexOf("<div", at), CODE.indexOf("/>", at) + 2);
    })();
    expect(leftCue).toContain("left: stickyEdge");
    expect(leftCue).not.toContain("-left-2");
    expect(CODE).toContain("bg-gradient-to-r from-surface-card to-transparent");
    // Measured from the sticky header itself, never assumed: the `Team` column
    // is 92px at its floor and 140px+ from `sm:`, so a hardcoded seam would be
    // wrong at one width or the other.
    expect(CODE).toMatch(/nameThRef\.current\?\.getBoundingClientRect\(\)/);
  });

  test("the cues are siblings of the scroller, or they scroll away with it", () => {
    // An absolutely positioned child of an overflow container travels with the
    // content it is supposed to be marking.
    const scroller = CODE.indexOf("ref={scrollRef}");
    const rightCue = CODE.indexOf('data-testid="progression-scroll-affordance"');
    const leftCue = CODE.indexOf('data-testid="progression-scroll-affordance-left"');
    expect(scroller).toBeGreaterThan(-1);
    expect(rightCue).toBeGreaterThan(scroller);
    expect(leftCue).toBeGreaterThan(scroller);
    const scrollerClose = CODE.indexOf("</table>");
    expect(scrollerClose).toBeLessThan(rightCue);
    expect(scrollerClose).toBeLessThan(leftCue);
    // Neither one may take a tap meant for a header link.
    const cueLines = CODE.split("\n").filter((l) => l.includes("progression-scroll-affordance"));
    expect(cueLines).toHaveLength(2);
    // SCOPE NARROWED BY #7246, intent unchanged. The file-wide count of
    // `pointer-events-none absolute` was standing in for "both cues are inert
    // overlays"; it read 2 because the cues were the only two overlays. The
    // #7246 cover is a third, so the claim is now made of each cue by name and
    // the file-wide count moved to that fix's own guard, which can say what the
    // third one is.
    const rightCueBlock = CODE.slice(
      CODE.lastIndexOf("<div", rightCue),
      CODE.indexOf("/>", rightCue) + 2,
    );
    const leftCueBlock = CODE.slice(
      CODE.lastIndexOf("<div", leftCue),
      CODE.indexOf("/>", leftCue) + 2,
    );
    expect(rightCueBlock).toContain("pointer-events-none absolute");
    expect(leftCueBlock).toContain("pointer-events-none absolute");
    // Their heights differ on purpose and the difference is load-bearing: the
    // right cue stays on the header (#4261 measured that a full-height wash
    // there erased the bars), the left one runs the full height because what it
    // covers is the cut-off tail of a column sliding under the sticky block.
    expect(CODE).toContain("pointer-events-none absolute top-0 -right-2");
    expect(CODE).toContain("pointer-events-none absolute inset-y-0 w-8 bg-gradient-to-r");
  });

  test("the sticky block has no slot in it for the scrolled columns to show through", () => {
    // 🔴 FOUND BY SCROLLING, WHICH IS WHY IT WAS NEVER FOUND BEFORE. `Team` is
    // pinned at `left-8` = 32px, and the rank column it is pinned beside
    // measured 21.3px on production: `w-8` is a hint and `table-layout: auto`
    // discards it at min-content width. At scrollLeft 0 the 10.7px difference
    // is an empty strip over nothing. The moment the grid opens on its sort
    // column, `Division`'s digits and 24h arrows run through it, between the
    // rank and the crest — measured on the local build before this line.
    // Both cells carry the floor, because a column is as wide as its widest
    // cell and the header is not always that cell.
    const rankCells = CODE.split("\n").filter((l) => l.includes("sticky left-0"));
    const nameCells = CODE.split("\n").filter((l) => l.includes("sticky left-8"));
    expect(rankCells).toHaveLength(2); // header + body
    expect(nameCells).toHaveLength(2);

    // Read both numbers out of the classes and compare them, rather than
    // asserting the literal 32 twice — the point is that they are the SAME
    // number, so a future `left-10` with no matching floor has to go red.
    const floors = rankCells.map((l) => Number(l.match(/min-w-\[(\d+)px\]/)?.[1]));
    const offsets = nameCells.map((l) => Number(l.match(/sticky left-(\d+)/)?.[1]) * 4);
    expect(new Set([...floors, ...offsets]).size).toBe(1);
  });

  test("the sticky columns the whole design rests on are still sticky", () => {
    // Scrolling is only free because the row keeps its identity. If either of
    // these stops being sticky, this fix becomes "hide the team name".
    expect(CODE).toContain("sticky left-0 z-10 bg-surface-card");
    expect(CODE).toContain("sticky left-8 z-10 bg-surface-card");
  });
});
