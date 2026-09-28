/**
 * #9461 — a finished game's Touchdowns tile printed a big red "— of 1".
 *
 * The venue grades anytime-TD props (`hit: false`, `resolution_source:
 * "api_settlement"`) but the served row carries `actual: null` — 51 of 51 on
 * /events/14780548. The graded tile printed `gradeActual ?? "—"` at text-2xl in
 * the verdict colour, plus "of 1": a placeholder painted as the verdict, and a
 * count the tile never gives. With no count, the number row is not drawn; the
 * verdict line carries the result. With a count, the tile is unchanged.
 *
 * Rows are the #9454 fixture's (production, unedited), filtered to one stat so
 * the tile under test is the card's only tile.
 */
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PlayerPropsDashboard from "../../components/PlayerPropsDashboard";
import type { GameMarketsResponse } from "../../lib/api";
import type { PlayerPropRow } from "../../lib/playerPropsGrouping";
import fixture from "../fixtures/propsTrayLadder9454.json";

const ROWS = fixture.player_props as PlayerPropRow[];

// Kalshi names the player in `outcome_name` ("Bo Nix: 1+"); Polymarket in
// `market_name` ("Courtland Sutton: Longest Reception O/U 19.5").
function rowsFor(player: string, stat: string): PlayerPropRow[] {
  const rows = ROWS.filter((r) => {
    const market = r.market_name ?? "";
    return (
      (market.endsWith(`: ${stat}`) && (r.outcome_name ?? "").startsWith(`${player}:`)) ||
      market.startsWith(`${player}: ${stat} O/U`)
    );
  });
  if (rows.length === 0) throw new Error(`fixture has no ${player} ${stat}`);
  return rows;
}

function render(rows: PlayerPropRow[]): string {
  return renderToStaticMarkup(
    <PlayerPropsDashboard
      data={{ player_props: rows, other: [] } as unknown as GameMarketsResponse}
      eventStatus="completed"
      homeTeam="Denver Broncos"
      awayTeam="Los Angeles Rams"
    />,
  );
}

describe("a graded tile with no published count", () => {
  // Sutton: Touchdowns 1+/2+/3+, every rung a venue MISS, every `actual` null.
  const rows = rowsFor("Courtland Sutton", "Touchdowns");
  const html = render(rows);

  it("the specimen is what production serves: graded, no count", () => {
    expect(rows.every((r) => r.hit === false && r.actual == null)).toBe(true);
  });

  it("still states the verdict and the line", () => {
    expect(html).toContain("MISS");
    expect(html).toContain("needed 1+");
  });

  it("draws no number row — no dash standing in for a count", () => {
    expect(html).not.toContain('data-testid="prop-tile-actual"');
    expect(html).not.toContain("—");
    expect(html).not.toMatch(/>of 1</);
  });
});

describe("a split ladder with no published count", () => {
  // Nix: Touchdowns HIT at 1+, MISS at 2+, `actual` null on both.
  const html = render(rowsFor("Bo Nix", "Touchdowns"));

  it("still prints both verdicts", () => {
    expect(html).toContain('data-settled-ladder="split"');
    expect(html).toMatch(/HIT<\/span><span[^>]*>1\+/);
    expect(html).toMatch(/MISS<\/span><span[^>]*>2\+/);
  });

  it("draws no number row", () => {
    expect(html).not.toContain('data-testid="prop-tile-actual"');
    expect(html).not.toContain("—");
  });
});

// The other direction (gotcha #43): a published count is still printed.
describe("a graded tile WITH a count is unchanged", () => {
  it("single verdict: the count and 'of N' both render", () => {
    const rows = rowsFor("Courtland Sutton", "Longest Reception");
    const html = render(rows);
    expect(html).toContain('data-testid="prop-tile-actual"');
    expect(html).toMatch(/>27<\/div>/);
    expect(html).toMatch(/>of \d+(\.\d+)?</);
  });

  it("split ladder: Stafford's 2 still renders above HIT 2+ / MISS 2.5+", () => {
    const html = render(rowsFor("Matthew Stafford", "Passing Touchdowns"));
    expect(html).toContain('data-testid="prop-tile-actual"');
    expect(html).toMatch(/>2<\/div>/);
  });
});
