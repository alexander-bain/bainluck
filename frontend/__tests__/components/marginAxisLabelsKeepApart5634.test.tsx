/**
 * THE MARGIN RAIL'S AXIS LABELS KEEP APART WHEN A SIDE NAMES A WHOLE CLUB.
 *
 * Seen on production at 390px on 2026-09-29 1:45 PM PDT, `/events/15318706`
 * — Dubai Basketball 94, FC Barcelona Bàsquet 87. Since #5634 the margin
 * rail names whole clubs, and the axis row under it was a flex row with
 * `space-between`: both side labels wrapped onto two lines, and the centre
 * `0` sat flush against the right one, so the reader saw
 * `0Dubai Basketball by 18+`.
 *
 * jsdom has no layout, so the guard pins the mechanism that makes a collision
 * impossible: three grid tracks (equal sides, the centre sized to its label)
 * with a gap between them, each side aligned to its own end of the rail.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMap from "@/components/MarketMap";

function axisRow(left: string, right: string): string {
  const html = renderToStaticMarkup(
    <MarketMap
      variant="margin"
      status="done"
      title="Margin: expected vs final"
      subtitle="Where it landed vs what was expected"
      headline=""
      rangeMin={-18}
      rangeMax={18}
      density={[]}
      bandDrawsShape={false}
      accentRgb="37, 99, 235"
      axisLabels={{ left, mid: "0", right }}
      zeroPosition={0}
      markers={[]}
      ladder={[]}
    />
  );
  const at = html.indexOf("data-axis-labels");
  expect(at).toBeGreaterThan(-1);
  expect(html.indexOf("data-axis-labels", at + 1)).toBe(-1);
  const start = html.lastIndexOf("<div", at);
  return html.slice(start, html.indexOf("</div>", at));
}

describe("#5634 margin rail axis labels at phone width", () => {
  const LEFT = "FC Barcelona Bàsquet by 18+";
  const RIGHT = "Dubai Basketball by 18+";

  it("carries all three labels, each in its own element", () => {
    const row = axisRow(LEFT, RIGHT);
    expect(row).toContain(`>${LEFT}</span>`);
    expect(row).toContain(">0</span>");
    expect(row).toContain(`>${RIGHT}</span>`);
  });

  it("lays them out on three grid tracks with a gap, never space-between", () => {
    const row = axisRow(LEFT, RIGHT);
    expect(row).toContain("display:grid");
    expect(row).toContain("grid-template-columns:minmax(0, 1fr) auto minmax(0, 1fr)");
    expect(row).toMatch(/column-gap:([1-9]\d*)px/);
    expect(row).not.toContain("space-between");
  });

  it("aligns each side label to its own end of the rail", () => {
    const row = axisRow(LEFT, RIGHT);
    const spans = row.match(/<span style="text-align:(left|center|right)">/g) ?? [];
    expect(spans.map((s) => /text-align:(\w+)/.exec(s)?.[1])).toEqual(["left", "center", "right"]);
  });
});
