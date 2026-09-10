/**
 * ONE HEADING, ONCE — #4803, ux/1183.
 *
 * PILLAR: TRUTH · SHIP 6 (#4460) · the Doubles tab stops claiming the US Open
 * played quarter-finals, then semi-finals, then quarter-finals again.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `/tournaments/us-open` → Doubles, 390px, production `d29c068a`:
 *
 *     QUARTER-FINALS      Harrison / Skupski, Heliovaara / Patten, Ram / Salisbury
 *     SEMI-FINALS         Krueger / Montgomery
 *     QUARTER-FINALS      Krawietz / Puetz
 *
 * Read literally, that is a tournament that went backwards.
 *
 * ═══ THE FILED CAUSE, AND THE HALF OF IT THAT WAS WRONG ═══
 *
 * #4803 diagnosed it as the Doubles pill merging three draws (#4124) while the
 * band was keyed on `round` alone, and concluded *"the men's and women's tabs
 * do not show this because each is a single draw."*
 *
 * The first half is right. The second half is not, and it is why this file
 * guards two shapes instead of one. Replaying the live payload 2026-09-10
 * through the band logic:
 *
 *     tab              rows   bands   distinct rounds   REPEATED
 *     mens-singles      219      16          8               2   (Round 1 ×5, Round 2 ×5)
 *     womens-singles    220      18          8               2   (Round 1 ×6, Round 2 ×6)
 *     doubles           143      42          8               7   (Round 2 ×11, …)
 *
 * A single draw interleaves with ITSELF: halves of a 128-draw progress at
 * different rates and rain moves matches, so a bottom-half Round 1 finishes
 * after a top-half Round 2. The singles tabs were never immune — they were
 * immune in the COLLAPSED five-row preview, where the newest five happened to
 * share a round. Expanded, all three tabs were wrong.
 *
 * So the fix is not a better sort key, and these tests are not "does the
 * doubles case work". They assert the invariant directly: **a band's text
 * appears once per list**, whatever the draw count and whatever the round
 * vocabulary (`roundHeading` passes ESPN's own words through verbatim for
 * anything the register cannot name, and those have no rung to sort on).
 *
 * The fixture MIXES DRAWS and MIXES ROUNDS OUT OF LADDER ORDER on purpose. A
 * single-draw, monotonic fixture is green on the parent commit — which is
 * exactly how this shipped.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentResults from "@/components/tournament/TournamentResults";
import {
  DRAW_LABELS,
  groupedResults,
  resultsSpanDraws,
  selectionLabel,
  sortedResults,
  type TournamentResult,
  type TournamentResults as ResultsModel,
} from "@/lib/tournamentResults";

function result(
  draw: string,
  round: string,
  winner: string,
  completedAt: string
): TournamentResult {
  return {
    matchup_key: `espn:${draw}:${round}:${winner}`,
    draw,
    draw_label: DRAW_LABELS[draw] ?? draw,
    round,
    source_round: round,
    players: [
      { entity_key: `espn:pair:${winner}`, display_name: winner, is_winner: true },
      { entity_key: `espn:pair:${winner}-opp`, display_name: `${winner} opponent`, is_winner: false },
    ],
    winner_entity_key: `espn:pair:${winner}`,
    score: "6-4, 6-3",
    completion: "final",
    completed_at: completedAt,
    source: "espn",
  } as TournamentResult;
}

function model(matches: TournamentResult[]): ResultsModel {
  return {
    matches,
    count: matches.length,
    unregistered_pairs: 0,
    winner_not_registered: 0,
    source_competitions: matches.length,
    source_scored: matches.length,
    source_errors: [],
  } as ResultsModel;
}

/**
 * The band texts a rendered section prints, in order — as a READER sees them.
 *
 * `renderToStaticMarkup` escapes the apostrophe in `Men's Doubles` to `&#x27;`,
 * so the entities are decoded here. Asserting against the escaped form would
 * pin the serializer's encoding rather than the words on the page.
 */
