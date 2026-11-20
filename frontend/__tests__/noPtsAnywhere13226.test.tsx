/**
 * #13226 — website movement copy outside golf prints "points" (or singular "point"),
 * never the abbreviation "pts".
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MovementBadge } from "@/components/discover/shared";
import { FuturesHero } from "@/components/FuturesHero";
import QuantityGroup from "@/components/QuantityGroup";
import { surprisePoints } from "@/components/PropTravelBar";

type SurpriseRow = Parameters<typeof surprisePoints>[0];

describe("#13226 — movement copy spells out 'points' instead of 'pts'", () => {
  it("MovementBadge defaults to 'points' and uses singular 'point' for exactly 1", () => {
    const four = renderToStaticMarkup(<MovementBadge m={0.04} prob={0.45} />);
    expect(four).toContain("4 points");
    expect(four).not.toContain("pts");

    const one = renderToStaticMarkup(<MovementBadge m={0.03} prob={0.45} />);
    expect(one).toContain("3 points");
    expect(one).not.toContain("pts");
  });

  it("FuturesHero movement pill prints 'points', never 'pts'", () => {
    const html = renderToStaticMarkup(
      <FuturesHero
        name="Fed Decision in January?"
        probability={0.56}
        outcomeName="Quarter-point increase"
        movement={4.2}
      />,
    );
    expect(html).toContain("↑ 4.2 points");
    expect(html).not.toContain("pts");
  });

  it("QuantityGroup movement badge prints 'points', never 'pts'", () => {
    const html = renderToStaticMarkup(
      <QuantityGroup
        sort={false}
        rungs={[
          { key: "a", label: "$300", probability: 0.62, value: 300, movement: 0.045 },
          { key: "b", label: "$350", probability: 0.38, value: 350 },
        ]}
      />,
    );
    expect(html).toContain("▲4.5 points");
    expect(html).not.toContain("pts");
  });

  it("PropTravelBar surprisePoints prints 'point' / 'points', never 'pts'", () => {
    expect(surprisePoints({ surprise: 0.01 } as SurpriseRow)).toBe("1 point");
    expect(surprisePoints({ surprise: 0.14 } as SurpriseRow)).toBe("14 points");
  });
});
