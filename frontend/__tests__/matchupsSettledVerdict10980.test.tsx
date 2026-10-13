/**
 * #10980 — a finished game's Matchups card states the venue's result, not `Last quotes 100% / 0%`.
 *
 * WHAT THE READER SAW. `/events/14780558` (BUF 37 – LAR 34, MNF, completed), 04:45Z 2026-10-13:
 *
 *   Head-to-Head Passing Yards: Allen vs Stafford · Last quotes
 *   Matthew Stafford  ████████  100%
 *   Josh Allen        ▏           0%
 *
 * while `/game-markets` served every leg `is_winner` + `resolution_source: "api_settlement"`.
 * MATCHUPS below is that served `matchups[]` verbatim (ids trimmed).
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import MatchupOutcomes from "@/components/event/MatchupOutcomes";
import type { GameMarketsResponse } from "@/lib/api";

type Matchup = NonNullable<GameMarketsResponse["matchups"]>[number];

const leg = (name: string, probability: number, is_winner: boolean) => ({
  name,
  probability,
  is_winner,
  resolution_source: "api_settlement",
});

const MATCHUPS: Matchup[] = [
  {
    market_name: "Head-to-Head Passing Yards: Allen vs Stafford",
    type: "h2h",
    source: "kalshi",
    outcomes: [leg("Matthew Stafford", 1.0, true), leg("Josh Allen", 0.0, false)],
  },
  {
    market_name: "Head-to-Head Receiving Yards: Nacua vs Adams",
    type: "h2h",
    source: "kalshi",
    outcomes: [leg("Puka Nacua", 1.0, true), leg("Davante Adams", 0.0, false)],
  },
  {
    market_name: "Head-to-Head Rushing Yards: Williams vs Cook",
    type: "h2h",
    source: "kalshi",
    outcomes: [leg("James Cook III", 1.0, true), leg("Kyren Williams", 0.0, false)],
  },
];

const render = (m: Matchup, finished: boolean) =>
  renderToStaticMarkup(<MatchupOutcomes matchup={m} finished={finished} />);

const verdicts = (html: string) =>
  [...html.matchAll(/data-verdict="(won|lost)"/g)].map((x) => x[1]);

describe("#10980 Matchups on a finished game", () => {
  it.each(MATCHUPS.map((m) => [m.market_name, m] as const))(
    "%s states Won / Lost and no last quote",
    (_name, m) => {
      const html = render(m, true);
      expect(verdicts(html)).toEqual(["won", "lost"]);
      expect(html).toContain(">Won<");
      expect(html).toContain(">Lost<");
      expect(html).not.toContain("Last quotes");
      expect(html).not.toContain("100%");
      expect(html).not.toContain(">0%<");
    },
  );

  it("names the winner on the Won row", () => {
    const html = render(MATCHUPS[0], true);
    expect(html).toMatch(/Matthew Stafford<\/span><span[^>]*>Won</);
    expect(html).toMatch(/Josh Allen<\/span><span[^>]*>Lost</);
  });
});

describe("#10980 rows the verdict rule withholds keep today's last quote", () => {
  const base = MATCHUPS[0];
  const withLegs = (patch: Partial<Matchup["outcomes"][number]>): Matchup => ({
    ...base,
    outcomes: base.outcomes.map((o) => ({ ...o, ...patch })),
  });

  it("a served null resolution_source (never graded) prints the price", () => {
    const html = render(withLegs({ resolution_source: null, is_winner: false }), true);
    expect(verdicts(html)).toEqual([]);
    expect(html).toContain("Last quotes");
    expect(html).toContain("100%");
  });

  it("an older payload without the keys prints the price", () => {
    const m: Matchup = {
      ...base,
      outcomes: base.outcomes.map(({ name, probability }) => ({ name, probability })),
    };
    const html = render(m, true);
    expect(verdicts(html)).toEqual([]);
    expect(html).toContain("Last quotes");
  });

  it("a retracted grade (ungradeable_result) prints the price", () => {
    const html = render(withLegs({ resolution_source: "ungradeable_result" }), true);
    expect(verdicts(html)).toEqual([]);
    expect(html).toContain("Last quotes");
  });

  it("before the final, a defaulted false never prints Lost", () => {
    const m = withLegs({ is_winner: false });
    const html = render(m, false);
    expect(html).not.toContain(">Lost<");
    expect(html).not.toContain("Last quotes");
    expect(html).toContain("100%");
  });

  it("one graded leg and one ungraded leg keep the Last quotes label for the priced row", () => {
    const m: Matchup = {
      ...base,
      outcomes: [base.outcomes[0], { ...base.outcomes[1], resolution_source: null }],
    };
    const html = render(m, true);
    expect(verdicts(html)).toEqual(["won"]);
    expect(html).toContain("Last quotes");
  });
});
