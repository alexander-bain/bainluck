// #3035 — a phone-width title-race chart must rest on TODAY, not on last week.
//
// Two arms, because the bug had two halves and a fix for either one alone still
// leaves a reader stuck:
//
//   A. the arithmetic (`lib/chartScroll.ts`) — where the plot rests and which
//      edges still hide plot;
//   B. the wiring (`components/FuturesChart.tsx`) — that the component actually
//      calls A and renders a fade for each edge.
//
// Arm B is a source scan because this repo's jest environment is `node` with no
// DOM and no @testing-library/react, so the effect that anchors the scroll can
// never run in-test. The scan is comment-stripped before matching: the fix's own
// comments quote the very strings being searched for (`min-w-[600px]`,
// `overflow-x-auto`, `scrollLeft`), and an un-stripped scan reads its own prose
// as code and passes on a component that renders none of it.
import { readFileSync } from "fs";
import { join } from "path";
import {
  anchorScrollLeft,
  edgeOverflowFor,
  EDGE_TOLERANCE_PX,
} from "../../lib/chartScroll";

// A 390px phone viewport showing a 600px-minimum plot: the geometry from the
// issue, where ~35% of the plot is outside the window.
const PHONE = { scrollWidth: 600, clientWidth: 390 };
const PHONE_MAX = 210;

describe("#3035 arm A — the resting offset is the RIGHT edge", () => {
  test("a plot wider than its window rests on now, not on the oldest data", () => {
    const rest = anchorScrollLeft(PHONE);
    expect(rest).toBe(PHONE_MAX);
    // The bug was scrollLeft = 0. Name it, so a regression to the browser's
    // default resting position cannot pass this test.
    expect(rest).not.toBe(0);
  });

  test("a desktop-width plot that does not overflow is left alone", () => {
    expect(anchorScrollLeft({ scrollWidth: 600, clientWidth: 1280 })).toBe(0);
  });

  test("never returns a negative offset", () => {
    expect(anchorScrollLeft({ scrollWidth: 100, clientWidth: 900 })).toBe(0);
  });
});

describe("#3035 arm A — fades mark only edges that still hide plot", () => {
  test("resting at the right edge: history is hidden left, nothing hidden right", () => {
    expect(edgeOverflowFor({ ...PHONE, scrollLeft: PHONE_MAX })).toEqual({
      left: true,
      right: false,
    });
  });

  test("scrolled hard left: nothing hidden left, the live end is hidden right", () => {
    expect(edgeOverflowFor({ ...PHONE, scrollLeft: 0 })).toEqual({
      left: false,
      right: true,
    });
  });

  test("mid-scroll: both edges hide plot, so both fades draw", () => {
    expect(edgeOverflowFor({ ...PHONE, scrollLeft: 100 })).toEqual({
      left: true,
      right: true,
    });
  });

  test("a chart that does not overflow draws no chrome at all", () => {
    expect(
      edgeOverflowFor({ scrollWidth: 600, clientWidth: 1280, scrollLeft: 0 }),
    ).toEqual({ left: false, right: false });
  });

  test("sub-pixel slack at either edge does not strand a fade", () => {
    // Fractional layout widths land scrollLeft a hair off a true edge. The 0.5px
    // offsets are deliberately LITERAL, not derived from EDGE_TOLERANCE_PX: a
    // test that computes its input from the constant it is checking moves with
    // that constant and survives its removal (measured — it did).
    expect(edgeOverflowFor({ ...PHONE, scrollLeft: PHONE_MAX - 0.5 }).right).toBe(
      false,
    );
    expect(edgeOverflowFor({ ...PHONE, scrollLeft: 0.5 }).left).toBe(false);
    // ...and the tolerance is genuinely sub-pixel, not a slab that would swallow
    // a real scroll offset.
    expect(EDGE_TOLERANCE_PX).toBeLessThanOrEqual(1);
    expect(edgeOverflowFor({ ...PHONE, scrollLeft: 5 }).left).toBe(true);
  });
});

