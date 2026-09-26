/**
 * #8870 — A MARGIN CARD NAMES ITS TWO SIDES DIFFERENTLY.
 *
 * Mystery-shopped on production 2026-09-26 at 390px, `/events/15315297`
 * (Granada CF 2–3 Andorra CF, Final). The hero printed both full names; the
 * margin card under it called BOTH sides "CF": `FINAL CF by 1`, rail ends
 * `CF by 5+ … CF by 5+`, every ladder row `CF by N+`. The event serves no
 * `home_team_data`/`away_team_data`, so both sides hit the abbreviation
 * fallback, which sliced the club-type suffix.
 *
 * The fixture is production's `spreads` block from
 * `/api/events/15315297/game-markets`, read 2026-09-26 19:3xZ; everything else
 * is emptied so only the margin card renders.
 *
 * Non-vacuous: every arm asserts the card is still drawn, so "no CF by" cannot
 * be satisfied by a card that vanished.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection, { marginSideLabels } from "@/components/MarketMapSection";
import gm from "../fixtures/8870GranadaAndorraMargin.20260926.json";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&[a-z#0-9]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function render(props: Partial<React.ComponentProps<typeof MarketMapSection>> = {}): string {
  return visibleText(
    renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={gm as never}
        eventStatus="completed"
        homeTeam="Granada CF"
        awayTeam="Andorra CF"
        sportKey="soccer_spain_segunda_division"
        {...props}
      />
    )
  );
}

describe("#8870 margin card on two same-suffix clubs", () => {
  it("names each side by the hero's name on the production card", () => {
    const text = render();
    expect(text).toContain("Margin: expected vs final");
    // Every "CF by" belongs to a named club; none stands alone.
    expect(text.replace(/(Granada|Andorra) CF by/g, "")).not.toContain("CF by");
    expect(text).toContain("Final Andorra CF by 1");
    expect(text).toContain("Andorra CF by 5+ 0 Granada CF by 5+");
    expect(text).toContain("Granada CF by 1.5+");
    expect(text).toContain("Andorra CF by 1.5+");
  });

  it("a graded row keeps a full-name label on one line", () => {
    const html = renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={gm as never}
        eventStatus="completed"
        homeTeam="Granada CF"
        awayTeam="Andorra CF"
        sportKey="soccer_spain_segunda_division"
      />
    );
    expect(html).toMatch(/white-space:nowrap[^>]*>Andorra CF by 2\.5\+</);
  });

  it("control: served abbreviations are still printed as served", () => {
    const text = render({ homeAbbr: "GRA", awayAbbr: "AND2" });
    expect(text).toContain("Final AND2 by 1");
    expect(text).toContain("GRA by 1.5+");
    expect(text).not.toContain("Granada CF by");
  });
});

describe("marginSideLabels", () => {
  it("keeps the shipped three-letter code when the last word names the side", () => {
    expect(marginSideLabels("Chicago Cubs", "St. Louis Cardinals", undefined, undefined, "baseball_mlb")).toEqual({
      home: "CUB",
      away: "CAR",
    });
  });

  it("a club-type suffix takes the hero's short name", () => {
    expect(marginSideLabels("Granada CF", "Andorra CF", undefined, undefined, "soccer_spain_segunda_division")).toEqual({
      home: "Granada CF",
      away: "Andorra CF",
    });
  });

  it("a club-type suffix is refused even when only one side lacks a served code", () => {
    expect(marginSideLabels("Real Madrid", "Andorra CF", "RMA", undefined, "soccer_spain_la_liga")).toEqual({
      home: "RMA",
      away: "Andorra CF",
    });
  });

  it("two sides that slice to the same code fall back to distinct names", () => {
    const labels = marginSideLabels(
      "Georgia Bulldogs",
      "Mississippi State Bulldogs",
      undefined,
      undefined,
      "americanfootball_ncaaf"
    );
    expect(labels.home.toLowerCase()).not.toBe(labels.away.toLowerCase());
    expect(labels).toEqual({ home: "Georgia Bulldogs", away: "Mississippi State Bulldogs" });
  });

  it("two identical served codes also fall back", () => {
    const labels = marginSideLabels("Georgia Bulldogs", "Fresno State Bulldogs", "UGA", "uga", "americanfootball_ncaaf");
    expect(labels).toEqual({ home: "Georgia Bulldogs", away: "Fresno State Bulldogs" });
  });

  it("distinct served codes are untouched", () => {
    expect(marginSideLabels("Leeds United", "Newcastle United", "LEE", "NEW", "soccer_epl")).toEqual({
      home: "LEE",
      away: "NEW",
    });
  });
});
