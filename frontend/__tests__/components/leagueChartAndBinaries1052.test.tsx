/**
 * UX-1052 items 7 and 8 — the MLB league page's chart labels and its yes/no board.
 *
 * Alex, shopping /sport/baseball/mlb at 1:00pm PT on 2026-09-03:
 *
 *   item 7: "MLB page odds-movement chart: 'AL/NL Champ' tab shows a team
 *            called 'D'."
 *   item 8: "Yes/No section needs to be formatted WAY better; very
 *            high-potential — and there is a SECOND Yes/No section at the
 *            bottom of the page. Remove the duplicate; design the one that
 *            stays (question, one bar, the number, the mover, the venue
 *            badges)."
 *
 * ITEM 7, MEASURED. `/api/futures/275` (Kalshi "Pro Baseball Champion") stores
 * its outcomes as city-plus-initial — "Los Angeles D", "New York Y", "Chicago
 * C" (gotcha #16). The chart's team list shortens a 3+ word name to its last
 * word, so "Los Angeles D" printed as **D**. The abbreviated NAMES are an
 * identity defect and are handed to lane1; what this component owns is not
 * turning one into a label that names nothing.
 *
 * ITEM 8, MEASURED. `/api/leagues/baseball_mlb` on the same day: 55 binaries in
 * `props`, 9 in `more_markets`, 1 in `awards`. `LeagueMarketSection`
 * partitioned its own markets, so that was three "Yes / no" blocks, one of them
 * a header over a single row.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

import LeagueBinaryBoard from "@/components/LeagueBinaryBoard";
import LeagueMarketSection from "@/components/LeagueMarketSection";
import { partitionLeagueMarkets, sortBinariesByAnswer } from "@/lib/leagueCards";
import { findBannedCopy } from "@/lib/copyBans";
import type { LeagueMarket } from "@/lib/api";

// ─────────────────────────────────────────────────────────────────────────────
// Item 7 — the chart's team labels
// ─────────────────────────────────────────────────────────────────────────────

// `shortName` is module-private to EvolutionLeaderboard; the behaviour is
// asserted through the component's own rendering below.
import { EvolutionLeaderboard } from "@/components/EvolutionLeaderboard";

/** The real merged outcome set the World Series tab charts, names verbatim. */
const CHART_OUTCOMES = [
  { outcome_id: 1, name: "Los Angeles Dodgers", history: [{ timestamp: "2026-09-01T00:00:00Z", probability: 0.353 }] },
  { outcome_id: 2, name: "Los Angeles Angels", history: [{ timestamp: "2026-09-01T00:00:00Z", probability: 0.153 }] },
  { outcome_id: 3, name: "Los Angeles D", history: [{ timestamp: "2026-09-01T00:00:00Z", probability: 0.147 }] },
  { outcome_id: 4, name: "Milwaukee", history: [{ timestamp: "2026-09-01T00:00:00Z", probability: 0.12 }] },
  { outcome_id: 5, name: "New York Y", history: [{ timestamp: "2026-09-01T00:00:00Z", probability: 0.112 }] },
  { outcome_id: 6, name: "Oklahoma City Thunder", history: [{ timestamp: "2026-09-01T00:00:00Z", probability: 0.05 }] },
] as never[];

function renderChartList() {
  return renderToStaticMarkup(
    <EvolutionLeaderboard
      historyData={CHART_OUTCOMES}
      selectedOutcomeIds={new Set([1, 2, 3, 4, 5, 6])}
      onToggleOutcome={() => {}}
      onAddOutcome={() => {}}
      entityLabel="Teams"
    />,
  );
}

