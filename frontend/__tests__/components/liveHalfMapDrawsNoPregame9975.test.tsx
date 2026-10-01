/**
 * #9975 — A LIVE HALF / FIRST-5 RUNS MAP STOPS RELABELLING THE LIVE LINE "PRE-GAME".
 *
 * Seen on production at 390px, notice-42 shop of BOS @ NYY, Wild Card G2
 * (`/events/15321907`), First 5 innings runs map:
 *
 *   00:07Z  pre-pitch        O/U 4 · PRE-GAME 4
 *   00:27Z  Mid 1st, 0–0     O/U 4 · PRE-GAME 4
 *   00:47Z  Top 3rd, 0–0     O/U 3 · PRE-GAME 3
 *
 * The "pre-game" expectation moved mid-game because the tile is
 * `ouLine.threshold` — the CURRENT ladder's nearest-to-even rung — and no
 * served `half_total` row carries a frozen value (`pregame_mark: null`,
 * `opening_probability: null` on all 14 rows at 00:48Z).
 *
 * ═══ WHAT MAKES THIS SUITE NON-VACUOUS ═══
 *
 * "No Pre-game tile" is also what a card that failed to render looks like. So
 * the live arm asserts the card is STILL THERE with its live headline, and the
 * controls render the SAME rows under `scheduled` (tile present, the value the
 * fix must not delete) and `completed` with a quoting ladder (#5143's control,
 * tile present). A fix that dropped the card, or keyed on anything but the game
 * being in play, fails one of them. Tiles are asserted through `data-tile`.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;|&#39;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function tileCount(html: string, key: string): number {
  return html.split(`data-tile="${key}"`).length - 1;
}

/** A First 5 ladder in the Top 3rd: nearest-to-even rung is 2.5 ⇒ `O/U 3`, the
 * specimen's headline. */
const F5_TOP_3RD = [
  [0.5, 0.86],
  [1.5, 0.71],
  [2.5, 0.52],
  [3.5, 0.36],
  [4.5, 0.22],
  [5.5, 0.12],
] as const;

function rows() {
  return F5_TOP_3RD.map(([threshold, over]) => ({
    threshold,
    over_probability: over,
    probability: null,
    source: "polymarket",
    market_type: "half_total",
    market_name: `Boston Red Sox vs. New York Yankees: 1st 5 Innings O/U ${threshold}`,
    outcome_name: "Over",
    is_winner: null,
    resolution_source: null,
    movement: 0,
    period: null,
    pregame_mark: null,
    opening_probability: null,
  }));
}

function render(eventStatus: "live" | "scheduled" | "completed"): string {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={
        {
          event_id: 15321907,
          home_team: "New York Yankees",
          away_team: "Boston Red Sox",
          home_score: 0,
          away_score: 0,
          status: eventStatus,
          player_props: [],
          team_totals: [],
          period_markets: rows(),
          matchups: [],
          other: [],
          pace: null,
          props_script: [],
          spreads: [],
          totals: [],
        } as never
      }
      eventStatus={eventStatus}
      homeTeam="New York Yankees"
      awayTeam="Boston Red Sox"
      homeAbbr="NYY"
      awayAbbr="BOS"
      sportKey="baseball_mlb"
    />
  );
}

describe("#9975 a live First 5 runs map draws no Pre-game tile", () => {
  it("keeps the card and its live line, and drops the relabelled tile", () => {
    const html = render("live");
    const text = visibleText(html);

    expect(text).toContain("First 5 innings runs map");
    expect(text).toContain("O/U 3");
    expect(tileCount(html, "pre")).toBe(0);
    expect(text).not.toMatch(/pre-game/i);
  });

  it("CONTROL: the same rows before first pitch keep the Pre-game tile", () => {
    const html = render("scheduled");

    expect(visibleText(html)).toContain("First 5 innings runs map");
    expect(tileCount(html, "pre")).toBe(1);
  });

  it("CONTROL: a finished game whose ladder quoted keeps it (#5143)", () => {
    const html = render("completed");

    expect(visibleText(html)).toContain("First 5 innings runs map");
    expect(tileCount(html, "pre")).toBe(1);
  });
});
