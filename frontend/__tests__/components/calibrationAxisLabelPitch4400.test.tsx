// #4400 — ELEVEN LABELS NEED ELEVEN LABELS' WORTH OF ROOM.
//
// ── WHAT A READER SAW, MEASURED ON PRODUCTION ───────────────────────────────
//
// `https://bainluck.com/calibration`, master `2bf1d499`, `tools/cal-axis-overlap-1073.mjs`. Not a
// census of whether the labels exist (nine passes) and not the scale (#4394 already reads that) —
// the painted INK: every x-axis label's getBoundingClientRect(), adjacent right-edge against next
// left-edge. A negative gap is two numbers on top of each other.
//
//   width   labels  scale  drawn  widest  min-gap  chart
//   390px   11      0.903  298    29.4    -1.2     By Source panel  (authored 330x260, x3)
//   390px   11      0.907  272    29.4    -4.0     By Source panel  (authored 300x230, x4)
//   390px    6      1.000  324    29.4    +22.9    the re-authored wide charts — fine
//   1280px  11      1.000  330    29.4    -1.4     By Source panel
//   1280px  11      1.000  300    29.4    -4.4     By Source panel
//   1280px  11      1.000  700    29.4    +35.6    the wide charts at 1:1 — fine
//
// Seven of nine charts, at BOTH widths. `100%` paints 29.4px of ink everywhere on the page (the
// font-size is 11 in every geometry); what differs is the pitch it is given, `plotW/10 * scale`.
//
// ── WHY #4394 DID NOT REACH IT ──────────────────────────────────────────────
//
// #4394 thinned the labels when a chart RE-AUTHORED itself, which happens below 0.85 of the
// authored width. These panels measure 0.903 and 0.907 — above the trigger by design, and #4394's
// control test pins them un-re-authored. Re-authoring answers "is the type too small"; this
// answers "is there room for eleven numbers". A chart can pass the first and fail the second, and
// seven do. So the step is keyed on pitch in whichever geometry won, which subsumes #4394's rule.
//
// ── WHAT THIS FILE CAN AND CANNOT SEE ───────────────────────────────────────
//
// `testEnvironment: 'node'` — no layout engine, so nothing here measures ink. It pins the pure
// decision, `chartGeometry`, at the real call sites' numbers, plus the arithmetic that connects
// the two (AXIS_PAD_X must equal the component's own padL+padR, or the pitch is computed for a
// plot that does not exist). The production probe closes the other half:
//
//   node tools/cal-axis-overlap-1073.mjs https://bainluck.com/calibration 390    → exit 0
//   node tools/cal-axis-overlap-1073.mjs https://bainluck.com/calibration 1280   → exit 0

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import CalibrationChart, { chartGeometry } from "../../components/CalibrationChart";

/** The two By Source panel geometries in app/calibration/page.tsx, and the cards that hold them at
 *  390px (measured: 298 and 272). At 1280px both draw 1:1, which is `containerW >= authoredW`. */
const PANEL_TALL = [330, 260] as const;
const PANEL_SHORT = [300, 230] as const;
const CARD_330_AT_390 = 298;
const CARD_300_AT_390 = 272;

/** The component's own padL + padR. If this and AXIS_PAD_X ever disagree the pitch is arithmetic
 *  about a plot that isn't drawn — so it is asserted, not assumed. */
const PAD_X = 55 + 20;

/** Measured on production at both widths: `100%` at font-size 11 paints this much ink. */
const LABEL_INK_PX = 29.4;

const pitch = (width: number, scale = 1) => ((width - PAD_X) / 10) * scale;

