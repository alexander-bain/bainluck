import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

let swrPayload: unknown = null;
jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: undefined, isLoading: false }),
}));

import RelatedByTag from "@/components/RelatedByTag";

describe("#13807 RelatedByTag rail does not truncate team names", () => {
  it("wraps long finished and live team names such as Minnesota Timberwolves without truncate", () => {
    swrPayload = {
      items: [
        {
          type: "event",
          score: 90,
          data: {
            id: 15349001,
            sport: "basketball_nba",
            status: "completed",
            away_team: "Minnesota Timberwolves",
            home_team: "Oklahoma City Thunder",
            away_score: 113,
            home_score: 106,
            winner: "away",
            pre_game_probability: { away: 0.44, home: 0.56, source: "consensus" },
          },
        },
        {
          type: "event",
          score: 85,
          data: {
            id: 15349002,
            sport: "basketball_nba",
            status: "live",
            away_team: "Portland Trail Blazers",
            home_team: "Minnesota Timberwolves",
            away_score: 64,
            home_score: 68,
            current_odds: {
              away_probability: 0.38,
              home_probability: 0.62,
              away_rendered_percent: 38,
              home_rendered_percent: 62,
            },
          },
        },
      ],
    };

    const html = renderToStaticMarkup(
      <RelatedByTag tags={["sport:basketball"]} excludeId={15348075} excludeType="event" limit={4} />
    );

    expect(html).toContain("Minnesota Timberwolves");
    expect(html).toContain("Oklahoma City Thunder");
    expect(html).toContain("Portland Trail Blazers");
    expect(html).toContain("break-words");
    expect(html).not.toMatch(/class="[^"]*\btruncate\b[^"]*"[^>]*>Minnesota Timberwolves/);
  });
});
