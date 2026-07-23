// #490 / L2-171 — SignalBars glyph. SSR-guards every tier state the queue calls
// out (bars 1/2/3 + absent) and that the tooltip/aria-label ships WITH the glyph
// (never unexplained chrome — the rank-chip lesson).

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import { SignalBars } from "../../components/discover/shared";
import { CONFIDENCE_TOOLTIP } from "@/lib/confidence";

// Each of the 3 bars is a <span>; an UNFILLED bar carries bg-surface-border.
// filled = 3 - (# of bg-surface-border occurrences).
function filledBars(html: string): number {
  const empties = html.split("bg-surface-border").length - 1;
  return 3 - empties;
}

describe("SignalBars", () => {
  it("renders 3 filled bars for high", () => {
    const html = renderToStaticMarkup(<SignalBars tier="high" />);
    expect(filledBars(html)).toBe(3);
    expect(html).toContain('role="img"');
  });

  it("renders 2 filled bars for moderate", () => {
    const html = renderToStaticMarkup(<SignalBars tier="moderate" />);
    expect(filledBars(html)).toBe(2);
  });

  it("renders 1 filled bar for low", () => {
    const html = renderToStaticMarkup(<SignalBars tier="low" />);
    expect(filledBars(html)).toBe(1);
  });

  it("renders nothing when the tier is absent or unknown", () => {
    expect(renderToStaticMarkup(<SignalBars tier={null} />)).toBe("");
    expect(renderToStaticMarkup(<SignalBars tier={undefined} />)).toBe("");
    expect(renderToStaticMarkup(<SignalBars tier="bogus" />)).toBe("");
  });

  it("ships its own explanation (tooltip + aria-label)", () => {
    const html = renderToStaticMarkup(<SignalBars tier="high" />);
    expect(html).toContain(CONFIDENCE_TOOLTIP);
    expect(html).toContain("High confidence");
    expect(html).toContain("aria-label");
  });
});
