/**
 * #8946 — A FINISHED GAME'S TOTAL CARD LISTED 33 "NOT CLEARED" LINES IN A ROW.
 *
 * Seen on production 2026-09-26 at 390px, `/events/14870011` — Texas 20 @
 * Tennessee 17, a 37-point game. Under "Each line vs the final": `Over 35.5
 * cleared`, `Over 36.5 cleared`, then every line from 37.5 to 78.5 `not
 * cleared`. A graded row has no bar (#3769), so every row past the final says
 * the same thing, and the FINAL 37 chip above already says it.
 *
 * The fix keeps the rows either side of where the result flips and puts the rest
 * behind "Show all N lines". The losing rungs #6196/#6218 made appear are still
 * rendered — hidden, in order — so this suite asserts BOTH directions: the wall
 * is gone from what a reader sees, and no row left the markup.
 *
 * The fixture is the real `/api/events/14870011/game-markets` `totals[]`,
 * rendered through the real `MarketMapSection`.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import {
  gradedLadderVisibleRows,
  GRADED_LADDER_COLLAPSE_OVER,
  type MarketMapLadderRow,
} from "@/components/MarketMap";

function rung(threshold: number, over: number, source: string, isWinner: boolean | null) {
  return {
    threshold,
    over_probability: over,
    source,
    market_type: "game_total",
    market_name: "Texas vs Tennessee: Total Points",
    outcome_name: `Over ${threshold} points`,
    is_winner: isWinner,
    resolution_source: null,
    movement: 0,
    period: null,
  };
}

// Served 2026-09-26 ~21:55Z, verbatim (threshold, over_probability, source, is_winner).
const TEXAS_TENNESSEE_TOTALS = [
  rung(35.5, 0.9995, "polymarket", false),
  rung(36.5, 1.0, "kalshi", true),
  rung(37.5, 0.005, "polymarket", null),
  rung(39.5, 0.0, "kalshi", false),
  rung(41.5, 0.0, "polymarket", null),
  rung(42.5, 0.0, "kalshi", false),
  rung(43.5, 0.0, "polymarket", null),
  rung(45.5, 0.0, "kalshi", false),
  rung(47.5, 0.0, "polymarket", null),
  rung(48.5, 0.0, "kalshi", false),
  rung(49.5, 0.0, "polymarket", false),
  rung(51.5, 0.0, "kalshi", false),
  rung(53.5, 0.0, "polymarket", false),
  rung(54.5, 0.0, "kalshi", false),
  rung(55.5, 0.0, "kalshi", false),
  rung(56.5, 0.0, "kalshi", false),
  rung(57.5, 0.0, "kalshi", false),
  rung(58.5, 0.0, "kalshi", false),
  rung(59.5, 0.0, "kalshi", false),
  rung(60.5, 0.0, "kalshi", false),
  rung(61.5, 0.0, "polymarket", false),
  rung(63.5, 0.0, "kalshi", false),
  rung(65.5, 0.0, "polymarket", null),
  rung(66.5, 0.0, "kalshi", false),
  rung(67.5, 0.0, "polymarket", null),
  rung(69.5, 0.0, "kalshi", false),
  rung(71.5, 0.0, "polymarket", null),
  rung(72.5, 0.0, "kalshi", false),
  rung(73.5, 0.0, "polymarket", null),
  rung(75.5, 0.0, "kalshi", false),
  rung(78.5, 0.0, "kalshi", false),
];

function renderCard(): string {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={
        {
          totals: TEXAS_TENNESSEE_TOTALS,
          spreads: [],
          period_markets: [],
          home_score: 17,
          away_score: 20,
        } as never
      }
      eventStatus={"completed" as never}
      homeTeam="Tennessee Volunteers"
      awayTeam="Texas Longhorns"
      homeAbbr="TENN"
      awayAbbr="TEX"
      homeWinProb={0}
      awayWinProb={1}
      overUnder={55}
      sportKey="americanfootball_ncaaf"
    />
  );
}

/** Each ladder row's label + verdict, and whether it is collapsed. */
function ladderRows(html: string): Array<{ text: string; collapsed: boolean }> {
  const rows: Array<{ text: string; collapsed: boolean }> = [];
  const re = /<div([^>]*grid-template-columns:94px 1fr 38px[^>]*)>([\s\S]*?cleared)<\/div><\/div>/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html))) {
    rows.push({
      text: m[2].replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim(),
      collapsed: /data-ladder-row-collapsed="1"/.test(m[1]),
    });
  }
  return rows;
}

describe("#8946 a graded ladder shows the lines around the final", () => {
  const html = renderCard();
  const rows = ladderRows(html);

  it("still renders every rung the payload served (#6218 is not undone)", () => {
    expect(rows).toHaveLength(TEXAS_TENNESSEE_TOTALS.length);
    expect(rows.filter((r) => r.text.endsWith("not cleared"))).toHaveLength(
      TEXAS_TENNESSEE_TOTALS.length - 2
    );
  });

  it("shows only the two lines either side of 37 points", () => {
    expect(rows.filter((r) => !r.collapsed).map((r) => r.text)).toEqual([
      "Over 35.5 cleared",
      "Over 36.5 cleared",
      "Over 37.5 not cleared",
      "Over 39.5 not cleared",
    ]);
  });

  it("hides the rest with display:none, which beats the grid's inline display", () => {
    const collapsedTags = html.match(/<div[^>]*data-ladder-row-collapsed="1"[^>]*>/g) ?? [];
    expect(collapsedTags).toHaveLength(TEXAS_TENNESSEE_TOTALS.length - 4);
    for (const tag of collapsedTags) {
      expect(tag).toContain("display:none");
      expect(tag).toContain("hidden");
    }
  });

  it("offers every line one tap away", () => {
    expect(html).toContain(`Show all ${TEXAS_TENNESSEE_TOTALS.length} lines`);
    expect(html).toContain('aria-expanded="false"');
  });
});

describe("#8946 gradedLadderVisibleRows", () => {
  const row = (label: string, outcome?: "cleared" | "missed"): MarketMapLadderRow => ({
    label,
    probability: outcome === "cleared" ? 100 : 0,
    side: "mid",
    outcome,
  });
  const graded = (pattern: string) =>
    pattern.split("").map((c, i) => row(`r${i}`, c === "c" ? "cleared" : "missed"));

  it("leaves a short graded ladder whole", () => {
    expect(gradedLadderVisibleRows(graded("c".repeat(3) + "m".repeat(GRADED_LADDER_COLLAPSE_OVER - 3)))).toBeNull();
  });

  it("never collapses a ladder that is still quoting a price per row", () => {
    const quoting = Array.from({ length: 30 }, (_, i) => row(`q${i}`));
    expect(gradedLadderVisibleRows(quoting)).toBeNull();
  });

  it("keeps a window at EVERY flip (a margin ladder flips twice)", () => {
    // TEX by 17.5+ … TEX by 2.5+ missed/cleared, then TENN side all missed.
    const ladder = graded("mmmmmcccccmmmmm");
    expect([...(gradedLadderVisibleRows(ladder) ?? [])].sort((a, b) => a - b)).toEqual([
      3, 4, 5, 6, 8, 9, 10, 11,
    ]);
  });

  it("with no flip at all, keeps the first rows", () => {
    expect([...(gradedLadderVisibleRows(graded("m".repeat(20))) ?? [])]).toEqual([0, 1, 2, 3]);
  });
});
