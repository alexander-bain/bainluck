/**
 * #10038 — on a live tennis page Kalshi's set questions vanished, and the set-2
 * line the card did print was one leg of Polymarket's: `Alex Michelsen wins Set
 * 2 — 24%`, no Alcaraz row (`/events/15320475`, 2026-10-01 08:27Z).
 *
 * The two venues write the same question in two grammars:
 *
 *     polymarket  Set 2 Winner: Carlos Alcaraz vs Alex Michelsen
 *     kalshi      Carlos Alcaraz vs Alex Michelsen: Set 2 Winner
 *
 * `periodWinnerParts` read the first, and read the second only without the
 * trailing `Winner` (the esports `A vs B: Map 1` form). So the Kalshi name was
 * no period at all, the `winner` rule in `isRedundantWithMarketMaps` took it for
 * the hero's moneyline, and both Kalshi set markets were dropped before the card
 * was built.
 *
 * The fixture is the VERBATIM production `other[]` for that event, re-read the
 * same morning (set 1 near-decided by then). The 08:2xZ prices the issue quotes
 * are applied on top in the second block, because that is the read the reader saw.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import SpecialEventMarkets from "../../components/SpecialEventMarkets";
import {
  buildMarketSection,
  isRedundantWithMarketMaps,
  periodWinnerParts,
  type OtherMarketRow,
} from "../../lib/otherMarketGroups";
import type { GameMarketsResponse } from "../../lib/api";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const fixture = require("../fixtures/other_15320475_10038.json");

const OTHER = fixture.other as OtherMarketRow[];
const OPTS = { homeTeam: fixture.home_team, awayTeam: fixture.away_team };
const CARD = "Carlos Alcaraz vs Alex Michelsen";

function setCard(rows: OtherMarketRow[]) {
  const section = buildMarketSection(rows, OPTS);
  return section.categories.flatMap((c) => c.cards).find((c) => c.name === CARD);
}

function labels(rows: OtherMarketRow[]): Record<string, number | null> {
  const card = setCard(rows);
  return Object.fromEntries((card?.outcomes ?? []).map((o) => [o.label, o.prob]));
}

const kalshiSets = OTHER.filter(
  (r) => r.source === "kalshi" && /: Set \d Winner$/.test(r.market_name ?? ""),
);

describe("#10038 — Kalshi's `A vs B: Set N Winner` is a set question, not the hero", () => {
  it("parses the Kalshi grammar to the same scope and sides as Polymarket's", () => {
    expect(periodWinnerParts("Carlos Alcaraz vs Alex Michelsen: Set 2 Winner")).toEqual(
      periodWinnerParts("Set 2 Winner: Carlos Alcaraz vs Alex Michelsen"),
    );
    expect(periodWinnerParts("Carlos Alcaraz vs Alex Michelsen: Set 2 Winner")).toEqual({
      scope: "Set 2",
      first: "Carlos Alcaraz",
      second: "Alex Michelsen",
    });
  });

  it("keeps a half or a quarter `… Winner` filtered — those can be drawn", () => {
    expect(periodWinnerParts("Arsenal vs Chelsea: 1st Half Winner")).toBeNull();
    expect(periodWinnerParts("Pittsburgh vs Cleveland: 2nd Quarter Winner")).toBeNull();
    expect(
      isRedundantWithMarketMaps({
        market_name: "Arsenal vs Chelsea: 1st Half Winner",
        outcome_name: "Draw",
      } as OtherMarketRow),
    ).toBe(true);
  });

  it("the production wire carries both Kalshi set markets, and none is redundant", () => {
    expect(kalshiSets.map((r) => r._market_id).sort()).toEqual([
      62972817, 62972817, 62972818, 62972818,
    ]);
    for (const row of kalshiSets) expect(isRedundantWithMarketMaps(row)).toBe(false);
  });

  it("a Kalshi-only page draws both players for both sets", () => {
    expect(labels(kalshiSets)).toEqual({
      "Carlos Alcaraz wins Set 1": 0.995,
      "Alex Michelsen wins Set 1": 0.01,
      "Carlos Alcaraz wins Set 2": 0.52,
      "Alex Michelsen wins Set 2": 0.445,
    });
  });
});

describe("#10038 — the read the reader saw (08:2xZ prices)", () => {
  // The issue's table: Polymarket's set-2 market served ONE leg, Michelsen 0.24.
  const PRICES: Record<string, number> = {
    "62972818|Carlos Alcaraz": 0.665,
    "62972818|Alex Michelsen": 0.33,
    "62972817|Carlos Alcaraz": 0.595,
    "62972817|Alex Michelsen": 0.39,
    "63141879|Carlos Alcaraz": 0.665,
    "63141879|Alex Michelsen": 0.33,
    "63017189|Alex Michelsen": 0.24,
  };
  const at0827 = OTHER.filter((r) => !/Set \d Winner/.test(r.market_name ?? "") ||
    `${r._market_id}|${r.outcome_name}` in PRICES).map((r) => {
    const key = `${r._market_id}|${r.outcome_name}`;
    return key in PRICES ? { ...r, probability: PRICES[key] } : r;
  });

  it("set 2 prints Kalshi's Alcaraz 60%, and the lone 24% no longer stands alone", () => {
    // Michelsen's set-2 price is 39 at Kalshi and 24 at Polymarket. The merge
    // withholds a label its venues disagree on (unchanged), so the card keeps
    // one number for set 2 — the one both sides of it can stand behind.
    expect(labels(at0827)).toEqual({
      "Carlos Alcaraz wins Set 1": 0.665,
      "Alex Michelsen wins Set 1": 0.33,
      "Carlos Alcaraz wins Set 2": 0.595,
    });
    expect(setCard(at0827)?.withheld).toBe(1);
  });

  it("renders: no `Michelsen wins Set 2 24%`, Alcaraz's set 2 present", () => {
    const data = {
      home_team: fixture.home_team,
      away_team: fixture.away_team,
      other: at0827,
    } as unknown as GameMarketsResponse;
    const html = renderToStaticMarkup(
      <SpecialEventMarkets data={data} eventStatus="live" completedSets={0} />,
    );
    expect(html).toContain("Carlos Alcaraz wins Set 2");
    expect(html).not.toContain("Alex Michelsen wins Set 2");
    expect(html).not.toContain("24%");
  });
});
