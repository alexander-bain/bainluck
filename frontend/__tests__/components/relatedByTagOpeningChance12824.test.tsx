import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RelatedByTag from "@/components/RelatedByTag";

let mockItems: unknown[];

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: { items: mockItems }, error: undefined, isLoading: false }),
}));

function renderRelatedGame(source: "opening" | "blend") {
  mockItems = [{
    type: "event",
    data: {
      id: 15350164,
      sport: "basketball_nba",
      status: "live",
      home_team: "Minnesota Timberwolves",
      away_team: "Portland Trail Blazers",
      home_score: 77,
      away_score: 79,
      hero_probability_source: source,
      current_odds: {
        home_probability: 0.58,
        away_probability: 0.42,
        home_rendered_percent: 58,
        away_rendered_percent: 42,
      },
    },
  }];
  return renderToStaticMarkup(<RelatedByTag tags={["sport:basketball"]} title="More basketball" />);
}

it("keeps the related game and score while withholding a stored opening chance", () => {
  const html = renderRelatedGame("opening");
  expect(html).toContain('href="/events/15350164"');
  expect(html).toContain("Portland Trail Blazers");
  expect(html).toContain("79 - 77");
  expect(html).not.toContain('data-testid="related-card-field"');
  expect(html).not.toMatch(/42%|58%/);
});

it("still prints both chances for the same pair when it comes from a blend", () => {
  const html = renderRelatedGame("blend");
  expect(html).toContain('data-testid="related-card-field"');
  expect(html).toContain("42%");
  expect(html).toContain("58%");
});
