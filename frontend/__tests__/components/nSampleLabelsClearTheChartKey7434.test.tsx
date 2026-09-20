// #7434 — THE SAMPLE-SIZE LABELS ARE PRINTED ON TOP OF THE KEY THAT EXPLAINS THEM.
//
// ── WHAT A READER SAW, MEASURED ON PRODUCTION ───────────────────────────────
//
// `https://bainluck.com/calibration` at 390px, all-markets cohort, 2026-09-20 (live at
// `bdd03611a`). In the By Source DataGolf panel the five `n=` labels are drawn inside the
// panel's own key caption, so both are unreadable in the overlap:
//
//   `● size = sample count ·` **`n=3  n=9  n=14  n=9  n=1`** `dashed = thin (n<1000)`
//
// Bounding boxes read from the live DOM, all four provider panels in one pass:
//
//   kalshi           key x93-326  y3291-3301    0 labels    0 overlapping
//   polymarket       key x93-326  y3616-3626    0 labels    0 overlapping
//   odds_api_family  key x78-313  y5248-5258   18 labels    0 overlapping
//   datagolf         key x93-326  y4317-4327    5 labels    5 overlapping
//
// ── WHY IT LANDS ON EXACTLY THAT PANEL ──────────────────────────────────────
//
// The label is drawn ABOVE its point and the key is drawn in the pad band above the plot,
// at `padT - 10`. They can only meet when a point is at the ceiling: `py(100) === padT`,
// so the label's baseline lands at `padT - r - 3`, inside the key's line. DataGolf's five
// buckets are ALL at 100% actual (36 outcomes, 36 winners — that is the whole content of
// #6211), so all five collide; kalshi and polymarket have no thin bucket and draw no
// labels at all; the sportsbook shapes draw 18 and none of their thin buckets is near the
// ceiling.
//
// So the population that triggers the collision is precisely the censored population the
// collision hurts most. #6211 item 3 rules the flat line at 100% stays drawn so it reads
// as an alarm, and #7411 made the panel say out loud that it cannot be scored — the `n=`
// labels are the part that tells a reader how little is behind each of those points.
//
// ── WHAT THIS FILE PINS ─────────────────────────────────────────────────────
//
// Overlap is measured as RECT INTERSECTION between the key and every `n=` label, over
// every panel, from the attributes the component actually emitted — never as a pixel
// offset, which would pass on a panel that never had the problem. Three arms carry it:
// the ceiling fixture is proven to REPRODUCE the defect at the pre-fix placement (so the
// zero-overlap arm is not vacuous), the labels are proven to still be drawn (moving them
// must not become hiding them), and the real sportsbook shape panels are the control.
//
// Every fixture is the production payload of 2026-09-20, run through the page's own
// `aggregateBuckets`, so the geometry under test is the geometry a reader was looking at.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import CalibrationChart, {
  nLabelPlacement,
  KEY_CHAR_ADVANCE_PX,
  N_LABEL_FONT_PX,
  N_LABEL_BELOW_OFFSET,
  thinBucketKey,
} from "../../components/CalibrationChart";
import { aggregateBuckets, ParityBucket } from "../../lib/calibrationParity";

/** `MIN_CHART_BUCKET_N` — the floor the page passes to every panel. */
const FLOOR = 1000;

/**
 * Per-character advance for the `n=` label's 9px `system-ui`, in the chart's own user
 * units. Derived from the production rects above: `n=3` painted 15 CSS px in a panel
 * scaled 0.903, i.e. 16.6 units over 3 characters. Rounded UP, so the model over-states
 * a label's width and the intersection test bites before a reader could see the two
 * marks touch. The key's own advance is the component's measured `KEY_CHAR_ADVANCE_PX`.
 */
const N_LABEL_ADVANCE_PX = 5.6;

