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

  test("cut/MC/WD players sink into a collapsed 'Missed cut' group, not mid-field (L2-68)", () => {
    const postCut: EventConceptCompetitor[] = [
      { name: "Rory McIlroy", probability: 0.3, position: "1", score_to_par: -12, thru: "F" },
      { name: "Scottie Scheffler", probability: 0.25, position: "2", score_to_par: -10, thru: "F" },
      // Missed the cut with a "better-looking" stale round-1 score — must NOT sort
      // above active players; sinks to the collapsed group.
      { name: "Early Casualty", probability: 0, position: "CUT", score_to_par: -14, thru: "F" },
      { name: "Withdrew Guy", probability: 0, position: "WD", score_to_par: 3, thru: "F" },
      { name: "Missed It", probability: 0, position: "MC", score_to_par: 5, thru: "F" },
    ];
    const html = renderToStaticMarkup(
      <EventLeaderboard competitors={postCut} label="Leaderboard" live asOf="x" />,
    );
    // Collapsed group present with the right count.
    expect(html).toContain("Missed cut (3)");
    // The -14 cut player must NOT sort above the -12 active leader.
    expect(html.indexOf("Rory McIlroy")).toBeLessThan(html.indexOf("Early Casualty"));
    // Cut chips rendered (normalized).
    expect(html).toContain("CUT");
    expect(html).toContain("WD");
    expect(html).toContain("MC");
    // no American odds anywhere
    expect(html).not.toMatch(/[+-]\d{3,}/);
  });

  test("no 'Missed cut' group pre-cut (all active)", () => {
    const html = renderToStaticMarkup(
      <EventLeaderboard competitors={liveCompetitors} label="Leaderboard" live asOf="x" />,
    );
    expect(html).not.toContain("Missed cut");
  });

  test("row shows the in-play prob_delta_live ('who's charging') when present (L2-69)", () => {
    const withDelta: EventConceptCompetitor[] = [
      // movement_24h is null during live; prob_delta_live carries the chip.
      { name: "Rory McIlroy", probability: 0.161, position: "T1", score_to_par: -5, thru: "18", prob_delta_live: 8.8 },
      { name: "Faller", probability: 0.02, position: "T20", score_to_par: 1, thru: "18", prob_delta_live: -3.4 },
    ];
    const html = renderToStaticMarkup(
      <EventLeaderboard competitors={withDelta} label="Leaderboard" live asOf="x" />,
    );
    expect(html).toContain("▲"); // charging up
    expect(html).toContain("8.8");
    expect(html).toContain("▼"); // falling
    expect(html).toContain("3.4");
    expect(html).toContain("16%"); // win% still the headline
    expect(html).not.toMatch(/[+-]\d{3,}/);
  });

  // L2-147 Item 1: active golfers ranked past the 20-row limit used to be silently
  // dropped in the golf-live branch (no expander, unlike the winner-field branch).
  // The full field must now be reachable behind "Show all N".
  test("reveals active golfers past the limit behind 'Show all N' (no hard cut)", () => {
    const bigField: EventConceptCompetitor[] = Array.from({ length: 25 }, (_, i) => ({
      name: `Golfer ${String(i + 1).padStart(2, "0")}`,
      probability: 0.5 - i * 0.01,
      position: `${i + 1}`,
      score_to_par: -20 + i,
      thru: "F",
      current_round: 4,
    }));
    const html = renderToStaticMarkup(
      <EventLeaderboard competitors={bigField} label="Leaderboard" live asOf="x" />,
    );
    // 25 active golfers, none cut → the "Show all 25" expander must appear.
    expect(html).toContain("Show all 25");
    // A golfer ranked past the 20-row default is still present in the DOM (inside
    // the expander), not dropped — the wall is gone.
    expect(html).toContain("Golfer 24");
    expect(html).not.toContain("Missed cut");
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
