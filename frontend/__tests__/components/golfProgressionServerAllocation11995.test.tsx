import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { ProgressionResponse } from "@/lib/types";
import TournamentProgressionTable from "@/components/TournamentProgressionTable";

jest.mock("@/hooks/useAnalytics", () => ({
  useAnalytics: () => ({ track: jest.fn() }),
}));

function fixture(): ProgressionResponse {
  return {
    sport: "golf",
    tournament_name: "Synthetic complete field",
    stages: [
      { key: "top_5", label: "Top 5", order: 0, market_id: null, market_name: null },
      { key: "win", label: "Win", order: 1, market_id: null, market_name: null },
    ],
    participants: ["Alice Smith", "Bob Jones", "Casey Reed"].map((name, i) => ({
      name, team_id: null, logo_url: null, primary_color: null, conference: null,
      region: null, seed: null, record: null,
      probabilities: { top_5: 0.6, win: 1 / 3 },
      rendered_percents: { win: i === 0 ? 34 : 33 },
      changes_24h: {}, status: {},
    })),
  };
}

function liveTexts(data: ProgressionResponse): string[] {
  const markup = renderToStaticMarkup(<TournamentProgressionTable data={data} pageType="golf" />);
  return Array.from(markup.matchAll(/<span[^>]*data-cell-state="live"[^>]*>(.*?)<\/span>/g))
    .map(match => match[1].replace(/&lt;/g, "<").replace(/&gt;/g, ">"));
}

it("prints the exact server allocation for tied floats and keeps overlapping Top 5 prices", () => {
  const texts = liveTexts(fixture());
  expect(texts).toEqual(["60%", "34%", "60%", "33%", "60%", "33%"]);
  expect(texts.filter((_, i) => i % 2 === 1).reduce((sum, text) => sum + Number(text.replace("%", "")), 0)).toBe(100);
});

it("retains the legacy decimal formatter when an allocation is absent or malformed", () => {
  const data = fixture();
  for (const participant of data.participants) participant.probabilities.win = 0.015;
  delete data.participants[0].rendered_percents;
  data.participants[1].rendered_percents = { win: 101 };
  data.participants[2].rendered_percents = { win: 33.5 };
  expect(liveTexts(data).filter((_, i) => i % 2 === 1)).toEqual(["1.5%", "1.5%", "1.5%"]);
});

it("keeps uncertain boundary markers when the allocation is zero or one hundred", () => {
  const data = fixture();
  data.participants[0].probabilities.win = 0.999;
  data.participants[0].rendered_percents = { win: 100 };
  data.participants[1].probabilities.win = 0.001;
  data.participants[1].rendered_percents = { win: 0 };
  const texts = liveTexts(data);
  expect(texts).toContain(">99%");
  expect(texts).toContain("<1%");
  expect(texts).not.toContain("0%");
  expect(texts).not.toContain("100%");
});

it("keeps authoritative terminal cells ahead of a server display allocation", () => {
  const data = fixture();
  data.participants[0].status.win = "clinched";
  const texts = liveTexts(data);
  expect(texts).not.toContain("34%");
  const markup = renderToStaticMarkup(<TournamentProgressionTable data={data} />);
  expect(markup).toContain('data-cell-state="clinched"');
  expect(markup).toContain("✓");
  expect(texts.filter(text => text === "33%")).toHaveLength(2);
});
