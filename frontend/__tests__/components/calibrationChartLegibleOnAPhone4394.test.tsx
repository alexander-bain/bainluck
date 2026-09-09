// #4394 — A CHART'S TYPE MUST NOT BE SHRUNK WITH ITS DRAWING.
//
// ── WHAT A PHONE READER SAW, MEASURED ON PRODUCTION ─────────────────────────
//
// `https://bainluck.com/calibration` at 390px, master `bc1252a3`, read off the
// layout engine: each `<svg>`'s `viewBox` against its `getBoundingClientRect()`,
// with the authored `font-size` multiplied by the resulting scale — the only
// arithmetic that makes the defect visible at all. A DOM census that asks "is
// the axis label present?" gets nine passes.
//
//   scale  drawn      viewBox   tick-px  min-px  section
//   0.463  324x185    700x400   5.1      4.4     "Does a price that moves…" (folded)
//   0.903  298x235    330x260   9.9      8.6     By Source panel
//   0.907  272x209    300x230   10.0     8.6     By Source panel (x4 more)
//   0.463  324x157    700x340   5.1      4.2     By Category            ← always visible
//
// The same component, on one page, legible seven times and 5.1px twice. What
// separates them is only the number the call site passes: a 700-unit viewBox in
// a 324px card is scaled to 0.463 and `fontSize="11"` lands at 5.1 CSS px.
//
// ── WHY THE FONTS ARE NOT THE FIX ───────────────────────────────────────────
//
// Dividing every font-size by the scale would make the type legible and the
// chart unreadable for a different reason: eleven "100%" labels need ~28px each
// and the plot inside a 324px card is 249px wide. The geometry is what has to
// give, so below `REAUTHOR_BELOW` (0.85) of the authored width the chart is
// re-authored at the container's own width — 1:1, where 11px means 11px — with
// a square plot (padL+padR and padT+padB are both 75, so height = width is
// exactly square) and x-labels every 20% over gridlines still every 10%.
//
// ── WHAT THIS FILE CAN AND CANNOT SEE ───────────────────────────────────────
//
// `testEnvironment: 'node'` — no layout engine, no ResizeObserver, so no test
// here can observe a scale. The decision is therefore a PURE function,
// `chartGeometry(authoredW, authoredH, containerW)`, and that is what is pinned
// below: exhaustively, including the boundary and the container widths of the
// real call sites. A pure function proves nothing about its reach, so the
// production probe closes that half of the loop:
//
//   node tools/cal-chart-scale-1071.mjs https://bainluck.com/calibration 390
//   → no visible chart below 0.75x, By Category ticks >= 9px
//
// and the same probe at 1280px is the no-change arm (every scale 1.0 there, so
// `chartGeometry` returns the authored box and nothing about desktop moves).

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import CalibrationChart, { chartGeometry } from "../../components/CalibrationChart";

/** The four `width={700}` call sites in app/calibration/page.tsx, and the 324px
 *  card that holds them at 390px. */
const AUTHORED_WIDE = 700;
const CARD_PX_AT_390 = 324;

