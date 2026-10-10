/**
 * #10830 — A POLYMARKET-ONLY HALF SPREAD LADDER DRAWS ITS HALF MARGIN CARD.
 *
 * #8739 taught the full-game rail to read the line from a Polymarket market
 * name (`Spread: Texas (-7.5)`). Polymarket titles a half the same way:
 *
 *   market_name "1H Spread: Indiana (-9.5)"   outcome "Nebraska"  p 0.805
 *   market_name "1H Spread: Indiana (-9.5)"   outcome "Indiana"   p 0.195
 *
 * The title rule is anchored at `Spread:` (so `1st 5 Innings Spread:` stays off
 * the full-game rail), and the half rails called the same rule, so every half
 * leg was dropped and the card did not render. The iPhone twin printed the
 * card's title over nothing.
 *
 * ═══ THE SPECIMEN (production, 2026-10-10 16:41Z, banked bytes, trimmed to
 * spreads / totals / period_markets) ═══
 *
 *   15322373 · Indiana @ Nebraska · live, 1st quarter, 3–3 · 12 1H legs and
 *   8 2H legs, every one Polymarket, `threshold` null.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import { parseSpreadRungs } from "@/lib/marketMapUtils";

import live15322373 from "../fixtures/ux10830_game_markets_15322373.20261010T1641Z.json";

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

const HOME = "Nebraska Cornhuskers";
const AWAY = "Indiana Hoosiers";

// Props as `app/events/[id]/page.tsx` builds them, from the event row read in
// the same minute (hero 31% / 69%, sportsbook spread 6.4, opening 9.0).
const indianaAtNebraska = {
  gameMarkets: live15322373,
  eventStatus: "live",
  homeTeam: HOME,
  awayTeam: AWAY,
  homeAbbr: "NEB",
  awayAbbr: "IU",
  homeWinProb: 0.314651,
  awayWinProb: 0.685349,
  homeSpread: 6.4,
  openingHomeSpread: 9.0,
  sportKey: "americanfootball_ncaaf",
};

const halfRows = (period: "1H" | "2H") =>
  live15322373.period_markets.filter((r) => r.market_type === "half_spread" && r.period === period);

describe("#10830 — a half rail reads a Polymarket half title", () => {
  it("the 1st half's six lines parse on Indiana's side, at the cover leg's price", () => {
    const rungs = parseSpreadRungs(halfRows("1H"), HOME, AWAY, "points", { readsHalfTitles: true });
    const byLine = [...rungs].sort((a, b) => a.threshold - b.threshold);
    expect(byLine.map((r) => [r.isHome, r.threshold, r.probability])).toEqual([
      [false, 2.5, 0.465],
      [false, 4.5, 0.35],
      [false, 5.5, 0.335],
      [false, 6.5, 0.31],
      [false, 7.5, 0.22],
      [false, 9.5, 0.195],
    ]);
  });

  it("control: without the half option the same rows still parse to nothing", () => {
    expect(parseSpreadRungs(halfRows("1H"), HOME, AWAY, "points")).toEqual([]);
  });

  it("an innings title is not a half, even on a half rail", () => {
    const innings = [
      { market_name: "1st 5 Innings Spread: Dodgers (-1.5)", outcome_name: "Dodgers", probability: 0.4 },
    ];
    expect(
      parseSpreadRungs(innings, "Los Angeles Dodgers", "San Francisco Giants", "runs", { readsHalfTitles: true })
    ).toEqual([]);
  });

  it("the page draws both half margin cards with their lines", () => {
    const text = render(indianaAtNebraska);
    expect(text).toContain("1st half margin");
    expect(text).toContain("2nd half margin");
    const first = text.slice(text.indexOf("1st half margin"));
    expect(first).toMatch(/IU by 2\.5\+/);
  });
});
