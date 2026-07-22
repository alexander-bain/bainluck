// L2-158 Items 1+2: SSR guards for the team-page game cards —
//  - upcoming card renders the win-prob split (probability-first),
//  - LIVE-chip honesty in BOTH directions (started → LIVE; future commence → Starts),
//  - settled 'closed'-status game renders in Recent Results with a W/L result.
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { UpcomingGameCard, RecentGameCard } from "../../components/TeamGameCards";
import type { TeamGameBrief } from "../../lib/api";

function brief(overrides: Partial<TeamGameBrief>): TeamGameBrief {
  return {
    id: 1,
    home_team: "Boston Celtics",
    away_team: "Los Angeles Lakers",
    home_score: null,
    away_score: null,
    status: "scheduled",
    commence_time: null,
    sport_key: "basketball_nba",
    is_home: true,
    opponent: "Los Angeles Lakers",
    win_probability: null,
    ...overrides,
  };
}

const future = () => new Date(Date.now() + 4 * 3600_000).toISOString();
const past = () => new Date(Date.now() - 1 * 3600_000).toISOString();

describe("UpcomingGameCard — probability-first + chip honesty", () => {
  test("scheduled game leads with the win-prob split", () => {
    const html = renderToStaticMarkup(
      <UpcomingGameCard
        game={brief({ status: "scheduled", commence_time: future(), win_probability: 0.62 })}
        teamName="Boston Celtics"
        teamColor="#007A33"
      />,
    );
    expect(html).toContain("62%");
    expect(html).toContain("win prob");
    expect(html).toContain("38%"); // opponent share
    expect(html).not.toContain("LIVE");
  });

  test("premature 'live' status before commence_time renders Starts, NOT LIVE", () => {
    const html = renderToStaticMarkup(
      <UpcomingGameCard
        game={brief({ status: "live", commence_time: future(), win_probability: 0.55 })}
        teamName="Boston Celtics"
        teamColor={null}
      />,
    );
    expect(html).toContain("Starts");
    expect(html).not.toContain(">LIVE<");
  });

  test("genuinely started 'live' game shows LIVE", () => {
    const html = renderToStaticMarkup(
      <UpcomingGameCard
        game={brief({ status: "live", commence_time: past(), win_probability: 0.55, home_score: 3, away_score: 2 })}
        teamName="Boston Celtics"
        teamColor={null}
      />,
    );
    expect(html).toContain("LIVE");
    expect(html).not.toContain("Starts");
  });

  test("doubleheader game renders its G-number chip", () => {
    const html = renderToStaticMarkup(
      <UpcomingGameCard
        game={brief({ status: "scheduled", commence_time: future(), win_probability: 0.5 })}
        teamName="Boston Celtics"
        teamColor={null}
        gameNo={2}
      />,
    );
    expect(html).toContain("G2");
  });
});

describe("RecentGameCard — result-first, closed status renders", () => {
  test("'closed'-status settled game renders with W and score", () => {
    const html = renderToStaticMarkup(
      <RecentGameCard
        game={brief({
          status: "closed",
          is_home: true,
          home_score: 6,
          away_score: 1,
          completed_at: new Date(Date.now() - 86_400_000).toISOString(),
        })}
      />,
    );
    expect(html).toContain(">W<");
    expect(html).toContain("6–1");
  });

  test("no misleading pre-game % is shown when the backend omits it", () => {
    const html = renderToStaticMarkup(
      <RecentGameCard
        game={brief({ status: "completed", is_home: true, home_score: 6, away_score: 1 })}
      />,
    );
    expect(html).not.toContain("we had them at");
    expect(html).not.toContain("Upset");
  });

  test("upset flag fires when the team won as a <35% underdog (pre-game field present)", () => {
    const html = renderToStaticMarkup(
      <RecentGameCard
        game={brief({
          status: "completed",
          is_home: true,
          home_score: 6,
          away_score: 1,
          pregame_win_probability: 0.22,
        })}
      />,
    );
    expect(html).toContain("Upset");
    expect(html).toContain("78%"); // beat 78% odds
  });
});
