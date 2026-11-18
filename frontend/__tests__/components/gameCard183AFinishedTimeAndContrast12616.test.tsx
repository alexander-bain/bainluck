import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import EventCard183A, {
  buildUnifiedCardFromEvent,
  buildUnifiedCardFromFeed,
  resolveLiveSummarySideInk,
} from "@/components/EventCard183A";
import { contrastVsCardSurface, darkenTeamColorForCardText } from "@/lib/teamColors";
import type { Event, FeedEventData, FeedItem } from "@/lib/types";

jest.mock("next/link", () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const R = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) =>
      R.createElement("a", { href, ...rest }, children),
  };
});

describe("#12616 — finished game start-time label & >=4.5:1 Chance text contrast", () => {
  it("prints a finished game's scheduled start time (commence_time), never completed_at", () => {
    // Chargers at Ravens: kicked off Yesterday 5:15 PM PT (01:15 UTC), finished 8:25 PM PT (04:25 UTC)
    const nowSpy = jest
      .spyOn(Date, "now")
      .mockReturnValue(Date.parse("2026-11-17T18:00:00Z"));
    try {
      const ev = {
        id: 15349001,
        sport: "americanfootball_nfl",
        sport_name: "NFL",
        away_team: "Los Angeles Chargers",
        home_team: "Baltimore Ravens",
        commence_time: "2026-11-17T01:15:00Z",
        completed_at: "2026-11-17T04:25:00Z",
        status: "completed",
        away_score: 23,
        home_score: 20,
        prematch_odds: {
          away_probability: 0.32,
          home_probability: 0.68,
        },
      } as unknown as Event;

      const expectedKickoff = new Date("2026-11-17T01:15:00Z").toLocaleTimeString("en-US", {
        hour: "numeric",
        minute: "2-digit",
      });
      const wrongEnd = new Date("2026-11-17T04:25:00Z").toLocaleTimeString("en-US", {
        hour: "numeric",
        minute: "2-digit",
      });

      const html = renderToStaticMarkup(
        <EventCard183A card={buildUnifiedCardFromEvent(ev)} surface="standard" />,
      );
      expect(html).toContain(expectedKickoff);
      expect(html).not.toContain(wrongEnd);
    } finally {
      nowSpy.mockRestore();
    }
  });

  it("darkens New Orleans Saints gold (#D3BC8D) and every <4.5:1 team colour on Chance numbers until contrast >= 4.5:1", () => {
    const rawSaintsRatio = contrastVsCardSurface("#D3BC8D")!;
    expect(rawSaintsRatio).toBeLessThan(2.5);

    const darkenedSaints = darkenTeamColorForCardText("#D3BC8D", 4.5);
    expect(contrastVsCardSurface(darkenedSaints)!).toBeGreaterThanOrEqual(4.5);
    expect(resolveLiveSummarySideInk("#D3BC8D")).toBe(darkenedSaints);

    for (const lightHex of ["#FFB612", "#FFC20E", "#008E97", "#4B92DB", "#FB4F14", "#FFFFFF"]) {
      const safeHex = darkenTeamColorForCardText(lightHex, 4.5);
      expect(contrastVsCardSurface(safeHex)!).toBeGreaterThanOrEqual(4.5);
    }

    // Already >=4.5:1 dark colours remain untouched
    expect(darkenTeamColorForCardText("#0076B6", 4.5).toLowerCase()).toBe("#0076b6");
    expect(darkenTeamColorForCardText("#041E42", 4.5).toLowerCase()).toBe("#041e42");

    const saintsAtBears = {
      id: 15349099,
      sport: "americanfootball_nfl",
      sport_name: "NFL",
      away_team: "New Orleans Saints",
      home_team: "Chicago Bears",
      commence_time: "2026-11-22T18:00:00Z",
      status: "scheduled",
      away_team_data: { name: "New Orleans Saints", primary_color: "#D3BC8D" },
      home_team_data: { name: "Chicago Bears", primary_color: "#C83803" },
      current_odds: { away_probability: 0.15, home_probability: 0.85 },
    } as unknown as Event;

    const html = renderToStaticMarkup(
      <EventCard183A card={buildUnifiedCardFromEvent(saintsAtBears)} surface="standard" />,
    );
    expect(html.toLowerCase()).not.toContain('style="color:#d3bc8d"');
    expect(html.toLowerCase()).toContain(`style="color:${darkenedSaints}" data-testid="primary-chance-away">15%<`);
  });

  it("drops the comma in older finished weekday dates ('Sun Nov 15', not 'Sun, Nov 15')", () => {
    const nowSpy = jest
      .spyOn(Date, "now")
      .mockReturnValue(Date.parse("2026-11-17T20:00:00Z"));
    try {
      const ev = {
        id: 15348001,
        sport: "americanfootball_nfl",
        sport_name: "NFL",
        away_team: "New England Patriots",
        home_team: "Detroit Lions",
        commence_time: "2026-11-15T18:00:00Z",
        completed_at: "2026-11-15T21:12:00Z",
        status: "completed",
        away_score: 10,
        home_score: 35,
        prematch_odds: { away_probability: 0.42, home_probability: 0.58 },
      } as unknown as Event;

      const html = renderToStaticMarkup(
        <EventCard183A card={buildUnifiedCardFromEvent(ev)} surface="standard" />,
      );
      expect(html).toContain("Sun Nov 15");
      expect(html).not.toContain("Sun, Nov 15");
    } finally {
      nowSpy.mockRestore();
    }
  });

  it("draws the same finished collection card after latest bookmaker fields are omitted", () => {
    const data: FeedEventData = {
      id: 14639206,
      external_id: "week-10-finished-game",
      sport: "americanfootball_nfl",
      sport_name: "NFL",
      away_team: "New England Patriots",
      home_team: "Detroit Lions",
      commence_time: "2026-11-15T18:00:00Z",
      ended_at: "2026-11-15T21:12:00Z",
      status: "completed",
      away_score: 10,
      home_score: 35,
      prematch_odds: { away_probability: 0.42, home_probability: 0.58, source: "kalshi" },
      opening_odds: { away_probability: 0.46, home_probability: 0.54, favorite: "home" },
    };
    const draw = (served: FeedEventData) => {
      const item: FeedItem = { type: "event", score: 0, reason: "", headline: null, data: served };
      return renderToStaticMarkup(<EventCard183A card={buildUnifiedCardFromFeed(item, served)} surface="standard" />);
    };
    const before = draw({
      ...data,
      current_odds: { away_probability: 0.02, home_probability: 0.98 },
    });
    const after = draw(data);

    expect(after).toBe(before);
    expect(after).toContain("42%");
    expect(after).toContain("58%");
    expect(after).not.toContain(">98%<");
  });
});