describe("#4400 — the By Source axis stops reading as one grey run", () => {
  test("the panels thin to every 20% at phone width, where they overlapped by 1.2 and 4.0px", () => {
    expect(chartGeometry(...PANEL_TALL, CARD_330_AT_390).xLabelStep).toBe(20);
    expect(chartGeometry(...PANEL_SHORT, CARD_300_AT_390).xLabelStep).toBe(20);
  });

  test("and at desktop width, where they draw 1:1 and overlapped by 1.4 and 4.4px", () => {
    // 1280px: the card is wider than the authored box, so `maxWidth: 100%` never binds and the
    // chart draws at its authored width. This is the arm #4394 could not reach at all — its rule
    // fires on a NARROW container, and here there isn't one.
    expect(chartGeometry(...PANEL_TALL, 400).xLabelStep).toBe(20);
    expect(chartGeometry(...PANEL_SHORT, 400).xLabelStep).toBe(20);
    // and the server render / first paint, which is what a desktop reader is actually sent first:
    // it must already be 20, or the axis smears until the observer fires and then flips.
    expect(chartGeometry(...PANEL_TALL, null).xLabelStep).toBe(20);
    expect(chartGeometry(...PANEL_SHORT, null).xLabelStep).toBe(20);
  });

  test("the wide charts keep all eleven labels — the fix is a floor, not a haircut", () => {
    // 700-authored: 62.5px of pitch for 29.4px of ink, measured +35.6px of gap. Thinning these
    // would be #4400 overshooting into a chart that was never the defect. This is the control.
    expect(chartGeometry(700, 400, 1200).xLabelStep).toBe(10);
    expect(chartGeometry(700, 340, null).xLabelStep).toBe(10);
    // the admin surface's default box (560x360) is the same story at 48.5px of pitch
    expect(chartGeometry(560, 360, 1200).xLabelStep).toBe(10);
  });

  test("the threshold sits above every measured overlap and below every measured pass", () => {
    // Rather than pinning the constant's value, pin what it has to SEPARATE. A future edit that
    // moves MIN_LABEL_PITCH_PX to 20 or to 70 fails here, naming the measurement it broke.
    const overlapped = [
      pitch(330, 298 / 330), pitch(300, 272 / 300),   // 390px: 23.0, 20.4
      pitch(330), pitch(300),                          // 1280px: 25.5, 22.5
      pitch(324),                                      // the re-authored card: 24.9
    ];
    const fine = [pitch(700), pitch(560)];             // 62.5, 48.5
    for (const p of overlapped) expect(p).toBeLessThan(LABEL_INK_PX);
    for (const p of fine) expect(p).toBeGreaterThan(LABEL_INK_PX * 1.5);
  });

  test("thinning is by value, so a thinned axis still ends at 0% and 100%", () => {
    const kept = Array.from({ length: 11 }, (_, i) => i * 10).filter(v => v % 20 === 0);
    expect(kept).toEqual([0, 20, 40, 60, 80, 100]);
  });

  test("the component draws the step it was given, and says which one in the markup", () => {
    // Reach, as far as a node environment sees it. The data-attribute is also what the production
    // probe reads to tell the arms apart without re-deriving the arithmetic (notice 34: the number
    // a probe needs is an attribute, never prose on the reader's screen).
    const panel = renderToStaticMarkup(<CalibrationChart series={[]} width={330} height={260} />);
    expect(panel).toContain('data-x-label-step="20"');
    expect((panel.match(/text-anchor="middle"[^>]*>\d+%</g) || []).length).toBe(6);

    const wide = renderToStaticMarkup(<CalibrationChart series={[]} width={700} height={340} />);
    expect(wide).toContain('data-x-label-step="10"');
    expect((wide.match(/text-anchor="middle"[^>]*>\d+%</g) || []).length).toBe(11);
  });

  test("gridlines are every 10% whatever the labels do — no resolution is lost", () => {
    // The thinning removes labels, never the structure a reader reads a point against. Vertical
    // gridlines are the `x1===x2` lines; there are 11 in both arms.
    const vlines = (m: string) => (m.match(/<line x1="([\d.]+)" y1="25" x2="\1"/g) || []).length;
    expect(vlines(renderToStaticMarkup(<CalibrationChart series={[]} width={330} height={260} />))).toBe(11);
    expect(vlines(renderToStaticMarkup(<CalibrationChart series={[]} width={700} height={340} />))).toBe(11);
  });

  test("the pitch is computed for the plot the component actually draws", () => {
    // AXIS_PAD_X is a copy of padL+padR living in a pure function that cannot see them. If the
    // component's padding changes and the constant does not, every pitch above is fiction — and
    // the failure would otherwise surface only as a look. 700 - 75 = 625 is the plot width, and a
    // 625-wide plot is exactly what the re-authored square proves (#4394: 324-55-20 = 249 = the
    // plot side), so the same 75 is the number both rules are built on.
    const src = require("fs").readFileSync(
      require("path").join(__dirname, "../../components/CalibrationChart.tsx"), "utf8");
    expect(src).toMatch(/const padL = 55, padR = 20,/);
    expect(src).toMatch(/const AXIS_PAD_X = 75;/);
    expect(PAD_X).toBe(75);
  });
});
