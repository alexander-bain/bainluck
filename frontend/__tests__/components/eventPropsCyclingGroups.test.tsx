// L2-146 Item 1: the Tour de France concept page hangs 21 stage winners + a team
// classification + 2 jersey markets off the GC winner-field leaderboard as prop
// children (prop_type stage/team/jersey — set ONLY by event_cycling.py). Before
// this fix EventProps had no group for those types, so all 24 collapsed into one
// undifferentiated "Other props" bucket on a page that gets real traffic when the
// Tour finishes in Paris. This asserts they render under proper cycling headings.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import EventProps from "../../components/event/EventProps";
import type { EventConceptChild, EventConceptSection } from "../../lib/types";

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

// L2-147 Item 4: the backend emits a structured `sections` split (market_ids per
// section). When present, EventProps groups children by the section that claims
// their id — the backend owns the split — instead of re-deriving from prop_type.
describe("EventProps — data.sections consumption (L2-147 Item 4)", () => {
  const children: EventConceptChild[] = [
    cyclingChild(101, "Tour de France: Stage 1 Winner", "stage"),
    cyclingChild(102, "Tour de France: Stage 2 Winner", "stage"),
    cyclingChild(103, "Tour de France: Green Jersey", "jersey"),
  ];
  const sections: EventConceptSection[] = [
    { type: "gc", label: "General Classification", market_ids: [999] },
    { type: "stages", label: "Daily Stages", market_ids: [101, 102] },
    { type: "jerseys", label: "Classifications & Jerseys", market_ids: [103] },
  ];

  test("groups by backend section label (not the prop_type label) when sections claim the children", () => {
    const html = renderToStaticMarkup(
      <EventProps items={children} sections={sections} />,
    );
    // Backend-owned labels win over EventProps' prop_type labels. (renderToStatic
    // escapes "&" → "&amp;", so match the distinctive stem.)
    expect(html).toContain("Daily Stages");
    expect(html).toContain("Classifications &amp; Jerseys");
    // The prop_type "Stages"/"Jerseys" labels are NOT used when sections drive it.
    expect(html).not.toContain("Team classification");
    // Empty sections (GC claims no rendered child) are dropped, not shown empty.
    expect(html).not.toContain("General Classification");
    // Every market still renders.
    expect(html).toContain("Tour de France: Stage 1 Winner");
    expect(html).toContain("Tour de France: Green Jersey");
  });

  test("children not claimed by any section fall back to prop_type grouping (additive, never lossy)", () => {
    const withUnclaimed = [
      ...children,
      cyclingChild(200, "Tour de France Team Winner", "team"),
    ];
    const html = renderToStaticMarkup(
      <EventProps items={withUnclaimed} sections={sections} />,
    );
    expect(html).toContain("Daily Stages"); // section-driven
    expect(html).toContain("Team classification"); // prop_type fallback for #200
    expect(html).toContain("Tour de France Team Winner");
  });

  test("absent/empty sections keep the prop_type grouping (unchanged behavior)", () => {
    const html = renderToStaticMarkup(
      <EventProps items={children} sections={[]} />,
    );
    expect(html).toContain("Stages"); // prop_type label
    expect(html).toContain("Jerseys");
  });
});

// L2-148: golf tags per-round Top-N children kind:"prop" but only its round-LEADER
// markets reach the props-script; the round_top family was computed into propChildren
// then dropped when the page rendered PropsSection XOR EventProps. EventProps now
// renders alongside the props-script as a SECONDARY section — it takes an optional
// title/anchorId so that instance reads "More props"/#more-props instead of colliding
// with the primary "Props"/#props.
describe("EventProps — secondary title/anchor override (L2-148)", () => {
  const items: EventConceptChild[] = [
    cyclingChild(301, "Round 1 Top 5", "round"),
  ];

  test("defaults to the Props heading and #props anchor (unchanged)", () => {
    const html = renderToStaticMarkup(<EventProps items={items} />);
    expect(html).toContain('id="props"');
    expect(html).toContain(">Props<");
  });

  test("renders a custom heading + anchor when supplied", () => {
    const html = renderToStaticMarkup(
      <EventProps items={items} title="More props" anchorId="more-props" />,
    );
    expect(html).toContain('id="more-props"');
    expect(html).toContain(">More props<");
    // The default identity is NOT used when overridden.
    expect(html).not.toContain('id="props"');
  });

  test("self-suppresses (renders nothing) when there are no items — the common no-leftover case", () => {
    const html = renderToStaticMarkup(
      <EventProps items={[]} title="More props" anchorId="more-props" />,
    );
    expect(html).toBe("");
  });
});
