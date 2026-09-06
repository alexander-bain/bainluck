/**
 * ux/1096 / #3028 — WHEN A LEAGUE PAGE WIDENS ITS WINDOW, AND WHEN IT MUST NOT.
 *
 * ═══ WHAT THE DAMAGING REGRESSION IS ═══
 *
 * 🔴 It is NOT "a dormant league stays empty". That is the bug as filed, it is
 * visible on the page, and it fixes itself the moment anyone looks. The
 * damaging regression is the mirror: an IN-SEASON league widening to 90 days,
 * because `americanfootball_nfl` measured 17 games at `days=14` and **120** at
 * `days=60` — this Sunday's slate would be buried under the rest of the season
 * on a page that works today, and nobody would file it as a bug because the
 * page would still be full of football.
 *
 * So every arm below that proves widening has a mirror that proves NOT
 * widening, and the in-season mirrors are the ones written first.
 *
 * ═══ THE ANCHOR ═══
 *
 * `now` is passed explicitly to every call (gotcha #44: offset from a fixed
 * anchor, never branch on the wall clock). Every fixture's `commence_time` is
 * built as an offset FROM that anchor, so no assertion here can rot with the
 * calendar — which matters more than usual for this module, since the defect
 * it fixes was itself the calendar moving under a hardcoded horizon.
 */

import type { Event } from "@/lib/types";
import {
  LEAGUE_NEAR_TERM_DAYS,
  LEAGUE_OFFSEASON_HORIZON_DAYS,
  LEAGUE_WINDOW_DAYS,
  needsWiderHorizon,
} from "@/lib/sports/leagueHorizon";

const NOW = new Date("2026-09-06T12:00:00Z").getTime();
const DAY = 24 * 60 * 60 * 1000;

/** No defaults on `status` or the offset — an arm whose job is to place a row
 *  on one side of a boundary cannot have either defaulted out from under it. */
function row(status: string, offsetMs: number | null, id = 1): Event {
  return {
    id,
    sport: "basketball_nba",
    home_team: "Detroit Pistons",
    away_team: "Boston Celtics",
    commence_time:
      offsetMs === null ? (null as unknown as string) : new Date(NOW + offsetMs).toISOString(),
    status,
  } as unknown as Event;
}

describe("#3028 — the in-season mirror: a league that is playing never widens", () => {
  test("a game today keeps the fixed window", () => {
    expect(needsWiderHorizon([row("scheduled", 6 * 60 * 60 * 1000)], NOW)).toBe(false);
  });

  test("a live game keeps the fixed window even with nothing else scheduled soon", () => {
    // The NFL shape that must never widen: something being played now, and the
    // next fixture beyond the near term.
    const events = [row("live", -30 * 60 * 1000, 1), row("scheduled", 30 * DAY, 2)];
    expect(needsWiderHorizon(events, NOW)).toBe(false);
  });

  test("a suspended game counts as being played, because the shared ladder says so", () => {
    // `eventSectionKey` files `suspended` under live. If this module wrote its
    // own status chain instead, a rain-delayed league would read as dormant and
    // widen mid-season — the exact fall-through `lib/eventState.ts` exists to
    // refuse.
    expect(needsWiderHorizon([row("suspended", -3 * 60 * 60 * 1000)], NOW)).toBe(false);
  });

  test("one near-term game is enough, however many far ones sit behind it", () => {
    const events = [
      row("scheduled", 40 * DAY, 1),
      row("scheduled", 41 * DAY, 2),
      row("scheduled", 2 * DAY, 3),
      row("scheduled", 60 * DAY, 4),
    ];
    expect(needsWiderHorizon(events, NOW)).toBe(false);
  });
});

describe("#3028 — the dormant league widens", () => {
  test("the NBA shape as filed: the window came back empty", () => {
    expect(needsWiderHorizon([], NOW)).toBe(true);
  });

  test("the NHL shape as re-measured: one fixture, at the far edge of the window", () => {
    // 🔴 THE ARM THE OBVIOUS FIX FAILS. A trigger written as "the payload was
    // empty" returns false here and calls the NHL page fixed while it shows
    // 1 of the 32 games we hold.
    expect(needsWiderHorizon([row("scheduled", 13 * DAY)], NOW)).toBe(true);
  });

  test("yesterday's results are not a reason to believe the window", () => {
    // `/api/events` includes completed events from yesterday, so a league that
    // has just finished its season comes back non-empty and entirely finished.
    const events = [
      row("completed", -20 * 60 * 60 * 1000, 1),
      row("closed", -30 * 60 * 60 * 1000, 2),
    ];
    expect(needsWiderHorizon(events, NOW)).toBe(true);
  });
});

describe("#3028 — the boundary, from both sides of one anchor", () => {
  test("a game exactly at the near-term bound is near term", () => {
    expect(
      needsWiderHorizon([row("scheduled", LEAGUE_NEAR_TERM_DAYS * DAY)], NOW),
    ).toBe(false);
  });

  test("a game one millisecond past it is not", () => {
    expect(
      needsWiderHorizon([row("scheduled", LEAGUE_NEAR_TERM_DAYS * DAY + 1)], NOW),
    ).toBe(true);
  });
});

describe("#3028 — an undated row cannot vote either way", () => {
  test("alone, it does not hold the window open", () => {
    // `new Date(null).getTime()` is NaN and `NaN <= cutoff` is false, so a row
    // with no usable time must not be able to argue the league is playing.
    expect(needsWiderHorizon([row("scheduled", null)], NOW)).toBe(true);
  });

  test("and it does not veto a real near-term game beside it", () => {
    const events = [row("scheduled", null, 1), row("scheduled", 3 * DAY, 2)];
    expect(needsWiderHorizon(events, NOW)).toBe(false);
  });
});

describe("#3028 — the constants say what was measured", () => {
  test("the near-term bound is inside the fixed window it is judging", () => {
    // A near-term bound at or beyond the window could never be crossed by a
    // row the window returned, so the NHL arm above would be unreachable and
    // the trigger would silently collapse back to "the payload was empty".
    expect(LEAGUE_NEAR_TERM_DAYS).toBeLessThan(LEAGUE_WINDOW_DAYS);
  });

  test("the widened horizon reaches past the furthest schedule measured", () => {
    // NBA's last held game on 2026-09-06 was 2026-11-28 — 83 days out, which
    // is why 60 was measured short and 90 is the constant.
    expect(LEAGUE_OFFSEASON_HORIZON_DAYS).toBeGreaterThan(83);
  });
});
