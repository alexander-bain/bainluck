// The league games rail — #1776 (the number) and UX-P074 / #1860 (the card).
//
// Two things were pinned here by #1776, and both survive the ruling-047
// retrofit unchanged, which is the point of keeping them in this file rather
// than rewriting it:
//
// 1. The cap declaration follows the rail. One component serves BOTH the
//    upcoming and the settled rail, and it printed "Showing the N most recent"
//    over FUTURE fixtures.
// 2. A null probability renders NO fabricated number. That behaviour is correct
//    (register E2: null must never be drawn as a claim) and it is exactly what
//    made #1776 invisible from the render side.
//
// UX-P074 adds the third: the rail draws the SHARED event card — the same one
// /sports/[key], search and My Stuff render — and not a league-local row. The
// assertions below are deliberately about what the SHARED card produces (both
// sides of the blend, the settled score block) rather than about class names,
// so they fail if the rail forks again and pass if the shared card evolves.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { LeagueGameBrief } from "../../lib/api";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

jest.mock("../../hooks", () => ({
  useAnalytics: () => ({ trackEventCardClick: jest.fn() }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
import LeagueGameRail from "../../components/LeagueGameRail";
import { leagueGameToEvent } from "../../lib/leagueCards";

// ux/1053 — the rail takes `Event[]` now, so the fixture goes through the
// league page's OWN adapter rather than being hand-written in the shape the
// card wants. That keeps these assertions about the league path end to end: a
// regression in `leagueGameToEvent` reddens them, which a hand-built Event
// would have hidden.
const event = (over: Partial<LeagueGameBrief> = {}) => leagueGameToEvent(game(over));

const game = (over: Partial<LeagueGameBrief> = {}): LeagueGameBrief =>
  ({
    id: 1,
    home_team: "Miami Marlins",
    away_team: "Pittsburgh Pirates",
    commence_time: "2030-08-12T22:40:00+00:00",
    status: "scheduled",
    home_score: null,
    away_score: null,
    home_win_probability: 0.642,
    sport: "baseball_mlb",
    ...over,
  }) as LeagueGameBrief;

describe("LeagueGameRail — the cap declaration follows the rail", () => {
  test("the UPCOMING rail does not describe future fixtures as 'most recent'", () => {
    const html = renderToStaticMarkup(
      <LeagueGameRail title="Upcoming Games" events={[event()]} hasMore />,
    );
    expect(html).toContain("more exist");
    expect(html).not.toContain("most recent");
  });

  test("the SETTLED rail still says 'most recent'", () => {
    const html = renderToStaticMarkup(
      <LeagueGameRail title="Recent Results" events={[event()]} hasMore settled />,
    );
    expect(html).toContain("most recent");
  });

  test("no cap, no declaration", () => {
    const html = renderToStaticMarkup(
      <LeagueGameRail title="Upcoming Games" events={[event()]} />,
    );
    expect(html).not.toContain("more exist");
  });
});

describe("LeagueGameRail — the probability", () => {
  test("a priced game renders its number", () => {
    const html = renderToStaticMarkup(
      <LeagueGameRail title="Upcoming Games" events={[event()]} />,
    );
    expect(html).toContain("64%");
  });

  test("BOTH sides of the blend render — the league-local row only ever showed home", () => {
    const html = renderToStaticMarkup(
      <LeagueGameRail title="Upcoming Games" events={[event()]} />,
    );
    expect(html).toContain("64%");
    expect(html).toContain("36%");
  });

  test("an unpriced game renders NO number and NO bar", () => {
    // The other direction. A fabricated 0%/50% here would be worse than the
    // blank rail #1776 fixed — it would be a claim we never measured. The shared
    // card's own null treatment is an em-dash-style placeholder, not a digit.
    const html = renderToStaticMarkup(
      <LeagueGameRail
        title="Upcoming Games"
        events={[event({ home_win_probability: null })]}
      />,
    );
    expect(html).not.toContain("0%");
    expect(html).not.toContain("50%");
    expect(html).not.toContain("%</span>");
    expect(html).toContain("Miami Marlins"); // the fixture itself still shows
  });

  test("an empty rail renders nothing at all", () => {
    expect(
      renderToStaticMarkup(<LeagueGameRail title="Upcoming Games" events={[]} />),
    ).toBe("");
  });
});

describe("LeagueGameRail — ruling 047: the card is the shared one", () => {
  test("a settled game shows the score, not a forecast", () => {
    const html = renderToStaticMarkup(
      <LeagueGameRail
        title="Recent Results"
        settled
        events={[
          event({
            status: "completed",
            home_score: 3,
            away_score: 7,
            commence_time: "2026-08-12T22:40:00+00:00",
            home_win_probability: 0.21,
          }),
        ]}
      />,
    );
    expect(html).toContain("Final");
    expect(html).toContain(">3<");
    expect(html).toContain(">7<");
    // Settled means settled: no live-style probability chip on a finished game.
    expect(html).not.toContain("21%");
  });

  test("no rail-local projection is invented — 'Proj NaN' cannot come back", () => {
    // The league envelope carries a blend and no projected score. The shared
    // card's guard was `!== null`, which an ABSENT key passes, so the first
    // render of this rail printed "Proj NaN-NaN".
    const html = renderToStaticMarkup(
      <LeagueGameRail title="Upcoming Games" events={[event()]} />,
    );
    expect(html).not.toContain("NaN");
    expect(html).not.toContain("Proj");
  });

  test("a game with no commence_time renders no date rather than 'Invalid Date'", () => {
    const html = renderToStaticMarkup(
      <LeagueGameRail title="Upcoming Games" events={[event({ commence_time: null })]} />,
    );
    expect(html).not.toContain("Invalid Date");
    expect(html).toContain("Miami Marlins");
  });
});
