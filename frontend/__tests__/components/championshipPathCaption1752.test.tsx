/**
 * #1752 — the championship-path card must not claim its steps are nested.
 *
 * The card carried "Each step conditions on the one before it." while
 * `championship_path` was `[]` for every team, so nobody ever saw it. Repairing
 * the backend query (PR #7187) would have published it on 332 team pages — and
 * it is false: a wild card reaches a conference final without winning its
 * division. Measured on production 2026-09-19, of the 47 teams serving BOTH a
 * division and a conference step, 14 (30%) have the division number BELOW the
 * conference one, which the sentence directly contradicts.
 */
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { TeamChampionshipPath } from "../../components/TeamChampionshipPath";
import type { ChampionshipPathEntry } from "../../lib/api";

function pathEntry(overrides: Partial<ChampionshipPathEntry>): ChampionshipPathEntry {
  return {
    tier: 1,
    label: "Championship",
    market_name: "World Series",
    market_id: 1,
    probability: 0.04,
    rank: null,
    movement: null,
    ...overrides,
  };
}

// Boston 10709 as production serves it once #1752's repair lands: an INVERTED
// path — 1% to win the AL East, 12% to win the pennant.
const BOSTON: ChampionshipPathEntry[] = [
  pathEntry({
    tier: 4,
    label: "Division",
    market_name: "AL East Division Winner",
    market_id: 6,
    probability: 0.01,
  }),
  pathEntry({
    tier: 2,
    label: "Conference",
    market_name: "American League Champion",
    market_id: 5,
    probability: 0.12,
  }),
  pathEntry({
    tier: 1,
    label: "Championship",
    market_name: "Pro Baseball Champion",
    market_id: 2,
    probability: 0.0475,
  }),
];

describe("#1752 championship path card", () => {
  it("does not tell the reader the steps are conditional", () => {
    const html = renderToStaticMarkup(
      <TeamChampionshipPath entries={BOSTON} color="#bd3039" />,
    );

    expect(html).not.toMatch(/conditions on the one before/i);
  });

  it("still renders every step, so the assertion above is not vacuous", () => {
    // The control: "the sentence is absent" is also satisfied by a card that
    // renders nothing at all — which is exactly the state #1752 exists to end.
    const html = renderToStaticMarkup(
      <TeamChampionshipPath entries={BOSTON} color="#bd3039" />,
    );

    expect(html).toContain("Championship path");
    expect(html).toContain("Win Division");
    expect(html).toContain("Win Conference");
    expect(html).toContain("Win Championship");
  });

  it("renders the inverted specimen's numbers without comment", () => {
    // The pair the removed sentence contradicted: division BELOW conference.
    const html = renderToStaticMarkup(
      <TeamChampionshipPath entries={BOSTON} color="#bd3039" />,
    );

    expect(html).toContain(">1%<");
    expect(html).toContain(">12%<");
    expect(html).toContain(">5%<"); // 0.0475 rounds to 5
  });
});
