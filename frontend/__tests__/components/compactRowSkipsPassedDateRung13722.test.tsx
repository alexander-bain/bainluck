/**
 * #13722 (Fable look 7160152824): a collapsed Discover bundle row never
 * headlines a passed date rung while a rung dated today or later is priced;
 * only when no today/future rung has a price may a passed rung stand.
 */
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { FuturesCompactRow } from "../../components/discover/FuturesCard";
import type { FeedFuturesData, FeedItem } from "@/lib/types";

function savedMiddleEastCeasefire(
  overrides: Partial<{
    thresholdPoints: Array<Record<string, unknown>>;
    distributionOutcomes: Array<Record<string, unknown>> | null;
    topOutcomes: FeedFuturesData["top_outcomes"];
  }> = {},
): FeedFuturesData {
  const defaultPoints = [
    { label: "November 22", value: 20001122, unit: "date", direction: "before", probability: 0.575, source: "date_bucket" },
    { label: "November 30", value: 20001130, unit: "date", direction: "before", probability: 0.765, source: "date_bucket" },
    { label: "December 31", value: 20001231, unit: "date", direction: "before", probability: 0.885, source: "date_bucket" },
  ];
  const defaultDist = [
    { label: "December 31", probability: 0.885, date: "2026-12-31" },
    { label: "November 30", probability: 0.765, date: "2026-11-30" },
    { label: "November 22", probability: 0.575, date: "2026-11-22" },
  ];
  const defaultTop = [
    { id: 260868679, name: "December 31", probability: 0.885, rank: 1, movement: null, rendered_percent: 89 },
    { id: 260851406, name: "November 30", probability: 0.765, rank: 2, movement: null, rendered_percent: 77 },
    { id: 260868681, name: "November 22", probability: 0.575, rank: 3, movement: null, rendered_percent: 58 },
  ];
  return {
    id: 69603905,
    name: "US x Iran Effective Ceasefire begins? (2 week pause)",
    llm_sport_category: "geopolitics",
    sport_name: "Geopolitics",
    status: "open",
    resolution_date: "2027-01-01T00:00:00Z",
    top_outcomes: overrides.topOutcomes ?? defaultTop,
    outcome_count: 3,
    volume_24h: 250_000,
    confidence_tier: "high",
    discover_card: {
      suggested_format: "threshold_heatmap",
      threshold_points: overrides.thresholdPoints ?? defaultPoints,
      ...(overrides.distributionOutcomes === null
        ? {}
        : { distribution_outcomes: overrides.distributionOutcomes ?? defaultDist }),
    },
  } as unknown as FeedFuturesData;
}

function renderRow(data: FeedFuturesData): { answer: string | null; percent: string | null } {
  const item = { type: "futures", score: 85, reason: "", headline: "", data } as unknown as FeedItem;
  const html = renderToStaticMarkup(<FuturesCompactRow item={item} data={data} />);
  return {
    answer: html.match(/data-testid="compact-row-answer">([^<]*)</)?.[1] ?? null,
    percent: html.match(/data-testid="compact-row-percent">([^<]*)</)?.[1] ?? null,
  };
}

describe("#13722 FuturesCompactRow skips passed date rungs while later rungs are priced", () => {
  afterEach(() => {
    jest.useRealTimers();
  });

  it("never puts November 22 under the title on November 25 when Nov 30 and Dec 31 are priced", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-11-25T12:00:00Z"));
    expect(renderRow(savedMiddleEastCeasefire())).toEqual({
      answer: "November 30",
      percent: "77%",
    });
  });

  it("still uses November 22 when dated today (November 22)", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-11-22T12:00:00Z"));
    expect(renderRow(savedMiddleEastCeasefire())).toEqual({
      answer: "November 22",
      percent: "58%",
    });
  });

  it("handles yearless threshold_points without distribution_outcomes on November 25", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-11-25T12:00:00Z"));
    expect(
      renderRow(savedMiddleEastCeasefire({ distributionOutcomes: null })),
    ).toEqual({
      answer: "November 30",
      percent: "77%",
    });
  });

  it("picks the strongest upcoming rung when only the passed rung clears 50%", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-11-25T12:00:00Z"));
    const data = savedMiddleEastCeasefire({
      thresholdPoints: [
        { label: "November 22", value: 20001122, unit: "date", direction: "before", probability: 0.58, source: "date_bucket" },
        { label: "November 30", value: 20001130, unit: "date", direction: "before", probability: 0.35, source: "date_bucket" },
        { label: "December 31", value: 20001231, unit: "date", direction: "before", probability: 0.45, source: "date_bucket" },
      ],
      topOutcomes: [
        { id: 260868681, name: "November 22", probability: 0.58, rank: 1, movement: null, rendered_percent: 58 },
        { id: 260868679, name: "December 31", probability: 0.45, rank: 2, movement: null, rendered_percent: 45 },
        { id: 260851406, name: "November 30", probability: 0.35, rank: 3, movement: null, rendered_percent: 35 },
      ],
    });
    expect(renderRow(data)).toEqual({
      answer: "December 31",
      percent: "45%",
    });
  });

  it("falls back to the passed rung when no today/future rung has a price", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-11-25T12:00:00Z"));
    const data = savedMiddleEastCeasefire({
      thresholdPoints: [
        { label: "November 22", value: 20001122, unit: "date", direction: "before", probability: 0.575, source: "date_bucket" },
        { label: "November 30", value: 20001130, unit: "date", direction: "before", probability: null, source: "date_bucket" },
        { label: "December 31", value: 20001231, unit: "date", direction: "before", probability: null, source: "date_bucket" },
      ],
      topOutcomes: [
        { id: 260868681, name: "November 22", probability: 0.575, rank: 1, movement: null, rendered_percent: 58 },
      ],
    });
    expect(renderRow(data)).toEqual({
      answer: "November 22",
      percent: "58%",
    });
  });
});
