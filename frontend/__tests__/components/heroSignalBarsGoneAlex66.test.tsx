// #10090, Alex decision 66 ("yes on the bars"): the live event hero has ONE
// signal, the EKG heartbeat. Its three always-full confidence bars read like
// Wi-Fi and are gone. Discover cards keep their bars; Alex may drop those later.
//
// The event page is too large to mount here, so its half is pinned by text (the
// same way `ekgHeartbeat10090.test.tsx` pins the EKG wiring). The Discover half
// renders a real card.

import fs from "fs";
import path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { FuturesCard } from "../../components/discover/FuturesCard";
import type { FeedItem, FeedFuturesData } from "@/lib/types";

const PAGE = fs.readFileSync(path.join(__dirname, "../../app/events/[id]/page.tsx"), "utf8");

describe("Alex 66 — the event hero draws no confidence bars", () => {
  it("neither imports nor renders SignalBars, and computes no hero tier", () => {
    expect(PAGE).not.toMatch(/import\s*\{[^}]*\bSignalBars\b[^}]*\}/);
    expect(PAGE).not.toContain("<SignalBars");
    expect(PAGE).not.toContain("heroConfidence");
    expect(PAGE).not.toContain("confidenceFromSources");
  });

  it("keeps the hero's source label row", () => {
    expect(PAGE).toMatch(
      /\{!isFinished && probSourceLabel && \(\s*<div[^>]*>\s*<span[^>]*>\s*\{probSourceLabel\}\s*<\/span>\s*<\/div>/,
    );
  });

  it("keeps the EKG as the hero's live signal", () => {
    expect(PAGE).toContain("<EkgHeartbeat tracker={ekgTrackerRef.current} status={streamStatus} />");
  });
});

describe("Alex 66 — Discover cards keep their bars", () => {
  it("a futures card with a tier still draws SignalBars", () => {
    const data = {
      id: 7,
      name: "Who wins the 2026 election?",
      llm_sport_category: "politics",
      sport_name: "Politics",
      resolution_date: "2026-11-03T00:00:00Z",
      source: "kalshi",
      top_outcomes: [
        { id: 1, name: "Candidate 1", probability: 0.5, movement: 1.4 },
        { id: 2, name: "Candidate 2", probability: 0.43, movement: 1.4 },
      ],
      outcome_count: 2,
      confidence_tier: "high",
    } as unknown as FeedFuturesData;
    const item = { type: "futures", score: 90, reason: "", headline: "", data } as unknown as FeedItem;
    const html = renderToStaticMarkup(
      <FuturesCard item={item} data={data} liked={false} setLiked={() => {}} trending={false} />,
    );
    expect(html).toContain('aria-label="High confidence');
  });
});
