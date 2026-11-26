/**
 * #13720 — Cut-off text fixes across Discover and Game Page at 390 px and 1280 px.
 *
 * Covers every defect filed in #13720:
 * 1. DeadlineFamilyCard eyebrow uses the short category label when sharedQuestion
 *    is present, keeping #6929 constraints intact without clipping the 52-char stem.
 * 2. DeadlineFamilyCard `Selected deadline` badge wraps cleanly without `truncate`.
 * 3. ComparisonCard leaderboard outcome labels wrap with `min-w-0 break-words` instead of `truncate`.
 * 4. MachineryDiscoverCard podium tile titles omit `line-clamp-2` so full names render.
 * 5. MarketBrowser category pills wrap on all viewports (`flex-wrap`, no `overflow-x-auto`).
 * 6. RelatedFutures compact side-column team cards stack 1-column so PlayerAwardsList keeps room.
 */

import fs from "fs";
import path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { FeedFuturesData, FeedItem } from "@/lib/types";
import type { DeadlineFamilyCardModel } from "@/lib/discover/deadlineFamilyCard";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
  usePathname: () => "/discover",
  useSearchParams: () => new URLSearchParams(),
}));

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));

jest.mock("@/lib/analytics", () => ({ trackEvent: () => {} }));
jest.mock("@/lib/discoverInteractions", () => ({
  getDiscoverItemAnalytics: () => ({}),
  recordDiscoverInteraction: () => {},
  sendDiscoverInteraction: () => {},
}));
jest.mock("@/components/Analytics/AnalyticsProvider", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
  AnalyticsProvider: ({ children }: { children: React.ReactNode }) => children,
}));

import DiscoverCard from "@/components/DiscoverCard";
import { DeadlineFamilyCard } from "@/components/discover/DeadlineFamilyCard";
import MarketBrowser from "@/components/event/MarketBrowser";
import {
  MachineryDiscoverCard,
  type MachineryCardContract,
} from "@/components/collections/MachinerySectionRenderer";