function bands(html: string): string[] {
  const found = [...html.matchAll(/data-testid="result-round"[^>]*>([^<]*)</g)];
  return found.map((match) =>
    match[1]
      .replace(/&#x27;/g, "'")
      .replace(/&quot;/g, '"')
      .replace(/&amp;/g, "&")
      .trim()
  );
}

/**
 * The five rows #4803 photographed, in the completion order the payload
 * serves them (newest first). Three men's quarter-finals, a women's
 * semi-final, then a fourth men's quarter-final.
 */
const FILED_SPECIMEN = [
  result("mens-doubles", "Quarterfinal", "Harrison / Skupski", "2026-09-10T02:45Z"),
  result("mens-doubles", "Quarterfinal", "Heliovaara / Patten", "2026-09-09T23:10Z"),
  result("mens-doubles", "Quarterfinal", "Ram / Salisbury", "2026-09-09T22:20Z"),
  result("womens-doubles", "Semifinal", "Krueger / Montgomery", "2026-09-09T22:15Z"),
  result("mens-doubles", "Quarterfinal", "Krawietz / Puetz", "2026-09-09T22:05Z"),
];

function renderDoubles(matches: TournamentResult[], expandedList = true): string {
  return renderToStaticMarkup(
    <TournamentResults
      results={model(matches)}
      draw="doubles"
      initialExpanded={expandedList}
    />
  );
}

describe("#4803 — a results band appears once per list", () => {
  it("renders the filed five rows with no repeated heading", () => {
    // THE SPECIMEN. On the parent this is
    // ["Quarter-finals", "Semi-finals", "Quarter-finals"].
    const printed = bands(renderDoubles(FILED_SPECIMEN));

    expect(printed.length).toBe(new Set(printed).size);
    expect(printed.length).toBe(2);
  });

  it("names the draw on every band when the list merges draws", () => {
    // The issue's second requirement: a reader must be able to tell WHICH
    // draw's quarter-finals they are looking at. `draw_label` has been on
    // every row since #4124 and no surface read it.
    const printed = bands(renderDoubles(FILED_SPECIMEN));

    expect(printed).toEqual([
      "Men's Doubles · Quarter-finals",
      "Women's Doubles · Semi-finals",
    ]);
  });

  it("keeps every row exactly once when it regroups them", () => {
    // Grouping REORDERS; it must never drop or duplicate. The bug this guards
    // against is a fix that dedupes the heading by dropping the rows under it.
    const html = renderDoubles(FILED_SPECIMEN);

    for (const match of FILED_SPECIMEN) {
      const winner = match.players[0].display_name;
      expect(html.split(winner).length - 1).toBeGreaterThanOrEqual(1);
    }
    const regrouped = groupedResults(sortedResults(FILED_SPECIMEN));
    expect(regrouped.length).toBe(FILED_SPECIMEN.length);
    expect(new Set(regrouped.map((row) => row.matchup_key)).size).toBe(
      FILED_SPECIMEN.length
    );
  });

  it("holds on ONE draw whose rounds interleave — the half #4803 ruled out", () => {
    // Men's singles on the live payload: Round 1 printed five times. One draw,
    // no merge. This is the case a single-draw fixture cannot catch and the
    // reason the singles tabs shipped with the same defect.
    const interleaved = [
      result("mens-singles", "Round 2", "Alcaraz", "2026-09-04T23:00Z"),
      result("mens-singles", "Round 1", "Fearnley", "2026-09-04T21:00Z"),
      result("mens-singles", "Round 2", "Sinner", "2026-09-04T19:00Z"),
      result("mens-singles", "Round 1", "Shelton", "2026-09-04T17:00Z"),
    ];

    const html = renderToStaticMarkup(
      <TournamentResults
        results={model(interleaved)}
        draw="mens-singles"
        initialExpanded
      />
    );
    const printed = bands(html);

    expect(printed.length).toBe(new Set(printed).size);
    expect(printed.length).toBe(2);
  });

  it("does NOT prefix the draw on a single-draw list", () => {
    // THE CONTROL, and a notice-34 rule: the section heading already says
    // `Finished · Men's Singles`, so repeating it on every band is noise. This
    // also pins that the singles tabs are visually unchanged by the fix.
    const html = renderToStaticMarkup(
      <TournamentResults
        results={model([
          result("mens-singles", "Quarterfinal", "Alcaraz", "2026-09-09T23:00Z"),
          result("mens-singles", "Round 4", "Sinner", "2026-09-08T23:00Z"),
        ])}
        draw="mens-singles"
        initialExpanded
      />
    );

    expect(bands(html)).toEqual(["Quarter-finals", "Round of 16"]);
  });

  it("prints the same band text collapsed as expanded", () => {
    // A heading must not depend on how many rows are visible. `spansDraws` is
    // asked of the whole list precisely so `Show all` cannot grow a draw name
    // onto a band that did not have one.
    const many = [
      ...FILED_SPECIMEN,
      result("mens-doubles", "Round 3", "Bolelli / Vavassori", "2026-09-08T23:30Z"),
      result("mixed-doubles", "Final", "Errani / Vavassori", "2026-09-07T23:30Z"),
    ];

    const collapsed = bands(renderDoubles(many, false));
    const expanded = bands(renderDoubles(many, true));

    expect(collapsed.length).toBe(new Set(collapsed).size);
    expect(expanded.length).toBe(new Set(expanded).size);
    // Every band the collapsed preview shows says exactly what it says expanded.
    expect(expanded.slice(0, collapsed.length)).toEqual(collapsed);
  });
});

describe("#4803 — the section heading names the pill, not its slug", () => {
  it("calls the doubles selection Doubles", () => {
    // `DRAW_LABELS` is keyed on real draws and `doubles` is a SELECTION over
    // three of them, so the lookup missed and the page printed the raw pill id:
    // `FINISHED · doubles · 143`.
    expect(selectionLabel("doubles")).toBe("Doubles");

    const html = renderDoubles(FILED_SPECIMEN);
    expect(html).toContain("Doubles");
    expect(html).not.toContain("· doubles ·");
  });

  it("still names a real draw by its label", () => {
    expect(selectionLabel("mens-singles")).toBe("Men's Singles");
    expect(selectionLabel("mixed-doubles")).toBe("Mixed Doubles");
  });

  it("falls back to the slug for a draw it does not know", () => {
    // Never blank. An unknown draw is a register change, not a reason to print
    // nothing where a name goes.
    expect(selectionLabel("wheelchair-quad")).toBe("wheelchair-quad");
  });
});

describe("#4803 — resultsSpanDraws", () => {
  it("is false for one draw and true for several", () => {
    expect(resultsSpanDraws([])).toBe(false);
    expect(resultsSpanDraws(FILED_SPECIMEN.slice(0, 3))).toBe(false);
    expect(resultsSpanDraws(FILED_SPECIMEN)).toBe(true);
  });
});
