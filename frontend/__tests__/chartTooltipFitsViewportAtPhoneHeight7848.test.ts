// #7848 — THE WIN-PROBABILITY TOOLTIP RAN OFF THE BOTTOM OF THE PHONE SCREEN.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// `bainluck.com/events/14780544` (Chiefs v Colts), 390px, the INLINE chart. Touch
// the chart and the tooltip card extends past the bottom of the display: the last
// source rows are not on screen, the card running down behind the nav with "Bain
// Luck Model" as the last thing readable.
//
// Measured against production with `tools/chart-tooltip-clip-1833.mjs`, which
// reads the painted card against the viewport, on 2026-09-21 AFTER #1833 went
// live — so this is not that fix's doing and narrowing the card did not touch it:
//
//     surface       card h     top -> bottom   vh    positions off the bottom
//     inline        303-477    438 -> 923      844   4 of 5   (worst 79px)
//     fullscreen    424-444    117 -> 561      844   0 of 5
//
// Same card, same content, same width on both surfaces. The difference is only
// WHERE it is anchored, which is what makes this a placement defect and not a
// content one.
//
// ── THE CAUSE ────────────────────────────────────────────────────────────────
//
// `recharts/util/tooltip/translate.js` clamps the card into the CHART's viewBox.
// A 444px card in a ~300px plot always takes the overflow branch and always
// resolves to `Math.max(negative, viewBox.y)` = `viewBox.y`, the plot's top. That
// is why the measured top is a constant ~447 while the height varies 303 -> 477,
// and why the bottom lands at 891 and 923 on an 844px screen. The clamp works; it
// is clamping to a box that is not what the reader can see.
//
// ── WHY THIS GUARD IS OVER THE ARITHMETIC ────────────────────────────────────
//
// jsdom does not lay out: every `getBoundingClientRect()` is zeros, so a render
// test reports this card as fine both before and after the fix — a test that
// passes on the broken code is worse than none (the same reason #1833's guard is
// a source scan). So the placement RULE is a pure function and this exercises it
// on the real measured specimens above, plus the properties the layout effect
// depends on. The layout claim itself is carried by the probe, run against
// production before the fix with `VERTICAL=1` and returning exit 1.
//
// The fixtures below are production reads, not invented numbers. Each `natural*`
// pair is a row of the table above.

import { readFileSync } from "fs";
import { join } from "path";
import {
  chartTooltipViewportShift,
  CHART_TOOLTIP_VIEWPORT_MARGIN_PX as MARGIN,
  VIEWPORT_BOTTOM_OBSTRUCTION_ATTR,
} from "@/lib/chartTooltipViewportFit";

const VH = 844; // iPhone 14/15 viewport height, the width the probe shoots at.
/** Measured top of the mobile BottomNav at 390x844: `fixed bottom-0`, 57px tall. */
const NAV_TOP = 787;

/** An unshifted card: what recharts placed, before any correction. */
const natural = (top: number, height: number) => ({
  rectTop: top,
  rectBottom: top + height,
  appliedShift: 0,
  viewportHeight: VH,
});

