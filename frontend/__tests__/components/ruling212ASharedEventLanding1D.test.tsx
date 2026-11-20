import React from "react";
import * as fs from "fs";
import * as path from "path";
import { renderToStaticMarkup } from "react-dom/server";
import {
  isSharedLinkPinBannerEnabled,
  normalizeSharedTeaserCopy,
  SharedLinkPinBanner,
  SharedMoreFromDiscoverSection,
} from "@/components/event/SharedEventLanding1D";
import { APP_STORE_APP_ID, buildAppleItunesMetaContent } from "@/lib/brandCopy";
import type { FeedItem } from "@/lib/types";

const FRONTEND_ROOT = path.join(__dirname, "..", "..");

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
              movement: 0.07, // 0.07 * 100 === 7.000000000000001 in IEEE-754; must print integer "7 points"
            },
          ],
        },
      },
      {
        type: "futures",
        score: 82,
        reason: "mover",
        headline: null,
        data: {
          id: 77702,
          name: "California winter 2026-27 wetter or drier?",
          sport: null,
          sport_name: null,
          llm_sport_category: "weather",
          source: "kalshi",
          source_count: 1,
          market_tier: 1,
          status: "open",
          resolution_date: "2027-03-31T19:00:00Z",
          outcome_count: 2,
          canonical_market_key: null,
          top_outcomes: [
            {
              id: 2,
              name: "Wetter",
              probability: 0.61,
              rendered_percent: 61,
              rank: 1,
              movement: -0.29, // -0.29 * 100 === -28.999999999999996 in IEEE-754; must print integer "29 points"
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
    // Futures teaser strips leading "Will the" and prints rounded integer "points", never float garbage or "pts"
    expect(html).toContain("Fed cut interest rates in December");
    expect(html).toContain("up 7 points");
    expect(html).toContain("down 29 points");
    expect(html).not.toContain("7.000");
    expect(html).not.toContain("28.999");
    expect(html).toContain("Moved +9 points after CPI report");
    expect(html).not.toMatch(/\bpts\b/i);
    expect(html).not.toContain("Projected: PIT");
    expect(html).toContain("See sports, awards, tech &amp; economy");
  });

  it("uses Apple's Smart App Banner site-wide (and on /events and /futures deep links) instead of a custom Get-the-app button", () => {
    const rootLayout = fs.readFileSync(path.join(FRONTEND_ROOT, "app", "layout.tsx"), "utf8");
    const eventLayout = fs.readFileSync(
      path.join(FRONTEND_ROOT, "app", "events", "[id]", "layout.tsx"),
      "utf8",
    );
    const futuresLayout = fs.readFileSync(
      path.join(FRONTEND_ROOT, "app", "futures", "[id]", "layout.tsx"),
      "utf8",
    );

    expect(rootLayout).toContain("itunes: { appId: APP_STORE_APP_ID }");
    expect(eventLayout).toContain("itunes: { appId: APP_STORE_APP_ID, appArgument: url }");
    expect(futuresLayout).toContain("itunes: { appId: APP_STORE_APP_ID, appArgument: url }");

    expect(buildAppleItunesMetaContent("https://www.bainluck.com/events/14780579", null)).toBe(
      `app-id=${APP_STORE_APP_ID}, app-argument=https://www.bainluck.com/events/14780579`,
    );
    expect(
      buildAppleItunesMetaContent(
        "https://www.bainluck.com/events/14780579",
        "com.bainluck.Bain-Luck.Clip",
      ),
    ).toBe(
      `app-id=${APP_STORE_APP_ID}, app-clip-bundle-id=com.bainluck.Bain-Luck.Clip, app-argument=https://www.bainluck.com/events/14780579`,
    );
  });

  it("keeps the Pin-for-swing-alerts banner OFF by default until 1.0.8 alerts exist, and never renders a custom Get-the-app button", () => {
    expect(isSharedLinkPinBannerEnabled(undefined)).toBe(false);
    expect(isSharedLinkPinBannerEnabled("0")).toBe(false);
    expect(isSharedLinkPinBannerEnabled("1")).toBe(true);

    const defaultOffHtml = renderToStaticMarkup(
      <SharedLinkPinBanner isPinned={false} pinDisabled={false} onPinToggle={() => {}} />,
    );
    expect(defaultOffHtml).toBe("");

    const enabledUnpinnedHtml = renderToStaticMarkup(
      <SharedLinkPinBanner
        enabled={true}
        isPinned={false}
        pinDisabled={false}
        onPinToggle={() => {}}
      />,
    );
    expect(enabledUnpinnedHtml).toContain("Pin for swing alerts");
    expect(enabledUnpinnedHtml).not.toContain("Get the app");
    expect(enabledUnpinnedHtml).toContain('aria-label="Pin game"');

    const enabledPinnedHtml = renderToStaticMarkup(
      <SharedLinkPinBanner
        enabled={true}
        isPinned={true}
        pinDisabled={false}
        onPinToggle={() => {}}
      />,
    );
    expect(enabledPinnedHtml).toContain("Pinned on this browser");
    expect(enabledPinnedHtml).not.toContain("Get the app");
    expect(enabledPinnedHtml).toContain('aria-label="Unpin game"');

    const maxPinsHtml = renderToStaticMarkup(
      <SharedLinkPinBanner
        enabled={true}
        isPinned={false}
        pinDisabled={true}
        onPinToggle={() => {}}
      />,
    );
    expect(maxPinsHtml).toContain('title="Max 6 pins"');
  });
});
