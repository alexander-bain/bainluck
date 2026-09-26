/**
 * #8811 — A RUNG THE VENUE HAS NEVER PRICED IS NOT A 0% RUNG.
 *
 * Seen on production at 390px on 2026-09-26 13:05Z (lane1's LOOK) on
 * `/events/15318133` → serves 15318132, Lynx v Liberty, WNBA playoffs. The
 * "1st half margin" card read "Six lines quoted" over six rungs, every one
 * `0%` — NY by 3.5+, NY by 1.5+, MIN by 1.5+, 6.5+, 9.5+, 12.5+ — while the
 * page's own First Half Winner had Minnesota at 62.5%.
 *
 * The seven `half_spread` rows below are `/api/events/15318132/game-markets`
 * verbatim (13:20Z). ONE rung has a price (MIN by 3.5+ at 0.495); six have
 * never had one (`probability: null`, `observed_at: null`).
 *
 * Two defects, one cause. `parseSpreadRungs` read `probability ?? 0`, so each
 * null became a 0% rung. The monotonicity pass then sorted MIN by 1.5 (the
 * null, now 0) ahead of MIN by 3.5, and `0.495 <= 0` is false — so the ONE
 * real price was thrown out as non-monotonic and the six fakes stayed.
 *
 * The strawman arm prices every rung and renders all seven: the rows parse,
 * so the null arm's single rung is the price filter and not a parser that
 * reads nothing.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import { parseSpreadRungs, selectHalfTotalRungs } from "@/lib/marketMapUtils";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;|&#39;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const HOME = "Minnesota Lynx";
const AWAY = "New York Liberty";
const MARKET = "New York vs Minnesota: First Half Spread";

function row(outcome_name: string, probability: number | null) {
  return {
    market_name: MARKET,
    outcome_name,
    observed_at: probability == null ? null : "2026-09-26T13:20:00.123940+00:00",
    threshold: 1.0,
    probability,
    source: "kalshi",
    market_type: "half_spread",
    period: "1H",
    is_winner: null,
    resolution_source: null,
    _market_id: 62399903,
  };
}

/** Production, verbatim order and values. */
const SERVED = [
  row("Minnesota wins the 1H by over 3.5 points", 0.495),
  row("Minnesota wins the 1H by over 12.5 points", null),
  row("Minnesota wins the 1H by over 6.5 points", null),
  row("Minnesota wins the 1H by over 1.5 points", null),
  row("New York wins the 1H by over 1.5 points", null),
  row("New York wins the 1H by over 3.5 points", null),
  row("Minnesota wins the 1H by over 9.5 points", null),
];

/** Strawman: the same seven rungs, each with a monotone price. */
const ALL_PRICED = [
  row("Minnesota wins the 1H by over 3.5 points", 0.495),
  row("Minnesota wins the 1H by over 12.5 points", 0.11),
  row("Minnesota wins the 1H by over 6.5 points", 0.33),
  row("Minnesota wins the 1H by over 1.5 points", 0.58),
  row("New York wins the 1H by over 1.5 points", 0.36),
  row("New York wins the 1H by over 3.5 points", 0.27),
  row("Minnesota wins the 1H by over 9.5 points", 0.2),
];

function card(rows: ReturnType<typeof row>[]): string {
  const text = visibleText(
    renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={
          {
            event_id: 15318132,
            home_team: HOME,
            away_team: AWAY,
            home_score: null,
            away_score: null,
            status: "scheduled",
            player_props: [],
            team_totals: [],
            period_markets: rows,
            matchups: [],
            other: [],
            pace: null,
            props_script: [],
            spreads: [],
            totals: [],
          } as never
        }
        eventStatus="scheduled"
        homeTeam={HOME}
        awayTeam={AWAY}
        homeAbbr="MIN"
        awayAbbr="NY"
        sportKey="basketball_wnba"
      />
    )
  );
  const at = text.indexOf("1st half margin");
  return at === -1 ? "" : text.slice(at);
}

/** A standalone `0%` — not the tail of `50%`. */
const ZERO_PERCENT = /(^|[^\d.])0%/;

describe("#8811 never-priced half-margin rungs", () => {
  it("the card still renders — suppression below is not an absent card", () => {
    expect(card(SERVED)).toContain("1st half margin");
  });

  it("prints no 0% rung", () => {
    expect(card(SERVED)).not.toMatch(ZERO_PERCENT);
  });

  it("names none of the six unpriced rungs", () => {
    const body = card(SERVED);
    for (const rung of ["NY by 1.5+", "NY by 3.5+", "MIN by 1.5+", "MIN by 6.5+", "MIN by 9.5+", "MIN by 12.5+"]) {
      expect(body).not.toContain(rung);
    }
  });

  it("keeps the one rung that has a price", () => {
    expect(card(SERVED)).toContain("MIN by 3.5+");
  });

  it("counts the lines it actually quotes", () => {
    const body = card(SERVED);
    expect(body).not.toContain("Six lines quoted");
    expect(body).not.toContain("Seven lines quoted");
  });

  it("strawman: priced, the same rows render all seven rungs", () => {
    const body = card(ALL_PRICED);
    for (const rung of ["NY by 1.5+", "NY by 3.5+", "MIN by 1.5+", "MIN by 3.5+", "MIN by 6.5+", "MIN by 9.5+", "MIN by 12.5+"]) {
      expect(body).toContain(rung);
    }
  });

  it("parseSpreadRungs returns only the priced rung, at its price", () => {
    const rungs = parseSpreadRungs(SERVED, HOME, AWAY, "points");
    expect(rungs.map((r) => [r.isHome, r.threshold, r.probability])).toEqual([[true, 3.5, 0.495]]);
  });

  it("an unpriced Polymarket cover leg does not suppress its priced complement", () => {
    // The complement rule (#8739) reads the uncovered leg only when the cover
    // leg is absent. A cover leg with no price is absent for that purpose.
    const rungs = parseSpreadRungs(
      [
        { market_name: "Spread: Minnesota Lynx (-6.5)", outcome_name: "Minnesota Lynx", probability: null, source: "polymarket" },
        { market_name: "Spread: Minnesota Lynx (-6.5)", outcome_name: "New York Liberty", probability: 0.495, source: "polymarket" },
      ],
      HOME,
      AWAY,
      "points"
    );
    expect(rungs).toHaveLength(1);
    expect(rungs[0].probability).toBeCloseTo(0.505, 6);
  });
});

describe("#8811 same class on the half TOTALS ladder", () => {
  const total = (threshold: number, p: number | null) => ({
    market_name: "First Half Total",
    outcome_name: `Over ${threshold}`,
    threshold,
    probability: p,
    market_type: "half_total",
    period: "1H",
  });

  it("an unpriced rung is dropped, not drawn at 0%", () => {
    const rungs = selectHalfTotalRungs([total(80.5, 0.62), total(82.5, 0.51), total(84.5, null), total(86.5, 0.4)], "1H");
    expect(rungs.map((r) => r.threshold)).toEqual([80.5, 82.5, 86.5]);
    expect(rungs.every((r) => r.overProbability > 0)).toBe(true);
  });

  it("control: priced, the same four rungs all survive", () => {
    const rungs = selectHalfTotalRungs([total(80.5, 0.62), total(82.5, 0.51), total(84.5, 0.45), total(86.5, 0.4)], "1H");
    expect(rungs.map((r) => r.threshold)).toEqual([80.5, 82.5, 84.5, 86.5]);
  });
});