describe("#13720 — Cut-off text fixes on Discover and Game Page", () => {
  test("DeadlineFamilyCard uses short category eyebrow above sharedQuestion and never truncates Selected deadline", () => {
    const model: DeadlineFamilyCardModel = {
      storyKey: "story:deadline_family:polymarket:1448088",
      source: "polymarket",
      groupId: "polymarket:1448088",
      title: "Jensen Huang announced resignation or removal again",
      sharedQuestion: "Jensen Huang announced resignation or removal again by…?",
      category: "tech",
      familyState: "open",
      ruleTemplateHash: "hash",
      cutoffTimezone: "America/New_York",
      cutoffLocalTime: "23:59",
      selectionReason: "nearest_50_pct_fallback",
      selectionBadgeText: "Selected deadline",
      tieBreakRule: "abs_supported_move_desc",
      representedCount: 3,
      verifiedFamilyCount: 3,
      providerMarketCount: 3,
      inventoryComplete: true,
      expandLabel: "All 3 deadlines",
      collapseLabel: "Hide deadlines",
      representative: {
        marketId: 72067051,
        name: "Will Jensen Huang announce resignation or removal by December 31?",
        deadlineLabel: "By Dec 31",
        yesOutcomeId: 101,
        yesProbability: 0.04,
        yesPercentText: "4%",
        barWidthPercent: 4,
        priceObservedAt: null,
        movementStatus: "none",
        showHeroMovementChip: false,
        heroMovementChipText: null,
        isSettled: false,
        isNearCertain: false,
        settledText: null,
        accessibleLabel: "By Dec 31 — 4%",
        detailHref: "/futures/72067051",
      } as unknown as DeadlineFamilyCardModel["representative"],
      members: [],
    } as unknown as DeadlineFamilyCardModel;

    const html = renderToStaticMarkup(<DeadlineFamilyCard model={model} />);
    const eyebrowMatch = html.match(/data-testid="bundle-eyebrow"[^>]*>([^<]+)</);
    expect(eyebrowMatch?.[1]).toContain("tech");
    expect(eyebrowMatch?.[1]).not.toContain("JENSEN HUANG");

    const badgeMatch = html.match(/class="([^"]*)"[^>]*data-testid="deadline-family-selection-badge"/);
    expect(badgeMatch).not.toBeNull();
    expect(badgeMatch![1]).not.toContain("truncate");
  });

  test("Both FuturesCard (3-outcome board) and ComparisonCard (4-outcome board) wrap Flower In A Hurricane with min-w-0 break-words instead of truncate", () => {
    const outcomes = [
      {
        id: 1,
        name: "Flower In A Hurricane - Justice, Tame Impala, SZA, King Gizzard & the Lizard Wizard",
        probability: 0.76,
        rendered_percent: 76,
      },
      { id: 2, name: "Stop The Wedding! - Ashe", probability: 0.21, rendered_percent: 21 },
      { id: 3, name: "Nicole Kidman - ADÉLA", probability: 0.01, rendered_percent: 1 },
      { id: 4, name: "Other", probability: 0.02, rendered_percent: 2 },
    ];
    const distOutcomes = outcomes.map((o) => ({
      label: o.name,
      probability: o.probability,
      rendered_percent: o.rendered_percent,
      movement: null,
    }));
    for (const topCount of [3, 4]) {
      const item = {
        type: "futures",
        score: 75,
        reason: "",
        headline: null,
        data: {
          id: 71237975,
          name: "#1 Spotify song this week? (November 27)",
          llm_sport_category: "entertainment",
          market_type: "field",
          status: "open",
          outcome_count: 10,
          discover_card: {
            suggested_format: "outcome_distribution",
            field_is_a_race: true,
            distribution_outcomes: distOutcomes,
          },
          top_outcomes: outcomes.slice(0, topCount),
        } as unknown as FeedFuturesData,
      } as unknown as FeedItem;

      const html = renderToStaticMarkup(
        <DiscoverCard groupedItem={{ type: "single", item }} positionIndex={0} />,
      );
      const titleMatch = html.match(
        /<span class="([^"]*)" title="Flower In A Hurricane - Justice, Tame Impala, SZA, King Gizzard &amp; the Lizard Wizard">/,
      );
      expect(titleMatch).not.toBeNull();
      expect(titleMatch![1]).toContain("min-w-0");
      expect(titleMatch![1]).toContain("break-words");
      expect(titleMatch![1]).not.toContain("truncate");
    }
  });

  test("MachineryDiscoverCard podium tiles do not clamp candidate names with line-clamp-2", () => {
    const card: MachineryCardContract = {
      slug: "machinery-2028-presidential",
      destination_href: "/collections/machinery-2028-presidential",
      kicker: "POLITICS · 2028",
      title: "2028 Presidential",
      subtitle: "",
      footer: "",
      section_count: 1,
      form_id: "contender_spotlight",
      rows: [
        { outcome_id: 1, name: "Alexandria Ocasio-Cortez", probability: 0.14, rendered_percent: 14 },
        { outcome_id: 2, name: "Gavin Newsom", probability: 0.22, rendered_percent: 22 },
        { outcome_id: 3, name: "JD Vance", probability: 0.28, rendered_percent: 28 },
      ],
    };
    const html = renderToStaticMarkup(<MachineryDiscoverCard card={card} />);
    expect(html).toContain('data-testid="machinery-spotlight-tile"');
    expect(html).toContain("Alexandria Ocasio-Cortez");
    expect(html).toContain("break-words");
    expect(html).not.toContain("line-clamp-2");
  });

  test("MarketBrowser wraps category pills on mobile as well as desktop (no overflow-x-auto)", () => {
    const html = renderToStaticMarkup(
      <MarketBrowser
        label="Player props"
        items={[
          { key: "p1", group: "Points", search: "Player Points", content: <div>Points</div> },
          { key: "r1", group: "Rebounds", search: "Player Rebounds", content: <div>Rebounds</div> },
        ]}
      />,
    );
    expect(html).toContain("basis-full flex flex-wrap gap-1.5");
    expect(html).not.toContain("overflow-x-auto");
  });

  test("RelatedFutures stacks Team Cards in a single column inside compact desktop side column", () => {
    const src = fs.readFileSync(
      path.join(process.cwd(), "components/RelatedFutures.tsx"),
      "utf8",
    );
    expect(src).toContain(
      'compact ? "grid grid-cols-1 gap-4" : "grid grid-cols-1 md:grid-cols-2 gap-4"',
    );
  });
});
