// L2-175 Item 2a/2b/2c: the Tour de France concept page, exam-ready.
//  - EventProps stage cards render GRADED (winner + "Won") for a settled stage and
//    NEVER two riders at 90%+; an upcoming stage shows an honest label, not empty.
//  - EventLeaderboard's GC list defaults to Top 5 (not the full ~1% tail) and
//    exposes a Top 5 / Top 10 / Full toggle.
// Guards both directions per gotcha #43: the flood is capped AND the real content
// (leader + graded winner) still renders.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import EventProps from "../../components/event/EventProps";
import EventLeaderboard from "../../components/event/EventLeaderboard";
import type { EventConceptChild, EventConceptCompetitor } from "../../lib/types";

const stage = (over: Partial<EventConceptChild>): EventConceptChild =>
  ({ kind: "prop", prop_type: "stage", ...over }) as EventConceptChild;

describe("EventProps — cycling stage cards, graded / upcoming / live (L2-175 Item 2b)", () => {
  test("a settled stage (two stale 90%+ prices) renders the winner + Won, not two riders at 90%+", () => {
    const children: EventConceptChild[] = [
      stage({
        market_id: 1,
        market_name: "Tour de France: Stage 1 Winner",
        outcomes: [
          { name: "Jonas Vingegaard", probability: 0.99 },
          { name: "Kevin Vauquelin", probability: 0.94 },
        ],
      }),
    ];
    const html = renderToStaticMarkup(<EventProps items={children} domain="cycling" />);
    expect(html).toContain("Jonas Vingegaard");
    expect(html).toContain(">Won<");
    // The stale runner-up (94%) must NOT be shown as a second near-winner.
    expect(html).not.toContain("Kevin Vauquelin");
    expect(html).not.toContain("94%");
  });

  test("an upcoming stage (no priced outcomes) shows an honest label, not an empty card", () => {
    const children: EventConceptChild[] = [
      stage({ market_id: 2, market_name: "Tour de France: Stage 20 Winner", outcomes: [], commence_time: null }),
    ];
    const html = renderToStaticMarkup(<EventProps items={children} domain="cycling" />);
    expect(html).toContain("Stage 20");
  });

  test("a genuine live stage still shows top-2 priced riders with bars", () => {
    const children: EventConceptChild[] = [
      stage({
        market_id: 3,
        market_name: "Tour de France: Stage 6 Winner",
        outcomes: [
          { name: "Tadej Pogacar", probability: 0.627 },
          { name: "Ben O Connor", probability: 0.12 },
        ],
      }),
    ];
    const html = renderToStaticMarkup(<EventProps items={children} domain="cycling" />);
    expect(html).toContain("Tadej Pogacar");
    expect(html).toContain("Ben O Connor");
    expect(html).toContain("bg-accent-futures"); // the probability bar
    expect(html).not.toContain(">Won<");
  });
});

describe("EventLeaderboard — GC Top 5 / Top 10 / Full toggle (L2-175 Item 2a)", () => {
  // A 12-rider field, all priced above the 0.5% contender floor (the "1% tail").
  const field: EventConceptCompetitor[] = Array.from({ length: 12 }, (_, i) => ({
    name: `Rider ${i + 1}`,
    probability: i === 0 ? 0.9 : 0.05 - i * 0.001,
  }));

  const html = renderToStaticMarkup(
    <EventLeaderboard competitors={field} label="General Classification" domain="cycling" />,
  );

  test("defaults to Top 5 — the leader shows, the deep tail does not", () => {
    expect(html).toContain("Rider 1"); // leader
    expect(html).toContain("Rider 5"); // last of the default view
    expect(html).not.toContain("Rider 6"); // capped by the Top 5 default
    expect(html).not.toContain("Rider 12");
  });

  test("exposes the Top 5 / Top 10 / Full toggle", () => {
    expect(html).toContain("Top 5");
    expect(html).toContain("Top 10");
    expect(html).toContain("Full 12");
  });

  test("a small field (<=5) renders without a toggle", () => {
    const small: EventConceptCompetitor[] = [
      { name: "Alpha", probability: 0.6 },
      { name: "Bravo", probability: 0.4 },
    ];
    const h = renderToStaticMarkup(<EventLeaderboard competitors={small} label="GC" domain="cycling" />);
    expect(h).toContain("Alpha");
    expect(h).not.toContain("Full 2");
  });
});
