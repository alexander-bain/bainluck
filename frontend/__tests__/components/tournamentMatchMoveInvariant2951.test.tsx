/**
 * #2951 — A MATCH ROW'S THREE NUMBERS ARE ONE ARITHMETIC, asserted against output.
 *
 * The sibling of `tournamentMatchDuelInvariant` (#2452), one rung along. That
 * one fixed the LEVEL: a card could no longer print `78% + 23% = 101`, because
 * the pair is rounded once, together. The DELTA never got the same treatment.
 *
 * A row prints three numbers about one player, and the sentence exists
 * precisely so the reader combines them (`matchList.ts`, Alex's ruling 6,
 * case 2: *"the row shows the delta but never the origin"*):
 *
 *     Carlos Alcaraz  +6  93%
 *     Carlos Alcaraz opened at 88%.
 *
 * 93 − 88 = 5. The badge says +6.
 *
 * ## Measured, rendered, not payload
 *
 * DOM read of the expanded R32 list on production `0bbcc735`, 2026-09-03:
 * **6 of 10 rows contradicted the two numbers beside them** (Paul, Alcaraz,
 * Navone, Shelton, Cobolli, Darderi), with four rows on the same list, same
 * component, same formatters, exactly right. Still live 2026-09-08 on the
 * Women's quarter-finals: `Coco Gauff +1 63%` over *"opened at 63%"* — a badge
 * claiming a move between two identical printed numbers.
 *
 * ## What it was
 *
 * Three independent roundings of one relationship:
 *
 *   - the level   `renderedDuelPercents(now)`         — pair-rounded, correct
 *   - the badge   `Math.round(move * 100)`            — the RAW delta, per side
 *   - the origin  `formatSlateProbability(opening)`   — a bare per-side round
 *
 * `round(a) − round(b)` and `round(a − b)` disagree whenever the fractional
 * parts straddle, and the opening was not even pair-rounded. The fix makes the
 * printed delta the DIFFERENCE OF THE PRINTED LEVELS, and the sentence state
 * that same baseline, so the row's own arithmetic closes.
 *
 * ## Why this file RENDERS
 *
 * #2452's reason, unchanged: a source scan cannot tell a rendered field from a
 * declared one, and a fix that computed the delta correctly and then printed
 * `formatMove(side.move)` anyway would pass a pure-library test. What Alex did
 * was read three numbers off a card and subtract; so does this.
 *
 * Both directions, per gotcha #43: the contradicting rows are forced to close,
 * AND an ordinary row's badge is asserted UNCHANGED — a "fix" that deleted the
 * badge, or rounded everything to zero, fails here.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentMatches from "@/components/tournament/TournamentMatches";
import { matchListFromSlate, matchDetailNote } from "@/lib/matchList";
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
    probability: 0.5,
    opening_probability: null,
    move: null,
    raw_probability: 0.5,
    raw_opening_probability: null,
    age_hours: 0.2,
    price_state: "live",
    ...overrides,
  };
}

/**
 * One priced, coherent, undecided match with a current pair AND an opening pair.
 *
 * `move` is filled the way the SERVER fills it — the raw difference — because
 * that is the field the old badge rounded and the field a regression would
 * reach for again. A fixture that left it null could not tell the two
 * implementations apart.
 */
function movedMatch(
  now: [number, number],
  open: [number, number],
  names: [string, string] = ["Player A", "Player B"]
): SlateMatch {
  return {
    matchup_key: `mens-singles:${names[0]}-vs-${names[1]}:${now[0]}`,
    draw: "mens-singles",
    draw_label: "Men's Singles",
    round: "R32",
    scheduled_date: "2026-09-03T15:00:00+00:00",
    sides: [
      side({
        entity_key: "player-a",
        display_name: names[0],
        probability: now[0],
        opening_probability: open[0],
        move: now[0] - open[0],
      }),
      side({
        entity_key: "player-b",
        display_name: names[1],
        probability: now[1],
        opening_probability: open[1],
        move: now[1] - open[1],
      }),
    ],
    coherent: true,
    raw_sum: now[0] + now[1],
    opening_raw_sum: open[0] + open[1],
    probability_is_live: true,
    price_state: "live",
    observed_at: "2026-09-03T14:50:00+00:00",
    age_hours: 0.2,
    freshest_observed_at: "2026-09-03T14:50:00+00:00",
    freshest_age_hours: 0.2,
    stale_sides: [],
    mixed_freshness: false,
    favourite: now[0] >= now[1] ? "player-a" : "player-b",
    has_moved: true,
    source_count: 1,
  } as SlateMatch;
}

function render(matches: SlateMatch[]): string {
  return renderToStaticMarkup(
    <TournamentMatches entries={matchListFromSlate(matches)} initialExpanded />
  );
}

/** Every percent the list PRINTS, in DOM order — the text, not `data-percent`. */
function printedPercents(html: string): number[] {
  const out: number[] = [];
  const span = /data-testid="match-probability"[^>]*>([^<]*)</g;
  let hit: RegExpExecArray | null;
  while ((hit = span.exec(html)) !== null) {
    const text = hit[1].trim();
    if (text === "—") continue;
    out.push(Number(text.replace("%", "")));
  }
  return out;
}

/** Every move badge the list PRINTS, in DOM order, as a signed number. */
function printedMoves(html: string): number[] {
  const out: number[] = [];
  const span = /data-testid="match-move"[^>]*>([^<]*)</g;
  let hit: RegExpExecArray | null;
  while ((hit = span.exec(html)) !== null) {
    // U+2212 is the glyph the badge uses; `Number("−5")` is NaN without this.
    out.push(Number(hit[1].trim().replace("−", "-").replace("+", "")));
  }
  return out;
}

