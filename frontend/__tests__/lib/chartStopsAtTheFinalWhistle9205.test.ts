/**
 * #9205 — A FINISHED GAME'S CHARTS STOP AT THE FINAL WHISTLE.
 *
 * Production, 390px, 2026-09-27: `/events/14781702` (Commanders 33–31
 * Seahawks, FINAL, `completed_at` 20:27:41Z = 1:27 PM PDT). A fresh load at
 * 20:28Z drew both charts to 1:27 PM. A fresh load at 20:38Z, and the tab left
 * open since halftime, drew both to 1:35 PM: a flat 100% on Win Probability
 * and a flat orange score line for eight minutes after the game.
 *
 * Why: for a finished game `computeSharedChartDomain` ends at the last
 * game-end reading (ESPN, 20:27:00Z) and then lets a sportsbook point up to
 * 10 minutes later extend it. The served payload carries a 20:35:00Z
 * sportsbook row written after the final. #8709's branch already refused a
 * post-`completed_at` quote; the 10-minute branch did not.
 *
 * The fixture is the served payload, banked from production and trimmed to
 * the tail (the window END is the subject). Arm 3: an in-game sportsbook tail
 * still extends the window. Arm 4 is the control: a payload with no
 * `completed_at` keeps today's rule.
 */

import { computeSharedChartDomain } from "@/lib/eventKeyStats";
import specimen from "../fixtures/chartStopsAtTheFinalWhistle9205.json";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Payload = any;
const base = (): Payload => JSON.parse(JSON.stringify(specimen));
const SPORT = "americanfootball_nfl";
const ms = (iso: string) => new Date(iso).getTime();

const LAST_ESPN = "2026-09-27T20:27:00+00:00";
const COMPLETED_AT = "2026-09-27T20:27:41.958869+00:00";
const POST_FINAL_QUOTE = "2026-09-27T20:35:00+00:00";

const endOf = (payload: Payload, range: "all" | "live" = "live") => {
  const d = computeSharedChartDomain(payload, range, "completed", payload.commence_time, SPORT);
  expect(d).not.toBeNull();
  return ms(d!.end);
};

describe("#9205 a post-final sportsbook row does not stretch a finished game's chart", () => {
  it("the fixture is the specimen: ESPN ends at the final, a sportsbook row sits 7 minutes after completed_at", () => {
    const p = base();
    expect(p.completed_at).toBe(COMPLETED_AT);
    expect(p.espn_history[p.espn_history.length - 1].timestamp).toBe(LAST_ESPN);
    const late = p.history.filter((pt: Payload) => ms(pt.timestamp) > ms(COMPLETED_AT));
    expect(late.map((pt: Payload) => pt.timestamp)).toEqual([POST_FINAL_QUOTE]);
    // Inside the 10-minute cap measured from the last game-end reading: the defect's precondition.
    expect(ms(POST_FINAL_QUOTE) - ms(LAST_ESPN)).toBeLessThanOrEqual(10 * 60_000);
  });

  it.each(["live", "all"] as const)("arm 1 (%s): the window ends at the final, not at the post-final row", (range) => {
    const end = endOf(base(), range);
    expect(end).toBeLessThanOrEqual(ms(COMPLETED_AT));
    expect(end).toBe(ms(LAST_ESPN));
  });

  it("arm 2: moving the post-final row back inside the game lets it extend the window again", () => {
    // Proves arm 1 is refused by the completed_at ceiling and nothing else.
    const p = base();
    p.completed_at = "2026-09-27T20:40:00+00:00";
    expect(endOf(p)).toBe(ms(POST_FINAL_QUOTE));
  });

  // Not a pure control: under the old rule this arm ALSO failed. The cap was
  // measured against the last quote even when that quote was post-final, so
  // the 20:35Z row (15 min past ESPN here) vetoed the in-game 20:27Z extension.
  it("arm 3: an in-game sportsbook tail still extends the window, and a post-final row no longer vetoes it", () => {
    const p = base();
    p.espn_history = p.espn_history.filter((pt: Payload) => ms(pt.timestamp) <= ms("2026-09-27T20:20:00Z"));
    p.win_prob_history = {};
    // Last in-game sportsbook point is the 20:27:00Z settle row, within 10 min of ESPN's last.
    const lastEspn = ms(p.espn_history[p.espn_history.length - 1].timestamp);
    const end = endOf(p);
    expect(end).toBeGreaterThan(lastEspn);
    expect(end).toBe(ms(LAST_ESPN));
  });

  it("arm 4 (control): with no completed_at the old 10-minute rule stands", () => {
    const p = base();
    p.completed_at = null;
    expect(endOf(p)).toBe(ms(POST_FINAL_QUOTE));
  });
});
