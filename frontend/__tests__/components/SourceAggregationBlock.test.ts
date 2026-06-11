import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  SourceAggregationBlock,
  SOURCE_DISAGREEMENT_PP,
} from "../../components/SourceAggregationBlock";

function makeSources(probs: Record<string, number>, opts?: { stale?: string[] }) {
  const staleSet = new Set(opts?.stale || []);
  return Object.entries(probs).map(([source, prob]) => ({
    source,
    outcomes: { 1: prob },
    captured_at: new Date().toISOString(),
    stale: staleSet.has(source),
  }));
}

describe("SourceAggregationBlock", () => {
  test("renders nothing with fewer than 2 sources", () => {
    const html = renderToStaticMarkup(
      React.createElement(SourceAggregationBlock, {
        sources: makeSources({ draftkings: 45.0 }),
        primaryOutcomeId: 1,
        aggregatedProbability: 45.0,
      })
    );
    expect(html).toBe("");
  });

  test("renders collapsed state with source count", () => {
    const html = renderToStaticMarkup(
      React.createElement(SourceAggregationBlock, {
        sources: makeSources({ draftkings: 45.0, fanduel: 46.0 }),
        primaryOutcomeId: 1,
        aggregatedProbability: 45.5,
      })
    );
    expect(html).toContain("2 sources");
    expect(html).toContain("within 1 point");
  });

  test("shows disagreement treatment when spread >= 5pp", () => {
    const html = renderToStaticMarkup(
      React.createElement(SourceAggregationBlock, {
        sources: makeSources({ draftkings: 40.0, fanduel: 48.0 }),
        primaryOutcomeId: 1,
        aggregatedProbability: 44.0,
      })
    );
    expect(html).toContain("sources disagree");
    expect(html).toContain("8pt spread");
    // Disagreement auto-expands — per-source rows visible
    expect(html).toContain("DraftKings");
    expect(html).toContain("FanDuel");
  });

  test("collapsed state does not show per-source rows", () => {
    const html = renderToStaticMarkup(
      React.createElement(SourceAggregationBlock, {
        sources: makeSources({ draftkings: 45.0, fanduel: 46.0 }),
        primaryOutcomeId: 1,
        aggregatedProbability: 45.5,
      })
    );
    // In agreement, rows are hidden (collapsed by default)
    expect(html).not.toContain("DraftKings");
    expect(html).not.toContain("FanDuel");
  });

  test("alphabetical footer shown when expanded", () => {
    const html = renderToStaticMarkup(
      React.createElement(SourceAggregationBlock, {
        // Spread > 5pp forces auto-expand
        sources: makeSources({ draftkings: 40.0, fanduel: 50.0 }),
        primaryOutcomeId: 1,
        aggregatedProbability: 45.0,
      })
    );
    expect(html).toContain("alphabetically");
  });

  test("exported disagreement threshold matches design spec", () => {
    expect(SOURCE_DISAGREEMENT_PP).toBe(5);
  });

  test("renders nothing when sources is empty", () => {
    const html = renderToStaticMarkup(
      React.createElement(SourceAggregationBlock, {
        sources: [],
        primaryOutcomeId: 1,
        aggregatedProbability: 50.0,
      })
    );
    expect(html).toBe("");
  });

  test("source labels are human-readable", () => {
    const html = renderToStaticMarkup(
      React.createElement(SourceAggregationBlock, {
        sources: makeSources({ kalshi: 40.0, polymarket: 50.0 }),
        primaryOutcomeId: 1,
        aggregatedProbability: 45.0,
      })
    );
    expect(html).toContain("Kalshi");
    expect(html).toContain("Polymarket");
  });

  test("stale sources excluded from spread calculation", () => {
    // espnbet is 20pp away but stale — spread should be 1pt (fresh only)
    const html = renderToStaticMarkup(
      React.createElement(SourceAggregationBlock, {
        sources: makeSources(
          { draftkings: 45.0, fanduel: 46.0, espnbet: 25.0 },
          { stale: ["espnbet"] }
        ),
        primaryOutcomeId: 1,
        aggregatedProbability: 45.5,
      })
    );
    expect(html).toContain("2 sources");
    expect(html).toContain("within 1 point");
    // Should NOT trigger disagreement despite 20pp raw spread
    expect(html).not.toContain("sources disagree");
  });

  test("stale sources render muted when expanded", () => {
    // Force expand via disagreement among fresh sources
    const html = renderToStaticMarkup(
      React.createElement(SourceAggregationBlock, {
        sources: makeSources(
          { draftkings: 40.0, fanduel: 50.0, espnbet: 25.0 },
          { stale: ["espnbet"] }
        ),
        primaryOutcomeId: 1,
        aggregatedProbability: 45.0,
      })
    );
    expect(html).toContain("ESPN Bet");
    // Stale row should have opacity-40 class
    expect(html).toContain("opacity-40");
  });

  test("all-stale sources → block hidden", () => {
    const html = renderToStaticMarkup(
      React.createElement(SourceAggregationBlock, {
        sources: makeSources(
          { draftkings: 45.0, fanduel: 46.0 },
          { stale: ["draftkings", "fanduel"] }
        ),
        primaryOutcomeId: 1,
        aggregatedProbability: 45.5,
      })
    );
    expect(html).toBe("");
  });
});
