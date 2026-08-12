// #1776 — the league games rail.
//
// Two things are pinned here, and the rail had NO test coverage at all before
// this file, which is part of why both survived:
//
// 1. The cap declaration follows the rail. One component serves BOTH the
//    upcoming and the settled rail, and it printed "Showing the N most recent"
//    over FUTURE fixtures.
// 2. A null probability renders NOTHING — no track, no 0%-width fill, no "0%".
//    That behaviour is correct (register E2: null must never be drawn as a
//    claim) and it is exactly what made #1776 invisible from the render side:
//    the rail was silently correct about a number the backend never sent. The
//    guard is here so a future "helpful" fallback to 0% or 50% cannot land.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { LeagueGameBrief } from "../../lib/api";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
import LeagueGameRail from "../../components/LeagueGameRail";

const game = (over: Partial<LeagueGameBrief> = {}): LeagueGameBrief =>
  ({
    id: 1,
    home_team: "Miami Marlins",
    away_team: "Pittsburgh Pirates",
    commence_time: "2026-08-12T22:40:00+00:00",
    status: "scheduled",
    home_score: null,
    away_score: null,
    home_win_probability: 0.642,
    ...over,
  }) as LeagueGameBrief;

describe("LeagueGameRail — the cap declaration follows the rail", () => {
  test("the UPCOMING rail does not describe future fixtures as 'most recent'", () => {
    const html = renderToStaticMarkup(
      <LeagueGameRail title="Upcoming Games" games={[game()]} hasMore />,
    );
    expect(html).toContain("more exist");
    expect(html).not.toContain("most recent");
  });

  test("the SETTLED rail still says 'most recent'", () => {
    const html = renderToStaticMarkup(
      <LeagueGameRail title="Recent Results" games={[game()]} hasMore settled />,
    );
    expect(html).toContain("most recent");
  });

  test("no cap, no declaration", () => {
    const html = renderToStaticMarkup(
      <LeagueGameRail title="Upcoming Games" games={[game()]} />,
    );
    expect(html).not.toContain("more exist");
  });
});

describe("LeagueGameRail — the probability", () => {
  test("a priced game renders its number", () => {
    const html = renderToStaticMarkup(
      <LeagueGameRail title="Upcoming Games" games={[game()]} />,
    );
    expect(html).toContain("64%");
  });

  test("an unpriced game renders NO number and NO bar", () => {
    // The other direction. A fabricated 0%/50% here would be worse than the
    // blank rail #1776 fixed — it would be a claim we never measured.
    const html = renderToStaticMarkup(
      <LeagueGameRail
        title="Upcoming Games"
        games={[game({ home_win_probability: null })]}
      />,
    );
    expect(html).not.toContain("0%");
    expect(html).not.toContain("50%");
    expect(html).toContain("Miami Marlins"); // the fixture itself still shows
  });

  test("an empty rail renders nothing at all", () => {
    expect(
      renderToStaticMarkup(<LeagueGameRail title="Upcoming Games" games={[]} />),
    ).toBe("");
  });
});
