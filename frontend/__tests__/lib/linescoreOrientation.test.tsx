/**
 * THE SET SCORE STAYS POINTED AT THE RIGHT PLAYER (CERT-913).
 *
 * `slateRowLinescore.test.tsx` guards that the compact row DRAWS a line.
 * This guards that the line it draws belongs to the names beside it.
 *
 * ## Why a correct backend line is not enough
 *
 * The backend states the score in `home`/`away` columns, oriented to the
 * `sides` list it built the row with. Two consumers then re-order those sides
 * before anybody sees them:
 *
 *  - `matchListFromSlate` sorts the FAVOURITE first. Every row served
 *    underdog-first is therefore displayed reversed.
 *  - `matchListFromBracket` joins its slate row on an ORDER-INSENSITIVE pair
 *    key and renders the DRAW's top/bottom. About half of all joins adopt the
 *    opposite order.
 *
 * Carried across either, `6-4, 4-6, 2-1` becomes `4-6, 6-4, 1-2` — a different
 * match, attributed confidently, with nothing on the card to contradict it.
 * `orient_sides` already refuses to guess this upstream; refusing it there and
 * re-introducing it two layers later would be a wasted refusal.
 *
 * ## Both directions (gotcha #43)
 *
 * The flip must happen when the order changed AND must not happen when it did
 * not — a line flipped twice is a line inverted, and it would look exactly as
 * plausible as a correct one.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentMatches from "@/components/tournament/TournamentMatches";
import { buildBracket } from "@/lib/bracket";
import { formatLine, orientLinescore } from "@/lib/linescore";
import { matchListFromBracket, matchListFromSlate } from "@/lib/matchList";
import type { SlateMatch, SlateSide } from "@/lib/slate";
import type { TennisLinescore as Linescore } from "@/lib/types";

const ALCARAZ = "carlos-alcaraz";
const DJOKOVIC = "novak-djokovic";

/**
 * Alcaraz leads Djokovic 6-4, 4-6, 2-1 — stated home-first for Alcaraz, which
 * is what the backend emits when Alcaraz is `sides[0]`.
 *
 * `line` here is the string the BACKEND produced (`tennis_linescore.
 * format_line`), copied verbatim, so the pinning test below compares two real
 * implementations rather than one implementation with itself.
 */
const ALCARAZ_HOME: Linescore = {
  source: "espn",
  unit: "games",
  state: "in_progress",
  completion: "unknown",
  status_detail: "4th Set",
  was_suspended: false,
  sets: [
    { home: 6, away: 4, home_tiebreak: null, away_tiebreak: null, won_by: "home" },
    { home: 4, away: 6, home_tiebreak: null, away_tiebreak: null, won_by: "away" },
    { home: 2, away: 1, home_tiebreak: null, away_tiebreak: null, won_by: null },
  ],
  current_set: 3,
  sets_won: { home: 1, away: 1 },
  games: { home: 12, away: 11 },
  line: "6-4, 4-6, 2-1",
  home_entity_key: ALCARAZ,
  away_entity_key: DJOKOVIC,
  observed_at: "2026-09-04T23:30:00Z",
  points: null,
  serving: null,
  state_source: "espn",
  score_as_of: "2026-09-04T23:30:00Z",
  state_disagrees: false,
};

function side(overrides: Partial<SlateSide> = {}): SlateSide {
  return {
    entity_key: ALCARAZ,
    display_name: "Carlos Alcaraz",
    seed: 1,
    country: null,
    role: "participant",
    probability: 0.78,
    opening_probability: 0.74,
    move: 0.04,
    raw_probability: 0.78,
    raw_opening_probability: 0.74,
    age_hours: 0.2,
    price_state: "live",
    ...overrides,
  };
}

const DJOKOVIC_SIDE = side({
  entity_key: DJOKOVIC,
  display_name: "Novak Djokovic",
  seed: 7,
  probability: 0.22,
  opening_probability: 0.26,
  move: -0.04,
});

