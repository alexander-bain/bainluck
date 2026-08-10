// UX-P042 (#1640) — the event hero must not assert a fabricated 50%.
//
// Deliberately a NEW file rather than an addition to eventKeyStats.test.ts: that file
// is one of the two historic standing rebase conflicts this stack has kept retired
// (see programs/ux.md), and there is no reason to re-open it for a new concern.
//
// The payload below is verbatim production for event 15187583 (Red Sox @ Blue Jays,
// scheduled), read 2026-08-09 ~21:15 PT. Note `hero_probability_source: "blend"` —
// the exact word resolveProbability's live branch gates on — sitting on top of a
// single untraded Polymarket source and ZERO bookmakers.

import { resolveProbability } from "../../lib/eventKeyStats";
import type { EventDetailResponse } from "../../lib/types";

function scheduledEvent(
  sources: Record<string, unknown>,
  homeProbability: number,
): EventDetailResponse {
  return {
    id: 15187583,
    home_team: "Toronto Blue Jays",
    away_team: "Boston Red Sox",
    status: "scheduled",
    commence_time: "2026-08-10T23:07:00+00:00",
    hero_probability: homeProbability,
    hero_probability_away: 1 - homeProbability,
    hero_probability_source: "blend",
    current_odds: {
      home_probability: homeProbability,
      away_probability: 1 - homeProbability,
      source: "aggregate",
      bookmaker_count: 0,
    },
    win_probability_sources: sources,
  } as unknown as EventDetailResponse;
}

/** The defect, verbatim. */
const PLACEHOLDER = scheduledEvent(
  { polymarket: { value: 0.5, display_name: "Polymarket", type: "market", color: "#3b82f6" } },
  0.5,
);

/** Event 15187584 — a real traded price, must survive. */
const TRADED = scheduledEvent({ polymarket: { value: 0.495 } }, 0.495);

describe("resolveProbability — scheduled game with no real evidence", () => {
  it("asserts NO probability when the only source is an untraded midpoint", () => {
    const r = resolveProbability(PLACEHOLDER, undefined, null, false, false);
    expect(r.homeProb).toBeNull();
    expect(r.awayProb).toBeNull();
  });

  it("does not label the withheld state as an 'Aggregate' answer", () => {
    const r = resolveProbability(PLACEHOLDER, undefined, null, false, false);
    expect(r.probSourceLabel).toBeNull();
  });

  it("cannot be re-introduced through the win_prob_history fallback", () => {
    // A chart point derived from that same placeholder source must not sneak the
    // number back in via the lastChartPoint branch.
    const r = resolveProbability(
      PLACEHOLDER,
      undefined,
      { homeProb: 0.42, awayProb: 0.58 } as never,
      false,
      false,
    );
    expect(r.homeProb).toBeNull();
  });

  // --- both-direction guards (gotcha #43) ---

  it("STILL renders a traded lone-Polymarket price (0.495)", () => {
    const r = resolveProbability(TRADED, undefined, null, false, false);
    expect(r.homeProb).toBe(0.495);
    expect(r.probSourceLabel).toBe("Aggregate");
  });

  it("STILL renders a genuine 0.500 quoted by the betting source", () => {
    const genuine = scheduledEvent({ betting: 0.5 }, 0.5);
    const r = resolveProbability(genuine, undefined, null, false, false);
    expect(r.homeProb).toBe(0.5);
  });

  it("STILL renders a multi-source event that agrees on 0.500", () => {
    const agreed = scheduledEvent({ polymarket: 0.5, betting: 0.5 }, 0.5);
    const r = resolveProbability(agreed, undefined, null, false, false);
    expect(r.homeProb).toBe(0.5);
  });
});
