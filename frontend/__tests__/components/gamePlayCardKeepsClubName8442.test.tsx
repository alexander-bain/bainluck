/**
 * #8442 — the readout under the chart named Tottenham Hotspur "Hotspur".
 *
 * Seen on production at 390px, `/events/15305207` (Tottenham Hotspur 2–3 Aston
 * Villa, final), 2026-09-24: hero and side axis read "Tottenham Hotspur", the
 * readout read "Hotspur 0%". `GamePlayCard` called `teamShortNames` without the
 * sport, so the #5634 football rule (a club keeps its whole name, up to three
 * words) never ran on this surface while it ran on the hero.
 *
 * Both directions (gotcha #43): a soccer key keeps the club's name; a club sport
 * that is not football, and a missing key, keep the shipped last-word rule.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import GamePlayCard from "../../components/GamePlayCard";
import { teamShortNames } from "../../lib/teamShortName";
import type { ActiveChartPoint } from "../../lib/types";

const point: ActiveChartPoint = {
  timestamp: "2026-09-24T19:40:00Z",
  homeProb: 0,
  awayProb: 1,
  homeScore: 2,
  awayScore: 3,
  period: null,
  clock: null,
  scoringPlay: null,
};

function render(homeTeam: string, awayTeam: string, sportKey?: string) {
  return renderToStaticMarkup(
    <GamePlayCard
      activePoint={null}
      lastPoint={point}
      homeTeam={homeTeam}
      awayTeam={awayTeam}
      sportKey={sportKey}
    />,
  );
}

/** The readout's label text with the markup stripped, whitespace collapsed. */
function text(html: string): string {
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

describe("#8442 the chart readout names a football club the way the hero does", () => {
  test("the production specimen: Tottenham Hotspur v Aston Villa, EPL", () => {
    const out = text(render("Tottenham Hotspur", "Aston Villa", "soccer_epl"));
    expect(out).toContain("Tottenham Hotspur");
    expect(out).toContain("Aston Villa");
    // "Hotspur" appears only inside "Tottenham Hotspur", never on its own.
    expect(out.replace(/Tottenham Hotspur/g, "")).not.toContain("Hotspur");
  });

  test("the readout's labels are exactly the hero's rule for the same sport", () => {
    const { home, away } = teamShortNames(
      { name: "Tottenham Hotspur" },
      { name: "Aston Villa" },
      "soccer_epl",
    );
    const out = text(render("Tottenham Hotspur", "Aston Villa", "soccer_epl"));
    expect(out).toContain(home);
    expect(out).toContain(away);
  });

  test("control: an NFL game keeps the last-word rule on this card", () => {
    const out = text(render("Dallas Cowboys", "Washington Commanders", "americanfootball_nfl"));
    expect(out).toContain("Cowboys");
    expect(out).not.toContain("Dallas Cowboys");
  });

  test("control: no sport key keeps the shipped last-word rule exactly", () => {
    const out = text(render("Tottenham Hotspur", "Aston Villa"));
    expect(out).not.toContain("Tottenham");
    expect(out).toContain("Hotspur");
  });
});
