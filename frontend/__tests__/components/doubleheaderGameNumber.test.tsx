// #8515 — a real doubleheader reads as ONE GAME SHOWN TWICE.
//
// Specimen (production, 2026-09-24 7:25 PM PDT, /sport/baseball/mlb at 390px):
// two cards, "Boston Red Sox / Chicago Cubs", "Tomorrow 10:05 AM" and
// "Tomorrow 3:05 PM", nothing else telling them apart. The data is CORRECT:
// MLB 824703 gameNumber 1 / 824706 gameNumber 2, ESPN 401817104 / 401817074,
// our rows 15316415 / 15316330. So this is a label, not a de-duplication.
//
// The rule, both directions (the issue's verification line):
//   · a pair the PROVIDER vouches for as a doubleheader renders two cards that
//     a reader can tell apart ("Game 1" / "Game 2");
//   · a same-day pair WITHOUT the provider field renders unchanged — no mark.
//     Same teams + same day is also exactly what a duplicate row looks like,
//     and a label must not dress a duplicate as a feature (#2866).
//
// Rendered through the league rail from the SERVED envelope shape, so the
// mapper (`leagueGameToEvent`) is in the path: a mapper that drops the fields
// fails here even though the card itself would be right.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { LeagueGameBrief } from "../../lib/api";
import { leagueGameToEvent } from "../../lib/leagueCards";
import { providerGameNumber } from "../../lib/teamGames";

// Forwards `aria-label`: the shell puts the card's accessible name on the Link,
// and a mock that drops it would make the announcement assertions vacuous.
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({
    href,
    children,
    "aria-label": ariaLabel,
  }: {
    href: string;
    children: React.ReactNode;
    "aria-label"?: string;
  }) => (
    <a href={href} aria-label={ariaLabel}>
      {children}
    </a>
  ),
}));

jest.mock("../../hooks", () => ({
  useAnalytics: () => ({ trackEventCardClick: jest.fn() }),
}));

import LeagueGameRail from "../../components/LeagueGameRail";

const game = (over: Partial<LeagueGameBrief> = {}): LeagueGameBrief =>
  ({
    id: 15316415,
    home_team: "Boston Red Sox",
    away_team: "Chicago Cubs",
    commence_time: "2030-09-25T17:05:00+00:00",
    status: "scheduled",
    home_score: null,
    away_score: null,
    home_win_probability: 0.53,
    sport: "baseball_mlb",
    ...over,
  }) as LeagueGameBrief;

const game1 = (over: Partial<LeagueGameBrief> = {}) => game(over);
const game2 = (over: Partial<LeagueGameBrief> = {}) =>
  game({ id: 15316330, commence_time: "2030-09-25T22:05:00+00:00", ...over });

const marks = (html: string): string[] =>
  Array.from(html.matchAll(/data-game-number="(\d+)"[^>]*>([^<]*)</g)).map(
    (m) => `${m[1]}:${m[2]}`,
  );

const render = (games: LeagueGameBrief[]) =>
  renderToStaticMarkup(<LeagueGameRail title="Upcoming Games" games={games} />);

describe("#8515 — a provider-vouched doubleheader reads as two games", () => {
  test("the 9/25 Cubs@Red Sox pair prints Game 1 and Game 2, one per card", () => {
    const html = render([
      game1({ doubleheader: true, game_number: 1 }),
      game2({ doubleheader: true, game_number: 2 }),
    ]);
    expect(marks(html)).toEqual(["1:Game 1", "2:Game 2"]);
  });

  test("the mark is announced — the two shells' labels are otherwise identical", () => {
    const html = render([
      game1({ doubleheader: true, game_number: 1 }),
      game2({ doubleheader: true, game_number: 2 }),
    ]);
    expect(html).toContain('aria-label="Chicago Cubs at Boston Red Sox - Game 1"');
    expect(html).toContain('aria-label="Chicago Cubs at Boston Red Sox - Game 2"');
  });

  test("the mapper carries both served fields onto the card's event", () => {
    const ev = leagueGameToEvent(game2({ doubleheader: true, game_number: 2 }));
    expect(ev.doubleheader).toBe(true);
    expect(ev.game_number).toBe(2);
  });
});

describe("#8515 / #2866 — nothing is inferred from same teams + same day", () => {
  test("the SAME pair without the provider field renders no mark at all", () => {
    const html = render([game1(), game2()]);
    expect(html).not.toContain("event-card-game-number");
    expect(html).not.toContain("Game 1");
    expect(html).toContain('aria-label="Chicago Cubs at Boston Red Sox"');
  });

  test.each([
    ["doubleheader true, no number", { doubleheader: true }],
    ["doubleheader true, number null", { doubleheader: true, game_number: null }],
    ["doubleheader true, number 0", { doubleheader: true, game_number: 0 }],
    ["doubleheader true, number 1.5", { doubleheader: true, game_number: 1.5 }],
    ["doubleheader true, number NaN", { doubleheader: true, game_number: NaN }],
    ["doubleheader false, number 1", { doubleheader: false, game_number: 1 }],
    ["doubleheader null, number 1", { doubleheader: null, game_number: 1 }],
    ["number 1, no flag", { game_number: 1 }],
  ])("%s → no mark", (_label, over) => {
    const html = render([game1(over as Partial<LeagueGameBrief>)]);
    expect(html).not.toContain("event-card-game-number");
    expect(providerGameNumber(over as Parameters<typeof providerGameNumber>[0])).toBeNull();
  });
});
