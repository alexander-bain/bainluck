/**
 * #2450 — TWO COUNTS ON ONE SCREEN, EACH NAMING ITS POPULATION.
 *
 * Alex: *"`ROUND OF 128 · 25 matches` next to `FINISHED · Men's Singles · 71`.
 * Nothing explains how a 128-draw shows 25 live and 71 finished, or what
 * happened to the rest."*
 *
 * Both numbers were correct. Both counted a different population. Neither said
 * which, so the only arithmetic available to a reader was the one that fails.
 *
 * MEASURED on the live `/api/tournaments/us-open` payload 2026-09-01:
 *
 *   - the men's slate held **16** R128 matches, and `build_slate` reported
 *     dropping `ALREADY_PLAYED: 28, DECIDED: 66` — so the list is the round's
 *     unfinished remainder and structurally never the whole round;
 *   - the men's results held **84** rows: **41** main-draw (`Round 1`) and
 *     **43** across `Qualifying 1st Round`, `Qualifying 2nd Round` and
 *     `Qualifying Final`. More than half the total was qualifying.
 *
 * ## What is asserted, and what is deliberately NOT
 *
 * The fix states two things the page can stand behind — a round's size, which
 * is definitional (`R128` means 128 players means 64 matches), and that
 * qualifying is inside the finished total. It does NOT state how many of the
 * round have finished, and the last test in this file pins that down as a
 * property rather than an omission: 17 of the payload's 82 Round-1 results had
 * already lost their register matchup and 134 finished matches were dropped for
 * unregistered players, so a printed `the other 48 have finished` would sit
 * beside a Finished list showing 41 and replace one checkable-and-wrong sum
 * with another.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentMatches from "@/components/tournament/TournamentMatches";
import TournamentResults from "@/components/tournament/TournamentResults";
import {
  matchListFromSlate,
  matchRoundReconciliation,
  matchRoundSize,
} from "@/lib/matchList";
import { resultsPopulationNote } from "@/lib/tournamentResults";
import type { TournamentResult, TournamentResults as ResultsModel } from "@/lib/tournamentResults";
import type { SlateMatch, SlateSide } from "@/lib/slate";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

function side(overrides: Partial<SlateSide> = {}): SlateSide {
  return {
    entity_key: "player-a",
    display_name: "Player A",
    seed: null,
    country: null,
    role: "participant",
    probability: 0.6,
    opening_probability: null,
    move: null,
    raw_probability: 0.6,
    raw_opening_probability: null,
    age_hours: 0.2,
    price_state: "live",
    ...overrides,
  };
}

function pending(index: number, round = "R128"): SlateMatch {
  return {
    matchup_key: `mens-singles:m${index}`,
    draw: "mens-singles",
    draw_label: "Men's Singles",
    round,
    scheduled_date: "2026-09-01T15:00:00+00:00",
    sides: [
      side({ entity_key: `a${index}`, display_name: `Player A${index}`, probability: 0.6 }),
      side({ entity_key: `b${index}`, display_name: `Player B${index}`, probability: 0.4 }),
    ],
    coherent: true,
    raw_sum: 1,
    opening_raw_sum: 1,
    probability_is_live: true,
    price_state: "live",
    observed_at: "2026-09-01T14:50:00+00:00",
    age_hours: 0.2,
    freshest_observed_at: "2026-09-01T14:50:00+00:00",
    freshest_age_hours: 0.2,
    stale_sides: [],
    mixed_freshness: false,
    favourite: `a${index}`,
    has_moved: false,
    source_count: 1,
  } as SlateMatch;
}

function finished(index: number, espnRound: string): TournamentResult {
  return {
    matchup_key: `espn:${espnRound}:${index}`,
    draw: "mens-singles",
    draw_label: "Men's Singles",
    round: espnRound,
    players: [
      {
        entity_key: `w${index}`,
        display_name: `Winner ${index}`,
        seed: null,
        is_winner: true,
        prematch_probability: null,
      },
      {
        entity_key: `l${index}`,
        display_name: `Loser ${index}`,
        seed: null,
        is_winner: false,
        prematch_probability: null,
      },
    ],
    winner_entity_key: `w${index}`,
    score: "6-3, 6-4",
    completed_at: "2026-09-01T12:00Z",
    source_round: espnRound,
    source: "espn",
  } as TournamentResult;
}

function resultsModel(matches: TournamentResult[]): ResultsModel {
  return {
    matches,
    count: matches.length,
    unregistered_pairs: 0,
    winner_not_registered: 0,
    source_competitions: 199,
    source_scored: 181,
    source_errors: [],
  } as ResultsModel;
}

/** The live 2026-09-01 men's shape: 16 pending R128, 41 main draw, 43 qualifying. */
const LIVE_PENDING = Array.from({ length: 16 }, (_, i) => pending(i));
const LIVE_FINISHED = [
  ...Array.from({ length: 41 }, (_, i) => finished(i, "Round 1")),
  ...Array.from({ length: 18 }, (_, i) => finished(100 + i, "Qualifying 1st Round")),
  ...Array.from({ length: 14 }, (_, i) => finished(200 + i, "Qualifying 2nd Round")),
  ...Array.from({ length: 11 }, (_, i) => finished(300 + i, "Qualifying Final")),
];

