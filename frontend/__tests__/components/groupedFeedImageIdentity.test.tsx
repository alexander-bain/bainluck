// L2-199 — grouped-feed avatar identity correctness (C4 P2 "wrong-face" bug).
//
// Two guarantees are proven here in the repo's node test env (renderToStaticMarkup
// + pure key logic; no jsdom/RTL):
//   1. groupedFeedItemKey() keys rows by ENTITY identity, not array index, so a
//      row replaced at the same position gets a fresh component instance (fresh
//      image state) and cannot retain the previous entity's face.
//   2. Each avatar component renders its OWN entity's direct image / initials
//      fallback — no cross-entity contamination in the static output. (The late-
//      lookup guard is unit-tested separately in lib/entityImage.test.ts.)

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

// framer-motion's motion.* render their base element under SSR; map them to the
// plain tag so the static markup is stable and dependency-light.
jest.mock("framer-motion", () => ({
  __esModule: true,
  motion: new Proxy(
    {},
    {
      get: (_t, tag: string) => {
        const Comp = ({ children, ...props }: { children?: React.ReactNode }) =>
          React.createElement(tag, props, children);
        Comp.displayName = `motion.${tag}`;
        return Comp;
      },
    },
  ),
}));

import PlayerStatCard from "../../components/PlayerStatCard";
import ProgressionLadder from "../../components/ProgressionLadder";
import { groupedFeedItemKey } from "../../components/GroupedFeedRenderer";
import type {
  StatPropFeedItem,
  PlayoffProgressionFeedItem,
  UngroupedMarketFeedItem,
} from "@/lib/types";

// getWikipediaImage would fire in an effect (never under renderToStaticMarkup),
// but mock it to a never-resolving promise so nothing escapes the test.
jest.mock("@/lib/images", () => ({
  ...jest.requireActual("@/lib/images"),
  getWikipediaImage: jest.fn(() => new Promise<string | null>(() => {})),
}));

describe("groupedFeedItemKey (recycle prevention)", () => {
  const statItem = (groupKey: string, player: string): StatPropFeedItem => ({
    type: "stat_prop",
    group_key: groupKey,
    player_name: player,
    stat_category: "points",
    lines: [],
    market_count: 1,
  });

  it("keys grouped items by stable entity identity, not array index", () => {
    expect(groupedFeedItemKey(statItem("g-lebron", "LeBron James"))).toBe(
      "stat_prop-g-lebron",
    );
  });

  it("gives two different entities two different keys (forces a fresh instance)", () => {
    const a = groupedFeedItemKey(statItem("g-lebron", "LeBron James"));
    const b = groupedFeedItemKey(statItem("g-curry", "Stephen Curry"));
    expect(a).not.toBe(b);
  });

  it("keeps the SAME key for the same entity across updates", () => {
    const first = groupedFeedItemKey(statItem("g-lebron", "LeBron James"));
    const again = groupedFeedItemKey(statItem("g-lebron", "LeBron James"));
    expect(first).toBe(again);
  });

  it("keys progression rows by entity group_key", () => {
    const item: PlayoffProgressionFeedItem = {
      type: "playoff_progression",
      group_key: "g-celtics",
      entity_name: "Boston Celtics",
      stages: [],
      market_count: 1,
    };
    expect(groupedFeedItemKey(item)).toBe("playoff_progression-g-celtics");
  });

  it("keys ungrouped markets by market id", () => {
    const item: UngroupedMarketFeedItem = {
      type: "market",
      market: { id: 4242, name: "X", source: "kalshi", category: null, sport: null, outcomes: [] },
    };
    expect(groupedFeedItemKey(item)).toBe("market-4242");
  });
});

describe("PlayerStatCard avatar renders its own entity (no cross-contamination)", () => {
  const A = "https://a.espncdn.com/i/headshots/nba/players/full/A.png";

  it("renders the direct headshot URL when provided", () => {
    const html = renderToStaticMarkup(
      <PlayerStatCard playerName="LeBron James" statCategory="points" lines={[]} headshotUrl={A} />,
    );
    expect(html).toContain(`src="${A}"`);
    expect(html).toContain('alt="LeBron James"');
  });

  it("falls back to initials when no image identity is available", () => {
    const html = renderToStaticMarkup(
      <PlayerStatCard playerName="Stephen Curry" statCategory="assists" lines={[]} />,
    );
    // No <img> — the initials square carries the entity's aria-label.
    expect(html).not.toContain("<img");
    expect(html).toContain('aria-label="Stephen Curry"');
    expect(html).toContain(">SC<");
  });

  it("swapping the entity at a position renders the NEW entity, never the old one", () => {
    const B = "https://a.espncdn.com/i/headshots/nba/players/full/B.png";
    const first = renderToStaticMarkup(
      <PlayerStatCard playerName="LeBron James" statCategory="points" lines={[]} headshotUrl={A} />,
    );
    const second = renderToStaticMarkup(
      <PlayerStatCard playerName="Stephen Curry" statCategory="points" lines={[]} headshotUrl={B} />,
    );
    expect(first).toContain(`src="${A}"`);
    expect(first).not.toContain(`src="${B}"`);
    expect(second).toContain(`src="${B}"`);
    expect(second).not.toContain(`src="${A}"`);
  });
});

describe("ProgressionLadder logo renders its own entity", () => {
  const logo = "https://logos.example/celtics.png";

  it("renders the direct logo URL when provided", () => {
    const html = renderToStaticMarkup(
      <ProgressionLadder entityName="Boston Celtics" stages={[]} logoUrl={logo} />,
    );
    expect(html).toContain(`src="${logo}"`);
    expect(html).toContain('alt="Boston Celtics"');
  });

  it("falls back to a colored initials square when no logo is available", () => {
    const html = renderToStaticMarkup(
      <ProgressionLadder entityName="Boston Celtics" stages={[]} />,
    );
    expect(html).not.toContain("<img");
    expect(html).toContain('aria-label="Boston Celtics"');
  });
});
