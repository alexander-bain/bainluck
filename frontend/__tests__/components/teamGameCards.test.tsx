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

// ---------------------------------------------------------------------------
// live/056 — the suspended match is VISIBLE on the team page, and it does not
// lie once it gets there.
//
// The two halves are one change on purpose. The backend fix (`teams.py`
// `recent_q` gains `suspended`) is the ship: before it, a rain-delayed match
// was on NEITHER of the team page's rails — not the recent one, which took only
// completed/closed, and not the upcoming one, which is floored at `now - 2h`
// and a match is suspended precisely because hours have passed. But the rail it
// now arrives on renders `RecentGameCard`, which graded any two scores as a
// W/L — so shipping visibility alone would have printed "L 1–2" over a match
// nobody said had ended: live/048's false Final, one component to the left.
// ---------------------------------------------------------------------------
describe("RecentGameCard — a suspended match (live/056)", () => {
  const suspended = (o: Partial<TeamGameBrief> = {}) =>
    brief({
      status: "suspended",
      is_home: true,
      home_score: 1,
      away_score: 2,
      commence_time: past(),
      ...o,
    });

  test("prints the app's one suspended sentence with the last score", () => {
    const html = renderToStaticMarkup(<RecentGameCard game={suspended()} />);
    expect(html).toContain("No result reported");
    expect(html).toContain("last score 1-2");
  });

  test("🔴 does NOT grade the partial score as a result", () => {
    const html = renderToStaticMarkup(<RecentGameCard game={suspended()} />);
    // The W/L char is rendered as a lone element; `>L<` is the shape the
    // settled arm emits and the shape this arm must never emit.
    expect(html).not.toContain(">L<");
    expect(html).not.toContain(">W<");
    expect(html).not.toContain(">T<");
    expect(html).not.toContain("1–2"); // the en-dash score block
  });

  test("🔴 does NOT fall through to the bare 'Final' branch", () => {
    // Scores absent is the OTHER way in: `teamResult` returns null for both, and
    // the pre-live/056 else-branch printed "Final" for anything that reached it.
    const html = renderToStaticMarkup(
      <RecentGameCard game={suspended({ home_score: null, away_score: null })} />,
    );
    expect(html).not.toContain("Final");
    expect(html).toContain("No result reported");
    expect(html).not.toContain("last score"); // half a score is no score
  });

  test("does not grade our call either — no 'we had them at', no upset", () => {
    const html = renderToStaticMarkup(
      <RecentGameCard game={suspended({ pregame_win_probability: 0.22 })} />,
    );
    expect(html).not.toContain("we had them at");
    expect(html).not.toContain("Upset");
  });

  test("CONTROL — the settled card is untouched by all of the above", () => {
    // A guard that suppressed the result everywhere would pass every assertion
    // above and delete the feature. Same fixture, settled status.
    const html = renderToStaticMarkup(
      <RecentGameCard
        game={suspended({ status: "completed", pregame_win_probability: 0.22 })}
      />,
    );
    expect(html).toContain(">L<");
    expect(html).toContain("1–2");
    expect(html).toContain("we had them at");
    expect(html).not.toContain("No result reported");
  });
});
