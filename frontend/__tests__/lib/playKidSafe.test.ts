// L2-176 — kid-safe filter guard test. The safety contract for /play:
// blocklist terms + disallowed categories must NEVER render to a kid, while
// legitimate sports/entertainment/weather content (incl. safe words that merely
// contain a blocked substring, e.g. "Warriors") must pass.

import {
  isKidSafeText,
  isKidSafeCategory,
  isKidSafeItem,
  filterKidSafe,
} from "@/lib/play/kidSafe";
import type { FeedItem, FeedEventData, FeedFuturesData } from "@/lib/types";

// The exact blocklist the queue named must always be rejected.
const REQUIRED_BLOCKED = [
  "war",
  "death",
  "invade",
  "pandemic",
  "virus",
  "pregnant",
  "regime",
  "election",
  "crypto",
  "gun",
];

describe("isKidSafeText — blocklist", () => {
  it("rejects every queue-required blocklist term", () => {
    for (const term of REQUIRED_BLOCKED) {
      expect(isKidSafeText(`Something about ${term} today`)).toBe(false);
    }
  });

  it("rejects inflections and phrasing variants", () => {
    for (const s of [
      "Russia will invade by August",
      "2028 presidential election winner",
      "Will the virus mutate?",
      "Deaths from the outbreak",
      "Regime change in the region",
      "New gun control law",
      "Crypto / Bitcoin price above $100k",
      "Nuclear missile test",
      "A deadly shooting downtown",
    ]) {
      expect(isKidSafeText(s)).toBe(false);
    }
  });

  it("does NOT reject safe words that merely contain a blocked substring", () => {
    for (const s of [
      "Golden State Warriors to win the title",
      "Gunnar Henderson home run prop",
      "Diego to score first",
      "Will the game beat the deadline?",
      "Warsaw marathon winner",
      "Coupled dance routine score",
      "Team stability rating",
      "Shootout goals in the final",
    ]) {
      expect(isKidSafeText(s)).toBe(true);
    }
  });

  it("treats empty/null as safe", () => {
    expect(isKidSafeText("")).toBe(true);
    expect(isKidSafeText(null)).toBe(true);
    expect(isKidSafeText(undefined)).toBe(true);
  });
});

describe("isKidSafeCategory — allowlist", () => {
  it("allows sports, entertainment, and weather", () => {
    for (const c of [
      "basketball",
      "baseball",
      "americanfootball",
      "icehockey",
      "soccer",
      "golf",
      "mma",
      "motorsports",
      "cycling",
      "entertainment",
      "weather",
    ]) {
      expect(isKidSafeCategory(c)).toBe(true);
    }
  });

  it("blocks every non-allowed category", () => {
    for (const c of [
      "politics",
      "geopolitics",
      "economics",
      "tech",
      "culture",
      "health",
      "crypto",
      "other",
      "",
      null,
    ]) {
      expect(isKidSafeCategory(c as string)).toBe(false);
    }
  });
});

// --- Item-level tests through the real getDiscoverItemAnalytics path ---

function futuresItem(
  name: string,
  category: string,
  headline: string | null = null
): FeedItem {
  const data: Partial<FeedFuturesData> = {
    id: 1,
    name,
    llm_sport_category: category,
    sport_name: category,
    sport: category,
    top_outcomes: [{ id: 1, name: "Yes", probability: 0.5, rank: 1, movement: null }],
  };
  return {
    type: "futures",
    score: 50,
    reason: "",
    headline,
    data: data as FeedFuturesData,
  };
}

function eventItem(sport: string, home: string, away: string): FeedItem {
  const data: Partial<FeedEventData> = {
    id: 2,
    external_id: "x",
    sport,
    sport_name: sport,
    home_team: home,
    away_team: away,
    commence_time: "2026-08-01T00:00:00Z",
    status: "scheduled",
    home_score: null,
    away_score: null,
  };
  return {
    type: "event",
    score: 50,
    reason: "",
    headline: null,
    data: data as FeedEventData,
  };
}

describe("isKidSafeItem", () => {
  it("passes a clean sports event", () => {
    expect(isKidSafeItem(eventItem("basketball_nba", "Warriors", "Lakers"))).toBe(true);
  });

  it("passes a clean entertainment futures card", () => {
    expect(isKidSafeItem(futuresItem("Taylor Swift album of the year", "entertainment"))).toBe(true);
  });

  it("blocks a politics card even with clean text", () => {
    expect(isKidSafeItem(futuresItem("Who wins the primary?", "politics"))).toBe(false);
  });

  it("blocks a sports-category card whose text hits the blocklist", () => {
    expect(
      isKidSafeItem(futuresItem("Player charged after gun incident", "basketball"))
    ).toBe(false);
  });

  it("blocks bundle cards outright", () => {
    const bundle = { type: "bundle", score: 50, reason: "", headline: null, data: {} } as unknown as FeedItem;
    expect(isKidSafeItem(bundle)).toBe(false);
  });
});

describe("filterKidSafe", () => {
  it("keeps only the safe items", () => {
    const items = [
      eventItem("basketball_nba", "Warriors", "Lakers"), // safe
      futuresItem("2028 election winner", "politics"), // blocked category + term
      futuresItem("Best Picture winner", "entertainment"), // safe
      futuresItem("Fed rate decision", "economics"), // blocked category
      futuresItem("Tornado warning count", "weather"), // safe category, safe text
    ];
    const safe = filterKidSafe(items);
    expect(safe).toHaveLength(3);
    expect(safe.map((i) => i.type)).toEqual(["event", "futures", "futures"]);
  });
});
