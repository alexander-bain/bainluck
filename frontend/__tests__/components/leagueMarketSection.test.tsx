// UX-P074 (#1860) — ruling 047 retrofits 2 and 3, at the render.
//
// `leagueCards.test.ts` pins the CLASSIFICATION (which market is a binary, which
// is a ladder, and what each one's answer is). This file pins that the section
// actually routes each shape to the shared presentation — the half a
// classification test cannot see, and the half a screenshot cannot check
// (one row versus two is countable; which side that row states is not).
//
// Fixtures are the verbatim production payload of `/api/leagues/baseball_mlb`,
// 2026-08-14.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { LeagueMarket, LeagueMarketOutcome } from "../../lib/api";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import LeagueMarketSection from "../../components/LeagueMarketSection";

const outcome = (
  id: number,
  name: string,
  probability: number | null,
): LeagueMarketOutcome => ({
  id,
  name,
  probability,
  opening_probability: null,
  rank: null,
  movement_24h: null,
  team_id: null,
});

const market = (over: Partial<LeagueMarket> = {}): LeagueMarket => ({
  id: 1,
  name: "A market",
  source: "polymarket",
  market_tier: 5,
  category: "game_prop",
  resolution_date: null,
  outcome_count: 2,
  top_outcomes: [],
  canonical_market_key: null,
  section: "props",
  ...over,
});

const NO_FIRST = market({
  id: 101,
  name: "Will the Athletics clinch a spot in the 2026 MLB Postseason?",
  top_outcomes: [outcome(1, "No", 0.9485), outcome(2, "Yes", 0.0515)],
});

const YES_FIRST = market({
  id: 102,
  name: "Will the Atlanta Braves clinch a spot in the 2026 MLB Postseason?",
  top_outcomes: [outcome(3, "Yes", 0.925), outcome(4, "No", 0.075)],
});

const DEBUT_LADDER = market({
  id: 103,
  name: "Walker Jenkins: Debut Date",
  source: "kalshi",
  category: "championship",
  outcome_count: 7,
  top_outcomes: [
    outcome(11, "Before Nov 1, 2027", 0.905),
    outcome(12, "Before May 1, 2027", 0.805),
    outcome(13, "Before Nov 1, 2026", 0.43),
    outcome(14, "Before Oct 1, 2026", 0.38),
    outcome(15, "Before Sep 1, 2026", 0.28),
    outcome(16, "Before Aug 15, 2026", 0.12),
    outcome(17, "Before Aug 1, 2026", 0.05),
  ],
});

function render(markets: LeagueMarket[]) {
  return renderToStaticMarkup(
    <LeagueMarketSection
      sectionKey="props"
      label="Props"
      markets={markets}
      sectionCount={3}
      tier="full"
    />,
  );
}

describe("retrofit 3 — one row per binary, and the row is YES", () => {
  test("a NO-first binary prints the YES number as its answer", () => {
    const html = render([NO_FIRST]);
    // 5% is the chance the Athletics clinch. 95% is the chance they do not, and
    // it was the first line of the old two-row card.
    expect(html).toContain("5%");
    expect(html).not.toContain("95%");
  });

  test("the complement is not printed anywhere — that IS the ruling", () => {
    const html = render([YES_FIRST]);
    expect(html).toContain("93%"); // 0.925 → the Yes side
    expect(html).not.toContain("8%"); // 0.075 → the No side, gone
  });

  test("the question is stated once per binary, not twice", () => {
    const html = render([NO_FIRST, YES_FIRST]);
    const rows = html.match(/href="\/futures\/10[12]"/g) || [];
    expect(rows).toHaveLength(2);
  });

  test("the yes/no block says what the column means, so a row can be one line", () => {
    expect(render([NO_FIRST])).toContain("chance of yes");
  });

  test("binaries do NOT render through the multi-row prop card", () => {
    const html = render([NO_FIRST]);
    expect(html).toContain('data-league-block="binaries"');
    // The old card's rank gutter ("#1", "#2") is the tell for a list card.
    expect(html).not.toContain("#1");
  });
});

describe("retrofit 2 — date ladders render as the shared ladder", () => {
  test("every rung renders — the old card stopped at six", () => {
    const html = render([DEBUT_LADDER]);
    for (const label of [
      "Nov 1, 2027",
      "May 1, 2027",
      "Nov 1, 2026",
      "Oct 1, 2026",
      "Sep 1, 2026",
      "Aug 15, 2026",
      "Aug 1, 2026",
    ]) {
      expect(html).toContain(label);
    }
  });

  test("rungs read in DATE order, earliest first — not probability order", () => {
    const html = render([DEBUT_LADDER]);
    expect(html.indexOf("Aug 1, 2026")).toBeLessThan(html.indexOf("Nov 1, 2027"));
    expect(html.indexOf("Sep 1, 2026")).toBeLessThan(html.indexOf("May 1, 2027"));
  });

  test("the direction is stated once for the ladder, not on every rung", () => {
    const html = render([DEBUT_LADDER]);
    expect(html).toContain("on or before");
    expect(html).not.toContain("Before Nov 1, 2027");
  });

  test("the ladder is a ladder block, not a card in the card grid", () => {
    expect(render([DEBUT_LADDER])).toContain('data-league-block="ladders"');
  });
});

describe("the shapes ruling 047 did NOT touch keep their card", () => {
  test("a multi-candidate field still renders as a list card", () => {
    const field = market({
      id: 104,
      name: "MLB: Team to win 100+ games",
      outcome_count: 30,
      top_outcomes: [
        outcome(21, "Los Angeles Dodgers", 0.695),
        outcome(22, "Milwaukee Brewers", 0.335),
        outcome(23, "Tampa Bay Rays", 0.165),
      ],
    });
    const html = render([field]);
    expect(html).toContain("Los Angeles Dodgers");
    expect(html).not.toContain('data-league-block="binaries"');
    expect(html).not.toContain('data-league-block="ladders"');
  });

  test("all three shapes in one section each get their own presentation", () => {
    const html = render([NO_FIRST, DEBUT_LADDER, YES_FIRST]);
    expect(html).toContain('data-league-block="binaries"');
    expect(html).toContain('data-league-block="ladders"');
  });

  test("an empty section still renders nothing", () => {
    expect(render([])).toBe("");
  });
});