describe("UX-1052 item 7 — no team is called 'D'", () => {
  it("keeps the full name when the last word is a bare initial", () => {
    const html = renderChartList();
    expect(html).toContain("Los Angeles D");
    // The single letter must not appear as a standalone label.
    expect(html).not.toMatch(/>\s*D\s*</);
  });

  it("does the same for the other Kalshi abbreviations on this market", () => {
    const html = renderChartList();
    expect(html).toContain("New York Y");
    expect(html).not.toMatch(/>\s*Y\s*</);
  });

  it("STILL shortens a real three-word team name — the rule is not disabled", () => {
    const html = renderChartList();
    expect(html).toContain("Thunder");
    expect(html).not.toContain("Oklahoma City Thunder");
  });

  it("shortens the two genuinely distinguishable Los Angeles clubs", () => {
    const html = renderChartList();
    expect(html).toContain("Dodgers");
    expect(html).toContain("Angels");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Item 8 — one yes/no board
// ─────────────────────────────────────────────────────────────────────────────

function binaryMarket(
  id: number,
  name: string,
  yesProb: number | null,
  section: string,
  source = "kalshi",
  movement: number | null = null,
): LeagueMarket {
  return {
    id,
    name,
    source,
    market_tier: 2,
    category: "prop",
    resolution_date: null,
    outcome_count: 2,
    canonical_market_key: null,
    section,
    top_outcomes: [
      { id: id * 10, name: "Yes", probability: yesProb, opening_probability: null, rank: 1, movement_24h: movement, team_id: null },
      { id: id * 10 + 1, name: "No", probability: yesProb == null ? null : 1 - yesProb, opening_probability: null, rank: 2, movement_24h: null, team_id: null },
    ],
  };
}

function listMarket(id: number, name: string, section: string): LeagueMarket {
  return {
    id,
    name,
    source: "polymarket",
    market_tier: 2,
    category: "award",
    resolution_date: null,
    outcome_count: 3,
    canonical_market_key: null,
    section,
    top_outcomes: [
      { id: id * 10, name: "Shohei Ohtani", probability: 0.5, opening_probability: null, rank: 1, movement_24h: null, team_id: null },
      { id: id * 10 + 1, name: "Aaron Judge", probability: 0.3, opening_probability: null, rank: 2, movement_24h: null, team_id: null },
      { id: id * 10 + 2, name: "Juan Soto", probability: 0.2, opening_probability: null, rank: 3, movement_24h: null, team_id: null },
    ],
  };
}

describe("UX-1052 item 8 — the duplicate yes/no section is gone", () => {
  it("a section that hoists its binaries draws no yes/no block", () => {
    const html = renderToStaticMarkup(
      <LeagueMarketSection
        sectionKey="props"
        label="Props"
        markets={[binaryMarket(1, "Team to win 100+ games", 0.4, "props"), listMarket(2, "NL MVP", "props")]}
        sectionCount={3}
        tier="standard"
        hoistBinaries
      />,
    );
    expect(html).not.toContain("Yes / no");
    // …but its list card is still there.
    expect(html).toContain("Shohei Ohtani");
  });

  it("a section left with NOTHING but hoisted binaries renders nothing at all", () => {
    // The `awards` section on the MLB page held exactly one binary. Hoisting it
    // must not leave a bare header over an empty grid.
    const html = renderToStaticMarkup(
      <LeagueMarketSection
        sectionKey="awards"
        label="Awards"
        markets={[binaryMarket(3, "Ohtani: Cy Young and MVP", 0.01, "awards")]}
        sectionCount={3}
        tier="standard"
        hoistBinaries
      />,
    );
    expect(html).toBe("");
  });

  it("without the flag the section behaves exactly as before (no silent change)", () => {
    const html = renderToStaticMarkup(
      <LeagueMarketSection
        sectionKey="props"
        label="Props"
        markets={[binaryMarket(1, "Team to win 100+ games", 0.4, "props")]}
        sectionCount={3}
        tier="standard"
      />,
    );
    expect(html).toContain("Yes / no");
  });

  it("the page-level partition collects binaries from every section, once", () => {
    const sections: [string, LeagueMarket[]][] = [
      ["awards", [binaryMarket(3, "Ohtani: Cy Young and MVP", 0.01, "awards"), listMarket(9, "NL MVP", "awards")]],
      ["props", [binaryMarket(1, "Team to win 100+ games", 0.4, "props")]],
      ["more_markets", [binaryMarket(2, "40+ Home Run Season", 0.7, "more_markets")]],
    ];
    const all = sections.flatMap(([, m]) => partitionLeagueMarkets(m).binaries);
    expect(all).toHaveLength(3);
    const html = renderToStaticMarkup(<LeagueBinaryBoard binaries={all} />);
    expect(html.split("Yes / no").length - 1).toBe(1);
  });
});

describe("UX-1052 item 8 — the board that stays", () => {
  const BINARIES = [
    binaryMarket(1, "MLB: Team to win 100+ games", 0.4, "props", "kalshi", 0.05),
    binaryMarket(2, "Pro Baseball: 40+ Home Run Season", 0.72, "more_markets", "polymarket"),
    binaryMarket(3, "Shohei Ohtani: Cy Young and MVP Winner", null, "awards", "kalshi"),
  ].map((m) => partitionLeagueMarkets([m]).binaries[0]);

  const html = renderToStaticMarkup(<LeagueBinaryBoard binaries={BINARIES} />);

  it("prints the question", () => {
    // …with the league prefix and season stripped, as `cleanMarketName` does.
    expect(html).toContain("Team to win 100+ games");
  });

  it("prints ONE bar per row, and it is not hidden on a phone", () => {
    // The old row's track was `hidden sm:block`, so at 390px the block was a
    // column of naked percentages — the thing Alex called badly formatted.
    expect(html).not.toContain("hidden sm:block");
    expect(html).toContain("rounded-full bg-surface-elevated");
  });

  it("prints the number", () => {
    expect(html).toContain("72%");
    expect(html).toContain("40%");
  });

  it("prints the mover, and only where something moved", () => {
    expect(html).toContain("+5.0");
    // The other two rows carry no movement and get no chip.
    expect(html.split("+5.0").length - 1).toBe(1);
  });

  it("prints the venue badge — which is what makes a MERGED board legible", () => {
    expect(html).toContain("Kalshi");
    expect(html).toContain("Polymarket");
  });

  it("draws no bar at all for an unpriced question, and says so in the product's words", () => {
    // CERT-859. The first draft of this row said "No price yet" — banned by
    // ruling 138, because the word is PROBABILITY. `shippedCopyBans` caught it
    // in the BUILT bundle rather than here, and the reason is the failure
    // UX-P220 named: a green capture asserting the banned sentence VERBATIM
    // says "keep it exactly as it is" while a ruling says we owe a fix.
    //
    // So the replacement is not merely spelled out again. It is run back
    // through the same rules the bundle scan runs, which is the only version
    // of this assertion that cannot pin a banned string a second time.
    const label = "No probability yet";
    expect(findBannedCopy(label)).toEqual([]);
    expect(html).toContain(label);
    expect(html).toContain("—");
  });

  it("reads most-likely-first, with the unpriced question last", () => {
    expect(html.indexOf("40+ Home Run Season")).toBeLessThan(html.indexOf("Team to win 100+ games"));
    expect(html.indexOf("Team to win 100+ games")).toBeLessThan(html.indexOf("Cy Young and MVP"));
  });

  it("caps the wall and offers the rest — 65 rows in one block is not a design", () => {
    const many = Array.from({ length: 30 }, (_, i) =>
      partitionLeagueMarkets([binaryMarket(100 + i, `Question ${i}`, 0.5 - i * 0.01, "props")]).binaries[0],
    );
    const wall = renderToStaticMarkup(<LeagueBinaryBoard binaries={many} />);
    expect(wall).toContain("Show 18 more questions");
    expect(wall).toContain("Question 0");
    expect(wall).not.toContain("Question 25");
    // The count in the header states the WHOLE board, not the visible slice.
    expect(wall).toContain("(30)");
  });

  it("renders nothing when there are no binaries", () => {
    expect(renderToStaticMarkup(<LeagueBinaryBoard binaries={[]} />)).toBe("");
  });

  it("sorts unpriced last rather than dropping the question", () => {
    const ordered = sortBinariesByAnswer(BINARIES);
    expect(ordered).toHaveLength(3);
    expect(ordered[ordered.length - 1].answer.probability).toBeNull();
  });
});
