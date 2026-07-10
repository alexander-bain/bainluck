// L2-81: EventLeaderboard SETTLED mode — a concluded winner-field (tennis slam,
// golf tournament, F1 race) renders the champion as "Won" with NO stale
// percentages, and collapses the rest into a dimmed "Did not win" group. Mirrors
// the L2-53 futures-detail settled ruling.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { EventConceptCompetitor } from "@/lib/types";

jest.mock("@/lib/api", () => ({
  formatProbability: (p: number | null) => (p == null ? "—" : `${Math.round(p * 100)}%`),
}));

import EventLeaderboard from "../../components/event/EventLeaderboard";

describe("EventLeaderboard settled mode (L2-81)", () => {
  test("marks the authoritative champion 'Won' and shows NO stale percentages", () => {
    const field: EventConceptCompetitor[] = [
      // Stale midpoint: a non-winner is highest — the `won` flag must win.
      { name: "Coco Gauff", probability: 0.55 },
      { name: "Aryna Sabalenka", probability: 0.45, won: true },
      { name: "Iga Swiatek", probability: 0.1 },
    ];
    const html = renderToStaticMarkup(
      <EventLeaderboard competitors={field} label="Winner" settled />,
    );
    expect(html).toContain("Final result");
    expect(html).toContain("Aryna Sabalenka");
    expect(html).toContain("Won");
    // The honesty bar: a concluded field must not read as a live prediction.
    expect(html).not.toContain("%");
    expect(html).not.toContain("55"); // no stale probability numerals
    // Non-winners collapse into the dimmed group.
    expect(html).toContain("Did not win (2)");
  });

  test("falls back to a confident (>=0.9) leader when no won flag is set yet", () => {
    // Between Polymarket resolving prices and backfill_winners stamping is_winner,
    // a ~1.0 top competitor is still confidently the champion.
    const field: EventConceptCompetitor[] = [
      { name: "Carlos Alcaraz", probability: 0.97 },
      { name: "Jannik Sinner", probability: 0.03 },
    ];
    const html = renderToStaticMarkup(
      <EventLeaderboard competitors={field} label="Winner" settled />,
    );
    expect(html).toContain("Final result");
    expect(html).toContain("Carlos Alcaraz");
    expect(html).toContain("Won");
    expect(html).not.toContain("%");
  });

  test("never falsely crowns an ambiguous field (no won flag, no confident leader)", () => {
    const field: EventConceptCompetitor[] = [
      { name: "A", probability: 0.4 },
      { name: "B", probability: 0.35 },
    ];
    const html = renderToStaticMarkup(
      <EventLeaderboard competitors={field} label="Winner" settled />,
    );
    expect(html).not.toContain("Won");
    expect(html).toContain("Awaiting the final result.");
    expect(html).toContain("Field (2)");
    expect(html).not.toContain("%");
  });

  test("empty field renders nothing", () => {
    const html = renderToStaticMarkup(
      <EventLeaderboard competitors={[]} label="Winner" settled />,
    );
    expect(html).toBe("");
  });
});
