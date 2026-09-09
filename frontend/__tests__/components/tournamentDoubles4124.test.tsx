/**
 * THE DOUBLES GET A DOOR — #4124, lane1b/101.
 *
 * PILLAR: TRUTH · SHIP: `/tournaments/us-open` has a Doubles pill, and behind it
 * the doubles matches and results that were on `/hub/tennis` all along.
 *
 * Alex's issue measured the tournament payload at **0 occurrences of the
 * substring "oubles" in 935 KB**. The backend half of that is fixed in
 * `services/espn_tennis.py` (a doubles competitor carries a `roster`, not an
 * `athlete`, and every read went to the athlete); this file guards the half a
 * reader actually touches.
 *
 * THE THREE DESIGN CALLS, asserted rather than described:
 *
 * 1. **One Doubles pill, not three.** Alex's ruling 1 is one strip and never a
 *    stacked second list, and five pills do not fit 390px. The grouping is in
 *    the chrome; each row still carries its own `draw_label`, so a mixed-
 *    doubles row under the Doubles pill says "Mixed Doubles" on itself.
 * 2. **The pill is derived, never a constant.** A pill that opens an empty
 *    section teaches the reader we do not cover the doubles — the exact
 *    conclusion the ship exists to stop them drawing.
 * 3. **No board, no grid, no props behind it.** No venue quotes a doubles
 *    outright, so those three sections have nothing true to say; under standing
 *    notice 34 they render nothing rather than a paragraph about the emptiness.
 *    The grid one is not cosmetic: passed no grid, `TournamentBracket` falls
 *    through to a fallback that renders BOTH SINGLES championship boards, so a
 *    reader who tapped Doubles would have been shown the men's and women's
 *    title races under it.
 */

import fs from "fs";
import path from "path";

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import DrawToggle, {
  DRAWS,
  DOUBLES_DRAW,
  drawOptions,
} from "@/components/tournament/DrawToggle";
import TournamentProps from "@/components/tournament/TournamentProps";
import TournamentResults from "@/components/tournament/TournamentResults";
import {
  DOUBLES_DRAWS,
  DOUBLES_SELECTION,
  DRAW_LABELS,
  drawIsPriced,
  resultsForDraw,
  selectionDraws,
  type TournamentResult,
} from "@/lib/tournamentResults";

function result(
  draw: string,
  a: string,
  b: string,
  overrides: Partial<TournamentResult> = {}
): TournamentResult {
  return {
    matchup_key: `espn:${a}`,
    draw,
    draw_label: DRAW_LABELS[draw] ?? draw,
    round: "Quarterfinal",
    players: [
      { entity_key: `espn:pair:${a}`, display_name: a, is_winner: true },
      { entity_key: `espn:pair:${b}`, display_name: b, is_winner: false },
    ],
    winner_entity_key: `espn:pair:${a}`,
    score: "6-4, 6-3",
    completion: "final",
    completed_at: "2026-09-08T20:00:00Z",
    ...overrides,
  } as TournamentResult;
}

const MENS_DOUBLES = result(
  "mens-doubles",
  "Marcelo Melo / John Peers",
  "James Duckworth / Miomir Kecmanovic"
);
const MIXED_DOUBLES = result(
  "mixed-doubles",
  "Luisa Stefani / Neal Skupski",
  "Erin Routliffe / Lloyd Glasspool"
);
const MENS_SINGLES = result("mens-singles", "Carlos Alcaraz", "Jaime Faria");

describe("#4124 — the doubles selection", () => {
  it("selects all three doubles draws, and exactly one singles draw", () => {
    expect(selectionDraws(DOUBLES_SELECTION)).toEqual([...DOUBLES_DRAWS]);
    expect(selectionDraws("mens-singles")).toEqual(["mens-singles"]);
  });

  it("pulls every doubles draw into one list and leaves the singles out", () => {
    const results = {
      matches: [MENS_SINGLES, MENS_DOUBLES, MIXED_DOUBLES],
    } as never;
    expect(
      resultsForDraw(results, DOUBLES_SELECTION).map((m) => m.draw)
    ).toEqual(["mens-doubles", "mixed-doubles"]);
    // THE CONTROL: a singles pill is unchanged — one draw, its own rows.
    expect(resultsForDraw(results, "mens-singles").map((m) => m.draw)).toEqual([
      "mens-singles",
    ]);
  });

  it("is not a priced draw, which is what keeps three sections off it", () => {
    expect(drawIsPriced(DOUBLES_SELECTION)).toBe(false);
    expect(drawIsPriced("mens-singles")).toBe(true);
    expect(drawIsPriced("womens-singles")).toBe(true);
  });
});