describe("#3035 arm B — FuturesChart actually wires the anchor and the fades", () => {
  // Strip block and line comments so the scan reads only what renders. Without
  // this the fix's own explanatory comments satisfy every assertion below.
  const CODE = readFileSync(
    join(__dirname, "../../components/FuturesChart.tsx"),
    "utf8",
  )
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");

  test("the scroll container is measured and its scroll is anchored", () => {
    expect(CODE).toContain("ref={scrollRef}");
    expect(CODE).toContain("anchorScrollLeft(el)");
    // The offset must be assigned, not merely computed and dropped.
    expect(CODE).toMatch(/el\.scrollLeft\s*=\s*anchorScrollLeft\(el\)/);
  });

  test("the fade state is recomputed on scroll, not frozen at mount", () => {
    expect(CODE).toContain("onScroll=");
    expect(CODE).toContain("edgeOverflowFor(el)");
  });

  test("both edges have a fade, and neither can swallow a chart interaction", () => {
    expect(CODE).toContain("futures-chart-fade-left");
    expect(CODE).toContain("futures-chart-fade-right");
    const fades = CODE.split("\n").filter((l) =>
      l.includes("futures-chart-fade-"),
    );
    expect(fades).toHaveLength(2);
    // Each fade renders inside a block that is pointer-events-none and hidden
    // from the accessibility tree — it marks plot, it is not a control.
    //
    // #3599 amendment: this used to assert the whole file contained exactly two
    // `pointer-events-none absolute inset-y-0` blocks, which read as "there are
    // two fades" but actually said "there are two pinned overlays of any kind".
    // The pinned y-axis is a legitimate third, so the count is now scoped to
    // the fades themselves — which is what the test was always about.
    const fadeBlocks = fades.filter((l) => l.includes("futures-chart-fade-"));
    expect(fadeBlocks).toHaveLength(2);
    expect(CODE.match(/pointer-events-none absolute inset-y-0/g)).toHaveLength(2);
    expect(CODE.match(/aria-hidden="true"/g)?.length).toBeGreaterThanOrEqual(2);
  });

  test("#3599 — the y-axis is pinned outside the scroller, not drawn inside it", () => {
    // The regression this guards: the axis labels were `<text>` inside the
    // scrolled SVG, so anchoring the scroll to the right (the whole point of
    // #3035) carried them out of view and left five unlabelled gridlines.
    expect(CODE).toContain("futures-chart-y-axis");

    const scroller = CODE.indexOf('className={mini ? "" : "overflow-x-auto relative"}');
    const wrapper = CODE.indexOf('className={mini ? "" : "relative"}');
    const axis = CODE.indexOf("futures-chart-y-axis");
    expect(wrapper).toBeLessThan(scroller);
    // Same rule as the fades: it must be a SIBLING of the scroller. If it ever
    // moves inside, it scrolls away again and this goes red.
    expect(axis).toBeGreaterThan(scroller);
    const scrollerClose = CODE.indexOf("</div>", CODE.indexOf("Hover tooltip"));
    expect(scrollerClose).toBeLessThan(axis);

    // Positioned as a FRACTION of the wrapper. A px offset would drift, because
    // the SVG's render scale changes with the viewport (`w-full min-w-[600px]`
    // against a viewBox 800 wide).
    expect(CODE).toMatch(/yScale\(maxProb \* pct\) \/ effectiveHeight\) \* 100/);

    // And it does not swallow a hover meant for the chart. Asserted against the
    // gutter's OWN class string, not a window around it: a ±400-char slice here
    // reaches the right fade's `pointer-events-none` and passed even with the
    // gutter's removed — the mutant survived until this line was tightened.
    expect(CODE).toContain(
      'className="pointer-events-none absolute bottom-0 left-0 top-0 z-20"',
    );
  });

  test("#3599 — a full chart draws its y labels exactly once", () => {
    // Both renderers exist (mini keeps the in-SVG text, which has no scroll
    // container to escape), so the risk is that a full chart draws BOTH and
    // prints every percentage twice, offset by the scroll.
    const svgLabel = CODE.indexOf("textAnchor=\"end\"");
    expect(svgLabel).toBeGreaterThan(-1);
    // The in-SVG label is gated on `mini`; the pinned gutter is gated on
    // `!mini`. Neither gate may be dropped.
    expect(CODE.slice(svgLabel - 200, svgLabel)).toContain("{mini && (");
    expect(CODE).toContain("{!mini && effectiveShowAxes && (");
  });

  test("the fades sit outside the scrolling element, or they scroll away with it", () => {
    // An absolutely positioned child of an overflow container travels with the
    // container's content. The fades must be siblings of the scroller, anchored
    // to a wrapper that does not scroll.
    const scroller = CODE.indexOf('className={mini ? "" : "overflow-x-auto relative"}');
    const wrapper = CODE.indexOf('className={mini ? "" : "relative"}');
    const firstFade = CODE.indexOf("futures-chart-fade-left");
    expect(wrapper).toBeGreaterThan(-1);
    expect(scroller).toBeGreaterThan(-1);
    expect(wrapper).toBeLessThan(scroller);
    // The closing </div> of the scroller precedes the fades.
    expect(firstFade).toBeGreaterThan(scroller);
    const scrollerClose = CODE.indexOf("</div>", CODE.indexOf("Hover tooltip"));
    expect(scrollerClose).toBeLessThan(firstFade);
  });

  test("sparklines keep their old chrome-free layout", () => {
    // Every new affordance is gated on !mini; a mini chart has no scroll
    // container to anchor and no room for a fade.
    expect(CODE).toContain("{!mini && edgeOverflow.left &&");
    expect(CODE).toContain("{!mini && edgeOverflow.right &&");
    expect(CODE).toMatch(/if \(mini \|\| !el\) return;/);
  });
});
