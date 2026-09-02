// UX-P074 (#1860) — ruling 047 against the LIVE SPECIMEN.
//
// The other two files test the retrofit with fixtures I chose. This one renders
// the ACTUAL production payload of `GET /api/leagues/baseball_mlb`, captured
// 2026-08-14 07:5x PT and committed verbatim as
// `__tests__/fixtures/leagueMlbProduction.json` — 36 markets, 8 upcoming games,
// 8 recent results — and counts what a reader would see.
//
// Why it exists: this queue's acceptance is a claim about a PAGE ("no bespoke
// card variant remains on the three ruled shapes"), and a page-level claim
// checked against hand-written fixtures is a claim about my imagination. The
// browser rail can only photograph production, which is the OLD page until this
// merges and deploys — so the pre-merge form of that proof is this: real
// payload in, counted render out.
//
// It is a specimen, not a spec. If MLB's market mix changes, the counts below
// change with it and the fixture should be re-captured rather than the
// assertions loosened.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { LeagueFuturesResponse, LeagueMarket } from "../../lib/api";
import { binaryAnswer, dateLadder } from "../../lib/leagueCards";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

// The module, not the `@/hooks` barrel — see LAT-P209 and EventCard.test.ts.
jest.mock("../../hooks/useAnalytics", () => ({
  useAnalytics: () => ({ trackEventCardClick: jest.fn() }),
}));

import LeagueMarketSection from "../../components/LeagueMarketSection";
import LeagueGameRail from "../../components/LeagueGameRail";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const payload = require("../fixtures/leagueMlbProduction.json") as LeagueFuturesResponse;

const props = (payload.sections.props || []) as LeagueMarket[];
const awards = (payload.sections.awards || []) as LeagueMarket[];

describe("the live MLB specimen — what the three shapes count", () => {
  test("the specimen still holds the shapes this queue was aimed at", () => {
    // If this fails, the fixture drifted from the queue's premise and the
    // numbers below stop meaning what their names say.
    expect(props).toHaveLength(28);
    expect(awards).toHaveLength(8);
    expect(payload.upcoming_games).toHaveLength(8);
    expect(payload.recent_results).toHaveLength(8);
  });

  test("21 of the 28 props are yes/no binaries, and 15 of them lead with No", () => {
    const binaries = props.filter((m) => binaryAnswer(m) !== null);
    expect(binaries).toHaveLength(21);

    const noFirst = binaries.filter(
      (m) => (m.top_outcomes[0]?.name || "").toLowerCase() === "no",
    );
    expect(noFirst).toHaveLength(15);
  });

  test("6 of the props are date ladders", () => {
    expect(props.filter((m) => dateLadder(m) !== null)).toHaveLength(6);
  });
});

describe("the live specimen, rendered — ruling 047's acceptance", () => {
  const html = renderToStaticMarkup(
    <LeagueMarketSection
      sectionKey="props"
      label="Props"
      markets={props}
      sectionCount={3}
      tier={payload.tier}
    />,
  );

  test("every binary occupies ONE row — 21 rows, not 42", () => {
    const rows = html.match(/href="\/futures\/\d+"/g) || [];
    const ladderCount = props.filter((m) => dateLadder(m) !== null).length;
    const cardCount = props.length - 21 - ladderCount;
    // 21 binary rows + one link per remaining card. Ladders are not links.
    expect(rows).toHaveLength(21 + cardCount);
  });

  test("no binary's complement is printed beside it", () => {
    // The clinching markets are the sharpest case: 94.9% is the chance the
    // Athletics MISS the postseason, and it was the first line of the old card.
    expect(html).toContain("Will the Athletics clinch a spot in the 2026 MLB Postseason?");
    expect(html).not.toContain("95%");
  });

  test("all six ladders render, and the biggest renders all eight rungs", () => {
    expect(html).toContain('data-league-block="ladders"');
    expect(html).toContain("Seth Hernandez: Debut Date");
    for (const rung of [
      "Aug 1, 2027",
      "Nov 1, 2027",
      "May 1, 2028",
      "Aug 1, 2028",
      "Nov 1, 2028",
      "May 1, 2029",
      "Aug 1, 2029",
      "Nov 1, 2029",
    ]) {
      expect(html).toContain(rung);
    }
  });

  test("the earliest rung of a ladder precedes the latest — in the render, not just the data", () => {
    expect(html.indexOf("Aug 1, 2027")).toBeLessThan(html.indexOf("Nov 1, 2029"));
  });

  test("the one true field market keeps its list card", () => {
    expect(html).toContain("Team to win 100+ games");
    expect(html).toContain("Los Angeles Dodgers");
  });
});

describe("the live specimen's games — the shared event card", () => {
  test("all 16 games render, both rails, through the shared card", () => {
    const upcoming = renderToStaticMarkup(
      <LeagueGameRail title="Upcoming Games" games={payload.upcoming_games!} />,
    );
    const results = renderToStaticMarkup(
      <LeagueGameRail title="Recent Results" games={payload.recent_results!} settled />,
    );

    expect((upcoming.match(/href="\/events\/\d+"/g) || [])).toHaveLength(8);
    expect((results.match(/href="\/events\/\d+"/g) || [])).toHaveLength(8);

    // Both sides of the blend on a live game: 10% / 90% for the Twins/Phillies
    // fixture the payload happens to carry (home_win_probability 0.0961).
    expect(upcoming).toContain("Philadelphia Phillies");
    expect(upcoming).toContain("10%");
    expect(upcoming).toContain("90%");

    // And the settled rail leads with results, not forecasts.
    expect(results).toContain("Final");
    expect(results).not.toContain("NaN");
    expect(upcoming).not.toContain("NaN");
  });
});
