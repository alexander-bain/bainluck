import { parseCollection } from "@/lib/collections";

function makeRoundupPayload(caption?: unknown) {
  return {
    state: "published",
    slug: "celtics-next-3-games",
    revision: 42,
    edition: null,
    subtitle: "Combined win probability · next 3 games in schedule order",
    caption,
    container: {
      id: 1001,
      slug: "celtics-next-3-games",
      name: "Boston Celtics: next 3 games",
      kind: "roundup",
      category: "nba",
      status: "open",
    },
    member_count: 1,
    withheld_count: 0,
    withheld: [],
    children: [],
    sections: [
      {
        class: "title",
        title: "Next 3 games",
        layout: "field",
        count: 1,
        members: [
          {
            id: 15343971,
            type: "event",
            destination: {
              kind: "event",
              id: 15343971,
              web: "/events/15343971",
              api: "/api/events/15343971",
            },
            card: {
              id: 15343971,
              home_team: "Milwaukee Bucks",
              away_team: "Boston Celtics",
              commence_time: "2026-11-09T01:00:00Z",
              status: "scheduled",
              current_odds: { home: 0.145, away: 0.855 },
            },
          },
        ],
      },
    ],
  };
}

describe("parseCollection caption contract (#12233)", () => {
  it("admits a no-number-verified caption with timestamped, source-linked figures", () => {
    const hub = parseCollection(
      makeRoundupPayload({
        commentary:
          "Boston's upcoming stretch pairs eastern division tests with immediate tip-off readings for each game in schedule order.",
        no_number_verified: true,
        figures: [
          {
            member_id: "15343971",
            label: "at Bucks · Sun Nov 8",
            value: "86%",
            observed_at: "2026-11-08T19:20:00Z",
            as_of_label: "as of Nov 08, 19:20 UTC",
            source: "blended",
            source_href: "/events/15343971",
          },
        ],
      }),
      "celtics-next-3-games"
    );
    expect(hub.caption).not.toBeNull();
    expect(hub.caption?.noNumberVerified).toBe(true);
    expect(hub.caption?.commentary).toContain("Boston's upcoming stretch");
    expect(hub.caption?.figures).toEqual([
      {
        memberId: "15343971",
        label: "at Bucks · Sun Nov 8",
        value: "86%",
        observedAt: "2026-11-08T19:20:00Z",
        asOfLabel: "as of Nov 08, 19:20 UTC",
        source: "blended",
        sourceHref: "/events/15343971",
      },
    ]);
  });

  it("refuses any caption whose commentary contains digits or lacks no_number_verified", () => {
    const withDigit = parseCollection(
      makeRoundupPayload({
        commentary: "Boston has an 86% chance in Milwaukee.",
        no_number_verified: true,
        figures: [],
      }),
      "celtics-next-3-games"
    );
    expect(withDigit.caption).toBeNull();

    const unverified = parseCollection(
      makeRoundupPayload({
        commentary: "Boston's upcoming stretch pairs eastern division tests.",
        no_number_verified: false,
        figures: [],
      }),
      "celtics-next-3-games"
    );
    expect(unverified.caption).toBeNull();
  });
});
