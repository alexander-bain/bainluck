// UX-P074 (#1860) — ruling 047 on the league page: the three classifications.
//
// These are the decisions a screenshot cannot check. A binary rendered as one
// row LOOKS right whichever side it printed; a date ladder LOOKS like a ladder
// whether or not the order is real. So each fixture below is the VERBATIM
// production shape from `GET /api/leagues/baseball_mlb` on 2026-08-14, not an
// invented one — including the payload's own ordering, which is the thing two of
// the three defects were hiding behind.

import {
  binaryAnswer,
  cleanMarketName,
  dateLadder,
  leagueGameToEvent,
} from "../../lib/leagueCards";
import type { LeagueGameBrief, LeagueMarket, LeagueMarketOutcome } from "../../lib/api";

const outcome = (
  id: number,
  name: string,
  probability: number | null,
  movement_24h: number | null = null,
): LeagueMarketOutcome => ({
  id,
  name,
  probability,
  opening_probability: null,
  rank: null,
  movement_24h,
  team_id: null,
});

const market = (over: Partial<LeagueMarket> = {}): LeagueMarket => ({
  id: 1,
  name: "A market",
  source: "polymarket",
  market_tier: 5,
  category: "game_prop",
  resolution_date: null,
  outcome_count: 2,
  top_outcomes: [],
  canonical_market_key: null,
  section: "props",
  ...over,
});

// ---------------------------------------------------------------------------
// 3. Yes/no → one row, and the row is the YES side
// ---------------------------------------------------------------------------

describe("binaryAnswer — one question, one answer", () => {
  test("a Yes-first binary answers with Yes", () => {
    const m = market({
      name: "Will the Atlanta Braves win more than 90.5 games in the 2026 MLB Regular Season?",
      top_outcomes: [outcome(1, "Yes", 0.695), outcome(2, "No", 0.305)],
    });
    expect(binaryAnswer(m)).toEqual({ probability: 0.695, movement: null });
  });

  test("a NO-FIRST binary still answers with Yes — the headline defect", () => {
    // Production, verbatim: `top_outcomes` is probability-sorted, and 15 of the
    // 21 MLB binaries therefore led with No. The old two-row card put
    // "No 94.9%" on the first line of a question asking about clinching, so the
    // line a reader takes as the answer stated the complement.
    const m = market({
      name: "Will the Athletics clinch a spot in the 2026 MLB Postseason?",
      top_outcomes: [outcome(1, "No", 0.9485), outcome(2, "Yes", 0.0515)],
    });
    expect(binaryAnswer(m)?.probability).toBeCloseTo(0.0515, 6);
  });

  test("a one-sided binary (a single 'Yes' outcome) is still a binary", () => {
    // "Shohei Ohtani: Cy Young and MVP Winner", outcome_count 1, Yes 1%.
    const m = market({
      name: "Shohei Ohtani: Cy Young and MVP Winner",
      outcome_count: 1,
      top_outcomes: [outcome(1, "Yes", 0.01)],
    });
    expect(binaryAnswer(m)?.probability).toBe(0.01);
  });

  test("a No-only market states the Yes side as the complement, and flips the movement with it", () => {
    const m = market({ outcome_count: 1, top_outcomes: [outcome(1, "No", 0.8, 0.05)] });
    const a = binaryAnswer(m)!;
    expect(a.probability).toBeCloseTo(0.2, 6);
    expect(a.movement).toBeCloseTo(-0.05, 6);
  });

  test("TWO REAL ANSWERS ARE NOT A BINARY — a series keeps both rows", () => {
    // The other direction (gotcha #43). "Two outcomes" is not the test; "Yes and
    // No" is. A playoff series is one question with two answers, and collapsing
    // it to one row would delete a team from the page.
    const m = market({
      name: "Dodgers vs Padres: Series Winner",
      section: "series",
      top_outcomes: [outcome(1, "Los Angeles Dodgers", 0.62), outcome(2, "San Diego Padres", 0.38)],
    });
    expect(binaryAnswer(m)).toBeNull();
  });

  test("a multi-candidate field is not a binary", () => {
    const m = market({
      name: "NL MVP Winner?",
      outcome_count: 53,
      top_outcomes: [outcome(1, "Shohei Ohtani", 0.625), outcome(2, "Pete Crow-Armstrong", 0.355), outcome(3, "James Wood", 0.025)],
    });
    expect(binaryAnswer(m)).toBeNull();
  });

  test("an unpriced binary answers with null rather than a manufactured number", () => {
    const m = market({ top_outcomes: [outcome(1, "Yes", null), outcome(2, "No", null)] });
    expect(binaryAnswer(m)).toEqual({ probability: null, movement: null });
  });
});

// ---------------------------------------------------------------------------
// 2. Date ladders → the shared Quantity kernel, in date order, whole
// ---------------------------------------------------------------------------

