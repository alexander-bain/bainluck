// #1003: computeLastChartPoint must treat history[].home_probability as a 0–1
// FRACTION (matching win_prob_history / current_odds / OddsChart), not 0–100.
// The old `/100` made the headline fallback show ~1% while the chart tooltip
// showed ~81% — the reported live tooltip-vs-headline mismatch.

import {
  computeLastChartPoint,
  computeSharedChartDomain,
} from "../../lib/eventKeyStats";
import type { EventHistoryResponse } from "../../lib/types";

function hist(partial: Partial<EventHistoryResponse>): EventHistoryResponse {
  return {
    event_id: 1,
    history: [],
    ...partial,
  } as unknown as EventHistoryResponse;
}

describe("computeLastChartPoint (#1003 fraction fix)", () => {
  test("history home_probability (0–1) is used as-is when win_prob_history is empty", () => {
    // England 0.81 favourite: headline must be 0.81, NOT 0.0081.
    const pt = computeLastChartPoint(
      hist({
        win_prob_history: {},
        history: [
          { timestamp: "2026-07-09T10:00:00Z", home_probability: 0.54 },
          { timestamp: "2026-07-09T16:00:00Z", home_probability: 0.81 },
        ] as never,
      }),
      null,
      null,
    );
    expect(pt).not.toBeNull();
    expect(pt!.homeProb).toBeCloseTo(0.81);
    expect(pt!.awayProb).toBeCloseTo(0.19);
  });

  test("prefers win_prob_history (0–1) when present", () => {
    const pt = computeLastChartPoint(
      hist({
        win_prob_history: {
          espn: [{ timestamp: "2026-07-09T16:00:00Z", home_probability: 0.62 }],
        } as never,
        history: [
          { timestamp: "2026-07-09T16:00:00Z", home_probability: 0.81 },
        ] as never,
      }),
      null,
      null,
    );
    expect(pt!.homeProb).toBeCloseTo(0.62);
  });

  test("defaults to 0.5 when no probability anywhere", () => {
    const pt = computeLastChartPoint(hist({ win_prob_history: {}, history: [] }), null, null);
    expect(pt!.homeProb).toBeCloseTo(0.5);
  });

  test("null historyData → null", () => {
    expect(computeLastChartPoint(null, null, null)).toBeNull();
  });
});

describe("computeSharedChartDomain (Queue #189: mis-attributed game-end)", () => {
  // Sox-Mets Jul-12: commence 17:40, real game data (polymarket) 18:52–20:07,
  // but mis-attributed espn/mlb/stat_model snapshots sit ~41h earlier (Jul-11
  // 00:xx). The old domain took `end` from those game-end sources, yielding
  // end < start (an empty chart). The floor guard must drop them.
  test("game-end timestamps before commence are ignored → domain not inverted", () => {
    const commence = "2026-07-12T17:40:00Z";
    const domain = computeSharedChartDomain(
      hist({
        commence_time: commence,
        status: "completed",
        // Mis-attributed earlier game: game-end sources ~41h before first pitch.
        win_prob_history: {
          espn: [{ timestamp: "2026-07-11T00:46:00Z", home_probability: 0 }],
          mlb: [{ timestamp: "2026-07-11T00:40:00Z", home_probability: 0 }],
          // The real game, only on polymarket (not a GAME_END_SOURCE):
          polymarket: [
            { timestamp: "2026-07-12T18:52:00Z", home_probability: 0.5 },
            { timestamp: "2026-07-12T20:07:00Z", home_probability: 0.001 },
          ],
        } as never,
        history: [],
      }),
      "all",
      "completed",
      commence,
      "baseball_mlb",
    );
    expect(domain).not.toBeNull();
    const startMs = new Date(domain!.start).getTime();
    const endMs = new Date(domain!.end).getTime();
    // Domain must be forward (start < end) and cover the real game window.
    expect(startMs).toBeLessThan(endMs);
    expect(endMs).toBeGreaterThanOrEqual(new Date(commence).getTime());
  });
});
