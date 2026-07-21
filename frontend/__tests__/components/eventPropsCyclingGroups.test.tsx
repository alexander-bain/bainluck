// L2-146 Item 1: the Tour de France concept page hangs 21 stage winners + a team
// classification + 2 jersey markets off the GC winner-field leaderboard as prop
// children (prop_type stage/team/jersey — set ONLY by event_cycling.py). Before
// this fix EventProps had no group for those types, so all 24 collapsed into one
// undifferentiated "Other props" bucket on a page that gets real traffic when the
// Tour finishes in Paris. This asserts they render under proper cycling headings.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import EventProps from "../../components/event/EventProps";
import type { EventConceptChild } from "../../lib/types";

function cyclingChild(
  market_id: number,
  market_name: string,
  prop_type: string,
): EventConceptChild {
  return {
    market_id,
    market_name,
    kind: "prop",
    prop_type,
    outcomes: [
      { name: "Tadej Pogacar", probability: 0.62 },
      { name: "Jonas Vingegaard", probability: 0.24 },
    ],
  } as unknown as EventConceptChild;
}

describe("EventProps — cycling grand-tour grouping (L2-146 Item 1)", () => {
  const children: EventConceptChild[] = [
    cyclingChild(1, "Tour de France: Stage 1 Winner", "stage"),
    cyclingChild(2, "Tour de France: Stage 2 Winner", "stage"),
    cyclingChild(3, "Tour de France Team Winner", "team"),
    cyclingChild(4, "Tour de France: Green Jersey Winner", "jersey"),
    cyclingChild(5, "Tour de France: Polka Dot Jersey Winner", "jersey"),
  ];

  const html = renderToStaticMarkup(<EventProps items={children} />);

  test("renders dedicated Stages / Team classification / Jerseys headings", () => {
    expect(html).toContain("Stages");
    expect(html).toContain("Team classification");
    expect(html).toContain("Jerseys");
  });

  test("does not dump cycling markets into the generic Other props bucket", () => {
    expect(html).not.toContain("Other props");
  });

  test("renders every stage/jersey/team market by name", () => {
    expect(html).toContain("Tour de France: Stage 1 Winner");
    expect(html).toContain("Tour de France: Stage 2 Winner");
    expect(html).toContain("Tour de France Team Winner");
    expect(html).toContain("Tour de France: Green Jersey Winner");
    expect(html).toContain("Tour de France: Polka Dot Jersey Winner");
  });

  test("an unknown prop_type still falls back to Other props (regression guard)", () => {
    const withUnknown = [
      ...children,
      cyclingChild(9, "Mystery Market", "totally-unknown-type"),
    ];
    const h = renderToStaticMarkup(<EventProps items={withUnknown} />);
    expect(h).toContain("Other props");
    expect(h).toContain("Mystery Market");
  });
});