function match(overrides: Partial<SlateMatch> = {}): SlateMatch {
  return {
    matchup_key: "mens-singles:alcaraz-vs-djokovic:2026-09-04",
    draw: "mens-singles",
    draw_label: "Men's Singles",
    round: "SF",
    scheduled_date: "2026-09-04T23:00:00+00:00",
    sides: [side(), DJOKOVIC_SIDE],
    coherent: true,
    raw_sum: 1,
    opening_raw_sum: 1,
    probability_is_live: true,
    price_state: "live",
    observed_at: "2026-09-04T23:29:00+00:00",
    age_hours: 0.2,
    freshest_observed_at: "2026-09-04T23:29:00+00:00",
    freshest_age_hours: 0.2,
    stale_sides: [],
    mixed_freshness: false,
    favourite: ALCARAZ,
    has_moved: true,
    source_count: 1,
    linescore: ALCARAZ_HOME,
    ...overrides,
  };
}

// ═══════════════════ THE HELPER, ON ITS OWN ═══════════════════

describe("orientLinescore", () => {
  it("returns the line untouched when it already points the right way", () => {
    expect(orientLinescore(ALCARAZ_HOME, ALCARAZ, DJOKOVIC)).toBe(ALCARAZ_HOME);
  });

  it("flips EVERY column when the displayed order is reversed", () => {
    const flipped = orientLinescore(ALCARAZ_HOME, DJOKOVIC, ALCARAZ)!;

    expect(flipped.sets.map((s) => [s.home, s.away])).toEqual([
      [4, 6],
      [6, 4],
      [1, 2],
    ]);
    expect(flipped.sets.map((s) => s.won_by)).toEqual(["away", "home", null]);
    expect(flipped.sets_won).toEqual({ home: 1, away: 1 });
    expect(flipped.games).toEqual({ home: 11, away: 12 });
    expect(flipped.line).toBe("4-6, 6-4, 1-2");
    expect(flipped.home_entity_key).toBe(DJOKOVIC);
    expect(flipped.away_entity_key).toBe(ALCARAZ);
  });

  it("carries the tiebreak superscript to the side that still owns it", () => {
    const withTiebreak: Linescore = {
      ...ALCARAZ_HOME,
      sets: [
        { home: 7, away: 6, home_tiebreak: 7, away_tiebreak: 4, won_by: "home" },
      ],
      line: "7-6(4)",
    };
    const flipped = orientLinescore(withTiebreak, DJOKOVIC, ALCARAZ)!;

    expect(flipped.sets[0]).toEqual({
      home: 6,
      away: 7,
      home_tiebreak: 4,
      away_tiebreak: 7,
      won_by: "away",
    });
    // The bracket names the LOSER's points, and the loser did not change.
    expect(flipped.line).toBe("6-7(4)");
  });

  it("flips the server and the point score too", () => {
    const live: Linescore = {
      ...ALCARAZ_HOME,
      source: "statpal",
      points: { home: "40", away: "30" },
      serving: "home",
    };
    const flipped = orientLinescore(live, DJOKOVIC, ALCARAZ)!;

    expect(flipped.points).toEqual({ home: "30", away: "40" });
    expect(flipped.serving).toBe("away");
  });

  it("flipping twice is the identity — a flip is not a mutation", () => {
    const once = orientLinescore(ALCARAZ_HOME, DJOKOVIC, ALCARAZ)!;
    const twice = orientLinescore(once, ALCARAZ, DJOKOVIC)!;

    expect(twice.sets).toEqual(ALCARAZ_HOME.sets);
    expect(twice.line).toBe(ALCARAZ_HOME.line);
    expect(ALCARAZ_HOME.sets[0].home).toBe(6); // the original was never touched
  });

  // ── the refusals ──

  it("REFUSES a line that states no entity keys, rather than assuming it fits", () => {
    const anchorless = { ...ALCARAZ_HOME };
    delete anchorless.home_entity_key;
    delete anchorless.away_entity_key;

    expect(orientLinescore(anchorless, ALCARAZ, DJOKOVIC)).toBeNull();
  });

  it("REFUSES a line whose entities are not the two being displayed", () => {
    expect(orientLinescore(ALCARAZ_HOME, "jannik-sinner", "taylor-fritz")).toBeNull();
    expect(orientLinescore(ALCARAZ_HOME, ALCARAZ, "taylor-fritz")).toBeNull();
  });

  it("is null-safe on an absent line", () => {
    expect(orientLinescore(null, ALCARAZ, DJOKOVIC)).toBeNull();
    expect(orientLinescore(undefined, ALCARAZ, DJOKOVIC)).toBeNull();
  });

  it("reproduces the backend's own `line` string, so the two cannot drift", () => {
    expect(formatLine(ALCARAZ_HOME.sets)).toBe(ALCARAZ_HOME.line);
  });
});

