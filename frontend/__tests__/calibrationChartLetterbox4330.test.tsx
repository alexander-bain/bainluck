// #4330 — A CHART MUST NOT RESERVE MORE BLANK SPACE THAN IT DRAWS IN.
//
// ── WHAT A PHONE READER SAW, MEASURED ON PRODUCTION ─────────────────────────
//
// `https://www.bainluck.com/calibration` at 390px, master `e6a68fad`, read off
// the layout engine and not off pixels — `getBoundingClientRect()` for the box
// the page reserved, `getBBox() x getScreenCTM()` for where the drawing lands:
//
//   chart                              box reserved   drawing        band/side
//   "Does a price that moves…" 700x400   324 x 400     324 x 185.1    107.4px
//   "By Category"              700x340   324 x 340     324 x 157.4     91.3px
//   "By Source" x7        330x260/300x230 298/272 …    298 x 234.8  10.7-12.6px
//
// 215px of blank around a 185px drawing, and 183px around a 157px one. The
// seven By Source charts are nearly square, so they letterbox by ~11px and look
// fine — this was never a component-wide look, it was the two call sites that
// pass a WIDE, SHORT box.
//
// ── THE MECHANISM, AND IT IS ONE MISSING PROPERTY ───────────────────────────
//
//     <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}
//          style={{ …, maxWidth: "100%" }}>
//
// `height` is a PRESENTATION ATTRIBUTE, so it sets the CSS height — 340px — and
// nothing overrode it. `maxWidth` shrank only the WIDTH, to 324px.
// `preserveAspectRatio` then defaults to `xMidYMid meet`, fits the 700-unit
// viewBox into 324px, draws 157px tall, and CENTRES that in the 340px box it
// was still given. The two transparent bands are the remainder.
//
// ── WHY THE ASSERTIONS BELOW ARE A PAIRING AND NOT ONE LINE ─────────────────
//
// `height: "auto"` only produces the right height because the browser derives
// an intrinsic aspect ratio from `width` + `height` + `viewBox`. Delete any one
// of those three and `auto` has nothing to compute from — the fix and the three
// attributes it stands on are one unit, so they are pinned as one unit. And
// `maxWidth` is pinned in the same breath because dropping IT would also drive
// the band to zero (a box that never shrinks never letterboxes) while handing
// the reader a 700px chart overflowing a 350px card. A guard that only asked
// "is the band gone" would grade that mutant a pass.
//
// The counterfactual behind all of this was measured, not argued: injecting
// `svg[viewBox]{height:auto}` into the live page took every band to 0px with
// `drawn` byte-identical in both arms (324x157.4 stayed 324x157.4 — the chart
// is not shrunk, only the dead space goes), and left all nine charts identical
// at 1280px, where the max-width never binds. Probe, both arms:
// `tools/chart-letterbox-1067.mjs <url> [width]`, `FIX=1` for the fixed arm.
//
// jsdom is not in this suite (`testEnvironment: 'node'`) and would not help if
// it were: it has no layout engine, so no test in this repo can observe a band.
// What a test CAN observe is the markup the browser is handed, so that is what
// these assert, and the production probe is what closes the loop.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import CalibrationChart from "../components/CalibrationChart";

/** The two call sites on /calibration whose box is wide and short — the ones
 *  that letterboxed. Sizes read from `app/calibration/page.tsx`, and the drawn
 *  heights from the production probe, so the two cannot drift apart silently. */
const WIDE_AND_SHORT: ReadonlyArray<readonly [string, number, number, number]> = [
  // label,                              width, height, drawn height at a 324px container
  ["By Category", 700, 340, 157.4],
  ["Does a price that moves predict better?", 700, 400, 185.1],
] as const;

const CONTAINER_PX = 324; // the real inner width of a /calibration card at 390px

// #4394 wrapped the svg in a measuring <div> (a ResizeObserver needs a box that is NOT the
// element it resizes, or re-authoring the svg's width feeds back into its own measurement), so
// the svg is no longer the first tag in the markup. Everything below is about the svg itself and
// is unchanged; only the way it is located moved.
const svgTag = (markup: string): string => {
  const m = markup.match(/<svg\b[^>]*>/);
  if (!m) throw new Error("no <svg> in the rendered markup");
  return m[0];
};

