// #8635 — a live game card on /sports says it is live ONCE.
//
// Production, 2026-09-25 14:52Z, /sports at 390px: VfB Stuttgart vs 1. FC
// Heidenheim printed a green "● LIVE" chip and then an orange "Live" pill. The
// pill is `highlight.label`, and "Live" is `get_highlight_label`'s last-resort
// answer for any live game with nothing more specific to say.
//
// Both directions (gotcha #43): the echo goes, and a live label that says
// something new, or a non-live "Live"-free label, still renders. A rule that
// only suppresses would pass by deleting the pill.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import FeedCard from "@/components/FeedCard";
import type { FeedEventData, FeedItem } from "@/lib/types";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

// The specimen's served shape (/api/events/15317344): live, no score, no clock.
function makeData(over: Partial<FeedEventData> = {}): FeedEventData {
  return {
    id: 15317344,
    external_id: "evt-15317344",
    sport: "soccer_germany_bundesliga",
    sport_name: "Bundesliga - Germany",
    home_team: "VfB Stuttgart",
    away_team: "1. FC Heidenheim",
    commence_time: "2026-09-25T14:30:00+00:00",
    status: "live",
    home_score: null,
    away_score: null,
    current_odds: { home_probability: 0.61, away_probability: null },
    highlight: { label: "Live" },
    ...over,
  } as unknown as FeedEventData;
}

function render(data: FeedEventData): string {
  const item = { type: "event", score: 50, reason: "", headline: "", data } as unknown as FeedItem;
  return renderToStaticMarkup(<FeedCard item={item} />);
}

/** Every visible text node of the card (attributes such as aria-label excluded). */
function textNodes(html: string): string[] {
  return html
    .split(/<[^>]+>/)
    .map((t) => t.trim())
    .filter(Boolean);
}

function liveWordCount(html: string): number {
  return textNodes(html).filter((t) => t.toLowerCase() === "live").length;
}

describe("#8635 live card prints one live badge", () => {
  test("the specimen: LIVE chip once, no orange 'Live' echo", () => {
    const html = render(makeData());
    expect(liveWordCount(html)).toBe(1);
    expect(html).not.toContain("text-accent-warning");
  });

  test("case and whitespace do not smuggle the echo back", () => {
    for (const label of ["live", " LIVE ", "Live"]) {
      expect(liveWordCount(render(makeData({ highlight: { label } } as Partial<FeedEventData>)))).toBe(1);
    }
  });

  test("a live label that adds information still renders", () => {
    const html = render(makeData({ highlight: { label: "Odds moved" } } as Partial<FeedEventData>));
    expect(textNodes(html)).toContain("Odds moved");
    expect(liveWordCount(html)).toBe(1);
  });

  test("a scheduled card keeps its highlight label", () => {
    const html = render(
      makeData({ status: "scheduled", highlight: { label: "Close matchup" } } as Partial<FeedEventData>),
    );
    expect(textNodes(html)).toContain("Close matchup");
  });
});
