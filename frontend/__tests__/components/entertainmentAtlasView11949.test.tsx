import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import EntertainmentAtlasView from "@/components/entertainment/EntertainmentAtlasView";
import { findBannedCopy, JARGON_BANS, visibleTextFromHtml } from "@/lib/copyBans";

describe("EntertainmentAtlasView (#11949 Order 10 + #12126/#12128 guards)", () => {
  it("renders entertainment markets while refusing blank outcome labels, keeping missing source null, and avoiding banned copy", () => {
    const data: any = {
      total_markets: 3,
      updated_at: "2026-11-06T12:00:00Z",
      trending: [
        {
          market_id: 701,
          q: "Oscar Best Picture Winner",
          prob: 50,
          src: "",
          external_id: "",
          kind: "multi",
          outcome_count: 3,
          top_outcomes: [
            { name: "Anora", prob: 50, delta_24h: 2 },
            { name: "   ", prob: 99, delta_24h: 0 },
            { name: "The Brutalist", prob: 33, delta_24h: -1 },
          ],
        },
      ],
      themes: {
        music: {
          count: 1,
          spotify_race: [],
          billboard_watch: [],
          billboard_groups: [
            {
              title: "Hot 100 Thresholds",
              image_url: null,
              thresholds: [
                { label: "≥80", prob: 65, market_id: 702 },
                { label: "   ", prob: 95, market_id: 703 },
                { label: "≥60", prob: 88, market_id: 704 },
              ],
            },
          ],
          album_drops: [],
          artist_streaming: [],
          side_markets: [
            {
              market_id: 705,
              q: "   ",
              prob: 50,
              src: "",
              external_id: "",
              kind: "binary",
              outcome_count: 2,
              top_outcomes: [{ name: "   ", prob: 50, delta_24h: 0 }],
            },
          ],
        },
        movies_tv: {
          count: 1,
          rt_groups: [],
          rt_markets: [],
          box_office_groups: [],
          box_office: [],
          reality_tv: [],
          side_markets: [],
        },
        tech_culture: {
          count: 0,
          markets: [],
        },
      },
      cultural_moments: [],
    };

    const html = renderToStaticMarkup(
      React.createElement(EntertainmentAtlasView, { data })
    );
    expect(html).toContain('data-testid="entertainment-atlas-view"');
    expect(html).toContain("Anora");
    expect(html).toContain("The Brutalist");
    expect(html).toContain("≥60");
    expect(html).toContain("≥80");
    expect(html).not.toContain("/futures/705");

    // Missing source stays null — never defaults to "Kalshi"
    expect(html).not.toMatch(/Kalshi/i);
    // No banned copy ("blend", etc.)
    expect(findBannedCopy(visibleTextFromHtml(html), JARGON_BANS)).toEqual([]);
  });
});
