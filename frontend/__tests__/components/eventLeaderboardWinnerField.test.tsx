// L2-132: EventLeaderboard LIVE/upcoming winner-field mode — the World Cup
// contender/tail chrome. A 48-nation field must not render as a wall of zeros:
// contenders show green bars, the 0% tail collapses behind a "Show all N"
// expander. OUT is the adapter's `eliminated` flag ONLY — a pre-kickoff 0%
// longshot reads "0%" (no OUT chip), never falsely "eliminated".

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { EventConceptCompetitor } from "@/lib/types";

jest.mock("@/lib/api", () => ({
  formatProbability: (p: number | null) => (p == null ? "—" : `${Math.round(p * 100)}%`),
}));

import EventLeaderboard from "../../components/event/EventLeaderboard";

describe("EventLeaderboard winner-field contender/tail chrome (L2-132)", () => {
  test("contenders show green bars; the 0% longshot tail collapses into 'Show all N' with NO OUT chip", () => {
    // Mirrors the real pre-tournament WC envelope: 3 priced, the rest at ~0%.
    const field: EventConceptCompetitor[] = [
      { name: "Spain", probability: 0.44 },
      { name: "Argentina", probability: 0.32 },
      { name: "England", probability: 0.24 },
      { name: "Ghana", probability: 0 }, // longshot, NOT eliminated
      { name: "Egypt", probability: 0.001 }, // longshot, NOT eliminated
    ];
    const html = renderToStaticMarkup(
      <EventLeaderboard competitors={field} label="Winner" />,
    );
    // Contenders visible with a green (accent-brand) bar.
    expect(html).toContain("Spain");
    expect(html).toContain("bg-accent-brand");
    // The 0% tail collapses behind the field expander (2 hidden of 5 total).
    expect(html).toContain("Show all 5");
    expect(html).toContain("Ghana");
    expect(html).toContain("Egypt");
    // HONESTY BAR: a pre-kickoff longshot is NOT eliminated — no OUT chip anywhere.
    expect(html).not.toContain(">Out<");
  });

  test("adapter `eliminated` flag marks a row OUT even at a stale non-zero price", () => {
    const field: EventConceptCompetitor[] = [
      { name: "Spain", probability: 0.3 },
      // Knocked-out nation the adapter graded eliminated before the price zeroed.
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
      { name: "Portugal", probability: 0.03 }, // 3% — still a contender
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
