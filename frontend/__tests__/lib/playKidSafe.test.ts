// L2-176 — kid-safe filter guard test. The safety contract for /play:
// blocklist terms + disallowed categories must NEVER render to a kid, while
// legitimate sports/entertainment/weather content (incl. safe words that merely
// contain a blocked substring, e.g. "Warriors") must pass.

import {
  isKidSafeText,
  isKidSafeCategory,
  isKidSafeItem,
  isFreshForPlay,
  isPlayEligible,
  collectKidVisibleText,
  filterKidSafe,
} from "@/lib/play/kidSafe";
import type {
  FeedItem,
  FeedEventData,
  FeedFuturesData,
  FeedFuturesOutcome,
  FeedConceptData,
  FeedTournamentData,
} from "@/lib/types";

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

  it("rejects pregnancy / relationship-gossip terms (L2-177 — the culture/TS corpus)", () => {
    for (const s of [
      "Will Taylor Swift be pregnant in 2026?",
      "Taylor Swift and Travis Kelce to get engaged",
      "Celebrity engagement announcement",
      "Will the couple divorce this year?",
      "Star caught in an affair",
      "Reality star breakup drama",
      "Who is the singer dating now?",
      "Cheating scandal rocks the show",
      "Secret mistress revealed",
      "Summer romance rumors",
      "Backstage hookup gossip",
      "Adultery allegations surface",
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
      // L2-177 gossip terms must respect word boundaries — these stay safe:
      "Updating the tour schedule", // "dating" only at a word boundary
      "Taylor Swift album of the year", // clean culture/music card — the point of L2-177
      "Best Picture winner at the Oscars",
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
  it("allows sports, entertainment, weather, and culture", () => {
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
      "culture", // L2-177 — pop-culture / Taylor-Swift cards
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
    // Fresh by default (status "open", no resolution date) so the SAFETY tests
    // below exercise content safety, not freshness — freshness has its own suite.
    status: "open",
    resolution_date: null,
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

function futuresItemWithOutcomes(
  name: string,
  category: string,
  outcomeNames: string[],
): FeedItem {
  const top_outcomes: FeedFuturesOutcome[] = outcomeNames.map((n, i) => ({
    id: i + 1,
    name: n,
    probability: 0.5,
    rank: i + 1,
    movement: null,
  }));
  const data: Partial<FeedFuturesData> = {
    id: 3,
    name,
    llm_sport_category: category,
    sport_name: category,
    sport: category,
    status: "open",
    resolution_date: null,
    top_outcomes,
  };
  return {
    type: "futures",
    score: 50,
    reason: "",
    headline: null,
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

  it("passes a clean culture card (L2-177 — the Taylor Swift gap)", () => {
    expect(
      isKidSafeItem(futuresItem("Taylor Swift to win Album of the Year", "culture"))
    ).toBe(true);
  });

  it("blocks a culture card whose text is relationship gossip (L2-177)", () => {
    expect(
      isKidSafeItem(futuresItem("Will Taylor Swift and Travis Kelce get engaged?", "culture"))
    ).toBe(false);
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

  // L2-178 — the gate must run the blocklist over OUTCOME labels too, not just
  // the title/headline. /play renders the outcome name as the guess subject, so a
  // clean title hiding a blocked outcome is the exact bypass this closes.
  it("blocks a clean-title card whose OUTCOME label hits the blocklist", () => {
    const item = futuresItemWithOutcomes(
      "Who will be the newsmaker of the year?", // clean title, allowed category
      "entertainment",
      ["A popular musician", "Regime change leader"], // blocked outcome ("regime")
    );
    expect(isKidSafeItem(item)).toBe(false);
  });

  it("keeps a clean-title card whose outcomes are also clean", () => {
    const item = futuresItemWithOutcomes(
      "Who wins Album of the Year?",
      "culture",
      ["Taylor Swift", "Beyoncé", "Olivia Rodrigo"],
    );
    expect(isKidSafeItem(item)).toBe(true);
  });

  it("blocks an event whose TEAM name hits the blocklist", () => {
    // Team names render as "<team> to win" — they are visible strings too.
    expect(isKidSafeItem(eventItem("basketball_nba", "Gun Club", "Lakers"))).toBe(false);
  });
});

describe("collectKidVisibleText", () => {
  it("includes futures outcome labels in the haystack", () => {
    const item = futuresItemWithOutcomes("Trophy winner", "entertainment", [
      "Nuclear option",
      "Safe pick",
    ]);
    const text = collectKidVisibleText(item);
    expect(text.toLowerCase()).toContain("nuclear option");
    expect(text).toContain("Trophy winner");
  });

  it("includes both event team names", () => {
    const text = collectKidVisibleText(eventItem("basketball_nba", "Warriors", "Lakers"));
    expect(text).toContain("Warriors");
    expect(text).toContain("Lakers");
  });
});

describe("filterKidSafe", () => {
  it("keeps only the safe items", () => {
    const items = [
      eventItem("basketball_nba", "Warriors", "Lakers"), // safe + fresh (scheduled)
      futuresItem("2028 election winner", "politics"), // blocked category + term
      futuresItem("Best Picture winner", "entertainment"), // safe + fresh (open)
      futuresItem("Fed rate decision", "economics"), // blocked category
      futuresItem("Tornado warning count", "weather"), // safe category, safe text, fresh
    ];
    const safe = filterKidSafe(items);
    expect(safe).toHaveLength(3);
    expect(safe.map((i) => i.type)).toEqual(["event", "futures", "futures"]);
  });
});

// ===========================================================================
// L2-187 — FRESHNESS gate. /play must never surface a completed/closed/settled/
// resolved card as a fresh swipe (REPORT-2.md: 19/78 deck cards were finished
// games rendering a live-looking % on a done game). The gate is FAIL-CLOSED and
// judged per card type, independent of content safety.
// ===========================================================================

const NOW = Date.parse("2026-07-27T12:00:00Z");
const PAST = "2026-07-20T00:00:00Z"; // a week before NOW
const FUTURE = "2026-09-01T00:00:00Z"; // well after NOW

function eventItemStatus(status: string): FeedItem {
  const data: Partial<FeedEventData> = {
    id: 2,
    external_id: "x",
    sport: "baseball_mlb",
    sport_name: "baseball",
    home_team: "Astros",
    away_team: "White Sox",
    commence_time: PAST,
    status: status as FeedEventData["status"],
    home_score: 12,
    away_score: 3,
    current_odds: { home_probability: 0.97, away_probability: 0.03 },
  };
  return { type: "event", score: 50, reason: "", headline: null, data: data as FeedEventData };
}

function futuresFresh(overrides: Partial<FeedFuturesData>): FeedItem {
  const data: Partial<FeedFuturesData> = {
    id: 1,
    name: "MLB World Series Winner",
    llm_sport_category: "baseball",
    sport_name: "baseball",
    sport: "baseball",
    status: "open",
    resolution_date: null,
    top_outcomes: [{ id: 1, name: "Dodgers", probability: 0.3, rank: 1, movement: null }],
    ...overrides,
  };
  return { type: "futures", score: 50, reason: "", headline: null, data: data as FeedFuturesData };
}

function conceptItem(overrides: Partial<FeedConceptData>): FeedItem {
  const data: Partial<FeedConceptData> = {
    key: "event:cycling:tour-de-france-2026",
    name: "Tour de France 2026",
    domain: "cycling",
    status: "live",
    is_major: true,
    fight_count: 0,
    ...overrides,
  };
  return { type: "concept", score: 50, reason: "", headline: null, data: data as FeedConceptData };
}

function tournamentItem(overrides: Partial<FeedTournamentData>): FeedItem {
  const data: Partial<FeedTournamentData> = {
    key: "golf-aig-womens-open",
    name: "AIG Women's Open",
    is_major: true,
    schedule_status: null,
    start_date: null,
    end_date: null,
    commence_time: null,
    resolution_date: FUTURE,
    golfers: [{ name: "Nelly Korda", probability: 0.2, rank: 1, movement_24h: null }],
    market_ids: [1],
    source_count: 1,
    ...overrides,
  };
  return { type: "tournament", score: 50, reason: "", headline: null, data: data as FeedTournamentData };
}

describe("isFreshForPlay — events (the measured 19/78 defect class)", () => {
  it("rejects completed and closed events (stale games shown with a live %)", () => {
    expect(isFreshForPlay(eventItemStatus("completed"), NOW)).toBe(false);
    expect(isFreshForPlay(eventItemStatus("closed"), NOW)).toBe(false);
  });

  it("keeps scheduled and live events", () => {
    expect(isFreshForPlay(eventItemStatus("scheduled"), NOW)).toBe(true);
    expect(isFreshForPlay(eventItemStatus("live"), NOW)).toBe(true);
  });

  it("fail-closed: rejects an event with a missing/unknown status", () => {
    expect(isFreshForPlay(eventItemStatus(""), NOW)).toBe(false);
    expect(isFreshForPlay(eventItemStatus("settled"), NOW)).toBe(false);
    expect(isFreshForPlay(eventItemStatus("resolved"), NOW)).toBe(false);
  });
});

describe("isFreshForPlay — futures", () => {
  it("keeps a genuinely open market (no resolution date, or future one)", () => {
    expect(isFreshForPlay(futuresFresh({}), NOW)).toBe(true);
    expect(isFreshForPlay(futuresFresh({ resolution_date: FUTURE }), NOW)).toBe(true);
  });

  it("rejects resolved/closed markets", () => {
    expect(isFreshForPlay(futuresFresh({ status: "resolved" }), NOW)).toBe(false);
    expect(isFreshForPlay(futuresFresh({ status: "closed" }), NOW)).toBe(false);
  });

  it("rejects a market surfaced result-first even if status stays 'open' (gotcha #33)", () => {
    expect(isFreshForPlay(futuresFresh({ status: "open", resolved: true }), NOW)).toBe(false);
    expect(isFreshForPlay(futuresFresh({ status: "open", winner: "Dodgers" }), NOW)).toBe(false);
  });

  it("rejects an 'open' market whose resolution time is already past", () => {
    expect(isFreshForPlay(futuresFresh({ status: "open", resolution_date: PAST }), NOW)).toBe(false);
  });

  it("fail-closed: rejects a market with an unknown status", () => {
    expect(isFreshForPlay(futuresFresh({ status: "" }), NOW)).toBe(false);
    expect(isFreshForPlay(futuresFresh({ status: "settled" }), NOW)).toBe(false);
  });
});

describe("isFreshForPlay — concept (explicit, not inferred from safety)", () => {
  it("keeps an upcoming or live concept", () => {
    expect(isFreshForPlay(conceptItem({ status: "live" }), NOW)).toBe(true);
    expect(isFreshForPlay(conceptItem({ status: "upcoming" }), NOW)).toBe(true);
  });

  it("rejects a settled concept", () => {
    expect(isFreshForPlay(conceptItem({ status: "settled" }), NOW)).toBe(false);
  });

  it("rejects a post-settlement WHAT-HIT concept (marquee_whathit / named champion)", () => {
    expect(isFreshForPlay(conceptItem({ status: "live", marquee_whathit: true }), NOW)).toBe(false);
    expect(isFreshForPlay(conceptItem({ status: "upcoming", winner: "Tadej Pogačar" }), NOW)).toBe(false);
  });

  it("fail-closed: rejects a concept with an unknown/empty status", () => {
    expect(isFreshForPlay(conceptItem({ status: "" }), NOW)).toBe(false);
    expect(isFreshForPlay(conceptItem({ status: "completed" }), NOW)).toBe(false);
  });
});

describe("isFreshForPlay — tournament (explicit, not inferred from safety)", () => {
  it("keeps a tournament with a future resolution window", () => {
    expect(isFreshForPlay(tournamentItem({ resolution_date: FUTURE }), NOW)).toBe(true);
    expect(isFreshForPlay(tournamentItem({ schedule_status: "upcoming" }), NOW)).toBe(true);
  });

  it("keeps a live tournament ('in-progress' hyphen form normalized)", () => {
    expect(isFreshForPlay(tournamentItem({ schedule_status: "in-progress" }), NOW)).toBe(true);
  });

  it("rejects a completed tournament schedule_status", () => {
    expect(isFreshForPlay(tournamentItem({ schedule_status: "completed", resolution_date: PAST }), NOW)).toBe(false);
  });

  it("rejects a tournament whose resolution/end date has passed", () => {
    expect(isFreshForPlay(tournamentItem({ resolution_date: PAST }), NOW)).toBe(false);
    expect(isFreshForPlay(tournamentItem({ resolution_date: null, end_date: PAST }), NOW)).toBe(false);
  });

  it("rejects a post-settlement WHAT-HIT tournament", () => {
    expect(isFreshForPlay(tournamentItem({ marquee_whathit: true, resolution_date: FUTURE }), NOW)).toBe(false);
  });

  it("fail-closed: rejects a tournament with no status and no date signal", () => {
    expect(
      isFreshForPlay(
        tournamentItem({ schedule_status: null, start_date: null, end_date: null, resolution_date: null }),
        NOW,
      ),
    ).toBe(false);
  });
});

describe("isFreshForPlay — bundle / unknown", () => {
  it("rejects bundle cards (cannot be freshness-vetted)", () => {
    const bundle = { type: "bundle", score: 50, reason: "", headline: null, data: {} } as unknown as FeedItem;
    expect(isFreshForPlay(bundle, NOW)).toBe(false);
  });
});

describe("isPlayEligible — safety AND freshness (independent gates)", () => {
  it("requires BOTH: a safe-but-stale card is rejected", () => {
    // Clean sports content, but the game is over → rejected by freshness alone.
    expect(isKidSafeItem(eventItemStatus("completed"))).toBe(true);
    expect(isPlayEligible(eventItemStatus("completed"), NOW)).toBe(false);
  });

  it("requires BOTH: a fresh-but-unsafe card is rejected", () => {
    const unsafe = futuresFresh({ name: "Who wins the 2028 election?", llm_sport_category: "politics" });
    expect(isFreshForPlay(unsafe, NOW)).toBe(true); // it IS fresh...
    expect(isPlayEligible(unsafe, NOW)).toBe(false); // ...but not kid-safe
  });

  it("admits a card that is both safe and fresh", () => {
    expect(isPlayEligible(eventItemStatus("live"), NOW)).toBe(true);
    expect(isPlayEligible(futuresFresh({ name: "Best Picture winner", llm_sport_category: "entertainment" }), NOW)).toBe(true);
  });
});

describe("filterKidSafe — no bypass via pagination merge or affinity reorder", () => {
  // The /play deck is filterKidSafe(feed) → dedup-merge → seedByAffinity. Since
  // the freshness gate lives in filterKidSafe (the single admission point BEFORE
  // both the merge and the affinity reorder), a stale card can never enter either
  // game regardless of ordering. This asserts the pool-level guarantee.
  it("drops every completed/closed event alongside safe/fresh cards", () => {
    const items = [
      eventItemStatus("completed"), // 🔴 stale — REPORT-2.md class
      eventItemStatus("closed"), // 🔴 stale
      eventItem("basketball_nba", "Warriors", "Lakers"), // scheduled → keep
      futuresFresh({ name: "Best Picture winner", llm_sport_category: "entertainment" }), // keep
      futuresFresh({ name: "Old award", llm_sport_category: "entertainment", status: "resolved" }), // stale → drop
      conceptItem({ status: "settled" }), // stale → drop
      conceptItem({ status: "live" }), // keep
    ];
    const safe = filterKidSafe(items);
    expect(safe).toHaveLength(3);
    expect(safe.map((i) => i.type)).toEqual(["event", "futures", "concept"]);
    // None of the survivors is a completed/closed event.
    for (const it of safe) {
      if (it.type === "event") {
        expect(["scheduled", "live"]).toContain((it.data as FeedEventData).status);
      }
    }
  });
});