interface Rect {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

function intersects(a: Rect, b: Rect): boolean {
  return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
}

function attr(tag: string, name: string): string | null {
  const m = tag.match(new RegExp(`\\b${name}="([^"]*)"`));
  return m ? m[1] : null;
}

function num(tag: string, name: string): number {
  const v = attr(tag, name);
  if (v == null) throw new Error(`tag has no ${name}: ${tag}`);
  return parseFloat(v);
}

/**
 * The box a `<text>` paints, from the attributes the component emitted plus a character
 * advance. `top` uses the full type size as the ascent and `bottom` a quarter of it as
 * the descent — the same conservative model the component's own flip rule uses, and
 * within a unit of the 10-11px boxes the browser reported for these labels.
 */
function textRect(tag: string, chars: number, advance: number): Rect {
  const x = num(tag, "x");
  const y = num(tag, "y");
  const fontSize = num(tag, "font-size");
  const w = chars * advance;
  const anchor = attr(tag, "text-anchor");
  const left = anchor === "end" ? x - w : anchor === "middle" ? x - w / 2 : x;
  return { left, right: left + w, top: y - fontSize, bottom: y + fontSize * 0.25 };
}

/** The thin-bucket key's `<text>` tag. Its content is never parsed out of the markup —
 *  the width comes from `thinBucketKey`, the pure function that produced it. */
function keyTag(markup: string): string {
  const tags = Array.from(markup.matchAll(/<text\b[^>]*>[^<]*<\/text>/g), m => m[0]);
  const found = tags.filter(t => t.includes("size = sample count"));
  expect(found).toHaveLength(1);
  return found[0];
}

function keyRect(markup: string): Rect {
  return textRect(keyTag(markup), thinBucketKey(FLOOR).length, KEY_CHAR_ADVANCE_PX);
}

interface NLabel {
  n: number;
  tag: string;
  rect: Rect;
  below: boolean;
  /** the marker this label belongs to, matched on the shared x */
  cy: number;
  r: number;
}

/** Every `n=` label the chart drew, paired with its own marker. */
function nLabels(markup: string): NLabel[] {
  const circles = Array.from(markup.matchAll(/<circle\b[^>]*>/g), m => m[0]);
  return Array.from(markup.matchAll(/(<text\b[^>]*>)n=(\d+)<\/text>/g), m => {
    const tag = m[1] + `n=${m[2]}</text>`;
    const chars = `n=${m[2]}`.length;
    const x = num(tag, "x");
    const marker = circles.find(c => Math.abs(num(c, "cx") - x) < 1e-6);
    if (!marker) throw new Error(`no marker at x=${x}`);
    return {
      n: parseInt(m[2], 10),
      tag,
      rect: textRect(tag, chars, N_LABEL_ADVANCE_PX),
      below: attr(tag, "data-n-label-below") === "true",
      cy: num(marker, "cy"),
      r: num(marker, "r"),
    };
  }).sort((a, b) => num(a.tag, "x") - num(b.tag, "x"));
}

/** The plot's top edge, read off the drawing rather than assumed: the perfect-calibration
 *  diagonal ends at `py(100)`, which is `padT`. */
function plotTop(markup: string): number {
  const dashed = Array.from(markup.matchAll(/<line\b[^>]*>/g), m => m[0]).filter(
    t => attr(t, "stroke-dasharray") === "6,4",
  );
  expect(dashed).toHaveLength(1);
  return num(dashed[0], "y2");
}

function render(data: ReturnType<typeof aggregateBuckets>, width: number, height: number): string {
  return renderToStaticMarkup(
    React.createElement(CalibrationChart, {
      series: [{ data, color: "#0f766e", label: "panel" }],
      width,
      height,
      thinFloor: FLOOR,
      showLegend: false,
    }),
  );
}

// ── The production payload of 2026-09-20 ────────────────────────────────────
// `GET /api/calibration`, the `buckets` rows for each source, summed over `category` and
// `price_moved` — which is the only thing `aggregateBuckets` does to them, so these are
// the exact `CalPoint`s each panel was drawing in the all-markets cohort. Nothing here is
// a round number chosen by hand; if one ever looks like one, it is not this payload.

const DATAGOLF_ROWS: ParityBucket[] = [
  { bucket_idx: 4, n: 3, winners: 3, sum_prob: 1.3101, sum_sq_err: 0.955 },
  { bucket_idx: 5, n: 9, winners: 9, sum_prob: 4.997, sum_sq_err: 1.7875 },
  { bucket_idx: 6, n: 14, winners: 14, sum_prob: 9.1052, sum_sq_err: 1.7213 },
  { bucket_idx: 7, n: 9, winners: 9, sum_prob: 6.6199, sum_sq_err: 0.6335 },
  { bucket_idx: 8, n: 1, winners: 1, sum_prob: 0.8326, sum_sq_err: 0.028 },
];

/** Moneylines (Odds API) — 10 bins, 4 of them thin, and the one at 94.1% actual is the
 *  closest any sportsbook label comes to the key. */
const MONEYLINE_ROWS: ParityBucket[] = [
  { bucket_idx: 0, n: 540, winners: 32, sum_prob: 32.1033, sum_sq_err: 30.9403 },
  { bucket_idx: 1, n: 944, winners: 136, sum_prob: 144.2138, sum_sq_err: 115.7315 },
  { bucket_idx: 2, n: 1506, winners: 344, sum_prob: 385.0355, sum_sq_err: 266.4014 },
  { bucket_idx: 3, n: 2241, winners: 830, sum_prob: 795.6899, sum_sq_err: 520.3022 },
  { bucket_idx: 4, n: 3838, winners: 1781, sum_prob: 1727.7411, sum_sq_err: 953.9768 },
  { bucket_idx: 5, n: 4140, winners: 2208, sum_prob: 2261.2588, sum_sq_err: 1029.4771 },
  { bucket_idx: 6, n: 2241, winners: 1411, sum_prob: 1445.31, sum_sq_err: 520.3021 },
  { bucket_idx: 7, n: 1505, winners: 1161, sum_prob: 1120.1644, sum_sq_err: 266.3615 },
  { bucket_idx: 8, n: 938, winners: 802, sum_prob: 794.2862, sum_sq_err: 115.7015 },
  { bucket_idx: 9, n: 547, winners: 515, sum_prob: 514.1971, sum_sq_err: 31.0103 },
];

/** Spreads (Odds API) — 8 of its 10 bins are thin, the most labels of any panel. */
const SPREADS_ROWS: ParityBucket[] = [
  { bucket_idx: 0, n: 7, winners: 1, sum_prob: 0.5093, sum_sq_err: 0.8812 },
  { bucket_idx: 1, n: 9, winners: 4, sum_prob: 1.29, sum_sq_err: 2.9852 },
  { bucket_idx: 2, n: 42, winners: 16, sum_prob: 11.7566, sum_sq_err: 10.5197 },
  { bucket_idx: 3, n: 793, winners: 282, sum_prob: 288.8369, sum_sq_err: 181.2103 },
  { bucket_idx: 4, n: 5590, winners: 2656, sum_prob: 2650.3367, sum_sq_err: 1392.519 },
  { bucket_idx: 5, n: 8203, winners: 4263, sum_prob: 4245.2703, sum_sq_err: 2044.8801 },
  { bucket_idx: 6, n: 417, winners: 264, sum_prob: 264.6078, sum_sq_err: 97.0394 },
  { bucket_idx: 7, n: 30, winners: 20, sum_prob: 21.706, sum_sq_err: 6.9917 },
  { bucket_idx: 8, n: 18, winners: 7, sum_prob: 15.2508, sum_sq_err: 8.1249 },
  { bucket_idx: 9, n: 11, winners: 5, sum_prob: 10.3995, sum_sq_err: 5.2694 },
];

/** Totals (Odds API) — the #7399 panel, 6 thin bins including the 7-outcome crash to 0%. */
const TOTALS_ROWS: ParityBucket[] = [
  { bucket_idx: 0, n: 26, winners: 6, sum_prob: 2.1663, sum_sq_err: 5.1636 },
  { bucket_idx: 1, n: 48, winners: 16, sum_prob: 7.4633, sum_sq_err: 12.1221 },
  { bucket_idx: 2, n: 34, winners: 7, sum_prob: 8.5079, sum_sq_err: 5.6494 },
  { bucket_idx: 3, n: 135, winners: 35, sum_prob: 50.9388, sum_sq_err: 27.6474 },
  { bucket_idx: 4, n: 5759, winners: 2585, sum_prob: 2742.8261, sum_sq_err: 1430.4431 },
  { bucket_idx: 5, n: 9414, winners: 4651, sum_prob: 4832.9162, sum_sq_err: 2353.5881 },
  { bucket_idx: 6, n: 114, winners: 57, sum_prob: 71.5397, sum_sq_err: 31.3633 },
  { bucket_idx: 7, n: 7, winners: 0, sum_prob: 5.0601, sum_sq_err: 3.6617 },
];

const DATAGOLF = aggregateBuckets(DATAGOLF_ROWS);

/** The By Source provider panels are authored at 330x260; the shape panels inside the
 *  Sportsbooks disclosure at 300x230. Both are call-site facts from `page.tsx`. */
const PROVIDER_PANEL: [number, number] = [330, 260];
const SHAPE_PANEL: [number, number] = [300, 230];

describe("#7434 — nLabelPlacement keeps the label out of the key's band", () => {
  test("a point with room above keeps the placement it always had", () => {
    // The no-change rule. A mid-plot point is the overwhelming majority of every panel,
    // and its label must still be drawn above the marker, at `y - r - 3`.
    expect(nLabelPlacement(120, 5, 25)).toEqual({ y: 112, below: false });
  });

  test("a point at the ceiling flips its label under the marker", () => {
    // `py(100) === plotTop`, which is the DataGolf case exactly. The literal is pinned,
    // not spelled with the constant: written as `25 + 10 + N_LABEL_BELOW_OFFSET` this
    // assertion passes for any value the constant could take, including one that puts
    // the label off the bottom of the panel.
    expect(nLabelPlacement(25, 10, 25)).toEqual({ y: 46, below: true });
    // and it IS the placement the always-below `showAllN` label has used since L2-103,
    // which is the reason no new position had to be invented.
    expect(N_LABEL_BELOW_OFFSET).toBe(11);
  });

  test("the boundary is the plot's top edge, and it is the label's TOP that has to clear it", () => {
    // Keyed on the baseline instead of the box top, the rule would let a label hang its
    // whole height into the key band and still call itself placed. Both sides pinned so
    // a future tweak to the ascent cannot quietly move the trigger.
    const plotTop = 25;
    const r = 4;
    // baseline `pointY - r - 3`, top `baseline - N_LABEL_FONT_PX`; the first pointY whose
    // top lands exactly on the edge is plotTop + r + 3 + N_LABEL_FONT_PX.
    const exact = plotTop + r + 3 + N_LABEL_FONT_PX;
    expect(nLabelPlacement(exact, r, plotTop).below).toBe(false);
    expect(nLabelPlacement(exact - 0.01, r, plotTop).below).toBe(true);
  });

  test("a bigger marker flips sooner, because the label starts further from the point", () => {
    // r is `4 + 6*sqrt(n/maxN)`, so the best-sampled thin bucket in a censored panel has
    // the largest dot and the highest label. Keyed on the point alone, the panel's own
    // biggest bucket would be the one left in the key.
    expect(nLabelPlacement(42, 4, 25).below).toBe(false);
    expect(nLabelPlacement(42, 10, 25).below).toBe(true);
  });
});

describe("#7434 — the censored DataGolf panel", () => {
  const markup = render(DATAGOLF, ...PROVIDER_PANEL);
  const labels = nLabels(markup);
  const key = keyRect(markup);

  test("REPRODUCES THE DEFECT: at the pre-fix placement, 5 of 5 labels sit in the key", () => {
    // THE NON-VACUITY ARM. Without it every assertion below would pass on a fixture that
    // never had the problem — which is what a panel with no at-the-ceiling point is. The
    // pre-fix baseline was `py(actual) - r - 3` with no plot-top test; both numbers are
    // read back off the markers the component drew, not re-derived from the payload.
    expect(labels).toHaveLength(5);
    const wouldOverlap = labels.filter(l =>
      intersects({ ...l.rect, top: l.cy - l.r - 3 - N_LABEL_FONT_PX, bottom: l.cy - l.r - 3 + N_LABEL_FONT_PX * 0.25 }, key),
    );
    expect(wouldOverlap).toHaveLength(5);
  });

  test("0 of 5 labels intersect the key as drawn", () => {
    expect(labels.filter(l => intersects(l.rect, key))).toHaveLength(0);
  });

  test("the labels are still drawn — moving them did not become hiding them", () => {
    // Every bucket the panel has, still named with its own count (L2-127: no populated
    // bucket is ever dropped). A "fix" that suppressed the labels would clear the arm
    // above and is exactly what this refuses.
    expect(labels.map(l => l.n)).toEqual([3, 9, 14, 9, 1]);
    expect(labels.every(l => l.below)).toBe(true);
  });

  test("every flipped label lands inside the plot, not below the axis", () => {
    const top = plotTop(markup);
    for (const l of labels) expect(l.rect.top).toBeGreaterThanOrEqual(top);
  });

  test("the labels do not land on each other", () => {
    // They share one y now, so a panel whose bins were closer together would stack them.
    // 25.5 units of pitch against a widest label of 4 characters is the margin.
    for (let i = 1; i < labels.length; i++) {
      expect(labels[i].rect.left).toBeGreaterThan(labels[i - 1].rect.right);
    }
  });
});

describe("#7434 — CONTROL: the real sportsbook shape panels", () => {
  const panels = [
    { label: "moneylines", data: aggregateBuckets(MONEYLINE_ROWS) },
    { label: "spreads", data: aggregateBuckets(SPREADS_ROWS) },
    { label: "totals", data: aggregateBuckets(TOTALS_ROWS) },
  ].map(p => {
    const markup = render(p.data, ...SHAPE_PANEL);
    return { ...p, markup, labels: nLabels(markup), key: keyRect(markup) };
  });

  test("they draw the 18 labels production measured", () => {
    // If this count drifts the control has stopped being the control, and the zero-overlap
    // arm below would be measuring a different drawing than the one that was clean.
    expect(panels.reduce((s, p) => s + p.labels.length, 0)).toBe(18);
  });

  test("0 of 18 intersect the key, as on production", () => {
    for (const p of panels) {
      expect(p.labels.filter(l => intersects(l.rect, p.key)).map(l => `${p.label}:n=${l.n}`)).toEqual([]);
    }
  });

  test("17 of 18 do not move at all, and the one that does was the next to collide", () => {
    // "Do not move to a worse place" measured rather than asserted. Only the 90-100%
    // moneyline bin moves: at 94.1% actual its label cleared the key's descender by ~0.3
    // units, so above was already the worse place for it. Every other sportsbook label
    // is drawn exactly where it was.
    const moved = panels.flatMap(p => p.labels.filter(l => l.below).map(l => `${p.label}:n=${l.n}`));
    expect(moved).toEqual(["moneylines:n=547"]);
  });

  test("every label that stayed is still above its own marker", () => {
    // The other half: unmoved must mean unmoved, not "relabelled and re-placed".
    for (const p of panels) {
      for (const l of p.labels.filter(x => !x.below)) {
        expect(l.rect.bottom).toBeLessThan(l.cy - l.r);
      }
    }
  });
});

describe("#7434 — the halo that makes either placement readable", () => {
  test("the label is painted with its stroke behind the glyphs, not through them", () => {
    // A flipped label on a ceiling point lands over its own CI bar, which runs the height
    // of the plot; either placement can land on a gridline. Without `paint-order` the
    // white stroke would be painted ON TOP of the letters and the label would disappear —
    // the one way this fix could make things worse than the collision it removes.
    const markup = render(DATAGOLF, ...PROVIDER_PANEL);
    for (const l of nLabels(markup)) {
      expect(attr(l.tag, "paint-order")).toBe("stroke");
      expect(attr(l.tag, "stroke")).toBe("white");
    }
  });
});
