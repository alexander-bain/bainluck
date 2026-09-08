// #3964 — a section heading must not outlive its cards.
//
// WHAT A READER SAW, `/sport/boxing/boxing` at 390px, 2026-09-08 13:33Z and
// again at 13:38Z (two separate loads, so not a mid-load frame):
//
//     📋  UPCOMING MATCHES   (10)
//
//                                     <- nothing. At all.
//
//     🎯  YES / NO   (2)
//
// The payload agrees. `sections.matches` carries twelve rows and TEN of them
// have `top_outcomes: []`; every one of the three cards this section can route
// to opens by returning null on an empty field, so ten cards drew nothing while
// the header — counting what the section was HANDED — promised ten matches.
//
// It is the CERT-859 rule one door further along ("the header counts what this
// section DRAWS, not what it was handed"), and it has to be fixed in the parent
// because a component that renders nothing cannot tell its parent so.
//
// Fixtures are the verbatim production payload of `/api/leagues/boxing_boxing`,
// 2026-09-08 13:38Z, names as served.

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

const outcome = (id: number, name: string, probability: number | null): LeagueMarketOutcome => ({
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
  outcome_count: 0,
  top_outcomes: [],
  canonical_market_key: null,
  section: "matches",
  ...over,
});

/** The ten rows that drew nothing, verbatim. */
const EMPTY_BOXING_MATCHES: LeagueMarket[] = [
  "Zuffa Boxing: Vanhouter vs. Akpejiori (Heavyweight, Prelims)",
  "Zuffa Boxing: Garcia vs. Benn (Welterweight, Main)",
  "Zuffa Boxing: Panin vs. Linger (Catchweight, Prelims)",
  "Zuffa Boxing: Ramirez vs. Rocha (Welterweight, Prelims)",
  "Zuffa Boxing: Molina vs. Rubio (Catchweight, Prelims)",
  "Zuffa Boxing 11: Cutler vs. Greene (Middleweight, Main)",
  "Zuffa Boxing: Gonzalez vs. Salomon (Catchweight, Prelims)",
  "Zuffa Boxing: Magsayo vs. Cortes (Lightweight, Main)",
  "Zuffa Boxing 11: Fisher vs. Pirotton (Heavyweight, Main)",
  "Zuffa Boxing 11: Richards vs. Kalajdzic (Light Heavyweight, Main)",
].map((name, i) => market({ id: 900 + i, name }));

const A_REAL_CARD = market({
  id: 950,
  name: "WBC Bantamweight Title on January 1, 2027",
  section: "futures",
  top_outcomes: [
    outcome(1, "Michael Angeletti", 0.37),
    outcome(2, "Tenshin Nasukawa", 0.21),
    outcome(3, "Andrew Cain", 0.2),
  ],
});

// `tier="standard"` is what `/sport/boxing/boxing` serves and it is what makes
// the COUNT CHIP visible (`earnsCountChip`) — the reader's "(10)" promise lives
// there, so a fixture on a chip-less tier would test half the defect.
const render = (markets: LeagueMarket[], sectionKey = "matches", sectionCount = 3) =>
  renderToStaticMarkup(
    <LeagueMarketSection
      sectionKey={sectionKey}
      label="Upcoming Matches"
      markets={markets}
      sectionCount={sectionCount}
      tier="standard"
    />,
  );

describe("#3964 — the heading counts what the section draws", () => {
  it("draws nothing at all when every card it was handed is empty", () => {
    // Asserted on the OUTPUT rather than on a heading query, because the whole
    // defect is a heading with no siblings: an empty string is the only render
    // that cannot be a header over nothing.
    expect(render(EMPTY_BOXING_MATCHES)).toBe("");
  });

  it("specifically does not print the label the reader was left staring at", () => {
    const html = render(EMPTY_BOXING_MATCHES);
    expect(html).not.toContain("Upcoming Matches");
    expect(html).not.toContain("(10)");
  });

  it("counts only the drawable cards when a section holds both", () => {
    const alsoReal = market({
      id: 951,
      name: "Another title",
      top_outcomes: [outcome(9, "Someone", 0.5)],
    });
    const html = render([...EMPTY_BOXING_MATCHES, A_REAL_CARD, alsoReal]);

    expect(html).toContain("Michael Angeletti");
    expect(html).toContain("Someone");
    // Twelve markets in, two cards drawn. The chip must say two.
    expect(html).toContain("(2)");
    expect(html).not.toContain("(12)");
  });

  it("drops the header entirely when only ONE card survives the filter", () => {
    // Ruling 027 already governs this ("a one-card section earns no chrome");
    // the point here is that the filter feeds it the DRAWN count, so eleven
    // markets that render one card get the one-card treatment and not a
    // header claiming eleven.
    const html = render([...EMPTY_BOXING_MATCHES, A_REAL_CARD]);
    expect(html).toContain("Michael Angeletti");
    expect(html).not.toContain("Upcoming Matches");
  });

  it("leaves a fully populated section byte-identical", () => {
    const populated = [
      A_REAL_CARD,
      market({ id: 951, name: "Another title", top_outcomes: [outcome(9, "Someone", 0.5)] }),
    ];
    const html = render(populated);
    expect(html).toContain("(2)");
    expect(html).toContain("Someone");
  });

  it("holds a series card to TWO outcomes, because SeriesCard needs two sides", () => {
    // The threshold mirrors each card's own contract. A shared `> 0` would keep
    // a bare header over a one-outcome series market — the same defect, a
    // different count — and `SeriesCard` returns null below two.
    const oneSided = market({
      id: 960,
      name: "A series with one side",
      section: "series",
      top_outcomes: [outcome(1, "Only team", 1.0)],
    });
    expect(render([oneSided], "series")).toBe("");
  });
});