describe("#7848 the tooltip card is lifted onto the viewport", () => {
  // ── the four production positions that were off the bottom ────────────────
  // frac / top / height / measured bottom, from BEFORE-prod-390.json.
  const CLIPPED_SPECIMENS: Array<[string, number, number, number]> = [
    ["frac 0.35, scoring play, 5 sources", 446, 477, 923],
    ["frac 0.50, halftime", 447, 444, 891],
    ["frac 0.65, end of 3rd", 447, 444, 891],
    ["frac 0.85, overtime", 447, 444, 891],
  ];

  it.each(CLIPPED_SPECIMENS)(
    "%s: is moved up until its bottom sits on the margin",
    (_label, top, height, measuredBottom) => {
      // the fixture agrees with what the probe read, so a typo cannot pass
      expect(top + height).toBe(measuredBottom);
      expect(measuredBottom).toBeGreaterThan(VH); // it really was off-screen

      const shift = chartTooltipViewportShift(natural(top, height));

      expect(shift).toBeGreaterThan(0);
      expect(top + height - shift).toBe(VH - MARGIN); // bottom lands on the margin
      expect(top - shift).toBeGreaterThanOrEqual(MARGIN); // and the top stays on
    }
  );

  it("moves the worst specimen by the 79px the probe measured, plus the margin", () => {
    // 923 - 844 = 79 off the bottom; the card also has to clear the 8px margin.
    expect(chartTooltipViewportShift(natural(446, 477))).toBe(79 + MARGIN);
  });

  // ── the surfaces that were already fine must not move ─────────────────────
  it("leaves the fullscreen modal exactly where it was", () => {
    // 390px fullscreen sample: 278x444 at top=117 -> bottom=561, 0 of 5 clipped.
    expect(chartTooltipViewportShift(natural(117, 444))).toBe(0);
  });

  it("leaves a card that ends exactly on the margin alone", () => {
    expect(chartTooltipViewportShift(natural(VH - MARGIN - 300, 300))).toBe(0);
  });

  it("leaves the short first-position card alone", () => {
    // frac 0.15: 303px at top=438 -> bottom=741, comfortably inside.
    expect(chartTooltipViewportShift(natural(438, 303))).toBe(0);
  });

  it("leaves a desktop-height viewport alone", () => {
    expect(
      chartTooltipViewportShift({ ...natural(447, 477), viewportHeight: 1080 })
    ).toBe(0);
  });

  // ── the property the layout effect depends on ─────────────────────────────
  //
  // The effect measures the card WHERE IT IS, so it feeds its own answer back in.
  // If that were not a fixed point the card would creep up the screen on every
  // mouse move until it left the top.
  it.each(CLIPPED_SPECIMENS)(
    "%s: re-measuring the corrected card returns the same answer",
    (_label, top, height) => {
      const first = chartTooltipViewportShift(natural(top, height));
      const second = chartTooltipViewportShift({
        rectTop: top - first, // where the card now IS
        rectBottom: top + height - first,
        appliedShift: first, // ...and what we already applied
        viewportHeight: VH,
      });
      expect(second).toBe(first);

      // and a third pass, in case the fixed point is only reached once
      expect(
        chartTooltipViewportShift({
          rectTop: top - second,
          rectBottom: top + height - second,
          appliedShift: second,
          viewportHeight: VH,
        })
      ).toBe(second);
    }
  );

  it("does not re-correct a card that is only on screen BECAUSE of the shift", () => {
    // Without adding the applied shift back, this reads as "fits, shift 0" and
    // the card would snap back down to where it was clipped.
    const naturalTop = 446;
    const height = 477;
    const applied = 87;
    expect(
      chartTooltipViewportShift({
        rectTop: naturalTop - applied,
        rectBottom: naturalTop + height - applied,
        appliedShift: applied,
        viewportHeight: VH,
      })
    ).toBe(applied);
  });

  // ── the honest degradation ────────────────────────────────────────────────
  it("never lifts the top of the card off the screen", () => {
    // A card taller than the viewport cannot fit. It is moved as far as the
    // headroom allows and no further, so the score/period/blend at the TOP stay
    // readable and the per-source tail is what is lost.
    const top = 200;
    const height = 900; // > 844
    const shift = chartTooltipViewportShift(natural(top, height));
    expect(shift).toBe(top - MARGIN);
    expect(top - shift).toBe(MARGIN);
    expect(shift).toBeLessThan(top + height - (VH - MARGIN)); // still overflows
  });

  it("does not move a card that already starts above the margin", () => {
    expect(chartTooltipViewportShift(natural(MARGIN, 1200))).toBe(0);
    expect(chartTooltipViewportShift(natural(-40, 1200))).toBe(0);
  });

  // ── the nav bar is painted OVER the page, so vh is not the readable bottom ──
  //
  // The first cut of this fix bounded at `window.innerHeight`, the probe scored
  // it 0 of 5, and the screenshot still showed the ESPN row hidden behind the
  // nav. These arms are that mistake, pinned.
  describe("the mobile nav bar counts as the bottom of the readable area", () => {
    const withNav = (top: number, height: number) => ({
      ...natural(top, height),
      bottomObstructionTop: NAV_TOP,
    });

    it.each(CLIPPED_SPECIMENS)(
      "%s: stops above the nav bar, not above the viewport edge",
      (_label, top, height) => {
        const shift = chartTooltipViewportShift(withNav(top, height));
        expect(top + height - shift).toBe(NAV_TOP - MARGIN);
        expect(top - shift).toBeGreaterThanOrEqual(MARGIN);
      }
    );

    it("moves the card 57px further than the viewport-only bound would", () => {
      const viewportOnly = chartTooltipViewportShift(natural(447, 444));
      const readable = chartTooltipViewportShift(withNav(447, 444));
      expect(readable - viewportOnly).toBe(VH - NAV_TOP); // the nav's own height
    });

    it("catches a card that clears the viewport but hides behind the nav", () => {
      // exactly the state the first cut shipped: bottom 836 on an 844px screen
      const top = 836 - 444;
      expect(chartTooltipViewportShift(natural(top, 444))).toBe(0); // "clean"
      expect(chartTooltipViewportShift(withNav(top, 444))).toBeGreaterThan(0);
    });

    it("ignores an obstruction that is not on screen", () => {
      // `md:hidden` => display:none => a zero-height rect at the origin. Treating
      // its `top` of 0 as a bound would clamp every desktop tooltip to nothing.
      for (const absent of [null, undefined, 0, -12]) {
        expect(
          chartTooltipViewportShift({
            ...natural(117, 444),
            bottomObstructionTop: absent as number | null,
          })
        ).toBe(0);
      }
    });

    it("stays idempotent with the nav in play", () => {
      const first = chartTooltipViewportShift(withNav(446, 477));
      expect(
        chartTooltipViewportShift({
          rectTop: 446 - first,
          rectBottom: 446 + 477 - first,
          appliedShift: first,
          viewportHeight: VH,
          bottomObstructionTop: NAV_TOP,
        })
      ).toBe(first);
    });
  });

  it("never returns a negative shift, on any of the specimens", () => {
    for (const [, top, height] of CLIPPED_SPECIMENS) {
      expect(chartTooltipViewportShift(natural(top, height))).toBeGreaterThan(0);
    }
    for (let top = -100; top <= 900; top += 37) {
      for (const height of [0, 40, 303, 444, 477, 900, 2000]) {
        expect(
          chartTooltipViewportShift(natural(top, height))
        ).toBeGreaterThanOrEqual(0);
      }
    }
  });
});

