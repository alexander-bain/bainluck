// UX-P054 (#1722) — an unpriced `other` row must not kill the whole event page.
//
// THE DEFECT, caught by the browser rail (run 31457595983, pack `event-page`,
// deployed sha 701837a1) and not by any unit test: `/events/15191146` rendered
// "Something went wrong — This page encountered an error" and NOTHING else.
// Not a blank section — the entire page, hero and script and chart included,
// behind its error boundary. A control event in the same run passed.
//
//   TypeError: Cannot read properties of undefined (reading 'threshold')
//       at .../chunks/8895.a3fa4543ba538f1e.js:1:15970  (Object.useMemo)
//
// THE CHAIN. The "scan `other` markets" pass created a stat bucket
// unconditionally but pushed its rung only `if (o.probability != null)`, so an
// unpriced row left a stat with zero rungs. `shape` is "line" for fewer than 3
// rungs — which includes ZERO — and the line branch dereferenced
// `sortedRungs[0]`. The sibling ladder branch was already optional-chained; the
// reachable one was not.
//
// WHY IT WAS THAT EVENT: 64 of 121 `other` rows on 15191146 carried
// `probability: null` and were player-prop shaped ("Austin Hedges: Home Runs
// Over 0.5"); the passing control had 0 of 73. One row is enough.
//
// This is gotcha #42 one level up — one bad ITEM wiping a whole pass, except
// the pass is the page.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PlayerPropsDashboard from "../../components/PlayerPropsDashboard";
import type { GameMarketsResponse } from "../../lib/api";

const MARKET = "Cleveland Guardians vs. Chicago White Sox - Player Props";

/**
 * VERBATIM production rows from event 15191146's `other` array — parseable as
 * player + stat, and unpriced. Transcribed exactly, `O/U` included: an earlier
 * draft of this test wrote "Over 0.5" from memory, which `parsePlayerName` does
 * not resolve the same way, and the test then passed for the wrong reason.
 */
const UNPRICED_OTHER = [
  "Austin Hedges: Home Runs O/U 0.5",
  "Colson Montgomery: Home Runs O/U 0.5",
  "Brayan Rocchio: Home Runs O/U 0.5",
].map((outcome_name) => ({
  market_name: MARKET,
  outcome_name,
  source: "kalshi",
  probability: null,
}));

/**
 * The healthy sibling comes from `player_props`, which is where priced props
 * actually live — on the real event the priced `other` rows are game markets
 * ("NRFI", "Tie", "Yes"), not player props.
 */
const PRICED_PROP = {
  market_name: MARKET,
  outcome_name: "Steven Kwan: Home Runs O/U 0.5",
  threshold: 0.5,
  over_probability: 0.42,
  source: "kalshi",
  movement: null,
  actual: null,
  hit: null,
  is_winner: null,
  resolution_source: null,
};

function render(
  other: Array<Record<string, unknown>>,
  player_props: Array<Record<string, unknown>> = [],
) {
  return renderToStaticMarkup(
    <PlayerPropsDashboard
      data={{ player_props, other } as unknown as GameMarketsResponse}
      eventStatus="completed"
      homeTeam="Chicago White Sox"
      awayTeam="Cleveland Guardians"
      boxScore={null as never}
    />,
  );
}

describe("#1722 — an unpriced player-prop row cannot take down the page", () => {
  it("does not throw on the exact production shape that killed /events/15191146", () => {
    // Before the fix this threw the TypeError above, which in the browser is
    // the whole route unmounting into its error boundary.
    expect(() => render(UNPRICED_OTHER)).not.toThrow();
  });

  it("renders no card for a stat that has no priced rung, rather than a broken one", () => {
    // The honest outcome: nothing to say about an unpriced prop, so it says
    // nothing. It must NOT invent a card with an undefined threshold.
    const html = render(UNPRICED_OTHER);
    expect(html).not.toContain("Austin Hedges");
    expect(html).not.toContain("undefined");
    expect(html).not.toContain("NaN");
  });

  it("still renders the priced prop beside the unpriced ones (gotcha #43)", () => {
    // A suppression that also swallows the healthy sibling is the failure this
    // lane keeps writing guards for. One bad row must cost exactly one row.
    const html = render(UNPRICED_OTHER, [PRICED_PROP]);
    expect(html).toContain("Steven Kwan");
    expect(html).not.toContain("Austin Hedges");
    expect(html).not.toContain("undefined");
  });

  it("a fully priced payload is unaffected", () => {
    const html = render([], [PRICED_PROP]);
    expect(html).toContain("Steven Kwan");
    expect(html).not.toContain("undefined");
  });

  it("the line branch can no longer be reached with an empty rung set", () => {
    // The invariant, asserted at the source rather than through the DOM: the
    // consumption site bails before the shape decision, so a future upstream
    // change cannot re-open the dereference.
    const src = require("fs").readFileSync(
      require("path").resolve(__dirname, "../../components/PlayerPropsDashboard.tsx"),
      "utf8",
    );
    const guardIdx = src.indexOf("if (sortedRungs.length === 0) continue;");
    const shapeIdx = src.indexOf('const shape: "ladder" | "line"');
    expect(guardIdx).toBeGreaterThan(-1);
    expect(shapeIdx).toBeGreaterThan(-1);
    expect(guardIdx).toBeLessThan(shapeIdx);
  });
});
