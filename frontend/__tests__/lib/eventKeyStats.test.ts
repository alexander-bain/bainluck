// #1003: computeLastChartPoint must treat history[].home_probability as a 0–1
// FRACTION (matching win_prob_history / current_odds / OddsChart), not 0–100.
// The old `/100` made the headline fallback show ~1% while the chart tooltip
// showed ~81% — the reported live tooltip-vs-headline mismatch.

import { computeLastChartPoint } from "../../lib/eventKeyStats";
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
