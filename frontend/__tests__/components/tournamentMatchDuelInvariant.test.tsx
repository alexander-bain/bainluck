/**
 * #2452 — THE TWO NUMBERS ON A MATCH CARD ARE ONE ANSWER, asserted against output.
 *
 * Alex, reading `/tournaments/us-open` on 2026-08-31, added two numbers up:
 *
 *     Berrettini 78% + Wawrinka 23%   = 101
 *     Tabilo     91% + Hanfmann 10%   = 101
 *     Khachanov  78% + Burruchaga 22% = 100
 *     Halys      73% + Diaz Acosta 27% = 100
 *
 * Two of the four cards on his screen were wrong, and nothing on the page said
 * which. "Visible to anyone who adds two numbers on a page whose whole promise
 * is honest probability."
 *
 * ## What it actually was
 *
 * A tennis match quote is a complement pair BY CONSTRUCTION — the served
 * `/api/tournaments/{slug}` payload carries the two sides summing to 1.0 to six
 * places. `TournamentMatches` rounded each side independently with half-up, so
 * whenever `p * 100` landed on `.5` — which for a half-cent quote grid means
 * BOTH sides at once — both rounded up. It could never print 99. It printed 101
 * or it printed right.
 *
 * MEASURED on the live payload 2026-09-01, before the fix: **12 of the 30 match
 * cards printed 101**. `0.275/0.725`, `0.075/0.925`, `0.195/0.805`,
 * `0.065/0.935`, `0.965/0.035`, `0.505/0.495`, `0.865/0.135`, `0.945/0.055`,
 * `0.935/0.065` and three more. Two fifths of the visible list.
 *
 * The fix routes the pair through `renderedDuelPercents`, which is the
 * product's standing answer to exactly this question (`contracts/
 * rendered_percent.json`, shared with the server and Swift) and was already
 * load-bearing on the Discover card, the event hero, the feed card and this
 * page's own results list. This surface was the one that never adopted it.
 *
 * ## Why this file RENDERS rather than greps
 *
 * The same reason `discoverEventCardDuelInvariant` does, and it is #2060's
 * forced lesson: a source scan cannot tell a rendered field from a declared
 * one. `renderedPercentContract` proves the helper is RIGHT; only a render
 * proves the CARD shows it, and a mutation that computed the pair correctly and
 * then printed `side.matchProbability` anyway would pass every other test in
 * the tree.
 *
 * Both directions, per gotcha #43: a boundary pair is forced to 100, and an
 * ordinary pair — the other 18 of the 30 measured cards — is asserted
 * UNCHANGED, so a fix that simply normalized everything would fail here.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentMatches from "@/components/tournament/TournamentMatches";
import { matchListFromSlate } from "@/lib/matchList";
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

/** One priced, coherent, undecided match with the given pair. */
function pairMatch(first: number, second: number): SlateMatch {
  return {
    matchup_key: `mens-singles:a-vs-b:${first}`,
    draw: "mens-singles",
    draw_label: "Men's Singles",
    round: "R128",
    scheduled_date: "2026-09-01T15:00:00+00:00",
    sides: [
      side({ entity_key: "player-a", display_name: "Player A", probability: first }),
      side({ entity_key: "player-b", display_name: "Player B", probability: second }),
    ],
    coherent: true,
    raw_sum: first + second,
    opening_raw_sum: first + second,
    probability_is_live: true,
    price_state: "live",
    observed_at: "2026-09-01T14:50:00+00:00",
    age_hours: 0.2,
    freshest_observed_at: "2026-09-01T14:50:00+00:00",
    freshest_age_hours: 0.2,
    stale_sides: [],
    mixed_freshness: false,
    favourite: first >= second ? "player-a" : "player-b",
    has_moved: false,
    source_count: 1,
  } as SlateMatch;
}

function render(matches: SlateMatch[]): string {
  return renderToStaticMarkup(
    <TournamentMatches entries={matchListFromSlate(matches)} initialExpanded />
  );
}

/**
 * Every percent the match list actually PRINTS, in DOM order.
 *
 * Read off the rendered text of the `match-probability` span rather than off
 * `data-percent`: the attribute is a convenience for a human reading the DOM,
 * and asserting on it would let a render that computes the pair correctly and
 * then prints something else sail through. The text is what Alex added up.
 */
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

describe("#2452 — a match card's two percents sum to 100", () => {
  /**
   * The twelve live pairs, verbatim off `/api/tournaments/us-open` on
   * 2026-09-01. Every one of them printed 101 before the fix. They are listed
   * as data rather than folded into one representative case because the point
   * of the finding is that this was the COMMON shape on the page, not a corner
   * somebody constructed.
   */
  const MEASURED_101 : Array<[number, number]> = [
    [0.275, 0.725],
    [0.075, 0.925],
    [0.195, 0.805],
    [0.065, 0.935],
    [0.725, 0.275],
    [0.965, 0.035],
    [0.505, 0.495],
    [0.865, 0.135],
    [0.555, 0.445],
    [0.055, 0.945],
    [0.935, 0.065],
    [0.145, 0.855],
  ];

  it.each(MEASURED_101)("%f / %f prints a pair that totals 100", (a, b) => {
    const printed = printedPercents(render([pairMatch(a, b)]));
    expect(printed).toHaveLength(2);
    expect(printed[0] + printed[1]).toBe(100);
  });

  it("the whole measured slate totals 100 on every card, none of them 101", () => {
    const html = render(MEASURED_101.map(([a, b]) => pairMatch(a, b)));
    const printed = printedPercents(html);
    expect(printed).toHaveLength(MEASURED_101.length * 2);
    for (let i = 0; i < printed.length; i += 2) {
      expect(printed[i] + printed[i + 1]).toBe(100);
    }
  });

  /**
   * THE OTHER DIRECTION (gotcha #43). A pair that already rounded correctly
   * must round to the SAME two numbers — a fix that reached 100 by moving
   * numbers that were never wrong is a different bug wearing this one's clothes.
   */
  const MEASURED_ALREADY_100: Array<[number, number, number, number]> = [
    // [away, home, expected away pct, expected home pct]
    [0.189055, 0.810945, 19, 81],
    [0.222772, 0.777228, 22, 78],
    [0.341584, 0.658416, 34, 66],
    [0.939698, 0.060302, 94, 6],
    [0.78, 0.22, 78, 22],
  ];

  it.each(MEASURED_ALREADY_100)(
    "%f / %f is left alone at %i / %i",
    (a, b, expectedA, expectedB) => {
      const printed = printedPercents(render([pairMatch(a, b)]));
      // The list sorts the favourite first, so compare as a set of the pair.
      expect(printed.slice().sort((x, y) => x - y)).toEqual(
        [expectedA, expectedB].sort((x, y) => x - y)
      );
      expect(printed[0] + printed[1]).toBe(100);
    }
  );

  /**
   * AND THE PAIR THAT SHOULD NOT TOTAL 100 IS NOT FORCED TO.
   *
   * Two quotes summing to 0.94 are not a complement pair; normalizing them
   * would invent six points of probability. `renderedDuelPercents` leaves
   * anything outside [0.99, 1.01] alone, and that restraint has to be a
   * guarded property too — otherwise the fix for a 101 becomes a licence to
   * make up numbers on every card whose book is genuinely split.
   */
  it("does not normalize a pair that is not a complement", () => {
    const printed = printedPercents(render([pairMatch(0.6, 0.34)]));
    expect(printed.slice().sort((x, y) => x - y)).toEqual([34, 60]);
    expect(printed[0] + printed[1]).not.toBe(100);
  });
});