describe("#4124 — the pill appears when there is something behind it", () => {
  it("adds Doubles once the payload carries a doubles row", () => {
    expect(drawOptions([[MENS_SINGLES], [MENS_DOUBLES]])).toEqual([
      ...DRAWS,
      DOUBLES_DRAW,
    ]);
  });

  it("finds it on either list — the slate or the finished one", () => {
    // Before the doubles draw starts the results list is empty and the slate is
    // not; after it finishes, the other way round. Reading one would blink the
    // pill out on the day the last doubles match ends.
    expect(drawOptions([[MIXED_DOUBLES], []])).toHaveLength(3);
    expect(drawOptions([[], [MIXED_DOUBLES]])).toHaveLength(3);
  });

  it("leaves the strip at two when there is nothing behind it", () => {
    expect(drawOptions([[MENS_SINGLES], [MENS_SINGLES]])).toEqual(DRAWS);
    expect(drawOptions([[], []])).toEqual(DRAWS);
    expect(drawOptions([])).toEqual(DRAWS);
  });

  it("renders three pills and no more — ruling 1's one strip", () => {
    const html = renderToStaticMarkup(
      <DrawToggle
        draw={DOUBLES_SELECTION}
        draws={drawOptions([[MENS_DOUBLES], []])}
        onSelect={() => {}}
      />
    );
    const pills = html.match(/data-draw="[^"]+"/g) ?? [];
    expect(pills).toEqual([
      'data-draw="mens-singles"',
      'data-draw="womens-singles"',
      'data-draw="doubles"',
    ]);
    expect(html).toContain(">Doubles<");
    // …and the one on screen is the one pressed.
    expect(html).toContain('data-draw="doubles" data-active="true"');
  });
});

describe("#4124 — what a reader sees behind the pill", () => {
  it("lists the doubles results, each row saying which doubles it is", () => {
    const html = renderToStaticMarkup(
      <TournamentResults
        results={
          {
            matches: [MENS_SINGLES, MENS_DOUBLES, MIXED_DOUBLES],
            count: 3,
          } as never
        }
        draw={DOUBLES_SELECTION}
        initialExpanded
      />
    );
    expect(html).toContain("Marcelo Melo / John Peers");
    expect(html).toContain("Luisa Stefani / Neal Skupski");
    // The singles row is behind a different pill.
    expect(html).not.toContain("Carlos Alcaraz");
  });

  it("shows nothing at all where a paragraph would have explained an absence", () => {
    // Standing notice 34: no diagnostic prose on a reader's screen. There is no
    // doubles outright market at either venue, so this section has nothing to
    // say and says nothing — the same call `TournamentResults` already makes.
    const html = renderToStaticMarkup(
      <TournamentProps markets={[]} draw={DOUBLES_SELECTION} />
    );
    expect(html).toBe("");
  });

  it("still explains a curation gap on a draw we DO price", () => {
    // THE CONTROL for the rule above. On a singles draw the empty box is the
    // only channel by which a curation gap reaches anyone who can close it, and
    // it must survive.
    const html = renderToStaticMarkup(
      <TournamentProps markets={[]} draw="mens-singles" />
    );
    expect(html).toContain('data-testid="props-empty"');
  });
});

/**
 * ═══ THE PAGE'S OWN TWO GATES ═══
 *
 * `app/tournaments/[slug]/page.tsx` is a client route with three GA4 hooks and
 * a fetch, and jest cannot render it — the same reason `DrawToggle` became a
 * component in the first place. So these two are source scans, and each is
 * SLICED to the region it is about rather than run over the whole file: a
 * bare `toContain` over 700 lines passes on any occurrence anywhere, including
 * a comment about the thing it is looking for.
 */
describe("#4124 — the page's two gates", () => {
  const PAGE = "app/tournaments/[slug]/page.tsx";

  function readSource(relative: string): string {
    const source = fs.readFileSync(
      path.join(__dirname, "..", "..", relative),
      "utf8"
    );
    // A source scan that cannot find its subject must RAISE, never quietly pass.
    if (source.trim().length === 0) {
      throw new Error(`source scan target is empty: ${relative}`);
    }
    return source;
  }

  it("gates the grid block on the selection being a priced draw", () => {
    const source = readSource(PAGE);
    const at = source.indexOf("<TournamentBracket");
    expect(at).toBeGreaterThan(0);
    // The 1,200 characters immediately before the component — i.e. its own
    // JSX guard and nothing else's.
    const guard = source.slice(Math.max(0, at - 1200), at);
    expect(guard).toContain("drawIsPriced(draw) && (");
  });

  it("filters the day's card through the selection, not through one draw", () => {
    const source = readSource(PAGE);
    const at = source.indexOf("buildMatchList({");
    expect(at).toBeGreaterThan(0);
    const call = source.slice(at, at + 900);
    expect(call).toContain("drawsShown.includes(match.draw");
  });
});