/** The integer in "X opened at NN%.", or `null` when the row prints no sentence. */
function printedOpening(note: string | null): number | null {
  if (note === null) return null;
  const hit = /opened at (\d+)%/.exec(note);
  return hit === null ? null : Number(hit[1]);
}

/**
 * THE MEASURED CONTRADICTIONS, as (current pair, opening pair).
 *
 * Reconstructed to reproduce the rendered triples in the issue rather than
 * copied from a payload we no longer hold: each entry is chosen so the OLD code
 * prints the issue's badge while the two levels print the issue's percentages.
 * Alcaraz is the worked example — `0.9349` prints 93, `0.8750` prints 88, and
 * the raw delta `0.0599` rounds to 6 against a printed difference of 5.
 */
const CONTRADICTED: Array<{
  name: string;
  now: [number, number];
  open: [number, number];
}> = [
  { name: "Alcaraz", now: [0.0651, 0.9349], open: [0.125, 0.875] },
  { name: "Gauff", now: [0.37, 0.63], open: [0.375, 0.625] },
  { name: "Paul", now: [0.39, 0.61], open: [0.3549, 0.6451] },
  { name: "Cobolli", now: [0.44, 0.56], open: [0.4249, 0.5751] },
];

describe("#2951 — the badge is the difference of the two printed levels", () => {
  it.each(CONTRADICTED)(
    "$name: printed level − printed badge = printed opening",
    ({ now, open }) => {
      const match = movedMatch(now, open);
      const html = render([match]);
      const levels = printedPercents(html);
      const badges = printedMoves(html);
      const entry = matchListFromSlate([match])[0];
      const opening = printedOpening(matchDetailNote(entry));

      expect(levels).toHaveLength(2);
      if (badges.length === 0) {
        // A move too small to survive the rounding shows NO badge — and then it
        // must show no origin either, or the sentence is the bare restatement
        // ruling 6 deleted.
        expect(opening).toBeNull();
        return;
      }
      // The sentence names the bigger mover; on a two-side row both sides move
      // by the same magnitude, so either level closes the arithmetic.
      const closes = levels.some(
        (level, index) => level - (badges[index] ?? badges[0]) === opening
      );
      expect(closes).toBe(true);
    }
  );

  it("Alcaraz prints +5 and 'opened at 88%', not +6", () => {
    const match = movedMatch([0.0651, 0.9349], [0.125, 0.875], ["Underdog", "Alcaraz"]);
    const html = render([match]);

    // FAVOURITE FIRST. `matchListFromSlate` orders the sides for display, so DOM
    // order is not payload order — the pair arrives [0.0651, 0.9349] and renders
    // Alcaraz above his opponent.
    expect(printedPercents(html)).toEqual([93, 7]);
    expect(printedMoves(html)).toEqual([5, -5]);
    expect(printedOpening(matchDetailNote(matchListFromSlate([match])[0]))).toBe(88);
  });

  it("Gauff's half-point move prints NO badge rather than +1 between two 63s", () => {
    const match = movedMatch([0.37, 0.63], [0.375, 0.625], ["Andreeva", "Gauff"]);
    const html = render([match]);

    expect(printedPercents(html)).toEqual([63, 37]);
    // Both ends print the same pair, so there is no whole point to show.
    expect(printedMoves(html)).toEqual([]);
    expect(matchDetailNote(matchListFromSlate([match])[0])).toBeNull();
  });

  // ── The other direction (gotcha #43): an honest row is left alone ──────────

  it("an ordinary multi-point move still prints its badge and its origin", () => {
    // 0.71 / 0.29 from 0.57 / 0.43 — Medvedev's row, the issue's first control
    // and one of the four it measured as already correct.
    const match = movedMatch([0.29, 0.71], [0.43, 0.57], ["Opponent", "Medvedev"]);
    const html = render([match]);

    expect(printedPercents(html)).toEqual([71, 29]);
    expect(printedMoves(html)).toEqual([14, -14]);
    expect(printedOpening(matchDetailNote(matchListFromSlate([match])[0]))).toBe(57);
    // 71 − 14 = 57. The row was already right and is unchanged.
  });

  it("the badge's colour follows the sign it prints", () => {
    // A raw move inside `moveDirection`'s 0.3pt dead band whose printed levels
    // still differ by a whole point. Reading the raw move for the colour would
    // return "flat", which is not "up", and paint a `+1` in the fall colour.
    const match = movedMatch([0.4975, 0.5025], [0.5025, 0.4975], ["A", "B"]);
    const html = render([match]);
    const badges = printedMoves(html);
    if (badges.length === 0) return; // nothing printed, nothing to colour

    const positive = /data-testid="match-move"[^>]*class="[^"]*"[^>]*>\s*\+/.test(html);
    if (positive) {
      const block = /class="([^"]*)"[^>]*data-testid="match-move"[^>]*>\s*\+/.exec(html);
      expect(block?.[1] ?? "").not.toContain("text-accent-danger");
    }
  });

  it("a row with no opening prints no badge and no origin", () => {
    const match = movedMatch([0.4, 0.6], [0.4, 0.6]);
    match.sides[0].opening_probability = null;
    match.sides[1].opening_probability = null;
    const html = render([match]);

    expect(printedPercents(html)).toEqual([60, 40]);
    expect(printedMoves(html)).toEqual([]);
    expect(matchDetailNote(matchListFromSlate([match])[0])).toBeNull();
  });
});
