/**
 * #12577 — Award Category Paired-Metric Card across Discover, Oscars Collection, and Category Pages
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import AwardCategoryPairedCard from "@/components/discover/forms/AwardCategoryPairedCard";
import DiscoverCard from "@/components/DiscoverCard";
import { PAIRED_METRIC_REGISTER, type PairedMetricSet } from "@/lib/discover/visualForms";
import type { FeedBundleData, FeedItem } from "@/lib/types";

jest.mock("next/link", () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const R = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) =>
      R.createElement("a", { href, ...rest }, children),
  };
});
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
}));
jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));
jest.mock("@/lib/analytics", () => ({ trackEvent: () => {} }));

describe("#12577 — AwardCategoryPairedCard on Discover, Collection, and Category surfaces", () => {
  const baseSet: PairedMetricSet = PAIRED_METRIC_REGISTER["oscars-2027-best-picture"];

  it("renders top 5 contenders with TMDB posters, Nominated % + Wins % bars, expander, traceable links, and zero raw #IDs on Discover", () => {
    const bundleData: FeedBundleData = {
      id: "roundup:oscars-best-picture",
      title: baseSet.title,
      kind: "roundup",
      story_key: "roundup:oscars-best-picture",
      item_count: 3,
      member_ids: [6173044, 5165726, 27988771],
      collection_ref: {
        slug: "roundup-oscars-best-picture",
        href: "/collections/roundup-oscars-best-picture",
        name: "Best Picture: who gets nominated, who wins",
        revision: 1,
        collection_count: 3,
      },
      roundup: {
        kicker: "THE OSCARS · BEST PICTURE",
        tag: "ENTERTAINMENT",
        footer: "Several films are nominated; one wins.",
        paired_metric_set: baseSet,
        rows: [
          { market_id: 6173044, outcome_id: 1, label: "The Odyssey", probability: 0.52, secondary_probability: 0.95 },
          { market_id: 6173044, outcome_id: 2, label: "You Can See Everything", probability: 0.16, secondary_probability: 0.85 },
          { market_id: 6173044, outcome_id: 3, label: "The Black Ball", probability: 0.14, secondary_probability: 0.78 },
        ],
      },
      items: [
        {
          type: "futures",
          score: 85,
          reason: "Best Picture winner",
          headline: "Best Picture winner",
          data: {
            id: 6173044,
            name: "Oscars 2027: Best Picture Winner",
            sport: null,
            sport_name: "Entertainment",
            llm_sport_category: "entertainment",
            source: "kalshi",
            source_count: 1,
            market_tier: 1,
            status: "open",
            resolution_date: "2027-03-14T23:59:59Z",
            outcome_count: 10,
            canonical_market_key: null,
            top_outcomes: [
              { id: 1, name: "The Odyssey", probability: 0.52, rank: 1, movement: null },
            ],
          },
        },
      ],
    };
    const feedItem: FeedItem = {
      type: "bundle",
      score: 90,
      reason: baseSet.title,
      headline: baseSet.title,
      data: bundleData,
    };

    const html = renderToStaticMarkup(
      <DiscoverCard groupedItem={{ type: "single", item: feedItem }} positionIndex={0} />,
    );
    expect(html).toContain('data-testid="award-category-paired-card-oscars-2027-best-picture"');
    expect(html).toContain('data-testid="award-paired-art-poster"');
    expect(html).toContain('data-testid="toggle-expand-all-rows"');
    expect(html).toContain("Show all 10 contenders (+5 more)");
    expect(html).toContain('href="/futures/6173044"');
    expect(html).toContain('href="/futures/5165726"');
    expect(html).toContain('href="/collections/oscars-2027"');
    expect(html).toContain('data-testid="tmdb-official-logo"');
    expect(html).toContain('data-testid="bundle-action-bar"');
    // Card face must never leak internal #marketId strings
    expect(html).not.toContain("#5165726");
    expect(html).not.toContain("#6173044");
  });

  it("renders all contenders expanded by default on the category page and switches Stage 1 to ✓ / ✗ after nominations settle", () => {
    const settledSet: PairedMetricSet = {
      ...baseSet,
      stage_1_settled: true,
      entries: baseSet.entries.map((e, i) => ({
        ...e,
        stage_1_settled_state: i < 5 ? "yes" : "no",
      })),
    };
    const html = renderToStaticMarkup(
      <AwardCategoryPairedCard
        set={settledSet}
        surface="category"
        defaultExpanded
        currentMarketId={6173044}
      />,
    );
    expect(html).toContain('data-testid="award-paired-row-10"');
    expect(html).toContain('data-testid="settled-stage-1-tick"');
    expect(html).toContain('data-testid="settled-stage-1-cross"');
    // On /futures/6173044 itself, links to the companion Nominees market (#5165726) without self-linking #6173044
    expect(html).toContain('href="/futures/5165726"');
    expect(html).not.toContain('data-testid="paired-card-winner-market-link"');
  });
});
