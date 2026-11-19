import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import DiscoverCard from "@/components/DiscoverCard";
import type { FeedBundleData, FeedItem } from "@/lib/types";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), prefetch: jest.fn() }),
}));

describe("#12825 Discover story & comparison bundles render served hero imagery", () => {
  const grammysItem: FeedItem = {
    type: "bundle",
    score: 88,
    reason: "",
    headline: "",
    data: {
      id: "theme:story:grammys:1-2",
      title: "Grammys",
      kind: "theme",
      story_key: "story:grammys",
      shared_question: "Where do the Grammys races stand?",
      item_count: 2,
      member_ids: [1, 2],
      image_url: "https://image.tmdb.org/t/p/w780/11QwqK3hUCWkLJclPUPzd6tgtxL.jpg",
      image_presentation: "photo",
      items: [
        {
          type: "futures",
          score: 80,
          reason: "",
          headline: "",
          data: {
            id: 1,
            name: "Grammys 2027: Best Musica Urbana Album Winner",
            sport_key: "entertainment",
            sport_name: "Entertainment",
            llm_sport_category: "entertainment",
            top_outcomes: [{ name: "Do Not Disturb - Young Miko", probability: 0.44 }],
          } as never,
        },
        {
          type: "futures",
          score: 78,
          reason: "",
          headline: "",
          data: {
            id: 2,
            name: "Grammys 2027: Best Latin Pop Album Winner",
            sport_key: "entertainment",
            sport_name: "Entertainment",
            llm_sport_category: "entertainment",
            top_outcomes: [{ name: "No Me Arrepiento de Sentir Tanto - KAROL G", probability: 0.51 }],
          } as never,
        },
      ],
    },
  };

  it("renders the TMDB Grammys banner image and music note eyebrow on ThemeBundleCard", () => {
    const html = renderToStaticMarkup(
      <DiscoverCard groupedItem={{ type: "single", item: grammysItem }} positionIndex={0} />,
    );
    expect(html).toContain('data-testid="bundle-hero-image"');
    expect(html).toContain("https://image.tmdb.org/t/p/w780/11QwqK3hUCWkLJclPUPzd6tgtxL.jpg");
    expect(html).toContain("🎵 Grammys");
    expect(html).not.toContain("🎬 Grammys");
  });

  it("renders served bundle image on comparison GroupCard as well", () => {
    const baseBundle = grammysItem.data as FeedBundleData;
    const comparisonItem: FeedItem = {
      ...grammysItem,
      data: {
        ...baseBundle,
        id: "comparison:ipo:1-2",
        title: "IPOs",
        kind: "comparison",
        shared_question: "Who goes public, and at what price?",
        image_url:
          "https://thumb.wikimedia.org/wikipedia/commons/thumb/9/92/New_York_Stock_Exchange_August_2017_02.jpg/500px-New_York_Stock_Exchange_August_2017_02.jpg",
        image_presentation: "photo",
      },
    };
    const html = renderToStaticMarkup(
      <DiscoverCard groupedItem={{ type: "single", item: comparisonItem }} positionIndex={1} />,
    );
    expect(html).toContain('data-testid="bundle-hero-image"');
    expect(html).toContain("New_York_Stock_Exchange_August_2017_02.jpg");
  });
});
