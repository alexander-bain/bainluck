// L2-132: EventLeaderboard LIVE/upcoming winner-field mode — the World Cup
// eliminated-entrant chrome. A 48-nation field must not render as a wall of dead
// entrants: contenders show green bars, the OUT tail (true-0 / adapter-flagged)
// collapses behind a "Show all N" expander and renders with NO green, an "OUT"
// chip, and a muted row. Consumes the adapter's `eliminated` flag when present
// (#208) and infers a true-0 tail honestly meanwhile.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { EventConceptCompetitor } from "@/lib/types";

jest.mock("@/lib/api", () => ({
  formatProbability: (p: number | null) => (p == null ? "—" : `${Math.round(p * 100)}%`),
}));

import EventLeaderboard from "../../components/event/EventLeaderboard";

describe("EventLeaderboard winner-field eliminated chrome (L2-132)", () => {
  test("contenders render with green bars; the 0% tail collapses into 'Show all N' with OUT chips", () => {
    const field: EventConceptCompetitor[] = [
      { name: "Brazil", probability: 0.24 },
      { name: "France", probability: 0.19 },
      { name: "Iceland", probability: 0 }, // true-0 → OUT
      { name: "Vanuatu", probability: 0.001 }, // <= floor → OUT
    ];
    const html = renderToStaticMarkup(
      <EventLeaderboard competitors={field} label="Winner" live />,
    );
    // Contenders are visible with a green (accent-brand) bar.
    expect(html).toContain("Brazil");
    expect(html).toContain("France");
    expect(html).toContain("bg-accent-brand");
    // The OUT tail is collapsed behind the field expander (2 hidden of 4 total).
    expect(html).toContain("Show all 4");
    // Eliminated rows carry an OUT chip and are present in the expander markup.
    expect(html).toContain(">Out<");
    expect(html).toContain("Iceland");
    expect(html).toContain("Vanuatu");
  });

  test("adapter `eliminated` flag marks a row OUT even at a stale non-zero price", () => {
    const field: EventConceptCompetitor[] = [
      { name: "Spain", probability: 0.3 },
      // Dead entrant the adapter graded eliminated before the price zeroed.
      { name: "Ghana", probability: 0.02, eliminated: true } as EventConceptCompetitor,
    ];
    const html = renderToStaticMarkup(
      <EventLeaderboard competitors={field} label="Winner" live />,
    );
    expect(html).toContain("Show all 2");
    expect(html).toContain(">Out<");
    // The stale 2% must NOT render as a live probability for an OUT entrant.
    expect(html).not.toContain("2%");
  });

  test("an all-contender field shows no expander and no OUT chip", () => {
    const field: EventConceptCompetitor[] = [
      { name: "Argentina", probability: 0.28 },
      { name: "England", probability: 0.15 },
      { name: "Portugal", probability: 0.03 }, // 3% stale — still a contender, not OUT
    ];
    const html = renderToStaticMarkup(
      <EventLeaderboard competitors={field} label="Winner" live />,
    );
    expect(html).not.toContain("Show all");
    expect(html).not.toContain(">Out<");
    expect(html).toContain("Portugal");
  });

  test("empty field renders nothing", () => {
    const html = renderToStaticMarkup(
      <EventLeaderboard competitors={[]} label="Winner" live />,
    );
    expect(html).toBe("");
  });
});
