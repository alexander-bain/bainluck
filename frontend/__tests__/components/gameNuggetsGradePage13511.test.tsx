import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }),
  usePathname: () => "/grade/game-nuggets",
  useSearchParams: () => new URLSearchParams(),
}));

jest.mock("@/hooks", () => ({
  usePageTracking: jest.fn(),
  useScrollDepth: jest.fn(),
  useEngagementTime: jest.fn(),
}));

jest.mock("@/components/admin/AdminAuthProvider", () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) =>
    React.createElement(React.Fragment, null, children),
  useAdminAuth: () => ({
    secret: "test-secret",
    mode: "secret",
    email: null,
    clearSecret: jest.fn(),
  }),
}));

import GameNuggetsDeckView from "@/components/admin/GameNuggetsDeckView";
import GameNuggetsGradePage from "@/app/grade/game-nuggets/page";
import {
  formatDeckCountLine,
  formatReaderLeague,
  type GameNuggetsDeckResponse,
  type GameNuggetsGame,
} from "@/lib/ranking/gameNuggetsSession";

function baseDeck(overrides: Partial<GameNuggetsDeckResponse> = {}): GameNuggetsDeckResponse {
  return {
    slate_id: "game-nuggets-2026-11-24",
    surface: "game_nuggets",
    built_at: "2026-11-24T19:45:00+00:00",
    requested_limit: 20,
    games_count: 2,
    games: [
      {
        event_id: 15197757,
        away_team: "Boston Celtics",
        home_team: "Washington Wizards",
        sport: "basketball_nba",
        sport_name: "NBA",
        status: "scheduled",
        commence_time: "2026-11-25T00:00:00+00:00",
        nugget_count: 8,
        kind_count: 5,
        graded_count: 0,
      },
      {
        event_id: 15197900,
        away_team: "US Catanzaro",
        home_team: "Juve Stabia",
        sport: "soccer_italy_serie_b",
        sport_name: "Serie B",
        status: "live",
        commence_time: "2026-11-24T18:00:00+00:00",
        nugget_count: 6,
        kind_count: 3,
        graded_count: 0,
      },
    ],
    summary: {
      graded_count: 0,
      yes_count: 0,
      no_count: 0,
      repeat_rate: null,
      target_rate: 0.75,
      meets_target: false,
    },
    ...overrides,
  };
}

describe("#13511 /grade/game-nuggets deck fixes", () => {
  it("formats league names for readers rather than raw machine keys", () => {
    expect(formatReaderLeague("basketball_nba", "NBA")).toBe("NBA");
    expect(formatReaderLeague("basketball_wncaab", "basketball_wncaab")).toBe(
      "Women's College Basketball",
    );
    expect(formatReaderLeague("soccer_italy_serie_b", "Serie B")).toBe("Serie B");
    expect(formatReaderLeague("tennis_other", "tennis_other")).toBe("Other Tennis");
  });

  it("shows shorter-deck count and reader league names when fewer than 20 games qualify", () => {
    const deck = baseDeck({ games_count: 2, requested_limit: 20 });
    expect(formatDeckCountLine(deck)).toContain("2 of 20 games qualify");

    const game: GameNuggetsGame = {
      ...deck.games[0],
      first_eight_kinds: 5,
      everything_map: [
        { kind: "game_flow", label: "Game flow", count: 2, target_section: "totals-spreads" },
      ],
      nuggets: [
        {
          id: "n1",
          position: 1,
          kind: "game_flow",
          kind_label: "Game flow",
          subject: { name: "Boston Celtics at Washington Wizards" },
          claim: "The total is set at 229.5 points",
          probability: 0.52,
          percent: 52,
          change_points: null,
          change_since: null,
          pregame_percent: null,
          form: "duel_bar",
          rank_reason: "Tight main total",
        },
      ],
    };

    const html = renderToStaticMarkup(
      <GameNuggetsDeckView
        deck={deck}
        grader="Alex"
        gamesById={{ [game.event_id]: game }}
        selectedGameIdx={0}
        loadingEventId={null}
        notice={null}
        error={null}
        gameError={null}
        notesByKey={{}}
        savingKey={null}
        onSelectGame={jest.fn()}
        onChangeNote={jest.fn()}
        onSubmitGrade={jest.fn()}
      />,
    );

    expect(html).toContain("Shorter deck: 2 of 20 games qualify");
    expect(html).toContain("NBA");
    expect(html).toContain("Boston Celtics at Washington Wizards");
    expect(html).toContain("The total is set at 229.5 points");
    expect(html).not.toContain("basketball_nba");
    expect(html).not.toContain("soccer_italy_serie_b");
  });

  it("shows 'Nothing to grade for this game' when a dealt game loses its items instead of 0/0 counts", () => {
    const deck = baseDeck({ games_count: 1, games: [baseDeck().games[0]] });
    const emptyGame: GameNuggetsGame = {
      ...deck.games[0],
      first_eight_kinds: 0,
      everything_map: [
        { kind: "game_flow", label: "Game flow", count: 0, target_section: "totals-spreads" },
      ],
      nuggets: [],
    };

    const html = renderToStaticMarkup(
      <GameNuggetsDeckView
        deck={deck}
        grader="Alex"
        gamesById={{ [emptyGame.event_id]: emptyGame }}
        selectedGameIdx={0}
        loadingEventId={null}
        notice={null}
        error={null}
        gameError={null}
        notesByKey={{}}
        savingKey={null}
        onSelectGame={jest.fn()}
        onChangeNote={jest.fn()}
        onSubmitGrade={jest.fn()}
      />,
    );

    expect(html).toContain("Nothing to grade for this game");
    expect(html).not.toContain("kinds represented in top 0");
    expect(html).not.toContain("Game flow: 0");
  });

  it("mounts the page wrapper cleanly in SSR", () => {
    const html = renderToStaticMarkup(<GameNuggetsGradePage />);
    expect(html).toContain("Loading game-nuggets deck");
  });
});
