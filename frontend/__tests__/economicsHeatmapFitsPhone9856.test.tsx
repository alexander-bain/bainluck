/**
 * #9856 — THE LAST MEETING MUST BE ON SCREEN.
 *
 * `https://bainluck.com/economics` at a 390px viewport, 2026-09-30: after
 * #9804 cut the rate path to three meetings, the heatmap grid kept its fixed
 * `minWidth: 500` inside a 316px scroller. The three `1fr` columns stretched
 * to fill 500px and Jan 2027 sat wholly past the right edge — the reader saw
 * Oct and a clipped Dec, and nothing said a third column existed.
 *
 * Measured on production by injecting the candidate floor into the live grid
 * (tools/econ-heatmap-fit-9856.mjs):
 *
 *     minWidth | grid | scroller | Jan visible
 *     ---------|------|----------|------------
 *     500      | 500  | 316      | no          <- served
 *     328      | 328  | 316      | no          <- 70 + 3×86, the first suggestion
 *     298      | 316  | 316      | yes
 *
 * jsdom does no layout, so this guard pins the arithmetic the fix rests on and
 * the wiring that makes the page use it.
 *
 *   npx jest --testPathPatterns=economicsHeatmapFitsPhone9856
 */

import { readFileSync } from "fs";
import { join } from "path";
import { heatmapMinWidth } from "@/lib/fedRatePath";

const PAGE = readFileSync(join(__dirname, "..", "app", "economics", "page.tsx"), "utf8");
const LINES = PAGE.split("\n");
const OPEN = LINES.findIndex(l => /^function FedHeatmap\(/.test(l));
const END = LINES.findIndex((l, i) => i > OPEN && /^}/.test(l));
const BODY = LINES.slice(OPEN, END).join("\n");

// The scroller's width at the narrowest phones we ship to, measured on
// production at 390 (316) and 360 (286) — page gutter + card padding = 74px.
const SCROLLER_AT_390 = 316;
const SCROLLER_AT_360 = 286;

describe("#9856 · a short rate path fits the phone", () => {
  test("three meetings fit a 390px phone's scroller (the served specimen)", () => {
    expect(heatmapMinWidth(3)).toBeLessThanOrEqual(SCROLLER_AT_390);
  });

  test("three meetings fit a 360px phone's scroller too", () => {
    expect(heatmapMinWidth(3)).toBeLessThanOrEqual(SCROLLER_AT_360);
  });

  test("the floor grows with the column count", () => {
    for (let n = 1; n < 6; n++) {
      expect(heatmapMinWidth(n + 1)).toBeGreaterThan(heatmapMinWidth(n));
    }
  });

  test("a long path keeps the old 500px floor, so it scrolls as before", () => {
    expect(heatmapMinWidth(7)).toBe(500);
    expect(heatmapMinWidth(12)).toBe(500);
  });
});

describe("#9856 · the page draws the grid with the scaled floor", () => {
  test("FedHeatmap's grid uses heatmapMinWidth(meetings.length), not a literal", () => {
    expect(OPEN).toBeGreaterThan(-1);
    expect(END).toBeGreaterThan(OPEN);
    expect(BODY).toMatch(/minWidth:\s*heatmapMinWidth\(meetings\.length\)/);
    // The fixed literal is what hid Jan 2027. It must not come back.
    expect(BODY).not.toMatch(/minWidth:\s*\d+/);
  });

  test("the grid still has one column per meeting", () => {
    expect(BODY).toContain("gridTemplateColumns: `70px repeat(${meetings.length}, 1fr)`");
  });
});
