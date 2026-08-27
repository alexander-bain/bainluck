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

import PlayoffGrid, { GRID_SIZING } from "@/components/tournament/PlayoffGrid";
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
  describe("the page shell", () => {
    it("keeps the 560px phone column — every prior ruling was verdicted on it", () => {
      // The desktop work must be ADDITIVE. UX-P131 through UX-P143 were all
      // signed off against a 390px capture whose content box is 358px inside a
      // 560px shell; moving that number silently re-opens every one of them.
      expect(TOURNAMENT_SHELL).toContain("max-w-[560px]");
    });

    it("widens above `lg` — the actual defect Alex reported", () => {
      expect(TOURNAMENT_SHELL).toMatch(/lg:max-w-\[\d{4}px\]/);
      expect(TOURNAMENT_SHELL).toMatch(/xl:max-w-\[\d{4}px\]/);

      // And the widths ascend. A typo that puts the smaller number at the
      // larger breakpoint gives you a page that gets NARROWER as the window
      // grows, which is both absurd and easy to miss without a browser.
      const widths = [...TOURNAMENT_SHELL.matchAll(/max-w-\[(\d+)px\]/g)].map((m) =>
        Number(m[1])
      );
      expect(widths.length).toBe(3);
      expect(widths).toEqual([...widths].sort((a, b) => a - b));
      expect(new Set(widths).size).toBe(3);
    });

    it("is the string the PAGE actually renders, not a constant nobody uses", () => {
      // The failure this catches: someone inlines a class on the wrapper div
      // and leaves the export behind, so this whole file goes on passing while
      // the page reverts to a phone column.
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

    it("P138's ruling 5 is UNCHANGED — scroll still applies where it was measured", () => {
      // Alex: "P138's horizontal-scroll ruling applies to mobile, not a 1400px
      // window." The fix was not to weaken the rule; the phone's arithmetic is
      // exactly as UX-P139 measured it, and desktop simply never asks.
      expect(gridWidthPx(5)).toBe(348);
      expect(gridScrolls(5)).toBe(false);
      expect(gridScrolls(6)).toBe(true);
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
