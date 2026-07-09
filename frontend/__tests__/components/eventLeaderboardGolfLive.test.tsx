// #999 L2-66: EventLeaderboard golf LIVE mode — fused row (position · name ·
// to-par · thru · win%), ordered by score-to-par, with an SSR-safe freshness chip.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { EventConceptCompetitor } from "@/lib/types";

jest.mock("@/lib/api", () => ({
  formatProbability: (p: number | null) => (p == null ? "—" : `${Math.round(p * 100)}%`),
}));

import EventLeaderboard from "../../components/event/EventLeaderboard";

const liveCompetitors: EventConceptCompetitor[] = [
  // Trailing on win% but leading on the course — must sort to the TOP by score.
  { name: "Rory McIlroy", probability: 0.28, position: "T1", score_to_par: -9, thru: "F", current_round: 3 },
  { name: "Scottie Scheffler", probability: 0.34, position: "T2", score_to_par: -7, thru: "12", current_round: 3 },
  { name: "Ludvig Aberg", probability: 0.05, position: "T5", score_to_par: 2, thru: "11", current_round: 3 },
];

describe("EventLeaderboard golf live mode (L2-66)", () => {
  test("renders fused row with position, to-par, thru, win%", () => {
    const html = renderToStaticMarkup(
      <EventLeaderboard competitors={liveCompetitors} label="Leaderboard" live asOf="2026-07-09T15:00:00Z" />,
    );
    expect(html).toContain("Pos");
    expect(html).toContain("To");           // "To par" header (may contain nbsp)
    expect(html).toContain("Thru");
    expect(html).toContain("Rory McIlroy");
    expect(html).toContain("-9");           // score to par
    expect(html).toContain("+2");           // over-par formatting
    expect(html).toContain("F");            // thru finished
    expect(html).toContain("H12");          // thru hole
    expect(html).toContain("34%");          // win% headline still shown
    // no American odds
    expect(html).not.toMatch(/[+-]\d{3,}/);
  });

  test("orders by score-to-par, not win% (leaderboard, not odds board)", () => {
    const html = renderToStaticMarkup(
      <EventLeaderboard competitors={liveCompetitors} label="Leaderboard" live asOf="x" />,
    );
    // Rory (-9) must appear before Scheffler (-7) despite lower win%.
    expect(html.indexOf("Rory McIlroy")).toBeLessThan(html.indexOf("Scottie Scheffler"));
  });

  test("probability-only: never renders american_odds on the golf-live row (L2-67 Item 2)", () => {
    // The envelope carries american_odds per competitor (allowed API field); the
    // row must NEVER surface it — probabilities are the only number.
    const withOdds: EventConceptCompetitor[] = [
      { name: "Rory McIlroy", probability: 0.16, american_odds: -450, position: "T1", score_to_par: -5, thru: "18" },
      { name: "Patrick Cantlay", probability: 0.04, american_odds: 550, position: "T1", score_to_par: -5, thru: "18" },
    ];
    const html = renderToStaticMarkup(
      <EventLeaderboard competitors={withOdds} label="Leaderboard" live asOf="x" />,
    );
    expect(html).not.toContain("-450");
    expect(html).not.toContain("450");
    expect(html).not.toContain("550");
    expect(html).not.toMatch(/[+-]\d{3,}/); // no moneyline pattern at all
    expect(html).toContain("16%"); // probability IS shown
  });

  test("real round-1 shapes: T1 ties, mid-round thru, not-started shows —", () => {
    const roundOne: EventConceptCompetitor[] = [
      { name: "Rory McIlroy", probability: 0.159, position: "T1", score_to_par: -5, thru: "18" },
      { name: "Tom Kim", probability: 0.041, position: "T1", score_to_par: -5, thru: "12" },
      { name: "Late Starter", probability: 0.01, position: null, score_to_par: null, thru: "0" },
    ];
    const html = renderToStaticMarkup(
      <EventLeaderboard competitors={roundOne} label="Leaderboard" live asOf="x" />,
    );
    expect(html).toContain("H12");        // mid-round hole
    expect(html).not.toContain("H0");     // not-started must NOT render "H0"
    expect(html).toContain("16%");        // 0.159 → 16%
  });

  test("falls back to the standard winner-field render when not golf-live", () => {
    const html = renderToStaticMarkup(
      <EventLeaderboard
        competitors={[{ name: "Scottie Scheffler", probability: 0.34 }]}
        label="Winner"
        live={false}
      />,
    );
    expect(html).toContain("Scottie Scheffler");
    expect(html).not.toContain("Thru"); // no golf-live columns
  });
});
