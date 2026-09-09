/**
 * #4262 — EVERY TICK LABEL ON THE FUTURES CHART RENDERS WHOLE AT PHONE WIDTH.
 *
 * WHAT WAS ON THE PAGE, read off production 2026-09-09 ~05:40 PT at 390px
 * (`https://www.bainluck.com/categories/golf`, Amgen Irish Open win-probability
 * chart). The x-axis has five ticks and BOTH ends failed, for two DIFFERENT
 * reasons — which is why a guard against either one alone would have shipped
 * the other:
 *
 *   RIGHT  `Sep 8 9 AM` rendered `Sep 8 9 AI`. Not a paint bug: the label is
 *          centred on its tick at viewBox x=780 and measures ~51 units, so its
 *          box ran to **805.53 in a viewBox 800 wide**. The card is
 *          `overflow: hidden`, so the tail was cut off the element.
 *
 *   LEFT   `Sep 7 9 PM` rendered `ep 7 9 PM`, and this one was never clipped at
 *          all — its box starts at CSS x=41.47 against a scroller edge at 41.00,
 *          i.e. 0.47px INSIDE. It was **painted over**: the `0%` y-axis chip is
 *          opaque `bg-surface-card` at `z-20`, was centred on the plot floor, and
 *          so hung half of itself into the x-axis strip, covering CSS x 41.47→63.67
 *          and the top 3.19px of the tick's 8.19px box.
 *
 * Both are the bug class #3520 already fixed on the OTHER chart
 * (`ContenderChart`, guarded by `chartTextStaysInsideThePlot.test.tsx`): no
 * rendered text outside the plot bounds, and a label on a boundary rule anchored
 * rather than centred. `FuturesChart` never got the same treatment.
 *
 * ═══ WHY THIS MEASURES BOXES AND NOT JUST ATTRIBUTES ═══
 *
 * `textAnchor="end"` pins the last label's right edge to the plot rule BY
 * CONSTRUCTION, so the strongest assertion here is structural and cannot be
 * defeated by a font metric. But asserting only the attribute would go green if
 * a future change moved the tick's `x` past the plot — so the boxes are laid out
 * with a ruler too, and the ruler is deliberately WIDER than any label measured
 * on production (see `UNITS_PER_CHAR`) so it errs toward catching an overflow.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import { FuturesChart } from "../../components/FuturesChart";
import type { FuturesOutcomeHistory } from "../../lib/types";

const HOUR = 60 * 60 * 1000;
/** The production window: 36h, which is the `Sep 8 9 AM` format branch. */
const NOW = Date.UTC(2026, 8, 8, 16, 0, 0);

/** The chart's own geometry, from `FuturesChart` (non-mini). */
const VIEWBOX_W = 800;
const HEIGHT = 300;
const PAD = { top: 20, right: 20, bottom: 40, left: 50 };
const INNER_W = VIEWBOX_W - PAD.left - PAD.right; // 730
const PLOT_LEFT = PAD.left; // 50
const PLOT_RIGHT = PAD.left + INNER_W; // 780
const AXIS_LABEL_Y = PAD.top + (HEIGHT - PAD.top - PAD.bottom) + 16; // 276

/**
 * Ruler for the 9px tick font, in viewBox units per character.
 *
 * MEASURED on production via `getBBox()` on the live SVG text nodes:
 *   `Sep 7 9 AM` 50.44  ·  `Sep 7 3 PM` 50.00  ·  `Sep 8 3 AM` 50.96
 *   `Sep 8 9 AM` 51.06
 * Ten characters each, so 5.00–5.11 units/char. 5.2 is above every one of them
 * on purpose: a ruler that under-measures is how a bounds guard goes vacuous.
 */
const UNITS_PER_CHAR = 5.2;

beforeAll(() => {
  jest.useFakeTimers({ doNotFake: ["performance"] });
  jest.setSystemTime(NOW);
});
afterAll(() => {
  jest.useRealTimers();
});

/** A 36h hourly series — the shape the golf hub draws. */
function goldSeries(): FuturesOutcomeHistory[] {
  const count = 37;
  return [
    {
      outcome_id: 1,
      name: "Rory McIlroy",
      history: Array.from({ length: count }, (_, i) => ({
        timestamp: new Date(NOW - (count - 1 - i) * HOUR).toISOString(),
        probability: 0.05 + i * 0.002,
        american_odds: null,
        bookmaker: "blend",
      })),
    },
  ];
}

function render(): string {
  return renderToStaticMarkup(
    <FuturesChart
      historyData={goldSeries()}
      height={HEIGHT}
      showAxes
      showLegend={false}
      fixedYAxis
    />
  );
}

