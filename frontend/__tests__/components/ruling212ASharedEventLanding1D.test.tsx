import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  normalizeSharedTeaserCopy,
  SharedLinkPinBanner,
  SharedMoreFromDiscoverSection,
} from "@/components/event/SharedEventLanding1D";
import { APP_STORE_URL } from "@/lib/brandCopy";
import type { FeedItem } from "@/lib/types";

describe("Ruling 212-A (#11934 Step 1D) — Shared-link web landing", () => {
  it("normalizes 'pts' to 'points' and suppresses raw 'Will ...' question copy", () => {
    expect(normalizeSharedTeaserCopy("Up +4.6 pts after CPI report")).toBe(
      "Up +4.6 points after CPI report",
    );
    expect(normalizeSharedTeaserCopy("Moved 3 pts this week")).toBe(
      "Moved 3 points this week",
    );
    expect(normalizeSharedTeaserCopy("Will the Fed cut rates in December?")).toBeNull();
  });

  it("renders game teasers via shipped EventCard183A and futures teasers with 'points' (never 'pts')", () => {
    const seedItems: FeedItem[] = [
      {
        type: "event",
        score: 90,
        reason: "featured",
        headline: "Celtics slight road favourites",
        data: {
          id: 999,
          sport: "basketball_nba",
          sport_name: "NBA",
          home_team: "Milwaukee Bucks",
          away_team: "Boston Celtics",
          commence_time: "2026-11-18T00:30:00Z",
          status: "scheduled",
          current_odds: {
            home_probability: 0.39,
            away_probability: 0.61,
            home_rendered_percent: 39,
            away_rendered_percent: 61,
            bookmaker_count: 10,
            projected_home_score: 112.5,
            projected_away_score: 116.5,
          },
          home_team_data: {
            name: "Milwaukee Bucks",
            abbreviation: "MIL",
            primary_color: "#00471B",
          },
          away_team_data: {
            name: "Boston Celtics",
            abbreviation: "BOS",
            primary_color: "#007A33",
            secondary_color: "#BA9653",
          },
        } as never,
      },
      {
        type: "futures",
        score: 85,
        reason: "mover",
        headline: "Moved +9 pts after CPI report",
        data: {
          id: 77701,
          name: "Will the Fed cut interest rates in December?",
          sport: null,
          sport_name: null,
          llm_sport_category: "economics",
          source: "kalshi",
          source_count: 2,
          market_tier: 1,
          status: "open",
          resolution_date: "2026-12-18T19:00:00Z",
          outcome_count: 2,
          canonical_market_key: null,
          top_outcomes: [
            {
              id: 1,
              name: "Yes",
              probability: 0.72,
              rendered_percent: 72,
              rank: 1,
              movement: 0.09,
            },
          ],
        },
      },
    ];

    const html = renderToStaticMarkup(
      <SharedMoreFromDiscoverSection currentEventId={123} seedItems={seedItems} />,
    );

    expect(html).toContain("More of what the world thinks now");
    expect(html).toContain('data-testid="shared-landing-event-teaser"');
    // Shipped EventCard183A renders Proj. · Chance columns on scheduled games
    expect(html).toContain("Proj.");
    expect(html).toContain("Chance");
    // Futures teaser strips leading "Will the" and prints "points", never "pts"
    expect(html).toContain("Fed cut interest rates in December");
    expect(html).toContain("up 9 points");
    expect(html).toContain("Moved +9 points after CPI report");
    expect(html).not.toMatch(/\bpts\b/i);
    expect(html).not.toContain("Projected: PIT");
    expect(html).toContain("See sports, awards, tech &amp; economy");
  });

  it("renders the fixed bottom Pin & Get-the-app banner with bookmark PinIcon and canonical App Store URL", () => {
    const unpinnedHtml = renderToStaticMarkup(
      <SharedLinkPinBanner isPinned={false} pinDisabled={false} onPinToggle={() => {}} />,
    );
    expect(unpinnedHtml).toContain("Pin for swing alerts");
    expect(unpinnedHtml).toContain("Free Bain Luck app · No sign-in");
    expect(unpinnedHtml).toContain(`href="${APP_STORE_URL}"`);
    expect(unpinnedHtml).toContain("Get the app");
    expect(unpinnedHtml).toContain('aria-label="Pin game"');

    const pinnedHtml = renderToStaticMarkup(
      <SharedLinkPinBanner isPinned={true} pinDisabled={false} onPinToggle={() => {}} />,
    );
    expect(pinnedHtml).toContain("Pinned on this browser");
    expect(pinnedHtml).toContain('aria-label="Unpin game"');
  });
});
