/**
 * #8709 — A SCORE CHANGE IS NOT THE FINAL WHISTLE.
 *
 * Production, 390px, 2026-09-25: `/events/15314642` (Girona FC 2–0 Albacete,
 * FINAL). Win Probability ran from kickoff (11:29 AM PDT) to the final (~1:25
 * PM). The Score Differential chart under it, same "Since Start" setting,
 * stopped at 12:19 PM, just after the second goal. The whole second half was
 * missing, so the two charts disagreed about how long the match lasted.
 *
 * Why: for a finished game `computeSharedChartDomain` ends the window at the
 * last game-end observation. On this game the only one is `score_history`,
 * which holds one row per score CHANGE: its last row (19:17:24Z, 2–0) is when
 * the last goal went in. The in-play sportsbook tail runs to 20:18Z, 61 minutes
 * past the 10-minute extension cap, so the window stopped at 19:17Z. The Score
 * Differential chart prunes to the window; Win Probability does not.
 *
 * The fixture is the served payload, banked from production and trimmed.
 *
 * Arm 2 is the ceiling: `completed_at` is the one column that says the game is
 * over (#7315), and a sportsbook write after it may not stretch the window.
 * Arms 3 and 4 are the controls: the change is scoped to "the latest evidence
 * is a score change", so dense ESPN evidence and a payload with no
 * `completed_at` keep the old window.
 */

import { computeSharedChartDomain } from "@/lib/eventKeyStats";
import specimen from "../fixtures/scoreDiffRunsToTheFinalWhistle8709.json";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Payload = any;
const base = (): Payload => JSON.parse(JSON.stringify(specimen));
const SPORT = "soccer_spain_segunda_division";
const ms = (iso: string) => new Date(iso).getTime();

const LAST_GOAL = "2026-09-25T19:17:24.431218+00:00";
const LAST_IN_PLAY_QUOTE = "2026-09-25T20:18:00+00:00";
const COMPLETED_AT = "2026-09-25T20:25:21.049696+00:00";

const endOf = (payload: Payload, status = "completed") => {
  const d = computeSharedChartDomain(payload, "live", status, payload.commence_time, SPORT);
  expect(d).not.toBeNull();
  return ms(d!.end);
};

describe("#8709 a finished game's chart window runs to the final whistle, not the last goal", () => {
  it("the fixture is the specimen: the last score change is an hour before completed_at, with in-play quotes between", () => {
    const p = base();
    expect(p.completed_at).toBe(COMPLETED_AT);
    expect(p.score_history[p.score_history.length - 1].timestamp).toBe(LAST_GOAL);
    expect(p.espn_history).toHaveLength(0);
    const quoted = p.history.filter(
      (pt: Payload) => pt.projected_home_score !== null && ms(pt.timestamp) > ms(LAST_GOAL),
    );
    expect(quoted[quoted.length - 1].timestamp).toBe(LAST_IN_PLAY_QUOTE);
  });

  it("arm 1: the window reaches the last in-play sportsbook point and stops at or before completed_at", () => {
    const end = endOf(base());
    expect(end).toBeGreaterThanOrEqual(ms(LAST_IN_PLAY_QUOTE));
    expect(end).toBeLessThanOrEqual(ms(COMPLETED_AT));
    // The served series ends with a settlement point at 20:25:00Z, before completed_at.
    expect(end).toBe(ms("2026-09-25T20:25:00Z"));
  });

  it("arm 2: a sportsbook write after completed_at does not stretch the window", () => {
    const p = base();
    p.history.push({
      timestamp: "2026-09-25T21:10:00+00:00",
      home_probability: 1,
      away_probability: 0,
      projected_home_score: 2.0,
      projected_away_score: 0.0,
    });
    expect(endOf(p)).toBe(ms("2026-09-25T20:25:00Z"));
  });

  it("arm 3 (control): when ESPN's dense series is the latest evidence, the old 10-minute rule stands", () => {
    const p = base();
    p.espn_history = [
      { timestamp: "2026-09-25T19:30:00+00:00", home_score: 2, away_score: 0 },
    ];
    expect(endOf(p)).toBe(ms("2026-09-25T19:30:00Z"));
  });

  it("arm 4 (control): with no completed_at the end stays at the last score change", () => {
    const p = base();
    p.completed_at = null;
    // The window rounds its end up to the next whole minute.
    const end = endOf(p);
    expect(end).toBeGreaterThanOrEqual(ms(LAST_GOAL));
    expect(end).toBeLessThanOrEqual(ms(LAST_GOAL) + 60_000);
  });
});
