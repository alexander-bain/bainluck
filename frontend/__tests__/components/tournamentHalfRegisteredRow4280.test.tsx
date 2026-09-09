/**
 * #4280 — A HALF-PINNED RESULT ROW RENDERS, AND THE COUNTS STILL SPLIT.
 *
 * live/121. The backend now publishes a decided match with ONE register-pinned
 * side and one named by the scoreboard (`source_pairing: "mixed"`) — 114 rows
 * on the live payload, 19 of them main draw, including Swiatek's round of 16.
 *
 * Two things are asserted here and they are different questions:
 *
 * 1. THE ROW RENDERS LIKE ANY OTHER. The scoreboard-named side has no
 *    `entity_key` the register knows and no image; the renderer must print both
 *    names and the score anyway, because "the register does not carry this
 *    person" is not a reason to hide a match that was played.
 *
 * 2. THE TWO COUNTS STAY DISTINGUISHABLE (notice 34). `unregistered_pairs` used
 *    to carry both populations; `data-mixed-pairings` is the other half. They
 *    are ATTRIBUTES and not sentences — Alex, on this page: *"all the grey text
 *    is madness"* — so the assertion is on the attribute and the test also
 *    checks the numbers reach no reader-visible string.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentResults from "@/components/tournament/TournamentResults";
import type {
  TournamentResult,
  TournamentResults as ResultsModel,
} from "@/lib/tournamentResults";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

/** The real row, with the real ESPN id: Zheng beat Swiatek 7-5, 6-3. */
const MIXED: TournamentResult = {
  matchup_key: "espn:184901",
  draw: "womens-singles",
  draw_label: "Women's Singles",
  round: "Round 4",
  players: [
    {
      entity_key: "espn:athlete:6048",
      display_name: "Zheng Qinwen",
      seed: null,
      is_winner: true,
      image: null,
      prematch_probability: null,
    },
    {
      entity_key: "iga-swiatek",
      display_name: "Iga Swiatek",
      seed: 2,
      is_winner: false,
      image: { url: "https://example.test/swiatek.jpg", flag_url: null },
      prematch_probability: null,
    },
  ],
  winner_entity_key: "espn:athlete:6048",
  score: "7-5, 6-3",
  completion: "final",
  completed_at: "2026-09-07T17:25Z",
  source_round: "Round 4",
  source: "espn",
};

const RESULTS: ResultsModel = {
  matches: [MIXED],
  count: 1,
  unregistered_pairs: 33,
  mixed_pairings: 114,
  winner_not_registered: 0,
  source_competitions: 605,
  source_scored: 601,
  source_errors: [],
};

function markup(overrides: Partial<ResultsModel> = {}): string {
  return renderToStaticMarkup(
    <TournamentResults
      results={{ ...RESULTS, ...overrides }}
      draw="womens-singles"
      initialExpanded
    />
  );
}

describe("#4280 — the half-pinned row on the page", () => {
  it("prints both names and the score, though we carry only one of the players", () => {
    const html = markup();
    expect(html).toContain("Iga Swiatek");
    expect(html).toContain("Zheng Qinwen");
    expect(html).toContain("7-5, 6-3");
  });

  it("marks the scoreboard-named side as the winner when it won", () => {
    /* The mutant this kills renders the register-pinned side as the winner,
       which would print Swiatek as beating the player who knocked her out. */
    const html = markup();
    expect(html).toContain('data-winner="espn:athlete:6048"');
  });

  it("keeps the two dropped-row populations separately readable", () => {
    const html = markup();
    expect(html).toContain('data-unregistered-pairs="33"');
    expect(html).toContain('data-mixed-pairings="114"');
  });

  it("omits the attribute rather than printing a zero for an old payload", () => {
    /* A payload cached from before the field existed must not read as "we
       recovered nothing" — absent and zero are different claims (gotcha #53).
       `?? undefined` is the line; this is what makes it observable. */
    const { mixed_pairings: _dropped, ...withoutField } = RESULTS;
    const html = renderToStaticMarkup(
      <TournamentResults
        results={withoutField as ResultsModel}
        draw="womens-singles"
        initialExpanded
      />
    );
    expect(html).not.toContain("data-mixed-pairings");
    // The control: the sibling attribute is still there, so an empty result
    // above means "this one attribute is absent" and not "nothing rendered".
    expect(html).toContain('data-unregistered-pairs="33"');
  });

  it("says none of it in prose (notice 34)", () => {
    /* The numbers are for probes. A reader gets the tennis. */
    const text = markup().replace(/<[^>]*>/g, " ");
    expect(text).not.toContain("114");
    expect(text).not.toContain("33");
    expect(text).not.toMatch(/could not tie/i);
  });
});