describe("#2450 — a count on this page says which population it counts", () => {
  it("the match list states the round's true size beside what it is showing", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches entries={matchListFromSlate(LIVE_PENDING)} initialExpanded />
    );
    expect(html).toContain('data-testid="match-round-reconciliation"');
    expect(html).toContain("This round is 64 matches");
    // And the count it is explaining is still on the heading.
    expect(html).toContain("16 matches");
  });

  it("the finished total says qualifying is inside it", () => {
    const html = renderToStaticMarkup(
      <TournamentResults results={resultsModel(LIVE_FINISHED)} draw="mens-singles" />
    );
    expect(html).toContain('data-testid="results-population-note"');
    expect(html).toContain("Includes 43 qualifying matches");
    expect(html).toContain("· 84");
  });

  /**
   * A round's size is definitional, not a payload field: `R128` means 128
   * players and 128 players is 64 matches. Asserted across the ladder so a
   * later "simplification" into a lookup keyed on something we do not have
   * cannot pass.
   */
  it("knows every main-draw round's size, and refuses to invent qualifying's", () => {
    expect(matchRoundSize("R128")).toBe(64);
    expect(matchRoundSize("R64")).toBe(32);
    expect(matchRoundSize("R32")).toBe(16);
    expect(matchRoundSize("R16")).toBe(8);
    expect(matchRoundSize("QF")).toBe(4);
    expect(matchRoundSize("SF")).toBe(2);
    expect(matchRoundSize("F")).toBe(1);
    // Qualifying buckets three rounds of a draw whose size we do not know.
    expect(matchRoundSize("qualifying")).toBeNull();
    expect(matchRoundReconciliation("qualifying", 12)).toBeNull();
  });

  /**
   * THE OTHER DIRECTION (gotcha #43). A note is owed only where a reader's
   * arithmetic can fail. When the whole round is on the page there is nothing
   * missing to explain, and when nothing was qualifying the total already means
   * what it looks like — a line saying so in either case is the noise this fix
   * is supposed to be removing, not adding.
   */
  it("says nothing when there is nothing to reconcile", () => {
    expect(matchRoundReconciliation("F", 1)).toBeNull();
    expect(matchRoundReconciliation("QF", 4)).toBeNull();
    expect(matchRoundReconciliation("QF", 3)).toContain("4 matches");

    const mainDrawOnly = Array.from({ length: 41 }, (_, i) => finished(i, "Round 1"));
    expect(resultsPopulationNote(mainDrawOnly)).toBeNull();
    const html = renderToStaticMarkup(
      <TournamentResults results={resultsModel(mainDrawOnly)} draw="mens-singles" />
    );
    expect(html).not.toContain('data-testid="results-population-note"');
  });

  /**
   * AND IT DOES NOT CLAIM A FINISHED-COUNT.
   *
   * We know the round's size and what is in the list; we do NOT know how many
   * of the remainder our results feed holds. On the live payload the men's
   * R128 had 16 pending against a 64-match round, while the results list showed
   * 41 — so `the other 48 have finished` would be a second checkable sum that
   * also fails. The page states the size and stops.
   */
  it("never asserts how many of the round have finished", () => {
    const note = matchRoundReconciliation("R128", 16) ?? "";
    expect(note).toContain("64 matches");
    expect(note).not.toContain("48");
    expect(note).not.toMatch(/\d+\s+(have\s+)?finished/);
  });
});