interface TickBox {
  label: string;
  anchor: string;
  x: number;
  left: number;
  right: number;
}

/** Every x-axis tick label, laid out into a box by its own anchor. */
function tickBoxes(html: string): TickBox[] {
  const out: TickBox[] = [];
  const re = /<text([^>]*)>([^<]*)<\/text>/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html)) !== null) {
    const attrs = m[1];
    const label = m[2].trim();
    const y = Number(/\by="([\d.]+)"/.exec(attrs)?.[1] ?? NaN);
    if (y !== AXIS_LABEL_Y) continue; // not the x-axis row
    const x = Number(/\bx="([\d.]+)"/.exec(attrs)?.[1] ?? NaN);
    const anchor = /text-anchor="(\w+)"/.exec(attrs)?.[1] ?? "";
    const w = label.length * UNITS_PER_CHAR;
    // THROW rather than guess: an unrecognised anchor must not silently
    // become a box that passes (the lesson in chartTextStaysInsideThePlot).
    let left: number;
    if (anchor === "middle") left = x - w / 2;
    else if (anchor === "start") left = x;
    else if (anchor === "end") left = x - w;
    else throw new Error(`unrecognised text-anchor "${anchor}" on tick "${label}"`);
    out.push({ label, anchor, x, left, right: left + w });
  }
  return out.sort((a, b) => a.x - b.x);
}

describe("#4262 — the futures chart's axis text stays inside the plot", () => {
  it("emits the x-axis ticks this guard is about", () => {
    // A bounds test over an empty set passes. Prove the specimen reaches the
    // axis and produces the production format before asserting anything.
    const boxes = tickBoxes(render());
    expect(boxes.length).toBeGreaterThanOrEqual(3);
    expect(boxes[boxes.length - 1].label).toMatch(/^[A-Z][a-z]{2} \d+ \d+ [AP]M$/);
  });

  it("keeps every tick label inside the viewBox — the `Sep 8 9 AI` defect", () => {
    for (const box of tickBoxes(render())) {
      const where = `${box.label} (anchor=${box.anchor}, x=${box.x})`;
      expect(`${where} left>=0: ${box.left >= 0}`).toBe(`${where} left>=0: true`);
      expect(`${where} right<=${VIEWBOX_W}: ${box.right <= VIEWBOX_W}`).toBe(
        `${where} right<=${VIEWBOX_W}: true`
      );
    }
  });

  it("anchors the END label to the plot's right rule, so no font metric can push it out", () => {
    const boxes = tickBoxes(render());
    const last = boxes[boxes.length - 1];
    expect(last.anchor).toBe("end");
    expect(last.x).toBe(PLOT_RIGHT);
    expect(last.right).toBe(PLOT_RIGHT); // exact, by construction — not by measurement
  });

  it("anchors the FIRST label to the plot's left rule, clear of the y-axis gutter", () => {
    // `padding.left` IS the gutter the opaque `0%` chip sits in. A centred first
    // label reaches back to x=24.78 — under the chip — which is the other half
    // of what the reader saw.
    const first = tickBoxes(render())[0];
    expect(first.anchor).toBe("start");
    expect(first.x).toBe(PLOT_LEFT);
    expect(first.left).toBeGreaterThanOrEqual(PLOT_LEFT);
  });

  it("lifts the `0%` chip's ink off the plot floor, and leaves the others centred", () => {
    // The left-hand defect was a paint, not a clip: the opaque chip covered the
    // tick's head. Anchoring it by its bottom is the #3520 rule.
    const html = render();
    const spans = [...html.matchAll(/<span([^>]*?data-testid="chart-y-label"[^>]*?)>([^<]*)</g)].map(
      (m) => ({
        anchor: /data-anchor="(\w+)"/.exec(m[1])?.[1],
        classes: /class="([^"]*)"/.exec(m[1])?.[1] ?? "",
        text: m[2].trim(),
      })
    );
    expect(spans.length).toBe(5);

    const floor = spans.find((s) => s.text === "0%");
    expect(floor?.anchor).toBe("bottom");
    expect(floor?.classes).toContain("-translate-y-full");
    expect(floor?.classes).not.toContain("-translate-y-1/2");

    // Two-directional (#2961's lesson): a chart where EVERY label moved has
    // swapped one defect for another, not fixed this one.
    for (const other of spans.filter((s) => s.text !== "0%")) {
      expect(`${other.text} anchor: ${other.anchor}`).toBe(`${other.text} anchor: centre`);
      expect(other.classes).toContain("-translate-y-1/2");
      expect(other.classes).not.toContain("-translate-y-full");
    }
  });
});
