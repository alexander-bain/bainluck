/**
 * #7839, at the rendered surface — the number and the pixel it is printed at.
 *
 * The helper test (`chartYTicksLabelTheLineTheySitOn7839`) proves the ladder.
 * This one proves the RENDERER uses it: it reads the pinned gutter's actual
 * `style="top: …%"` out of the markup, converts that back to a probability
 * through the chart's own geometry, and compares it with the number printed in
 * the span. That is the reader's question — "the rule says 3%, is it at 3%?" —
 * and it is the one a test on the helper alone cannot answer, because the
 * defect lived in the component's two hard-coded `[0, .25, .5, .75, 1]` arrays
 * and would survive any correct helper that nothing called.
 *
 * Both frames are the ones photographed on `/futures/59165099` at 390px.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import { FuturesChart } from "../../components/FuturesChart";
import { ceilingForMax } from "../../lib/chartCeiling";
import type { FuturesOutcomeHistory } from "../../lib/types";

const HOUR = 60 * 60 * 1000;
const NOW = Date.UTC(2026, 8, 21, 16, 0, 0);

/** `FuturesChart`'s own non-mini geometry. */
const HEIGHT = 300;
const PAD_TOP = 20;
const PAD_BOTTOM = 40;
const INNER_H = HEIGHT - PAD_TOP - PAD_BOTTOM;

beforeAll(() => {
  jest.useFakeTimers({ doNotFake: ["performance"] });
  jest.setSystemTime(NOW);
});
afterAll(() => {
  jest.useRealTimers();
});

/** A field whose leader pins the #2451 ladder to `wantedCeiling`. */
function field(leader: number): FuturesOutcomeHistory[] {
  const count = 24;
  return [
    {
      outcome_id: 1,
      name: "Leader",
      history: Array.from({ length: count }, (_, i) => ({
        timestamp: new Date(NOW - (count - 1 - i) * HOUR).toISOString(),
        probability: leader,
        american_odds: null,
        bookmaker: "blend",
      })),
    },
  ];
}

function render(leader: number): string {
  return renderToStaticMarkup(
    <FuturesChart
      historyData={field(leader)}
      height={HEIGHT}
      showAxes
      showLegend={false}
      fieldCeiling
    />
  );
}

interface Rule {
  label: string;
  /** The percent printed in the span. */
  printed: number;
  /** The probability the span is actually positioned at, in percent. */
  drawnAt: number;
}

/**
 * Every pinned-gutter rule, with its printed number and the probability its
 * own `top` puts it at.
 *
 * The component writes `top: (yScale(maxProb * pct) / effectiveHeight) * 100 %`
 * and `yScale(p) = PAD_TOP + (1 - p / maxProb) * INNER_H`, so
 *   topPx  = (top% / 100) * HEIGHT
 *   pct    = 1 - (topPx - PAD_TOP) / INNER_H
 * and the probability drawn at that pixel is `pct * ceiling`.
 */
function rules(html: string, ceiling: number): Rule[] {
  const out: Rule[] = [];
  const re =
    /<span([^>]*?data-testid="chart-y-label"[^>]*?)>([^<]*)<\/span>/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html)) !== null) {
    const attrs = m[1];
    const label = m[2].trim();
    const topPct = Number(/top:\s*([\d.eE+-]+)%/.exec(attrs)?.[1] ?? NaN);
    // THROW rather than guess: a rule we cannot place must not silently pass.
    if (!Number.isFinite(topPct)) {
      throw new Error(`no readable top on y-label ${JSON.stringify(label)}`);
    }
    const topPx = (topPct / 100) * HEIGHT;
    const pct = 1 - (topPx - PAD_TOP) / INNER_H;
    out.push({
      label,
      printed: Number(label.replace("%", "")),
      drawnAt: pct * ceiling * 100,
    });
  }
  return out;
}

describe("#7839 the futures chart's gridline labels sit where they say", () => {
  // leader → the ladder rung it pins, i.e. the axis top the reader gets.
  const FRAMES: [string, number, number, string[]][] = [
    ["the 'All' frame (15% axis)", 0.12, 0.15, ["0%", "5%", "10%", "15%"]],
    [
      "the '1W' frame (10% axis)",
      0.08,
      0.1,
      ["0%", "2%", "4%", "6%", "8%", "10%"],
    ],
  ];

  it.each(FRAMES)("%s", (_name, leader, ceiling, expected) => {
    // The fixture must actually reach the rung the frame is about, or the test
    // is measuring a different chart than the one it names.
    expect(ceilingForMax(leader)).toBeCloseTo(ceiling, 9);

    const drawn = rules(render(leader), ceiling);
    expect(drawn.map((r) => r.label)).toEqual(expected);

    for (const r of drawn) {
      expect(`${r.label} is drawn at ${r.drawnAt.toFixed(3)}%`).toBe(
        `${r.label} is drawn at ${r.printed.toFixed(3)}%`
      );
    }
  });

  it("POSITIVE CONTROL: the pre-#7839 ladder fails this assertion", () => {
    // What the component printed before the fix, at the 15% rung. If the
    // reader-facing check above can be satisfied by the defect, it is vacuous.
    const ceiling = 0.15;
    const old = [0, 0.25, 0.5, 0.75, 1].map((pct) => ({
      label: `${Math.round(ceiling * pct * 100)}%`,
      printed: Math.round(ceiling * pct * 100),
      drawnAt: pct * ceiling * 100,
    }));
    const liars = old.filter((r) => Math.abs(r.printed - r.drawnAt) > 1e-9);
    expect(liars.map((r) => `${r.label} drawn at ${r.drawnAt.toFixed(2)}%`)).toEqual([
      "4% drawn at 3.75%",
      "8% drawn at 7.50%",
      "11% drawn at 11.25%",
    ]);
  });

  it("the in-SVG grid draws one line per gutter rule, at the same heights", () => {
    // Two lists were the original defect's shape: rules from one array, labels
    // from another. They are one array now, and this is what says so.
    const html = render(0.12);
    const gridYs = [
      ...html.matchAll(/<line[^>]*?y1="([\d.]+)"[^>]*?stroke-dasharray="4"/g),
    ].map((m) => Number(m[1]));
    const gutterYs = rules(html, 0.15).map(
      (r) => PAD_TOP + (1 - r.printed / 15) * INNER_H
    );
    expect(gridYs.length).toBe(gutterYs.length);
    for (let i = 0; i < gridYs.length; i++) {
      expect(gridYs[i]).toBeCloseTo(gutterYs[i], 6);
    }
  });
});
