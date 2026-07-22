// L2-161: SSR render guards for the futures Hero C ambient-history treatment.
// Both directions: ambient curve + tinted movement pill render when history is
// present; a plain 64px numeral renders when it isn't; resolved markets never
// show a live number or ambient layer (settled-means-settled).
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { FuturesHero } from "../../components/FuturesHero";

const UP_CURVE = [0.4, 0.45, 0.5, 0.58, 0.62, 0.68];

describe("FuturesHero — Hero C ambient history", () => {
  test("renders ambient curve + tinted up pill + 64px numeral when points present", () => {
    const html = renderToStaticMarkup(
      <FuturesHero
        name="Avatar opens above $150M"
        probability={0.68}
        outcomeName="Yes"
        movement={11}
        sourceCount={4}
        sparklinePoints={UP_CURVE}
      />,
    );
    expect(html).toContain("68");
    expect(html).toContain("text-[64px]"); // hero numeral bumped to 64px
    expect(html).toContain("↑ 11.0 pts");
    expect(html).toContain("bg-accent-live/15"); // tinted up pill
    expect(html).toContain("<svg"); // ambient layer present
    expect(html).toContain("Aggregated from");
  });

  test("down movement uses the danger tint", () => {
    const html = renderToStaticMarkup(
      <FuturesHero name="M" probability={0.4} movement={-6} sparklinePoints={UP_CURVE} />,
    );
    expect(html).toContain("↓ 6.0 pts");
    expect(html).toContain("bg-accent-danger/15");
  });

  test("falls back to a plain numeral (no ambient svg) when history is absent", () => {
    const html = renderToStaticMarkup(
      <FuturesHero name="M" probability={0.55} outcomeName="Yes" movement={3} />,
    );
    expect(html).toContain("55");
    expect(html).toContain("text-[64px]");
    expect(html).not.toContain("<svg"); // no ambient layer without points
  });

  test("resolved market shows the winner + chip, never a live number or ambient", () => {
    const html = renderToStaticMarkup(
      <FuturesHero
        name="Who wins?"
        probability={0.72}
        outcomeName="Denver"
        resolved
        resolvedWon
        sparklinePoints={UP_CURVE}
      />,
    );
    expect(html).toContain("Denver");
    expect(html).toContain("Won");
    expect(html).not.toContain("text-[64px]"); // no live hero numeral
    expect(html).not.toContain("<svg"); // no ambient layer on settled
  });
});
