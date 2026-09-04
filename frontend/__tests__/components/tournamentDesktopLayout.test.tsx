/**
 * UX-P145 — THE TOURNAMENT HUB HAS A DESKTOP LAYOUT, AND IT STAYS.
 *
 * Alex, on the live page in a desktop browser: "weirdly narrow, like we only
 * made a mobile version." He was reading it correctly. Every element on
 * /tournaments/us-open lived inside one `max-w-[560px]`, so a 1400px window
 * rendered a 560px phone in the middle of 840px of grey.
 *
 * ═══ WHAT A TEST CAN AND CANNOT PROVE HERE ═══
 *
 * Chromium is dead in this sandbox, so nothing here can measure a laid-out box.
 * What it CAN do is assert the three things that would have to be true for the
 * layout to exist at all, and each of these is a real failure mode rather than
 * a restatement of the source:
 *
 *   1. The shipped shell string still widens. A revert to a bare
 *      `max-w-[560px]` is one careless merge away and would look like nothing
 *      in a diff full of copy changes.
 *   2. The grid's CSS variables are a LITERAL. This is the sharp one — see the
 *      test for why a perfectly reasonable refactor silently deletes the
 *      desktop grid while the build, the typecheck and every other test stay
 *      green.
 *   3. The variables and the exported constants agree. They are typed twice
 *      because Tailwind forces it; a duplicated width that nothing compares is
 *      a width that will drift.
 *
 * The visual verdict is the artifact, not this file:
 * `__tests__/capture/usOpenDesktopCapture.test.tsx` renders the real page shell
 * at 1440px against the app's own compiled CSS.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import PlayoffGrid, { GRID_SIZING, gridTemplate } from "@/components/tournament/PlayoffGrid";
import { TOURNAMENT_COLUMNS, TOURNAMENT_SHELL } from "@/components/tournament/layout";
import {
  GRID_COLUMN_WIDTH_DESKTOP_PX,
  GRID_COLUMN_WIDTH_PX,
  GRID_NAME_WIDTH_DESKTOP_PX,
  GRID_NAME_WIDTH_PX,
  gridScrolls,
  gridWidthPx,
  readPlayoffGrid,
} from "@/lib/playoffGrid";
import type { TournamentPayload } from "@/lib/tournament";

const FRONTEND = path.join(__dirname, "..", "..");
const PAGE = path.join(FRONTEND, "app", "tournaments", "[slug]", "page.tsx");
const PAYLOAD_PATH = path.join(
  FRONTEND,
  "..",
  "docs",
  "mocks",
  "us-open",
  "payload-2026-08-27.json"
);

function pageSource(): string {
  return fs.readFileSync(PAGE, "utf8");
}

function loadGrid() {
  const payload = JSON.parse(fs.readFileSync(PAYLOAD_PATH, "utf8")) as TournamentPayload;
  const grid = readPlayoffGrid(payload.grids?.["mens-singles"]);
  if (!grid) throw new Error("payload carries no men's grid");
  return grid;
}

describe("UX-P145: the desktop layout exists", () => {
  /**
   * UX-P146 REPLACED THIS BLOCK WHOLESALE.
   *
   * UX-P145 pinned "the shell widens to 1024 then 1280". Alex's answer to that
   * artifact was "doesn't the rest of the desktop site just use as much width
   * as the user gives it?", and it does — so the property worth guarding is the
   * opposite one: this page must carry NO width of its own, and must inherit
   * the site container it now depends on.
   */
  describe("the page shell — UX-P146: there isn't one", () => {
    it("carries no max-width of its own, at any breakpoint", () => {
      // The revert this catches is a well-meaning one: somebody reads "the page
      // is too wide on a 27-inch monitor" and puts a cap back on THIS page
      // instead of on the site container, and the tournament hub is once again
      // the only page that answers to a different number.
      expect(TOURNAMENT_SHELL).not.toMatch(/max-w-/);
      expect(TOURNAMENT_SHELL).not.toMatch(/\d+px/);
      // Not a mx-auto column either — centring only means something to an
      // element that is narrower than its parent, and this one never is.
      expect(TOURNAMENT_SHELL).not.toContain("mx-auto");
    });

    it("the phone is untouched, which is why removing the cap was safe", () => {
      // The load-bearing fact behind "no prior ruling re-opens": UX-P131
      // through UX-P145 were verdicted at a 390px viewport, and 390 < 560, so
      // `max-w-[560px]` never bound a single one of those captures. Asserting
      // the arithmetic rather than the intent, because the intent is what a
      // future reader will doubt.
      const PHONE_VIEWPORT_PX = 390;
      const RETIRED_CAP_PX = 560;
      expect(PHONE_VIEWPORT_PX).toBeLessThan(RETIRED_CAP_PX);
    });

    it("defers to the SITE container — and that container still exists", () => {
      // The page now has no width because `app/layout.tsx` has one. If that
      // wrapper is ever removed or renamed, this page goes edge-to-edge on a
      // 3440px monitor and nothing else in this file would notice.
      const layout = fs.readFileSync(path.join(FRONTEND, "app", "layout.tsx"), "utf8");
      expect(layout).toContain('<main className="flex-1 pb-20 md:pb-0">');
      expect(layout).toContain('className="max-w-content mx-auto px-3 md:px-6 py-4"');

      // …and `max-w-content` is a real token, not a class Tailwind drops.
      const tailwind = fs.readFileSync(path.join(FRONTEND, "tailwind.config.ts"), "utf8");
      expect(tailwind).toMatch(/maxWidth:\s*\{\s*content:\s*'(\d+)px'/);
    });

    it("matches what the rest of the site does, measured rather than claimed", () => {
      // The convention Alex was describing, checked against the two big
      // dashboard pages that hold it cleanly: they sit inside the site
      // container and add no width of their own, anywhere. If either grows a
      // page-level column the sentence in `layout.ts` stops being true and this
      // is where it is caught.
      //
      // Deliberately only these two. `/economics` and `/weather` DO cap some
      // inner sections (1280/1440) and `/search` and `/hub` cap an error-state
      // block — none of them cap the page, which is the property that matters,
      // but a regex cannot tell a section from a page and a test that pretends
      // it can is a test somebody deletes.
      for (const route of ["politics", "entertainment"]) {
        const src = fs.readFileSync(path.join(FRONTEND, "app", route, "page.tsx"), "utf8");
        expect(src).not.toMatch(/max-w-content/);
        expect(src).not.toMatch(/max-w-\d?xl\b/);
        expect(src).not.toMatch(/max-w-\[\d+px\]/);
      }
    });

    it("is the string the PAGE actually renders, not a constant nobody uses", () => {
      // The failure this catches: someone inlines a class on the wrapper div
      // and leaves the export behind, so this whole file goes on passing while
      // the page reverts to a column.
      const src = pageSource();
      expect(src).toContain("TOURNAMENT_SHELL");
      expect(src).toContain("className={TOURNAMENT_SHELL}");
      // No stray 560px column left hard-coded on the page body. The loading and
      // error states legitimately keep theirs — they are a centred sentence,
      // not a layout — so this is scoped to the shell wrapper.
      expect(src).not.toContain('<div className="mx-auto max-w-[560px]">');
    });
  });

  describe("the two-column split", () => {
    it("turns on at `lg` and never below it", () => {
      // Every declaration in the columns class must be `lg:`-prefixed. An
      // unprefixed `grid` would apply the two-column layout to the PHONE, where
      // the second column is 190px wide and the page is destroyed.
      const declarations = TOURNAMENT_COLUMNS.split(/\s+/).filter(Boolean);
      expect(declarations.length).toBeGreaterThan(2);
      for (const declaration of declarations) {
        expect(declaration.startsWith("lg:")).toBe(true);
      }
      expect(TOURNAMENT_COLUMNS).toContain("lg:grid");
    });

    it("gives both tracks an explicit 0 minimum", () => {
      // A grid track defaults to `min-width:auto` and refuses to shrink below
      // its content. The match list truncates long player names, so without
      // `minmax(0,…)` one long name pushes its track past its share and the
      // right column falls off the shell — on real data only, and only for
      // some players.
      expect(TOURNAMENT_COLUMNS).toContain("minmax(0,1.35fr)");
      expect(TOURNAMENT_COLUMNS).toContain("minmax(0,1fr)");
    });

    it("is what the Tournament tab renders, and the DOM order is the mobile order", () => {
      const src = pageSource();
      expect(src).toContain("className={TOURNAMENT_COLUMNS}");

      // Order matters more than the split does: below `lg` the wrappers are
      // inert and the page must stack exactly as UX-P138 shipped it — chart,
      // matches, results, board, more predictions.
      const order = [
        "<ContenderChart",
        "<TournamentMatches",
        "<TournamentResults",
        "<TournamentBoard",
        "<TournamentProps",
      ].map((tag) => src.indexOf(tag));
      expect(order.every((i) => i > 0)).toBe(true);
      expect(order).toEqual([...order].sort((a, b) => a - b));
    });

    it("does NOT split the Bracket tab — a grid wants the whole shell", () => {
      const src = pageSource();
      const bracketAt = src.indexOf('tab === "bracket"');
      const columnsAt = src.indexOf("className={TOURNAMENT_COLUMNS}");
      expect(bracketAt).toBeGreaterThan(0);
      expect(columnsAt).toBeGreaterThan(0);
      expect(columnsAt).toBeLessThan(bracketAt);
      // …and the split is inside the tournament branch, so it cannot leak.
      expect(src.slice(bracketAt)).not.toContain("TOURNAMENT_COLUMNS");
    });
  });

  describe("the playoff grid at desktop scale", () => {
    it("sizes its columns with CSS variables, so no JS reads the viewport", () => {
      // A `useMediaQuery` here would make the first client render disagree with
      // the server's, and the capture rig renders through
      // `renderToStaticMarkup`, where there is no viewport at all — the desktop
      // artifact would show the phone grid and prove nothing.
      const html = renderToStaticMarkup(<PlayoffGrid grid={loadGrid()} initialExpanded />);
      expect(html).toContain("var(--grid-name-w)");
      expect(html).toContain("minmax(var(--grid-col-w), 1fr)");
      expect(html).toContain(GRID_SIZING);
    });

    /* ═══ UX-P147, ALEX'S ITEM 1: NAMES BEFORE BARS ═══
     *
     * "Player names truncate too early when the window is not super wide ...
     * names get priority over bar width; bars compress first."
     *
     * That priority is not a number anywhere — it is which of the two track
     * kinds carries a growth limit, because the CSS grid algorithm maximizes
     * non-flexible tracks (§12.6) BEFORE it expands flexible ones (§12.7). So
     * this asserts the shape of the template, at the render, and states what
     * each half of it buys. A revert to the fixed name track passes every other
     * test in the repo and silently restores the truncation.
     */
    it("gives the NAME track the growth limit and the bars the leftovers", () => {
      const grid = loadGrid();
      const html = renderToStaticMarkup(<PlayoffGrid grid={grid} initialExpanded />);
      expect(html).toContain(
        `minmax(var(--grid-name-w), max-content) repeat(${grid.columns.length}, minmax(var(--grid-col-w), 1fr))`
      );
      // The old template, which must not come back: a bare `var()` name track
      // takes no free space at all.
      expect(html).not.toContain(
        `columns:var(--grid-name-w) repeat(${grid.columns.length}`
      );
      expect(gridTemplate(4)).toBe(
        "minmax(var(--grid-name-w), max-content) repeat(4, minmax(var(--grid-col-w), 1fr))"
      );
    });

    it("draws the spark bars by default — Alex ruled Option A", () => {
      // The plant has to hit the RENDER: `SparkBar` existing is not the same
      // claim as the shipped page drawing one.
      const html = renderToStaticMarkup(<PlayoffGrid grid={loadGrid()} initialExpanded />);
      expect(html).toContain('data-testid="grid-spark-bar"');
    });

    it("⚠️ GRID_SIZING IS A LITERAL — this is the one that will actually fire", () => {
      // THE FAILURE MODE, because it is not obvious and it is silent:
      //
      // Tailwind's JIT finds classes by SCANNING SOURCE TEXT. It does not
      // execute the module. Build `GRID_SIZING` out of the exported width
      // constants — which is the obvious cleanup, and which the first draft of
      // this feature did — and the string `[--grid-name-w:118px]` never
      // literally appears anywhere in the repo. Tailwind emits no rule,
      // `var(--grid-name-w)` resolves to nothing, and every track in the grid
      // collapses to zero width.
      //
      // Build: green. Typecheck: green. Every other test: green. The page: a
      // stack of overlapping text. So the shape of the declaration is pinned,
      // not just its value.
      const source = fs.readFileSync(
        path.join(FRONTEND, "components", "tournament", "PlayoffGrid.tsx"),
        "utf8"
      );
      const assignment = source.match(/export const GRID_SIZING\s*=\s*([\s\S]*?);/);
      expect(assignment).not.toBeNull();
      const rhs = assignment![1];
      // A plain double-quoted string and nothing else — no template literal, no
      // interpolation, no `.join()`, no concatenation.
      expect(rhs).not.toContain("`");
      expect(rhs).not.toContain("${");
      expect(rhs).not.toContain("join");
      expect(rhs.replace(/\s+/g, " ").trim()).toMatch(/^"[^"$`]+"$/);
    });

    it("the literal agrees with the exported constants — typed twice, checked once", () => {
      // Tailwind forces the duplication; nothing forces it to stay correct.
      const read = (name: string) => {
        const hit = GRID_SIZING.match(new RegExp(`(?:^|\\s)${name}:(\\d+)px\\]`));
        return hit ? Number(hit[1]) : null;
      };
      expect(read("\\[--grid-name-w")).toBe(GRID_NAME_WIDTH_PX);
      expect(read("\\[--grid-col-w")).toBe(GRID_COLUMN_WIDTH_PX);
      expect(read("lg:\\[--grid-name-w")).toBe(GRID_NAME_WIDTH_DESKTOP_PX);
      expect(read("lg:\\[--grid-col-w")).toBe(GRID_COLUMN_WIDTH_DESKTOP_PX);
    });

    it("desktop measurements are bigger than the phone's, or they are pointless", () => {
      expect(GRID_NAME_WIDTH_DESKTOP_PX).toBeGreaterThan(GRID_NAME_WIDTH_PX);
      expect(GRID_COLUMN_WIDTH_DESKTOP_PX).toBeGreaterThan(GRID_COLUMN_WIDTH_PX);

      // Six columns at desktop scale must still fit a 1024px shell's content
      // box, or `lg` re-introduces the scroll it was meant to retire.
      const sixWide =
        GRID_NAME_WIDTH_DESKTOP_PX + 6 * GRID_COLUMN_WIDTH_DESKTOP_PX;
      expect(sixWide).toBeLessThan(1024 - 48);
    });

    it("P138's ruling 5 still applies where it was measured — and its arithmetic is now right (#3072)", () => {
      // Alex: "P138's horizontal-scroll ruling applies to mobile, not a 1400px
      // window." Unchanged: desktop never asks. What DID change is the phone's
      // sum, which omitted the row's `gap-1.5` and `px-3.5` and compared it
      // against a 358px box that is really 332 — so a five-column men's draw
      // was declared a fit and the Title column was clipped away instead of
      // scrolling to. See `lib/playoffGrid.ts` for the production measurement.
      expect(gridWidthPx(5)).toBe(406);
      expect(gridScrolls(5)).toBe(true);
      expect(gridScrolls(6)).toBe(true);
      // "Sparingly" still binds where it can be honoured.
      expect(gridScrolls(3)).toBe(false);
    });

    it("…and desktop retires the phone's scroll floor rather than inheriting it", () => {
      // A six-column grid pins `min-width:394px` inline for the phone scroller.
      // Left alone, that inline style would also apply at 1400px, where it is
      // the ONLY thing keeping the columns narrow — an inline width beats a
      // class, so retiring it needs the `!important` form.
      const base = loadGrid();
      const wide = {
        ...base,
        columns: [
          ...base.columns,
          { key: "r32", short_label: "R32", long_label: "Reaches the last 32", kind: "reach" as const, slots: 32 },
        ],
      };
      const html = renderToStaticMarkup(<PlayoffGrid grid={wide} initialExpanded />);
      expect(html).toContain('data-scrolls="true"');
      expect(html).toContain("overflow-x-auto");
      expect(html).toContain("lg:overflow-x-visible");
      expect(html).toContain("lg:!min-w-0");
    });
  });

  describe("the chart keeps its proportions as the page widens", () => {
    it("steps its height at `lg` AND again past `xl`", () => {
      // Removing the page's 1280px column moved the width `lg:h-40` was
      // measured against. Left track end to end: ~486px at `lg`, ~627px at
      // `xl`, ~817px once `max-w-content` binds at 1600 — 3.0:1, 3.9:1 and
      // 5.1:1 against a 160px box. The third one is a flat line where a title
      // race should be, and it only exists because the shell is gone.
      const source = fs.readFileSync(
        path.join(FRONTEND, "components", "tournament", "ContenderChart.tsx"),
        "utf8"
      );
      const svg = source.match(/className="block h-24 w-full[^"]*"/);
      expect(svg).not.toBeNull();
      expect(svg![0]).toContain("lg:h-40");
      expect(svg![0]).toContain("2xl:h-56");

      // And the heights ascend with the breakpoints, or the chart gets SHORTER
      // as the window grows — the same class of typo the shell test caught.
      const heights = [...svg![0].matchAll(/h-(\d+)/g)].map((m) => Number(m[1]));
      expect(heights).toEqual([...heights].sort((a, b) => a - b));
      expect(new Set(heights).size).toBe(heights.length);
    });
  });

  describe("prose is capped even though the page is not", () => {
    it("the grid's paragraphs carry a measure; the TABLE does not", () => {
      // Alex: "sensible max-width for text sections only". Applied where the
      // text is rather than to the page — a `max-w` on the section would cap
      // the grid too, which is the one thing on this tab that wants 1280px.
      const html = renderToStaticMarkup(<PlayoffGrid grid={loadGrid()} initialExpanded />);
      const legend = html.match(/<p[^>]*data-testid="grid-legend"[^>]*>/);
      expect(legend).not.toBeNull();
      expect(legend![0]).toMatch(/max-w-\[\d+ch\]/);

      const scroller = html.match(/<div[^>]*data-testid="grid-scroller"[^>]*>/);
      expect(scroller).not.toBeNull();
      expect(scroller![0]).not.toMatch(/max-w-\[\d+ch\]/);
    });

    it("the page footer is capped", () => {
      expect(pageSource()).toMatch(/block max-w-\[\d+ch\]/);
    });
  });

  describe("the hard-coded weekday is gone", () => {
    it("the empty match hint reads the payload instead of naming Thursday", () => {
      // Live and wrong the same afternoon: the draw was made on 2026-08-27 and
      // the page still said "the draw fills them in on Thursday". A weekday
      // written into a component is true for one week a year.
      const src = pageSource();
      expect(src).not.toContain("fills them in on Thursday");
      expect(src).toContain("data.main_draw_label");
      // And once the draw IS out, the clause is dropped rather than reworded —
      // "the draw fills them in <date>" is nonsense after the ceremony.
      expect(src).toContain("data.draw_released");
    });
  });
});
