/**
 * #8739 — A POLYMARKET-ONLY SPREAD LADDER DRAWS A MARGIN MAP.
 *
 * Polymarket writes the line in the MARKET name and only a team in each leg:
 *
 *   market_name "Spread: Texas (-7.5)"   outcome "Texas"      p 0.405
 *   market_name "Spread: Texas (-7.5)"   outcome "Tennessee"  p 0.595
 *
 * `parseSpreadOutcome` read the threshold from the outcome alone, so every row
 * returned null and the card did not render — college football pages carrying
 * a full priced ladder showed the Points map and nothing else.
 *
 * ═══ THE SPECIMENS (production, 2026-09-25 ~23:35Z, banked bytes) ═══
 *
 *   | event    | state              | spread rows          | card before |
 *   |----------|--------------------|----------------------|-------------|
 *   | 14870011 | scheduled          | 52, both legs served | none        |
 *   | 15315985 | final ARMY 21–17   | 30, ONE leg per mkt  | none        |
 *
 * The Tennessee leg of "Spread: Texas (-7.5)" is Tennessee +7.5 — "Texas does
 * not cover" — and must never be drawn as "Tennessee by 7.5+". It is read as
 * the Texas rung at 1 − p, which is also what keeps 15315985's one-legged
 * markets on the rail.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import { parseSpreadOutcome, parseSpreadRungs } from "@/lib/marketMapUtils";

import pre14870011 from "../fixtures/ux8739_game_markets_14870011.20260925.json";
import done15315985 from "../fixtures/ux8739_game_markets_15315985.20260925.json";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function render(props: Record<string, unknown>): string {
  const p = props as unknown as React.ComponentProps<typeof MarketMapSection>;
  return visibleText(renderToStaticMarkup(<MarketMapSection {...p} />));
}

// Props as `app/events/[id]/page.tsx` builds them, from the served event rows
// read in the same minute as the banked payloads.
const texasAtTennessee = {
  gameMarkets: pre14870011,
  eventStatus: "scheduled",
  homeTeam: "Tennessee Volunteers",
  awayTeam: "Texas Longhorns",
  homeAbbr: "TENN",
  awayAbbr: "TEX",
  homeWinProb: 0.355,
  awayWinProb: 0.645,
  homeSpread: 4.8,
  openingHomeSpread: null,
  sportKey: "americanfootball_ncaaf",
};

const armyAtTemple = {
  gameMarkets: done15315985,
  eventStatus: "completed",
  homeTeam: "Temple Owls",
  awayTeam: "Army Black Knights",
  homeAbbr: "TEM",
  awayAbbr: "ARMY",
  homeWinProb: 0.0,
  awayWinProb: 1.0,
  homeSpread: 3.9,
  openingHomeSpread: 4.0,
  sportKey: "americanfootball_ncaaf",
};

describe("#8739 — the line is read from a Polymarket market name", () => {
  const rungs = parseSpreadRungs(pre14870011.spreads, "Tennessee Volunteers", "Texas Longhorns", "points");
  const at = (isHome: boolean, threshold: number) =>
    rungs.filter((r) => r.isHome === isHome && r.threshold === threshold).map((r) => r.probability);

  it("14870011: all 26 markets give ONE rung each, read from the cover leg", () => {
    expect(rungs).toHaveLength(26);
    // Texas -7.5: the Texas leg (0.405) is the rung; the Tennessee leg is not re-read.
    expect(at(false, 7.5)).toEqual([0.405]);
    // Tennessee -9.5 is Tennessee's own cover rung.
    expect(at(true, 9.5)).toEqual([0.145]);
  });

  it("the complement is used only where the cover leg is not served", () => {
    const tennesseeLegOnly = pre14870011.spreads.filter(
      (s) => !(s.market_name === "Spread: Texas (-7.5)" && s.outcome_name === "Texas")
    );
    const r = parseSpreadRungs(tennesseeLegOnly, "Tennessee Volunteers", "Texas Longhorns", "points");
    const tex75 = r.filter((x) => !x.isHome && x.threshold === 7.5);
    expect(tex75).toHaveLength(1);
    expect(tex75[0].probability).toBeCloseTo(0.405, 6);
  });

  it("the uncovered leg is never its own team's cover rung", () => {
    // Tennessee +7.5 at 0.595 would read "Tennessee by 7.5+" at 59.5% — false.
    expect(at(true, 7.5)).toEqual([]);
  });

  it("fails closed: a +N line, an ambiguous team name, a leg naming neither team", () => {
    expect(parseSpreadOutcome("Texas", 0.4, "polymarket", "Tennessee Volunteers", "Texas Longhorns", "Spread: Texas (+7.5)")).toBeNull();
    expect(parseSpreadOutcome("Texas", 0.4, "polymarket", "Texas Tech Red Raiders", "Texas Longhorns", "Spread: Texas (-7.5)")).toBeNull();
    expect(parseSpreadOutcome("Oklahoma", 0.4, "polymarket", "Tennessee Volunteers", "Texas Longhorns", "Spread: Texas (-7.5)")).toBeNull();
    // No market name — the old behaviour for a numberless outcome is unchanged.
    expect(parseSpreadOutcome("Texas", 0.4, "polymarket", "Tennessee Volunteers", "Texas Longhorns")).toBeNull();
  });

  it("a Kalshi outcome that carries its number is read exactly as before", () => {
    const r = parseSpreadOutcome("Buffalo Bills -6.5", 0.4, "kalshi", "Buffalo Bills", "Miami Dolphins", "Buffalo vs Miami: Game Spread");
    expect(r).toMatchObject({ isHome: true, threshold: 6.5, probability: 0.4, margin: 6.5 });
  });
});

describe("#8739 — the card draws on production specimens", () => {
  it("scheduled 14870011: a Margin map with Texas rungs, and no Tennessee-by-7.5 rung", () => {
    const text = render(texasAtTennessee);
    expect(text).toContain("Margin map");
    expect(text).toMatch(/TEX by 7\.5\+/);
    expect(text).not.toMatch(/TENN by 7\.5\+/);
  });

  it("final 15315985: one-legged markets still draw the card, graded against ARMY by 4", () => {
    const legs = parseSpreadRungs(done15315985.spreads, "Temple Owls", "Army Black Knights", "points");
    expect(legs).toHaveLength(done15315985.spreads.length);
    const text = render(armyAtTemple);
    expect(text).toContain("Margin: expected vs final");
    expect(text).toMatch(/Final\s+ARMY by 4\b/);
  });
});
