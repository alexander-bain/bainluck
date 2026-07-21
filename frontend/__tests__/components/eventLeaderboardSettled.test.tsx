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

  // L2-89 Item 3 (render-side guard): the DATA layer can hand us a corrupt
  // settled field with TWO `won: true` competitors (the Women's Wimbledon
  // "two winners" mis-grade — data fix owned by the resolver lane). The render
  // must degrade gracefully: crown exactly ONE champion (the higher-probability
  // `won` per `settledChampion`'s `.find` over `fieldOrder`), and sink the second
  // "winner" into the "Did not win" group. Never two crowns.
  test("crowns exactly ONE champion when the data hands it two winners", () => {
    const field: EventConceptCompetitor[] = [
      { name: "Iga Swiatek", probability: 0.55, won: true },
      { name: "Amanda Anisimova", probability: 0.45, won: true },
    ];
    const html = renderToStaticMarkup(
      <EventLeaderboard competitors={field} label="Winner" settled />,
    );
    // Exactly one crown + one "Won" chip — the negative case that guards against
    // a future refactor switching settledChampion/render to .filter()+.map().
    expect(html.split("🏆").length - 1).toBe(1);
    expect(html.split("Won").length - 1).toBe(1);
    // The higher-probability winner is crowned; the second sinks into the group.
    expect(html).toContain("Iga Swiatek");
    expect(html).toContain("Did not win (1)");
    expect(html).not.toContain("%");
  });

  // L2-147 Item 1: the settled field must be fully visible — top ~10 rendered by
  // default, the FULL field behind "Show all N" (never the old slice(0,20) that
  // dropped the tail, and never fully collapsed). Alex: "I still can't see detail
  // beyond the 5 golfers listed."
  test("shows the top ~10 by default and the FULL field behind 'Show all N'", () => {
    const field: EventConceptCompetitor[] = [
      { name: "Scottie Scheffler", probability: 0.98, won: true },
      ...Array.from({ length: 24 }, (_, i) => ({
        name: `Contender ${String(i + 1).padStart(2, "0")}`,
        probability: 0.5 - i * 0.01,
      })),
    ];
    const html = renderToStaticMarkup(
      <EventLeaderboard competitors={field} label="Winner" settled domain="golf" />,
    );
    // Champion crowned once.
    expect(html).toContain("Scottie Scheffler");
    expect(html).toContain("Won");
    // 25 total → "Show all 25" reveals the full field; the tail (e.g. #20) is in
    // the DOM, not dropped by a hard cut.
    expect(html).toContain("Show all 25");
    expect(html).toContain("Contender 20");
    // The head is visible by default (top of the "did not win" list).
    expect(html).toContain("Contender 01");
    // Settled honesty: no stale percentages anywhere.
    expect(html).not.toContain("%");
  });

  test("golf champion hero carries a headshot avatar (initials fallback on SSR)", () => {
    const field: EventConceptCompetitor[] = [
      { name: "Rory McIlroy", probability: 0.99, won: true },
      { name: "Jon Rahm", probability: 0.4 },
    ];
    const html = renderToStaticMarkup(
      <EventLeaderboard competitors={field} label="Winner" settled domain="golf" />,
    );
    // EntityImage renders the initials chip on SSR (no network) — "RM" for the
    // champion proves the avatar slot mounted for the golf person-field.
    expect(html).toContain("RM");
    expect(html).toContain("Won");
    expect(html).not.toContain("%");
  });

  test("empty field renders nothing", () => {
    const html = renderToStaticMarkup(
      <EventLeaderboard competitors={[]} label="Winner" settled />,
    );
    expect(html).toBe("");
  });
});
