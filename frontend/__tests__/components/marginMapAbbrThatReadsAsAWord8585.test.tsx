/**
 * #8585 — A MARGIN MAP NEVER NAMES A SIDE WITH A CODE THAT READS AS A WORD.
 *
 * Mystery-shopped on production 2026-09-25 at 390px, `/events/14792803`
 * (LSU 24 at Ole Miss 32, Final). The hero said "Rebels WON"; the margin card
 * under it said `FINAL MISS by 8` and ended its rail `MISS by 18+`. "MISS" is
 * ESPN's real code for Ole Miss (served as `home_team_data.abbreviation`), and
 * on a card titled "expected vs final" it reads as "the forecast missed by 8".
 *
 * The fixture is production's `spreads` block from
 * `/api/events/14792803/game-markets`, read 2026-09-25 09:2xZ; everything else
 * on the payload is emptied so only the margin card renders.
 *
 * Non-vacuous: every arm asserts the card is still drawn and that the OTHER
 * side's code is untouched, so "no MISS" cannot be satisfied by a card that
 * vanished or by a fix that drops abbreviations wholesale.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import gm from "../fixtures/8585OleMissMarginMap.20260925.json";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&[a-z#0-9]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function render(homeAbbr: string | undefined, homeTeam = "Ole Miss Rebels"): string {
  return visibleText(
    renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={gm as never}
        eventStatus="completed"
        homeTeam={homeTeam}
        awayTeam="LSU Tigers"
        homeAbbr={homeAbbr}
        awayAbbr="LSU"
        sportKey="americanfootball_ncaaf"
      />
    )
  );
}

describe("#8585 margin labels never print an abbreviation that reads as a word", () => {
  it("names Ole Miss by the hero's short name on the production card", () => {
    const text = render("MISS");
    expect(text).toContain("Margin: expected vs final");
    expect(text).toContain("Final Rebels by 8");
    expect(text).toContain("Rebels by 18+");
    expect(text).toContain("Rebels by 7.5+ cleared");
    expect(text).not.toMatch(/\bMISS\b/);
    // The other side keeps its served code.
    expect(text).toContain("LSU by 18+");
    expect(text).toContain("LSU by 3.5+ not cleared");
  });

  it("matches the word case-insensitively", () => {
    const text = render("Miss");
    expect(text).toContain("Final Rebels by 8");
    expect(text).not.toMatch(/\bMiss by\b/);
  });

  it("covers New Orleans's NO the same way", () => {
    const text = render("NO", "New Orleans Saints");
    expect(text).toContain("Final Saints by 8");
    expect(text).not.toMatch(/\bNO by\b/);
  });

  it("control: a code that is not a word is printed as served", () => {
    const text = render("OM");
    expect(text).toContain("Final OM by 8");
    expect(text).not.toContain("Rebels by");
  });
});
