/**
 * #9249 — the /weather city panel's most-likely bucket draws the tallest bar.
 *
 * WHAT A READER SAW, production 2026-09-28 at 390px: New York's panel said
 * "38% most likely bucket · 72-73°F is the modal outcome" and labelled the
 * 72-73°F bar 38%, while the 70-71°F bar beside it (36%) drew visibly taller.
 * The peak bar was `height: 100%` inside a fixed-height flex column that also
 * holds its label, so flexbox shrank it by the label's height.
 *
 * jsdom does no layout, so this pins the two properties that make the picture
 * right — one shared scale that leaves room for the label, and no shrinking —
 * over the SHIPPED component's markup. The production LOOK is the picture.
 *
 *   TZ=UTC npx jest --testPathPatterns=weatherPeakBarIsTheTallest9249
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import DistributionPanel, {
  PEAK_LABEL_RESERVE_PX,
} from "@/components/weather/DistributionPanel";
import type { CityData, TempBucket } from "@/components/weather/data";

// New York, `GET /api/weather/cities`, 2026-09-28 00:4xZ (market 62721466).
const NEW_YORK: TempBucket[] = [
  { label: "63°F or below", prob: 1, probability: 0.01 },
  { label: "64-65°F", prob: 1, probability: 0.01 },
  { label: "66-67°F", prob: 1, probability: 0.01 },
  { label: "68-69°F", prob: 13, probability: 0.13 },
  { label: "70-71°F", prob: 36, probability: 0.36 },
  { label: "72-73°F", prob: 38, probability: 0.375 },
  { label: "74-75°F", prob: 10, probability: 0.1 },
  { label: "76-77°F", prob: 2, probability: 0.025 },
  { label: "78-79°F", prob: 0, probability: 0.0035 },
  { label: "80-81°F", prob: 0, probability: 0.0005 },
  { label: "82°F or higher", prob: 0, probability: 0.0005 },
];

function city(dist: TempBucket[]): CityData {
  return {
    id: "nyc",
    name: "New York",
    preferredX: 28.6,
    preferredY: 37.8,
    x: 28.6,
    y: 37.8,
    region: "Americas",
    srcs: ["kalshi"],
    high: { unit: "F", mode: 72.5, dist },
  };
}

const BAR_HEIGHT = /height:calc\(([\d.e-]+) \* \(100% - (\d+)px\)\)/g;

function barStyles(html: string): { fraction: number; reserve: number; style: string }[] {
  // Every bar carries a background colour and a rounded top; nothing else on
  // the panel carries the calc height.
  return Array.from(html.matchAll(/style="([^"]*height:calc[^"]*)"/g)).map(m => {
    const style = m[1];
    const [, fraction, reserve] = new RegExp(BAR_HEIGHT.source).exec(style)!;
    return { fraction: Number(fraction), reserve: Number(reserve), style };
  });
}

describe("#9249 the most-likely bucket draws the tallest bar", () => {
  const html = renderToStaticMarkup(
    React.createElement(DistributionPanel, { city: city(NEW_YORK) }),
  );
  const bars = barStyles(html);

  it("draws one bar per bucket, all on one scale that leaves room for the label", () => {
    expect(bars).toHaveLength(NEW_YORK.length);
    for (const bar of bars) {
      expect(bar.reserve).toBe(PEAK_LABEL_RESERVE_PX);
      expect(bar.style).toContain("flex-shrink:0");
    }
  });

  it("gives the peak the whole scale and its 36% neighbour 36/38 of it", () => {
    const at = (label: string) => bars[NEW_YORK.findIndex(b => b.label === label)];
    expect(at("72-73°F").fraction).toBe(1);
    expect(at("70-71°F").fraction).toBeCloseTo(36 / 38, 6);
    expect(Math.max(...bars.map(b => b.fraction))).toBe(at("72-73°F").fraction);
  });

  it("reserves at least the peak label's own height (11px type × 1.5 + 4px margin)", () => {
    expect(html).toContain("font-size:11px");
    expect(html).toContain("margin-bottom:4px");
    expect(PEAK_LABEL_RESERVE_PX).toBeGreaterThanOrEqual(11 * 1.5 + 4);
  });
});
