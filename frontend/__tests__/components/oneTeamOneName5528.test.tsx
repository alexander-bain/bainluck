/**
 * #5528 — the game's own winner card prints one club under one name.
 *
 * Production 2026-09-28, 390px, settled `/events/15319741` (Red Sox 2 – Cubs 6).
 * Kalshi titles the side `Boston`, Polymarket `Boston Red Sox`, the merge keys on
 * the label, and the card read:
 *
 *     Boston Red Sox vs Chicago Cubs          2x
 *     Chicago Cubs                           Won
 *     Boston                                Lost
 *     Boston Red Sox                        Lost
 *
 * The rows below are the served `other[]` rows for those two markets, verbatim
 * except for `observed_at`. Each rename is paired with the case that must NOT
 * rename, so a guard that renamed everything to the home team would fail.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import SpecialEventMarkets from "../../components/SpecialEventMarkets";
import { buildMarketSection, eventSideForLabel } from "../../lib/otherMarketGroups";
import type { GameMarketsResponse } from "../../lib/api";

const row = (market_name: string, outcome_name: string, probability: number | null, is_winner: boolean, source: string, id: number) => ({
  market_name,
  outcome_name,
  probability,
  source,
  is_winner,
  resolution_source: "api_settlement",
  observed_at: "2026-09-28T16:47:50Z",
  _market_id: id,
});

const WIRE = [
  row("Chicago Cubs vs. Boston Red Sox", "Chicago Cubs", 1.0, true, "polymarket", 62232222),
  row("Chicago Cubs vs. Boston Red Sox", "Boston Red Sox", null, false, "polymarket", 62232222),
  row("Chicago Cubs vs Boston", "Chicago Cubs", 1.0, true, "kalshi", 62341415),
  row("Chicago Cubs vs Boston", "Boston", null, false, "kalshi", 62341415),
  row("Will there be a run scored in the first inning?: Chicago Cubs vs. Boston Red Sox", "Yes", 1.0, true, "polymarket", 62803342),
  row("Chicago Cubs vs Boston: First Inning Run", "Yes", 1.0, true, "kalshi", 62401252),
];

const payload = (other: unknown[], home = "Boston Red Sox", away = "Chicago Cubs") =>
  ({ home_team: home, away_team: away, status: "completed", other }) as unknown as GameMarketsResponse;

function winnerCard(other: unknown[], home?: string, away?: string) {
  const section = buildMarketSection(payload(other, home, away).other as never, {
    homeTeam: home ?? "Boston Red Sox",
    awayTeam: away ?? "Chicago Cubs",
  });
  const cards = section.categories.flatMap((c) => c.cards);
  return cards.find((c) => c.name === `${home ?? "Boston Red Sox"} vs ${away ?? "Chicago Cubs"}`);
}

describe("#5528 the game's own winner card names each team once", () => {
  it("the production specimen merges Boston and Boston Red Sox into one row", () => {
    const card = winnerCard(WIRE);
    expect(card?.outcomes.map((o) => o.label)).toEqual(["Chicago Cubs", "Boston Red Sox"]);
    const boston = card?.outcomes.find((o) => o.label === "Boston Red Sox");
    expect(boston?.sourceCount).toBe(2);
    expect(boston?.isWinner).toBe(false);
  });

  it("the rendered card prints no bare 'Boston' row", () => {
    const html = renderToStaticMarkup(
      <SpecialEventMarkets data={payload(WIRE)} eventStatus="completed" />,
    );
    expect(html).toContain("Boston Red Sox");
    expect(html).not.toMatch(/>Boston</);
  });

  it("a side question on the same page keeps its own labels", () => {
    const section = buildMarketSection(WIRE as never, {
      homeTeam: "Boston Red Sox",
      awayTeam: "Chicago Cubs",
    });
    const labels = section.categories.flatMap((c) => c.cards).flatMap((c) => c.outcomes.map((o) => o.label));
    expect(labels).toContain("Yes");
  });

  it("a team named on a different question keeps the venue's spelling", () => {
    const other = [
      ...WIRE,
      row("Chicago Cubs vs Boston: Most Hits", "Boston", 1.0, true, "kalshi", 9),
      row("Chicago Cubs vs Boston: Most Hits", "Chicago Cubs", null, false, "kalshi", 9),
    ];
    const section = buildMarketSection(other as never, {
      homeTeam: "Boston Red Sox",
      awayTeam: "Chicago Cubs",
    });
    const card = section.categories.flatMap((c) => c.cards).find((c) => c.name.includes("Most Hits"));
    expect(card?.outcomes.map((o) => o.label)).toContain("Boston");
  });

  it("without our team names nothing is renamed", () => {
    const section = buildMarketSection(WIRE as never, {});
    const labels = section.categories.flatMap((c) => c.cards).flatMap((c) => c.outcomes.map((o) => o.label));
    expect(labels).toContain("Boston");
  });
});

describe("eventSideForLabel", () => {
  it.each([
    ["Boston", "Boston Red Sox"],
    ["San Diego", "San Diego Padres"],
    ["Stade Rennais", "Stade Rennais FC"],
    ["Lloyd Harris", "Harris"],
  ])("%s is %s", (side, team) => {
    expect(eventSideForLabel(side, team, "Chicago Cubs")).toBe("home");
    expect(eventSideForLabel(side, "Chicago Cubs", team)).toBe("away");
  });

  it.each([
    ["New York", "New York Yankees", "New York Mets"],
    ["Draw", "Stade Rennais FC", "Olympique de Marseille"],
    ["A's", "Athletics", "Houston Astros"],
    ["San Francisco", "San Diego Padres", "Chicago Cubs"],
    ["", "Boston Red Sox", "Chicago Cubs"],
  ])("%s on %s v %s stays the venue's", (side, home, away) => {
    expect(eventSideForLabel(side, home, away)).toBeNull();
  });
});

describe("the fuller spelling wins, whichever side supplies it", () => {
  it("a surname-only event keeps the venue's full name", () => {
    const other = [
      row("Vacherot vs Harris", "Lloyd Harris", 1.0, true, "kalshi", 1),
      row("Vacherot vs Harris", "Valentin Vacherot", null, false, "kalshi", 1),
      row("Vacherot vs. Harris", "Harris", 1.0, true, "polymarket", 2),
    ];
    const card = winnerCard(other, "Vacherot", "Harris");
    expect(card?.outcomes.map((o) => o.label)).toEqual(["Lloyd Harris", "Valentin Vacherot"]);
  });

  it("a single-venue short side takes our event name", () => {
    const card = winnerCard(WIRE.slice(2, 4));
    expect(card?.outcomes.map((o) => o.label)).toEqual(["Chicago Cubs", "Boston Red Sox"]);
  });
});
