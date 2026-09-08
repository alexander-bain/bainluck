// #3867, CERT-2224's required repair `PERCENT-3867-ROUTE-READER-LABELS-THROUGH-CONTRACT`.
//
// THE GAP THE BLOCK FOUND. #3867 moved the whole-percent rule into
// `contracts/rendered_percent.json` and its Python / TypeScript / Swift / widget
// arms, and every one of them agreed. But `SpecialEventMarkets.OutcomeBar` — the
// Additional Markets rows Alex filed the issue AGAINST, on `/events/15306225` —
// still ran `Math.round(outcome.prob * 100)`, a second copy of the rule that had
// just been replaced. So the contract said 57 and 15 while the surface in the
// screenshot went on printing 56 and 14. The rule shipped; the ship did not.
//
// A rule with a second copy is not a rule, so this file asserts the SURFACE and
// not the helper. `renderedPercentContract.test.ts` covers the helper.
//
// The four probabilities are the ones actually measured on the wire for that
// page, and they are the four three-decimal values in the whole grid whose
// printed percent moved: 0.145, 0.285, 0.565, 0.575 (0.585 and 0.615 are here as
// the CONTROLS — the neighbours that always printed correctly, and whose printing
// correctly was the entire reason the two wrong ones were visible as a defect).

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import SpecialEventMarkets from "../../components/SpecialEventMarkets";
import { renderedPercent } from "../../lib/renderedPercent";
import type { GameMarketsResponse } from "../../lib/api";

const PM = "polymarket";
// The row SHAPE is copied from `SpecialEventMarkets.test.tsx`'s production
// fixture, not invented: `buildMarketSection` groups by a recognized statistic
// family, and a shape it does not group renders NOTHING — which would make every
// `not.toContain` below pass against an empty string. It did, on the first draft.
const MARKET = "Atlanta Braves vs. New York Yankees - Player Props";

/** The values Alex's issue named, plus the neighbours that were already right. */
const MOVED = [0.145, 0.565] as const;
const CONTROLS = [0.585, 0.615] as const;

function payload(rows: Array<Record<string, unknown>>): GameMarketsResponse {
  return { other: rows } as unknown as GameMarketsResponse;
}

/** `SpecialEventMarkets.test.tsx`'s production rows, Braves @ Yankees
 *  (15191123), 2026-08-09 — reused whole rather than trimmed, because the
 *  section only builds for a payload this component recognises. Only Aaron
 *  Judge's price varies; every other row is a fixed neighbour. */
function rowsWith(probability: number) {
  return [
    { market_name: MARKET, outcome_name: "Ronald Acuña Jr.: Home Runs O/U 0.5", probability: 0.095, source: PM },
    { market_name: MARKET, outcome_name: "Ronald Acuña Jr.: Home Runs O/U 0.5", probability: 0.125, source: PM },
    { market_name: MARKET, outcome_name: "Ronald Acuña Jr.: Home Runs O/U 0.5", probability: 0.905, source: PM },
    { market_name: MARKET, outcome_name: "Aaron Judge: Home Runs O/U 0.5", probability, source: PM },
    { market_name: MARKET, outcome_name: "Matt Olson: Home Runs O/U 0.5", probability: 0.02, source: PM },
    { market_name: MARKET, outcome_name: "Max Fried: Strikeouts O/U 5.5", probability: 0.44, source: PM },
  ];
}

function renderOne(probability: number): string {
  const html = renderToStaticMarkup(
    <SpecialEventMarkets data={payload(rowsWith(probability))} />,
  );
  // A `not.toContain` against an empty render is a pass that proves nothing.
  expect(html).toContain("Home Runs");
  return html;
}

describe("Additional Markets prints the contract's percent, not its own", () => {
  test.each(MOVED)("a half-percent quote rounds UP on the filing surface (%s)", (p) => {
    const html = renderOne(p);
    const expected = renderedPercent(p);

    expect(html).toContain(`${expected}%`);
    // The DEFECT number, stated so a regression cannot pass by also being present.
    expect(html).not.toContain(`${Math.round(p * 100)}%`);
    expect(expected).toBe(Math.round(p * 100) + 1);
  });

  test.each(CONTROLS)("its neighbour is unchanged (%s)", (p) => {
    const html = renderOne(p);
    // The control's whole point: the rule did NOT move these, and a repair that
    // moved them would be a new defect wearing the old one's fix.
    expect(renderedPercent(p)).toBe(Math.round(p * 100));
    expect(html).toContain(`${renderedPercent(p)}%`);
  });

  test("the two Alex reported no longer print the two he reported", () => {
    // Read as the sentence in the issue: 0.565 printed 56% and 0.145 printed 14%,
    // while 0.585 and 0.615 printed 59% and 62%.
    expect(renderOne(0.565)).not.toContain("56%");
    expect(renderOne(0.145)).not.toContain("14%");
    expect(renderOne(0.585)).toContain("59%");
    expect(renderOne(0.615)).toContain("62%");
  });
});
