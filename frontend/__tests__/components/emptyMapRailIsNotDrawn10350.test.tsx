/**
 * A MAP WITH NO SHAPE AND NOTHING ON IT DRAWS NO RAIL.
 *
 * Seen on production at 390px on 2026-10-03 9:38 AM PDT, `/events/15318030`
 * (Alabama at Mississippi State, 1st quarter): "2nd half points map · Two lines
 * quoted" drew a full-width empty grey track labelled `24 · 29 · 34+`, with no
 * shading, dot or tile, above its two quoted lines. #3210 keeps the bare track
 * as a number line FOR THE MARKERS ON IT. Before the half starts there are none,
 * so the track meant nothing.
 *
 * Both directions are pinned: no rail when the band is shapeless and no marker
 * has a value, and the rail still renders when one marker exists (#3210's case)
 * or when the band has a shape.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMap, { type MarketMapMarker } from "@/components/MarketMap";

const LADDER = [
  { label: "Over 27.5", probability: 0.52, side: "mid" as const },
  { label: "Over 30.5", probability: 0.42, side: "mid" as const },
];

function render(opts: { bandDrawsShape: boolean; markers: MarketMapMarker[]; density?: number[] }): string {
  return renderToStaticMarkup(
    <MarketMap
      variant="total"
      status="live"
      title="2nd half points map"
      subtitle="Two lines quoted"
      headline="O/U 27.5"
      rangeMin={24}
      rangeMax={34}
      density={opts.density ?? [10, 10, 10, 10]}
      bandDrawsShape={opts.bandDrawsShape}
      accentRgb="139, 92, 246"
      axisLabels={{ left: "24", mid: "29", right: "34+" }}
      markers={opts.markers}
      ladder={LADDER}
    />
  );
}

const ACTUAL: MarketMapMarker = {
  key: "actual",
  value: 7,
  type: "actual",
  label: "ACTUAL",
  displayValue: "7 points",
};

describe("#10350 an empty map rail is not drawn", () => {
  it("drops the track and axis row when the band is shapeless and nothing is placed", () => {
    const html = render({ bandDrawsShape: false, markers: [] });
    expect(html).not.toContain("data-map-rail");
    expect(html).not.toContain("data-axis-labels");
    expect(html).not.toContain(">34+</span>");
  });

  it("treats a marker whose value is missing as nothing placed", () => {
    const unplaced = { ...ACTUAL, value: null as unknown as number };
    const html = render({ bandDrawsShape: false, markers: [unplaced] });
    expect(html).not.toContain("data-map-rail");
  });

  it("still prints the quoted lines inline, once", () => {
    const html = render({ bandDrawsShape: false, markers: [] });
    expect(html.match(/data-inline-ladder/g)).toHaveLength(1);
    expect(html).toContain("Over 27.5");
    expect(html).toContain("Over 30.5");
  });

  it("keeps the number line when one marker is on it (#3210)", () => {
    const html = render({ bandDrawsShape: false, markers: [ACTUAL] });
    expect(html).toContain("data-map-rail");
    expect(html).toContain("data-axis-labels");
    expect(html).toContain('data-dot="actual"');
  });

  it("keeps the rail when the band has a shape, even with no marker", () => {
    const html = render({ bandDrawsShape: true, markers: [], density: [10, 40, 80, 20] });
    expect(html).toContain("data-map-rail");
    expect(html).toContain("data-density-segment");
  });
});
