// #3868 / CERT-2215 — a settled ladder leg is a RESULT, never a percentage, and
// it never takes a live contender's slot.
//
// THE BLOCK THIS ANSWERS. #3868's first presentation fixed the DATA — the
// refresh rail learned to read Polymarket's child-level settlement — and stopped
// there. CERT-2215 found the ship did not reach the reader: the league payload
// dropped `is_winner`/`resolution_source`, a mixed ladder was not filtered, and
// `PropGroupCard` drew a settled winner as an ordinary `100%`. Worse, settled
// rows carry 1.0 and the card ranks by probability, so the eight already-through
// players would have filled all six visible slots of "TO REACH QUARTERFINALS"
// and displaced the five still fighting for one — the fix would have taken the
// card's only live question away.
//
// So this is a ROUTE-THROUGH-COMPONENT guard on the mixed case, which is the
// only case that can show all three failures at once: settled winner, settled
// loser, and an open child that has to survive both.
//
// The fixture is the real thing: US Open 2026 To Reach Quarterfinals (Men's
// Singles), market 59556819, read at the venue 2026-09-07 09:3xZ. Alcaraz and
// Shelton closed at ["1","0"]; Djokovic, Medvedev, Fritz and Auger-Aliassime at
// ["0","1"]; Zverev, Tien, Blockx, Cerundolo and Darderi genuinely still
// trading. Ordering matches what the backend `_live_first` emits, because that
// is what this component is handed.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { LeagueMarket, LeagueMarketOutcome } from "../../lib/api";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import PropGroupCard from "../../components/PropGroupCard";

const live = (
  id: number,
  name: string,
  probability: number,
): LeagueMarketOutcome => ({
  id,
  name,
  probability,
  opening_probability: null,
  rank: null,
  movement_24h: null,
  team_id: null,
  settled: false,
  is_winner: false,
});

const settled = (
  id: number,
  name: string,
  won: boolean,
): LeagueMarketOutcome => ({
  id,
  name,
  probability: won ? 1 : 0,
  opening_probability: null,
  rank: null,
  movement_24h: null,
  team_id: null,
  settled: true,
  is_winner: won,
});

/** `_live_first`'s order: open, then winners, then losers. */
const QF_MENS_OUTCOMES: LeagueMarketOutcome[] = [
  live(221651253, "Alexander Zverev", 0.885),
  live(221651260, "Learner Tien", 0.62),
  live(221651262, "Alexander Blockx", 0.6),
  live(221651261, "Francisco Cerundolo", 0.385),
  live(221651263, "Luciano Darderi", 0.135),
  settled(221651252, "Carlos Alcaraz", true),
  settled(221651256, "Ben Shelton", true),
  settled(221651254, "Novak Djokovic", false),
  settled(221651255, "Daniil Medvedev", false),
  settled(221651257, "Taylor Fritz", false),
];

const market = (outcomes: LeagueMarketOutcome[]): LeagueMarket => ({
  id: 59556819,
  name: "US Open 2026: To Reach Quarterfinals (Men's Singles)",
  source: "polymarket",
  market_tier: 5,
  category: "futures",
  resolution_date: "2026-09-09T23:59:00Z",
  outcome_count: 44,
  top_outcomes: outcomes,
  canonical_market_key: null,
  section: "more_markets",
});

const render = (outcomes: LeagueMarketOutcome[]) =>
  renderToStaticMarkup(<PropGroupCard market={market(outcomes)} />);

describe("#3868 — the mixed ladder: settled winner, settled loser, open child", () => {
  it("draws no percentage for a settled leg", () => {
    // The whole reader-facing defect in one assertion. Alcaraz settled at the
    // venue; "100%" is still the card quoting odds on an answered question.
    const html = render([settled(1, "Carlos Alcaraz", true)]);
    expect(html).not.toContain("100%");
    expect(html).toContain("Won");
  });

  it("draws a settled loser as Lost, not as 0%", () => {
    const html = render([settled(1, "Novak Djokovic", false)]);
    expect(html).not.toContain("0%");
    expect(html).toContain("Lost");
  });

  it("KEEPS THE OPEN CHILD VISIBLE when settled legs are present", () => {
    // The displacement half. Six slots; five live contenders and five settled
    // rows are handed over. Every live one must survive.
    const html = render(QF_MENS_OUTCOMES);
    for (const name of [
      "Alexander Zverev",
      "Learner Tien",
      "Alexander Blockx",
      "Francisco Cerundolo",
      "Luciano Darderi",
    ]) {
      expect(html).toContain(name);
    }
  });

  it("still prices the open children", () => {
    const html = render(QF_MENS_OUTCOMES);
    expect(html).toContain("89%"); // Zverev 0.885
    expect(html).toContain("62%"); // Tien
  });

  it("shows no settled leg as a percentage anywhere on the mixed card", () => {
    const html = render(QF_MENS_OUTCOMES);
    // 1.0 and 0.0 are what settled rows carry. Neither may reach the reader as
    // a number on this card.
    expect(html).not.toContain("100%");
    expect(html).toContain("Won");
  });

  it("does not rank a settled row among the live contenders", () => {
    // "#6 Carlos Alcaraz — Won" would read as sixth place in a race he has
    // already left.
    const html = render(QF_MENS_OUTCOMES);
    expect(html).toContain("#5");
    expect(html).not.toContain("#6");
  });

  it("draws no probability bar or 24h move on a settled row", () => {
    // Both are readings of a live book. The threshold branch is the one with
    // the bar, so it is exercised with threshold-shaped names.
    const html = renderToStaticMarkup(
      <PropGroupCard
        market={market([
          { ...settled(1, "Over 2.5", true), movement_24h: 0.31 },
          live(2, "Under 2.5", 0.4),
        ])}
      />,
    );
    expect(html).toContain("Won");
    expect(html).not.toContain("+31.0");
    // One bar, for the one live row.
    expect(html.match(/bg-purple-500\/50/g) ?? []).toHaveLength(1);
  });
});

describe("#3868 — settlement is a GRADE, never a certainty", () => {
  it("does not call a live 0.9995 book settled", () => {
    // Measured: the Alcaraz leg read 0.9995 for a day BEFORE it closed. A card
    // that inferred settlement from the number would have stamped a result on a
    // market that was still trading.
    const html = render([
      { ...live(1, "Carlos Alcaraz", 0.9995), settled: false },
    ]);
    expect(html).not.toContain("Won");
    // `>99%`, not `100%`: the formatter already refuses to round a live book up
    // to certainty. Exactly 1.0 — what a settled row carries — DOES print
    // "100%", which is what makes the assertions above real ones.
    expect(html).toContain("99%"); // `&gt;99%` once the markup escapes it
  });

  it("renders an old payload exactly as before (split deploy)", () => {
    // Vercel ships the frontend before Heroku, so for a window this component
    // is handed payloads with neither field. Absent must read as "not settled",
    // never as "lost" (#3508's rule).
    const legacy = {
      id: 1,
      name: "Carlos Alcaraz",
      probability: 0.775,
      opening_probability: null,
      rank: null,
      movement_24h: null,
      team_id: null,
    } as LeagueMarketOutcome;
    const html = render([legacy]);
    expect(html).toContain("78%");
    expect(html).not.toContain("Won");
    expect(html).not.toContain("Lost");
  });
});