const render = (width: number, height: number): string =>
  svgTag(renderToStaticMarkup(<CalibrationChart series={[]} width={width} height={height} />));

describe("#4330 — the svg scales its height with its width", () => {
  test("the root svg carries height:auto", () => {
    // The whole ship. Without it the presentation attribute wins and the box
    // stays 340px tall around a 157px drawing.
    expect(render(700, 340)).toMatch(/style="[^"]*height:\s*auto/);
  });

  test("height:auto is exactly auto, never a second fixed height", () => {
    // A "fix" that swaps 340px for some other px is the same defect at a
    // different size, and would pass a bare `toContain("height")`.
    const style = render(700, 340).match(/style="([^"]*)"/)?.[1] ?? "";
    const declared = [...style.matchAll(/(?:^|;)\s*height\s*:\s*([^;]+)/g)].map(m => m[1].trim());
    expect(declared).toEqual(["auto"]);
  });

  test("max-width:100% survives alongside it", () => {
    // Dropping max-width ALSO takes the band to zero — by never shrinking the
    // box — while overflowing a 350px card with a 700px chart. The pair is the
    // fix; either half alone is a different bug.
    expect(render(700, 340)).toMatch(/style="[^"]*max-width:\s*100%/);
  });

  // One test per ATTRIBUTE rather than one per call site: all three are load
  // bearing for the fix even though none of them changed in it, and asserting
  // them together makes "the width attribute went" and "the height attribute
  // went" the same red. Split, the failing test NAMES the missing attribute.
  test.each(
    WIDE_AND_SHORT.flatMap(([label, width, height]) =>
      (["width", "height", "viewBox"] as const).map(attr => [label, attr, width, height] as const)
    )
  )(
    "%s keeps its %s — height:auto has nothing to compute from without it",
    (_label, attr, width, height) => {
      const expected = attr === "viewBox" ? `0 0 ${width} ${height}` : String(attr === "width" ? width : height);
      expect(render(width, height)).toContain(`${attr}="${expected}"`);
    }
  );

  test.each(WIDE_AND_SHORT)(
    "%s: the viewBox predicts the height the SERVER render draws at 324px",
    (_label, width, height, measuredDrawnH) => {
      // Ties the guard to the live measurement. The browser scales the viewBox
      // to the container width, so the rendered height is C x H/W — and if
      // someone changes the viewBox formula, this stops agreeing with the
      // number in #4330 instead of failing silently somewhere else.
      //
      // #4394 AMENDMENT — WHAT THIS NUMBER NOW DESCRIBES. 157.4 and 185.1 were
      // measured on production BEFORE #4394. They are still exactly what the
      // markup below produces, and still what a reader with no JS sees, but they
      // are no longer what production measures at 390px: once the ResizeObserver
      // fires, these two call sites re-author to a square 324x324 box drawn at
      // 1:1. The post-fix production table lives with its own guard, in
      // `__tests__/components/calibrationChartLegibleOnAPhone4394.test.tsx`.
      // Left here rather than deleted because the SERVER render is precisely
      // what this file is about, and a number with no stated as-of is the thing
      // that goes stale silently.
      const vb = render(width, height).match(/viewBox="0 0 (\d+) (\d+)"/);
      expect(vb).not.toBeNull();
      const [vbW, vbH] = [Number(vb![1]), Number(vb![2])];
      expect(CONTAINER_PX * (vbH / vbW)).toBeCloseTo(measuredDrawnH, 0);
    }
  );

  test("a near-square By Source box is left alone by all of this", () => {
    // The seven By Source charts were never the defect (band ~11px) and the fix
    // must not be written in a way that only holds for 700-wide boxes.
    const tag = render(330, 260);
    expect(tag).toMatch(/style="[^"]*height:\s*auto/);
    expect(tag).toContain('viewBox="0 0 330 260"');
  });
});