// ═══════════════════ THE SLATE PATH — FAVOURITE-FIRST SORT ═══════════════════

describe("matchListFromSlate keeps the line with its player", () => {
  it("leaves the line alone when the favourite was already served first", () => {
    const [entry] = matchListFromSlate([match()]);

    expect(entry.sides.map((s) => s.entityKey)).toEqual([ALCARAZ, DJOKOVIC]);
    expect(entry.linescore!.line).toBe("6-4, 4-6, 2-1");
  });

  it("FLIPS the line when the underdog was served first and the sort reorders", () => {
    // The backend served Djokovic (the underdog) as `sides[0]`, so its line is
    // stated Djokovic-home. The favourite-first sort then displays Alcaraz
    // first, and the line must follow.
    const underdogFirst = match({
      sides: [DJOKOVIC_SIDE, side()],
      linescore: {
        ...ALCARAZ_HOME,
        sets: [
          { home: 4, away: 6, home_tiebreak: null, away_tiebreak: null, won_by: "away" },
          { home: 6, away: 4, home_tiebreak: null, away_tiebreak: null, won_by: "home" },
          { home: 1, away: 2, home_tiebreak: null, away_tiebreak: null, won_by: null },
        ],
        games: { home: 11, away: 12 },
        line: "4-6, 6-4, 1-2",
        home_entity_key: DJOKOVIC,
        away_entity_key: ALCARAZ,
      },
    });
    const [entry] = matchListFromSlate([underdogFirst]);

    expect(entry.sides.map((s) => s.entityKey)).toEqual([ALCARAZ, DJOKOVIC]);
    expect(entry.linescore!.line).toBe("6-4, 4-6, 2-1");
    expect(entry.linescore!.home_entity_key).toBe(ALCARAZ);
    expect(entry.linescore!.games).toEqual({ home: 12, away: 11 });
  });

  it("an incoherent pair keeps server order, and so does its line", () => {
    // `matchListFromSlate` skips the sort when the split is untrustworthy, so
    // there is nothing to re-orient and the line must NOT be flipped.
    const [entry] = matchListFromSlate([
      match({ sides: [DJOKOVIC_SIDE, side()], coherent: false }),
    ]);

    expect(entry.sides.map((s) => s.entityKey)).toEqual([DJOKOVIC, ALCARAZ]);
    expect(entry.linescore!.line).toBe("4-6, 6-4, 1-2");
  });
});

// ═══════════════════ THE BRACKET PATH — ORDER-BLIND JOIN ═══════════════════

