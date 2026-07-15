// L2-119: settled Higher/Lower results get full context, are clickable back to
// their market, and collapse 3+ into one "Your results" group with settled chrome.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { ResolutionGroup } from "../../components/discover/ResolutionGroup";
import { ResolutionCard } from "../../components/discover/ResolutionCard";
import type { ResolutionItem } from "../../lib/api";

const RESULTS: ResolutionItem[] = [
  { market_id: 11, market_name: "Fed cuts rates in June?", category: "economics", guess: "higher", threshold: 55, actual: 62, correct: true, created_at: null },
  { market_id: 22, market_name: "Will it rain in NYC Saturday?", category: "weather", guess: "lower", threshold: 40, actual: 12, correct: true, created_at: null },
  { market_id: 33, market_name: "Chiefs to win the AFC?", category: "sports", guess: "higher", threshold: 30, actual: 18, correct: false, created_at: null },
];

describe("ResolutionGroup", () => {
  test("renders the 'Your results' header with a correct/total summary", () => {
    const html = renderToStaticMarkup(<ResolutionGroup resolutions={RESULTS} />);
    expect(html).toContain("Your results");
    expect(html).toContain("2/3 correct");
  });

  test("each result links back to its /futures/{market_id} market", () => {
    const html = renderToStaticMarkup(<ResolutionGroup resolutions={RESULTS} />);
    expect(html).toContain('href="/futures/11"');
    expect(html).toContain('href="/futures/33"');
  });

  test("keeps full context per row (market + guess vs outcome)", () => {
    const html = renderToStaticMarkup(<ResolutionGroup resolutions={RESULTS} />);
    expect(html).toContain("Fed cuts rates in June?");
    expect(html).toContain("You guessed higher than 55% — resolved at 62%");
  });

  test("settled chrome uses design tokens, not raw Tailwind palette", () => {
    const html = renderToStaticMarkup(<ResolutionGroup resolutions={RESULTS} />);
    expect(html).toMatch(/text-accent-(live|danger)/);
    expect(html).not.toMatch(/(text|bg|border)-(green|red|purple|gray|slate)-\d/);
  });

  test("empty list renders nothing", () => {
    expect(renderToStaticMarkup(<ResolutionGroup resolutions={[]} />)).toBe("");
  });
});

describe("ResolutionCard", () => {
  test("is clickable back to its market and shows the guess-vs-outcome recap", () => {
    const html = renderToStaticMarkup(
      <ResolutionCard marketId={99} marketName="CPI above 3%?" guess="higher" threshold={50} actual={44} correct={false} />,
    );
    expect(html).toContain('href="/futures/99"');
    expect(html).toContain("CPI above 3%?");
    expect(html).toContain("Not this time");
    expect(html).toContain("resolved at");
    expect(html).not.toMatch(/(text|bg|border)-(green|red|purple)-\d/);
  });
});