// ── the call site actually routes through the rule ───────────────────────────
//
// The arithmetic above is worth nothing if the card does not use it. jsdom cannot
// show that either, so read the source — the same channel #1833's guard uses. The
// POSITIVE CONTROL is that these assertions fail on the shipped markup: the card
// root was a bare `<div className="bg-surface-card ...">` before this change.
describe("#7848 the card root is the fitted wrapper, not a bare div", () => {
  const source = readFileSync(
    join(__dirname, "..", "components", "OddsChart.tsx"),
    "utf8"
  );

  it("routes the win-probability tooltip card through ViewportFittedTooltipCard", () => {
    // the card is identified by the width cap #1833 put on it, so this cannot
    // drift onto some other div
    const cardRoot = source.match(
      /<(\w+)([^>]*?)className="bg-surface-card p-3 rounded-lg shadow-lg border border-surface-border max-w-\[min\(24rem,calc\(100vw_-_7rem\)\)\]"/
    );
    expect(cardRoot).not.toBeNull();
    expect(cardRoot![1]).toBe("ViewportFittedTooltipCard");
  });

  it("closes that element as the wrapper too", () => {
    expect(source).toContain("</ViewportFittedTooltipCard>");
    // exactly one card, so a future second copy has to come here and think
    expect(source.match(/<ViewportFittedTooltipCard\b/g)).toHaveLength(1);
  });

  it("defines the wrapper at module scope so its hook keeps its state", () => {
    // `CustomTooltip` is re-created on every chart render; a hook owned by it
    // would get a new component identity each time and reset the shift. Module
    // scope (no leading indentation) is what makes the shift survive.
    expect(source).toMatch(/^function ViewportFittedTooltipCard\(/m);
  });

  it("applies the shift as an upward transform driven by the shared rule", () => {
    const wrapper = source.slice(
      source.indexOf("function ViewportFittedTooltipCard("),
      source.indexOf("export default function OddsChart(")
    );
    expect(wrapper).toContain("chartTooltipViewportShift(");
    expect(wrapper).toContain("window.innerHeight");
    expect(wrapper).toContain("translateY(-${shift}px)");
    // useLayoutEffect, or the reader sees the card painted low for one frame
    expect(wrapper).toContain("useLayoutEffect(");
    expect(wrapper).not.toContain("useEffect(");
  });

  it("imports the rule rather than restating it", () => {
    expect(source).toContain("from \"@/lib/chartTooltipViewportFit\"");
    expect(source).toContain("chartTooltipViewportShift,");
  });

  it("feeds the bottom obstruction in, not just the viewport height", () => {
    const wrapper = source.slice(
      source.indexOf("function ViewportFittedTooltipCard("),
      source.indexOf("export default function OddsChart(")
    );
    expect(wrapper).toContain("VIEWPORT_BOTTOM_OBSTRUCTION_ATTR");
    expect(wrapper).toContain("bottomObstructionTop:");
    // a zero-height (display:none) rect must not be read as a bound at y=0
    expect(wrapper).toContain("obstruction?.height");
  });
});

// ── the OTHER half of the contract ───────────────────────────────────────────
//
// A consumer that queries a marker is half of an agreement; if nothing emits the
// marker the query returns null, the rule reads "nothing in the way", and the
// card goes back to hiding behind the nav — with every arm above still green,
// because they pass the obstruction in by hand. So assert the producer too.
describe("#7848 the mobile nav declares itself as a bottom obstruction", () => {
  const nav = readFileSync(
    join(__dirname, "..", "components", "BottomNav.tsx"),
    "utf8"
  );

  it("carries the attribute the tooltip looks for", () => {
    expect(nav).toContain(`${VIEWPORT_BOTTOM_OBSTRUCTION_ATTR}=""`);
  });

  it("puts it on the fixed bar itself, not on an inner element", () => {
    const openTag = nav.slice(nav.indexOf("<nav"), nav.indexOf(">", nav.indexOf("data-viewport-bottom-obstruction")) + 1);
    expect(openTag).toContain("fixed bottom-0");
    expect(openTag).toContain(VIEWPORT_BOTTOM_OBSTRUCTION_ATTR);
  });

  it("is the only thing claiming to be one, so the query cannot pick the wrong node", () => {
    // `document.querySelector` takes the FIRST match; a second emitter would make
    // which bound applies depend on DOM order.
    const all = readFileSync(
      join(__dirname, "..", "components", "BottomNav.tsx"),
      "utf8"
    ).match(new RegExp(`${VIEWPORT_BOTTOM_OBSTRUCTION_ATTR}`, "g"));
    expect(all).toHaveLength(1);
  });
});
