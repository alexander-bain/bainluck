/**
 * #2449 — ONE TOURNAMENT, ONE NAME PER ROUND, asserted on one screen.
 *
 * Alex, on `/tournaments/us-open`: *"the left column header reads `ROUND OF
 * 128` while every row in the Finished list reads `ROUND 1`. Same round, two
 * names, one screen."*
 *
 * MEASURED on the live payload 2026-09-01: all 82 men's + women's `Round 1`
 * results carry `round` AND `source_round` set to ESPN's `"Round 1"`, while the
 * 30 undecided matches of the SAME round carry the register's `"R128"` and the
 * match list heads them `Round of 128`. Both lists were on the screen at once.
 *
 * ## Why the guard renders BOTH components
 *
 * The defect is not "the results list uses the wrong word" — either vocabulary
 * is defensible on its own. The defect is that two surfaces sharing a screen
 * disagree, and a test that only checked the results heading would pass just as
 * happily if somebody later "fixed" the match list into ESPN's vocabulary and
 * broke the pills, the grid and the bracket with it.
 *
 * So the load-bearing assertion below renders the match list and the results
 * list from ONE round's data and asserts the union of the two DOMs contains one
 * name for that round and not the other. That is Alex's sentence, executable.
 *
 * Both directions, per gotcha #43: the main-draw ordinal is translated, and
 * ESPN's finer QUALIFYING wording is asserted to survive untouched — the
 * register buckets three qualifying rounds into one and ESPN's split is real
 * information, so a fix that flattened everything into the register's ladder
 * would be a different regression wearing this one's clothes.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentMatches from "@/components/tournament/TournamentMatches";
import TournamentResults from "@/components/tournament/TournamentResults";
import { matchListFromSlate } from "@/lib/matchList";
import { registerRoundFromSource, roundHeading } from "@/lib/tournamentResults";
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

/** An undecided match in the register's vocabulary — what the match list gets. */
function pendingMatch(registerRound: string): SlateMatch {
  return {
    matchup_key: `mens-singles:a-vs-b:${registerRound}`,
    draw: "mens-singles",
    draw_label: "Men's Singles",
    round: registerRound,
    scheduled_date: "2026-09-01T15:00:00+00:00",
    sides: [
      side({ entity_key: "player-a", display_name: "Player A", probability: 0.6 }),
      side({ entity_key: "player-b", display_name: "Player B", probability: 0.4 }),
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
    favourite: "player-a",
    has_moved: false,
    source_count: 1,
  } as SlateMatch;
}

/** A finished match in ESPN's vocabulary — what the results list gets. */
function finished(espnRound: string): TournamentResult {
  return {
    matchup_key: `espn:${espnRound}`,
    draw: "mens-singles",
    draw_label: "Men's Singles",
    round: espnRound,
    players: [
      {
        entity_key: "player-c",
        display_name: "Player C",
        seed: null,
        is_winner: true,
        prematch_probability: null,
      },
      {
        entity_key: "player-d",
        display_name: "Player D",
        seed: null,
        is_winner: false,
        prematch_probability: null,
      },
    ],
    winner_entity_key: "player-c",
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

describe("#2449 — the two lists on one screen name a round the same way", () => {
  /**
   * THE FINDING, EXECUTABLE. The live payload's exact pairing: the pending
   * half of the first round arrives as `R128`, the finished half as `Round 1`,
   * and both lists render into the same column of the same page.
   */
  it("prints ONE name for the first round across the match list and the results list", () => {
    const screen =
      renderToStaticMarkup(
        <TournamentMatches entries={matchListFromSlate([pendingMatch("R128")])} initialExpanded />
      ) +
      renderToStaticMarkup(
        <TournamentResults
          results={resultsModel([finished("Round 1")])}
          draw="mens-singles"
          initialExpanded
        />
      );

    expect(screen).toContain("Round of 128");
    // The whole complaint: the other name must not also be on the screen.
    expect(screen).not.toMatch(/>\s*Round 1\s*</);
  });

  it("translates every ESPN main-draw round onto the register's ladder", () => {
    // Ordinals, resolved against the 7-round Grand Slam ladder.
    expect(roundHeading(finished("Round 1"))).toBe("Round of 128");
    expect(roundHeading(finished("Round 2"))).toBe("Round of 64");
    expect(roundHeading(finished("Round 3"))).toBe("Round of 32");
    expect(roundHeading(finished("Round 4"))).toBe("Round of 16");
    // Rounds ESPN names for itself, which need no ladder at all.
    expect(roundHeading(finished("Round of 16"))).toBe("Round of 16");
    expect(roundHeading(finished("Quarterfinals"))).toBe("Quarter-finals");
    expect(roundHeading(finished("Semifinals"))).toBe("Semi-finals");
    expect(roundHeading(finished("Final"))).toBe("Final");
  });

  /**
   * THE LADDER IS A PARAMETER, NOT A CONSTANT. `Round 1` is the round of 128 in
   * a 128-draw and the round of 32 in a 32-draw; resolving an ordinal without
   * the ladder length is the guess this signature exists to refuse.
   */
  it("resolves an ordinal against the draw it is actually in", () => {
    expect(registerRoundFromSource("Round 1", 7)).toBe("R128");
    expect(registerRoundFromSource("Round 1", 5)).toBe("R32");
    // A 3-round draw is 8 players: QF, SF, F. Its first round IS the
    // quarter-finals — the ladder is anchored at the FINAL, exactly as
    // `buildBracket` anchors the fold, so a shorter draw starts further in.
    expect(registerRoundFromSource("Round 1", 3)).toBe("QF");
    expect(registerRoundFromSource("Round 3", 3)).toBe("F");
    expect(roundHeading(finished("Round 1"), 5)).toBe("Round of 32");
  });

  /**
   * THE OTHER DIRECTION (gotcha #43). ESPN splits qualifying into three rounds
   * where the register holds one bucket, so its wording there is strictly finer
   * than ours and must survive. `Qualifying` visibly contains `Qualifying 1st
   * Round`; `Round of 128` does not contain `Round 1`, which is the whole
   * difference between a refinement and a contradiction.
   */
  it("leaves ESPN's finer qualifying wording alone", () => {
    expect(roundHeading(finished("Qualifying 1st Round"))).toBe("Qualifying 1st Round");
    expect(roundHeading(finished("Qualifying 2nd Round"))).toBe("Qualifying 2nd Round");
    expect(roundHeading(finished("Qualifying Final"))).toBe("Qualifying Final");
    // And it is never folded onto a main-draw round: a qualifying final is not
    // the tournament's final.
    expect(registerRoundFromSource("Qualifying Final")).toBeNull();
    expect(registerRoundFromSource("Qualifying 1st Round")).toBeNull();
  });

  /** An unrecognised round is ESPN's words, not a guess. */
  it("passes an unrecognised round through verbatim", () => {
    expect(roundHeading(finished("Consolation Playoff"))).toBe("Consolation Playoff");
    expect(registerRoundFromSource("Consolation Playoff")).toBeNull();
    expect(registerRoundFromSource("Round 99")).toBeNull();
    expect(registerRoundFromSource("")).toBeNull();
    expect(registerRoundFromSource(null)).toBeNull();
  });

  /**
   * THE THIRD NAME IS GONE. `ROUND_HEADINGS` used to say `First round` for
   * `R128` — a wording nothing on the page ever printed, because `source_round`
   * always won the branch above it, and one that would have become a third name
   * for the same round the moment it did. It is now `ROUND_LABELS` spread, so
   * the two tables cannot drift apart again.
   */
  it("has no wording of its own for a round the register already names", () => {
    const { ROUND_HEADINGS } = require("@/lib/tournamentResults");
    const { ROUND_LABELS } = require("@/lib/bracket");
    for (const [key, label] of Object.entries(ROUND_LABELS)) {
      expect(ROUND_HEADINGS[key]).toBe(label);
    }
    expect(Object.values(ROUND_HEADINGS)).not.toContain("First round");
  });
});