describe("dateLadder — a ladder in the order a ladder has", () => {
  /** Verbatim: "Seth Hernandez: Debut Date", 8 outcomes, probability-sorted. */
  const debutDate = market({
    id: 105251763,
    name: "Seth Hernandez: Debut Date",
    source: "kalshi",
    category: "championship",
    outcome_count: 8,
    top_outcomes: [
      outcome(1, "Before Nov 1, 2029", 0.91),
      outcome(2, "Before May 1, 2029", 0.87),
      outcome(3, "Before Aug 1, 2029", 0.865),
      outcome(4, "Before Nov 1, 2028", 0.79),
      outcome(5, "Before Aug 1, 2028", 0.605),
      outcome(6, "Before May 1, 2028", 0.49),
      outcome(7, "Before Nov 1, 2027", 0.41),
      outcome(8, "Before Aug 1, 2027", 0.215),
    ],
  });

  test("all eight rungs survive — the old card truncated to six", () => {
    expect(dateLadder(debutDate)!.rungs).toHaveLength(8);
  });

  test("rungs carry an epoch sort value in date order, not probability order", () => {
    const rungs = dateLadder(debutDate)!.rungs;
    const values = rungs.map((r) => r.value!);
    const ascending = [...values].sort((a, b) => a - b);
    // QuantityGroup sorts on `value`; what matters is that the value it sorts on
    // is the DATE. Aug 2027 must be able to precede Nov 2029.
    expect(new Set(values).size).toBe(8);
    expect(ascending[0]).toBe(Date.parse("Aug 1, 2027"));
    expect(ascending[7]).toBe(Date.parse("Nov 1, 2029"));
  });

  test("the direction word is stated once, not on every rung", () => {
    const ladder = dateLadder(debutDate)!;
    expect(ladder.hint).toBe("on or before");
    expect(ladder.rungs[0].label).toBe("Nov 1, 2029");
  });

  test("a MIXED-direction ladder keeps the word on each rung and states no hint", () => {
    const m = market({
      top_outcomes: [
        outcome(1, "Before Nov 1, 2029", 0.9),
        outcome(2, "After May 1, 2029", 0.5),
        outcome(3, "Before Aug 1, 2028", 0.3),
      ],
    });
    const ladder = dateLadder(m)!;
    expect(ladder.hint).toBeNull();
    expect(ladder.rungs.map((r) => r.label)).toContain("After May 1, 2029");
  });

  test("a market whose rungs are NOT all dates is not a ladder", () => {
    const m = market({
      top_outcomes: [
        outcome(1, "Before Nov 1, 2029", 0.9),
        outcome(2, "Never", 0.05),
        outcome(3, "Before Aug 1, 2028", 0.3),
      ],
    });
    expect(dateLadder(m)).toBeNull();
  });

  test("two rungs are a pair of props, not a ladder", () => {
    const m = market({
      top_outcomes: [outcome(1, "Before Nov 1, 2029", 0.9), outcome(2, "Before Aug 1, 2028", 0.3)],
    });
    expect(dateLadder(m)).toBeNull();
  });

  test("a team field is not a ladder", () => {
    const m = market({
      name: "MLB: Team to win 100+ games",
      outcome_count: 30,
      top_outcomes: [
        outcome(1, "Los Angeles Dodgers", 0.695),
        outcome(2, "Milwaukee Brewers", 0.335),
        outcome(3, "Tampa Bay Rays", 0.165),
      ],
    });
    expect(dateLadder(m)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// 1. Events → the shared card's Event
// ---------------------------------------------------------------------------

describe("leagueGameToEvent — a rename, never an invention", () => {
  const brief = (over: Partial<LeagueGameBrief> = {}): LeagueGameBrief => ({
    id: 15191156,
    home_team: "Minnesota Twins",
    away_team: "Philadelphia Phillies",
    commence_time: "2026-08-13T23:30:00+00:00",
    status: "live",
    home_score: 1,
    away_score: 5,
    home_win_probability: 0.0961,
    ...over,
  });

  test("both sides of the blend arrive, and away is the complement of home", () => {
    const e = leagueGameToEvent(brief());
    expect(e.current_odds!.home_probability).toBeCloseTo(0.0961, 6);
    expect(e.current_odds!.away_probability).toBeCloseTo(0.9039, 6);
  });

  test("a served current_odds is preferred over re-deriving it", () => {
    const e = leagueGameToEvent(
      brief({ current_odds: { home_probability: 0.4, away_probability: 0.6 } }),
    );
    expect(e.current_odds!.home_probability).toBe(0.4);
  });

  test("an UNPRICED game carries no current_odds at all — not a zero, not a half", () => {
    // #1776's other half, and the invariant the old rail was already right
    // about: null must never be drawn as a claim. `current_odds` absent is how
    // the shared card knows to withhold.
    const e = leagueGameToEvent(brief({ home_win_probability: null }));
    expect(e.current_odds).toBeUndefined();
  });

  test("team chrome and the live clock pass through under the names the card reads", () => {
    const e = leagueGameToEvent(
      brief({
        sport: "baseball_mlb",
        home_team_data: { primary_color: "#002B5C", secondary_color: null, logo_small: "x.png", logo_large: null, record: "60-58" },
        espn: { period: "T7", broadcast: "MLBN" },
      }),
    );
    expect(e.sport).toBe("baseball_mlb");
    expect(e.home_team_data!.primary_color).toBe("#002B5C");
    expect(e.espn!.period).toBe("T7");
  });

  test("a missing commence_time becomes an empty string, never the string 'Invalid Date'", () => {
    const e = leagueGameToEvent(brief({ commence_time: null }));
    expect(e.commence_time).toBe("");
  });
});

describe("cleanMarketName", () => {
  test("strips the league prefix and the trailing season", () => {
    expect(cleanMarketName("MLB: Team to win 100+ games")).toBe("Team to win 100+ games");
    expect(cleanMarketName("NBA Finals MVP 2026")).toBe("Finals MVP");
  });
});
