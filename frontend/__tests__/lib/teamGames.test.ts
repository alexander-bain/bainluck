// L2-158 Item 2: state-honesty logic for team-page game cards.
import {
  isGameLive,
  isGameSettled,
  assignGameNumbers,
  teamResult,
} from "../../lib/teamGames";
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

describe("isGameLive — chip honesty both directions", () => {
  const NOW = new Date("2026-07-22T20:00:00Z").getTime();

  test("LIVE only once the game has actually started", () => {
    const started = brief({
      status: "live",
      commence_time: "2026-07-22T19:00:00Z", // 1h ago
    });
    expect(isGameLive(started, NOW)).toBe(true);
  });

  test("premature 'live' status before commence_time is NOT live", () => {
    // Backend flipped status='live' ~4h before first pitch (gotcha #14). The
    // chip must derive from commence+status BOTH, not status alone.
    const early = brief({
      status: "live",
      commence_time: "2026-07-23T00:00:00Z", // 4h in the future
    });
    expect(isGameLive(early, NOW)).toBe(false);
  });

  test("scheduled games are never live", () => {
    expect(
      isGameLive(brief({ status: "scheduled", commence_time: "2026-07-22T19:00:00Z" }), NOW),
    ).toBe(false);
  });

  test("live status with no commence_time is not live (can't prove it started)", () => {
    expect(isGameLive(brief({ status: "live", commence_time: null }), NOW)).toBe(false);
  });
});

describe("isGameSettled — completed AND closed", () => {
  test("completed is settled", () => {
    expect(isGameSettled(brief({ status: "completed" }))).toBe(true);
  });
  test("closed is settled (r242: closed games must not vanish)", () => {
    expect(isGameSettled(brief({ status: "closed" }))).toBe(true);
  });
  test("scheduled/live are not settled", () => {
    expect(isGameSettled(brief({ status: "scheduled" }))).toBe(false);
    expect(isGameSettled(brief({ status: "live" }))).toBe(false);
  });
});

describe("assignGameNumbers — doubleheaders", () => {
  test("two games vs the same opponent on the same day get G1/G2 in time order", () => {
    // Local (no Z) datetimes so the calendar-day grouping is timezone-stable.
    const g2 = brief({ id: 2, opponent: "New York Yankees", commence_time: "2026-07-22T19:00:00" });
    const g1 = brief({ id: 1, opponent: "New York Yankees", commence_time: "2026-07-22T13:00:00" });
    const nums = assignGameNumbers([g2, g1]);
    expect(nums[1]).toBe(1);
    expect(nums[2]).toBe(2);
  });

  test("a solo game gets no number", () => {
    const solo = brief({ id: 9, opponent: "New York Yankees", commence_time: "2026-07-22T13:00:00" });
    expect(assignGameNumbers([solo])[9]).toBeUndefined();
  });

  test("same opponent on different days are not a doubleheader", () => {
    const a = brief({ id: 1, opponent: "Yankees", commence_time: "2026-07-22T13:00:00" });
    const b = brief({ id: 2, opponent: "Yankees", commence_time: "2026-07-23T13:00:00" });
    const nums = assignGameNumbers([a, b]);
    expect(nums[1]).toBeUndefined();
    expect(nums[2]).toBeUndefined();
  });
});

describe("teamResult — team-relative W/L", () => {
  test("home win", () => {
    expect(
      teamResult(brief({ is_home: true, home_score: 6, away_score: 1 })),
    ).toEqual({ char: "W", teamScore: 6, oppScore: 1 });
  });
  test("away win (is_home false flips perspective)", () => {
    expect(
      teamResult(brief({ is_home: false, home_score: 1, away_score: 6 })),
    ).toEqual({ char: "W", teamScore: 6, oppScore: 1 });
  });
  test("loss and tie", () => {
    expect(teamResult(brief({ is_home: true, home_score: 1, away_score: 3 }))?.char).toBe("L");
    expect(teamResult(brief({ is_home: true, home_score: 2, away_score: 2 }))?.char).toBe("T");
  });
  test("null scores yield null", () => {
    expect(teamResult(brief({ home_score: null, away_score: null }))).toBeNull();
  });
});