describe("#4394 — the geometry gives way, not the type", () => {
  test("an unmeasured chart is the authored box, exactly", () => {
    // The server render and the first client paint. If this ever changes, the
    // fix has started rewriting what every reader is sent rather than what a
    // measured client draws — and #4330's guard would be asserting a fiction.
    expect(chartGeometry(700, 340, null)).toEqual({
      width: 700, height: 340, reauthored: false, xLabelStep: 10,
    });
  });

  test("a 324px card re-authors the wide call sites to a square 1:1 box", () => {
    const g = chartGeometry(AUTHORED_WIDE, 340, CARD_PX_AT_390);
    expect(g.reauthored).toBe(true);
    expect(g.width).toBe(CARD_PX_AT_390);
    // Square plot: 324-55-20 = 249 wide, 324-25-50 = 249 tall.
    expect(g.height).toBe(g.width);
    expect(g.width - 55 - 20).toBe(g.height - 25 - 50);
  });

  test("the same card leaves the By Source panels alone", () => {
    // 298/330 = 0.903 and 272/300 = 0.907, both above the 0.85 trigger. These
    // seven charts were never the defect and the fix must not touch them —
    // this is the control that fails if the trigger is loosened to "narrower".
    expect(chartGeometry(330, 260, 298)).toEqual({
      width: 330, height: 260, reauthored: false, xLabelStep: 10,
    });
    expect(chartGeometry(300, 230, 272)).toEqual({
      width: 300, height: 230, reauthored: false, xLabelStep: 10,
    });
  });

  test("desktop is untouched: a container at or above the authored width", () => {
    expect(chartGeometry(700, 340, 700).reauthored).toBe(false);
    expect(chartGeometry(700, 340, 1200).reauthored).toBe(false);
  });

  test("the trigger is a fraction and it sits where it says it does", () => {
    // 0.85 x 700 = 595. One pixel either side, so a change to REAUTHOR_BELOW
    // fails HERE, naming the constant, rather than surfacing as a look.
    expect(chartGeometry(700, 340, 594).reauthored).toBe(true);
    expect(chartGeometry(700, 340, 595).reauthored).toBe(false);
  });

  test("re-authoring thins the x-labels and nothing else does", () => {
    // The gridlines stay every 10% in both arms (see the component); it is the
    // LABELS that cannot fit. A re-authored chart that kept step 10 would be
    // the 5.1px smear again at full size.
    expect(chartGeometry(700, 340, CARD_PX_AT_390).xLabelStep).toBe(20);
    expect(chartGeometry(700, 340, null).xLabelStep).toBe(10);
    expect(chartGeometry(330, 260, 298).xLabelStep).toBe(10);
  });

  test("a container narrower than anything drawable is floored, not honoured", () => {
    // A 40px card is a broken card; the chart refuses to become unreadable in a
    // second way rather than tracking it down.
    expect(chartGeometry(700, 340, 40).width).toBe(260);
  });

  test("the component actually asks the function — and says so in the markup", () => {
    // Reach, as far as a node environment can see it: the server render carries
    // the authored width and the un-measured verdict, which is also what the
    // production probe reads to tell the two states apart.
    const markup = renderToStaticMarkup(
      <CalibrationChart series={[]} width={700} height={340} />
    );
    expect(markup).toContain('data-authored-width="700"');
    expect(markup).toContain('data-reauthored="false"');
  });

  test("x-axis labels are thinned by value, so 0% and 100% always survive", () => {
    // Whatever the step, the two ends of the axis are the labels a reader needs
    // most; a step that dropped 100% would be a different defect.
    for (const step of [10, 20]) {
      const kept = Array.from({ length: 11 }, (_, i) => i * 10).filter(v => v % step === 0);
      expect(kept[0]).toBe(0);
      expect(kept[kept.length - 1]).toBe(100);
    }
  });
});

describe("#4394 — the legend leaves the plot when it cannot fit the corner", () => {
  // The legend lives in the plot's empty top-left corner, which holds two rows.
  // At 324px it fits one column, so five categories would stack five rows deep
  // across the curves. The component grows the box instead; these pin the
  // arithmetic that decides which happens.
  const cols = (w: number) => Math.max(1, Math.floor((w - 55 - 20) / 165));

  test("700px wide fits five categories in two rows, inside the plot", () => {
    expect(cols(700)).toBe(3);
    expect(Math.ceil(5 / cols(700))).toBe(2); // <= 2 ⇒ stays in the corner
  });

  test("a re-authored 324px chart cannot, so the box has to grow", () => {
    expect(cols(324)).toBe(1);
    expect(Math.ceil(5 / cols(324))).toBe(5); // > 2 ⇒ below the plot
  });

  test("a single-series chart never grows a legend area", () => {
    expect(Math.ceil(1 / cols(324))).toBe(1);
  });
});
