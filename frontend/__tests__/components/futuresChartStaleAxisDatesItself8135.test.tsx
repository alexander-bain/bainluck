/**
 * #8135 — THE FUTURES CHART'S AXIS, ON THE REAL RENDERER.
 *
 * `lib/chartAxisTimeLabel`'s own guard proves the RULE. This one proves the
 * chart is wired to it, on the specimen that was photographed: `/futures/59520336`,
 * six observations on the afternoon of 24 August, read on production 2026-09-23
 * at 390px with an axis that said `1:48 PM · 4:03 PM · 6:19 PM` and no date.
 *
 * Three obligations, and the third is the one a label change owes:
 *
 *  1. the stale burst's ticks now name their day;
 *  2. a burst of the SAME SHAPE ending now still does not — the control, without
 *     which "every label has a date" would be satisfied by dating everything;
 *  3. the longer label still fits, measured with #4262's ruler. `Aug 24, 1:16 PM`
 *     is half again as wide as `1:16 PM`, and `Sep 8 9 AM` overflowing a viewBox
 *     800 wide by 5.53 units is exactly how that defect reached a reader.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import { FuturesChart } from "../../components/FuturesChart";
import type { FuturesOutcomeHistory } from "../../lib/types";

const HOUR = 60 * 60 * 1000;

/** 2026-09-23 14:20Z — when the defect was photographed. */
const NOW = Date.UTC(2026, 8, 23, 14, 20, 0);
/** The specimen's first observation: 2026-08-24 20:16:49Z. */
const BURST_START = Date.UTC(2026, 7, 24, 20, 16, 49);

/* The chart's own geometry (non-mini), as #4262's guard states it. */
const VIEWBOX_W = 800;
const HEIGHT = 300;
const PAD = { top: 20, right: 20, bottom: 40, left: 50 };
const INNER_W = VIEWBOX_W - PAD.left - PAD.right; // 730
const PLOT_RIGHT = PAD.left + INNER_W; // 780
const AXIS_LABEL_Y = PAD.top + (HEIGHT - PAD.top - PAD.bottom) + 16; // 276

/**
 * #4262's measured ruler: 9px ticks run 5.00–5.11 viewBox units per character,
 * and 5.2 is deliberately above every one of them — a ruler that under-measures
 * is how a bounds guard goes vacuous.
 */
const UNITS_PER_CHAR = 5.2;

beforeAll(() => {
  jest.useFakeTimers({ doNotFake: ["performance"] });
  jest.setSystemTime(NOW);
});
afterAll(() => {
  jest.useRealTimers();
});

/** The specimen's six points: hourly, starting at `firstMs`. */
function burst(firstMs: number): FuturesOutcomeHistory[] {
  return [
    {
      outcome_id: 1,
      name: "Yes",
      history: Array.from({ length: 6 }, (_, i) => ({
        timestamp: new Date(firstMs + i * HOUR).toISOString(),
        probability: 0.5,
        american_odds: null,
        bookmaker: "blend",
      })),
    },
  ];
}

function render(firstMs: number): string {
  return renderToStaticMarkup(
    <FuturesChart
      historyData={burst(firstMs)}
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

/** Every x-axis tick label, laid out into a box by its own anchor (#4262). */
function tickBoxes(html: string): TickBox[] {
  const out: TickBox[] = [];
  const re = /<text([^>]*)>([^<]*)<\/text>/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html)) !== null) {
    const attrs = m[1];
    const label = m[2].trim();
    const y = Number(/\by="([\d.]+)"/.exec(attrs)?.[1] ?? NaN);
    if (y !== AXIS_LABEL_Y) continue;
    const x = Number(/\bx="([\d.]+)"/.exec(attrs)?.[1] ?? NaN);
    const anchor = /text-anchor="(\w+)"/.exec(attrs)?.[1] ?? "";
    const w = label.length * UNITS_PER_CHAR;
    let left: number;
    if (anchor === "middle") left = x - w / 2;
    else if (anchor === "start") left = x;
    else if (anchor === "end") left = x - w;
    else throw new Error(`unrecognised text-anchor "${anchor}" on tick "${label}"`);
    out.push({ label, anchor, x, left, right: left + w });
  }
  return out.sort((a, b) => a.x - b.x);
}

/**
 * `Aug 24, 1:16 PM`. Anchored at both ends so a label that merely CONTAINS a
 * date (`1:16 PM Aug 24`, or a stray prefix) cannot satisfy it.
 */
const DATED_CLOCK = /^[A-Z][a-z]{2} \d{1,2}, \d{1,2}:\d{2} [AP]M$/;
/** `1:16 PM` — the bare clock the defect printed. */
const BARE_CLOCK = /^\d{1,2}:\d{2} [AP]M$/;

describe("#8135 — a four-week-old burst dates its own axis", () => {
  it("emits the ticks this guard is about", () => {
    // A bounds/shape test over an empty set passes. Prove the specimen reaches
    // the axis before asserting anything about it.
    const boxes = tickBoxes(render(BURST_START));
    expect(boxes.length).toBeGreaterThanOrEqual(3);
  });

  it("gives EVERY tick its day — the `1:48 PM` on a 29-day-old board", () => {
    for (const box of tickBoxes(render(BURST_START))) {
      expect(`${box.x}: ${box.label}`).toMatch(
        new RegExp(`^[\\d.]+: ${DATED_CLOCK.source.slice(1, -1)}$`),
      );
      expect(box.label).not.toMatch(BARE_CLOCK);
    }
  });

  it("CONTROL — the same six points ending now keep their bare clock", () => {
    // Without this, "date everything" passes the test above and takes the
    // clock-only axis away from every market that is behaving.
    const boxes = tickBoxes(render(NOW - 5 * HOUR));
    expect(boxes.length).toBeGreaterThanOrEqual(3);
    for (const box of boxes) {
      expect(`${box.x}: ${box.label}`).toMatch(
        new RegExp(`^[\\d.]+: ${BARE_CLOCK.source.slice(1, -1)}$`),
      );
    }
  });

  it("keeps the longer label inside the viewBox, and anchored at the ends", () => {
    const boxes = tickBoxes(render(BURST_START));
    for (const box of boxes) {
      const where = `${box.label} (anchor=${box.anchor}, x=${box.x})`;
      expect(`${where} left>=0: ${box.left >= 0}`).toBe(`${where} left>=0: true`);
      expect(`${where} right<=${VIEWBOX_W}: ${box.right <= VIEWBOX_W}`).toBe(
        `${where} right<=${VIEWBOX_W}: true`
      );
    }
    const last = boxes[boxes.length - 1];
    expect(last.anchor).toBe("end");
    expect(last.right).toBe(PLOT_RIGHT); // exact, by construction
  });

  it("does not let two dated labels collide with each other", () => {
    // The wider label's other failure mode. #4262 guarded the plot edges; two
    // 15-character labels 182 units apart would overlap in the middle of the
    // axis, and nothing before this asserted they do not.
    const boxes = tickBoxes(render(BURST_START));
    for (let i = 1; i < boxes.length; i += 1) {
      const gap = boxes[i].left - boxes[i - 1].right;
      expect(`${boxes[i - 1].label} | ${boxes[i].label} gap>0: ${gap > 0}`).toBe(
        `${boxes[i - 1].label} | ${boxes[i].label} gap>0: true`,
      );
    }
  });
});