describe("matchListFromBracket keeps the line with its player", () => {
  // `buildBracket` seeds the draw, so the two orders below differ by which
  // player the draw puts on top — the join finds the same slate row either way.
  const drawSide = (entity_key: string, display_name: string, seed: number) => ({
    entity_key,
    display_name,
    seed,
    probability: 0.3,
  });

  it("FLIPS the line when the draw's top is the slate row's away side", () => {
    const rounds = buildBracket([
      drawSide(DJOKOVIC, "Novak Djokovic", 7),
      drawSide(ALCARAZ, "Carlos Alcaraz", 1),
    ]);
    const [entry] = matchListFromBracket(rounds, { slate: [match()] });

    const [first, second] = entry.sides.map((s) => s.entityKey);
    expect(new Set([first, second])).toEqual(new Set([ALCARAZ, DJOKOVIC]));
    // Whichever way the draw ordered them, the first displayed side's first-set
    // games must be that player's — 6 for Alcaraz, 4 for Djokovic.
    const expectedFirstSet = first === ALCARAZ ? [6, 4] : [4, 6];
    expect([
      entry.linescore!.sets[0].home,
      entry.linescore!.sets[0].away,
    ]).toEqual(expectedFirstSet);
    expect(entry.linescore!.home_entity_key).toBe(first);
  });

  it("holds the same correspondence with the draw ordered the other way", () => {
    const rounds = buildBracket([
      drawSide(ALCARAZ, "Carlos Alcaraz", 1),
      drawSide(DJOKOVIC, "Novak Djokovic", 7),
    ]);
    const [entry] = matchListFromBracket(rounds, { slate: [match()] });

    const first = entry.sides[0].entityKey;
    const expectedFirstSet = first === ALCARAZ ? [6, 4] : [4, 6];
    expect([
      entry.linescore!.sets[0].home,
      entry.linescore!.sets[0].away,
    ]).toEqual(expectedFirstSet);
    expect(entry.linescore!.home_entity_key).toBe(first);
  });
});

// ═══════════════════ RENDERED — WHAT THE READER ACTUALLY SEES ═══════════════

describe("the rendered row attributes the score to the right name", () => {
  /** Visible text with markup collapsed, superscripts dropped first. */
  function visible(html: string): string {
    return html
      .replace(/<sup[^>]*>.*?<\/sup>/g, "")
      .replace(/<[^>]+>/g, " ")
      .replace(/&[a-z#0-9]+;/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  it("prints 6-4 first when Alcaraz is displayed first", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches entries={matchListFromSlate([match()])} />,
    );
    const text = visible(html);

    expect(text.indexOf("Carlos Alcaraz")).toBeLessThan(text.indexOf("Novak Djokovic"));
    expect(text.replace(/\s+/g, "")).toContain("6-44-62-1");
  });

  it("prints 6-4 first STILL when the backend served the underdog first", () => {
    // Same match, same true score, opposite server order. The reader must see
    // the identical card — this is the assertion the pre-repair tree fails.
    const underdogFirst = match({
      sides: [DJOKOVIC_SIDE, side()],
      linescore: {
        ...ALCARAZ_HOME,
        sets: [
          { home: 4, away: 6, home_tiebreak: null, away_tiebreak: null, won_by: "away" },
          { home: 6, away: 4, home_tiebreak: null, away_tiebreak: null, won_by: "home" },
          { home: 1, away: 2, home_tiebreak: null, away_tiebreak: null, won_by: null },
        ],
        games: { home: 11, away: 12 },
        line: "4-6, 6-4, 1-2",
        home_entity_key: DJOKOVIC,
        away_entity_key: ALCARAZ,
      },
    });
    const html = renderToStaticMarkup(
      <TournamentMatches entries={matchListFromSlate([underdogFirst])} />,
    );
    const text = visible(html);

    expect(text.indexOf("Carlos Alcaraz")).toBeLessThan(text.indexOf("Novak Djokovic"));
    expect(text.replace(/\s+/g, "")).toContain("6-44-62-1");
    expect(text.replace(/\s+/g, "")).not.toContain("4-66-41-2");
  });

  it("draws NO line at all when it cannot be oriented — never a guess", () => {
    const anchorless = { ...ALCARAZ_HOME };
    delete anchorless.home_entity_key;
    delete anchorless.away_entity_key;

    const html = renderToStaticMarkup(
      <TournamentMatches entries={matchListFromSlate([match({ linescore: anchorless })])} />,
    );
    const text = visible(html).replace(/\s+/g, "");

    expect(text).not.toContain("6-44-62-1");
    expect(text).not.toContain("4-66-41-2");
    // The row itself survives — only the line is withheld.
    expect(visible(html)).toContain("Carlos Alcaraz");
  });
});
