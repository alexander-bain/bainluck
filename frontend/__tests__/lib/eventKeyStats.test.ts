// #1003: computeLastChartPoint must treat history[].home_probability as a 0–1
// FRACTION (matching win_prob_history / current_odds / OddsChart), not 0–100.
// The old `/100` made the headline fallback show ~1% while the chart tooltip
// showed ~81% — the reported live tooltip-vs-headline mismatch.

import {
  computeLastChartPoint,
  computeSharedChartDomain,
  latestBlendPoint,
  resolveProbability,
} from "../../lib/eventKeyStats";
import type {
  EventHistoryResponse,
  EventDetailResponse,
} from "../../lib/types";

function hist(partial: Partial<EventHistoryResponse>): EventHistoryResponse {
  return {
    event_id: 1,
    history: [],
    ...partial,
  } as unknown as EventHistoryResponse;
}

function evt(partial: Partial<EventDetailResponse>): EventDetailResponse {
  return {
    id: 1,
    home_team: "Home",
    away_team: "Away",
    status: "live",
    commence_time: "2026-07-23T00:00:00Z",
    ...partial,
  } as unknown as EventDetailResponse;
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

  test("L2-174: readout-at-rest reads the aggregate_line BLEND, not an oppositely-oriented win_prob_history source", () => {
    // THE READOUT INVERSION. The hero (resolveProbability live branch) and the
    // scrub tooltip (OddsChart bainLuckDelta) both read the aggregate_line blend.
    // The at-rest readout used to trust a single win_prob_history source whose
    // home-orientation was OPPOSITE the blend — so the strip showed "home 99%"
    // under a hero that correctly showed "home 1%". Asymmetric probs (0.01 vs
    // 0.99) so an accidental 1-x swap cannot pass this test.
    const historyData = hist({
      aggregate_line: [
        { timestamp: "2026-07-23T02:00:00Z", home_probability: 0.01 },
      ],
      win_prob_history: {
        espn: [{ timestamp: "2026-07-23T03:00:00Z", home_probability: 0.99 }],
      } as never,
      history: [
        { timestamp: "2026-07-23T03:00:00Z", home_probability: 0.99 },
      ] as never,
    });

    const pt = computeLastChartPoint(historyData, null, null);
    expect(pt!.homeProb).toBeCloseTo(0.01); // the blend, NOT the 0.99 source
    expect(pt!.awayProb).toBeCloseTo(0.99);

    // The strip-at-rest must match the hero: resolveProbability's live branch
    // reads the same blend, so the two speak one orientation-consistent number.
    const hero = resolveProbability(
      evt({ status: "live" }),
      historyData,
      pt,
      true, // isLive
      false, // isFinished
    );
    expect(hero.homeProb).toBeCloseTo(0.01);
    expect(pt!.homeProb).toBeCloseTo(hero.homeProb!);
  });

  test("L2-174: with no blend point, the readout still falls back to win_prob_history", () => {
    // The blend-first change must not break the win_prob_history path for sports
    // that never emit an aggregate_line yet.
    const pt = computeLastChartPoint(
      hist({
        win_prob_history: {
          espn: [{ timestamp: "2026-07-09T16:00:00Z", home_probability: 0.62 }],
        } as never,
      }),
      null,
      null,
    );
    expect(pt!.homeProb).toBeCloseTo(0.62);
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

  // L2-163 Item 2c: a LIVE game's "All" window is capped to ≤2h before first
  // pitch so it can never span >12h — which is what lets the 12-hour "h:mm a"
  // inning markers collide and render T9 left of T1. (Previously the cap was
  // completed-only; live "All" could run all the way back to morning pregame
  // odds.)
  test("live 'All' domain start is capped to 2h before commence", () => {
    const commence = "2026-07-23T02:00:00Z"; // 7:00 PM PT first pitch
    const domain = computeSharedChartDomain(
      hist({
        commence_time: commence,
        status: "live",
        // Pregame betting odds captured ~16h before first pitch (morning-of).
        history: [
          { timestamp: "2026-07-22T10:00:00Z", home_probability: 0.5 },
          { timestamp: "2026-07-23T02:30:00Z", home_probability: 0.55 },
          { timestamp: "2026-07-23T03:30:00Z", home_probability: 0.6 },
        ] as never,
      }),
      "all",
      "live",
      commence,
      "baseball_mlb",
    );
    expect(domain).not.toBeNull();
    const startMs = new Date(domain!.start).getTime();
    const twoHoursBefore = new Date(commence).getTime() - 2 * 60 * 60 * 1000;
    expect(startMs).toBeGreaterThanOrEqual(twoHoursBefore);
    // The rendered window stays under 12h → no "h:mm a" categorical collision.
    const spanMs = new Date(domain!.end).getTime() - startMs;
    expect(spanMs).toBeLessThan(12 * 60 * 60 * 1000);
  });

  test("scheduled/pregame 'All' domain is NOT capped (odds drift is the story)", () => {
    const commence = "2026-07-23T02:00:00Z";
    const domain = computeSharedChartDomain(
      hist({
        commence_time: commence,
        status: "scheduled",
        history: [
          { timestamp: "2026-07-22T10:00:00Z", home_probability: 0.5 },
          { timestamp: "2026-07-23T01:00:00Z", home_probability: 0.55 },
        ] as never,
      }),
      "all",
      "scheduled",
      commence,
      "baseball_mlb",
    );
    expect(domain).not.toBeNull();
    // Full pre-game window preserved (starts at the earliest odds snapshot).
    expect(new Date(domain!.start).getTime()).toBe(
      new Date("2026-07-22T10:00:00Z").getTime(),
    );
  });
});

describe("latestBlendPoint (L2-163 Item 2b)", () => {
  test("returns the last valid aggregate_line home probability", () => {
    expect(
      latestBlendPoint([
        { timestamp: "t1", home_probability: 0.4 },
        { timestamp: "t2", home_probability: 0.48 },
      ]),
    ).toBeCloseTo(0.48);
  });

  test("walks back past a trailing null value", () => {
    expect(
      latestBlendPoint([
        { timestamp: "t1", home_probability: 0.4 },
        { timestamp: "t2", home_probability: null as never },
      ]),
    ).toBeCloseTo(0.4);
  });

  test("empty / missing → null", () => {
    expect(latestBlendPoint([])).toBeNull();
    expect(latestBlendPoint(undefined)).toBeNull();
  });
});

describe("resolveProbability — live hero binds to the blend (L2-163 Item 2b)", () => {
  // The 57%-hero vs 20%-chart bug: the hero read a lagged sportsbook consensus
  // while the chart drew the blend. Live, the hero must read the SAME
  // aggregate_line the chart draws.
  test("live hero uses aggregate_line, not the diverging current_odds", () => {
    const r = resolveProbability(
      evt({
        status: "live",
        current_odds: { home_probability: 0.57, away_probability: 0.43, bookmaker_count: 12 } as never,
        opening_odds: { home_probability: 0.5, away_probability: 0.5 } as never,
      }),
      hist({
        aggregate_line: [
          { timestamp: "2026-07-23T00:10:00Z", home_probability: 0.22 },
          { timestamp: "2026-07-23T00:17:00Z", home_probability: 0.2 },
        ],
      }),
      null,
      true, // isLive
      false, // isFinished
    );
    expect(r.homeProb).toBeCloseTo(0.2);
    expect(r.awayProb).toBeCloseTo(0.8);
    expect(r.probSourceLabel).toBe("Live · Bain Luck blend");
  });

  test("live hero falls back to current_odds when no blend exists yet", () => {
    const r = resolveProbability(
      evt({
        status: "live",
        current_odds: { home_probability: 0.57, away_probability: 0.43, bookmaker_count: 12 } as never,
      }),
      hist({ aggregate_line: [] }),
      null,
      true,
      false,
    );
    expect(r.homeProb).toBeCloseTo(0.57);
    expect(r.probSourceLabel).toContain("12 sportsbook");
  });

  test("finished hero still shows pregame opening odds (unchanged)", () => {
    const r = resolveProbability(
      evt({
        status: "completed",
        current_odds: { home_probability: 0.9, away_probability: 0.1 } as never,
        opening_odds: { home_probability: 0.35, away_probability: 0.65 } as never,
      }),
      hist({ aggregate_line: [{ timestamp: "t", home_probability: 0.99 }] }),
      null,
      false,
      true, // isFinished
    );
    expect(r.homeProb).toBeCloseTo(0.35);
    expect(r.probSourceLabel).toBe("Pre-game odds");
  });
});

describe("computeLastChartPoint — moments readout scaffold (L2-163 Item 3)", () => {
  test("attaches the most recent scoring play for the resting readout", () => {
    const pt = computeLastChartPoint(
      hist({
        win_prob_history: {
          espn: [{ timestamp: "2026-07-23T00:16:00Z", home_probability: 0.6 }],
        } as never,
        scoring_plays: [
          { timestamp: "2026-07-23T00:05:00Z", description: "Solo homer", type: "HR", team: "Home", home_score: 1, away_score: 0 },
          { timestamp: "2026-07-23T00:15:00Z", description: "RBI double", type: "2B", team: "Away", home_score: 1, away_score: 1 },
        ] as never,
      }),
      1,
      1,
    );
    expect(pt).not.toBeNull();
    // The LATEST play by timestamp, not array order.
    expect(pt!.scoringPlay?.description).toBe("RBI double");
  });

  test("no scoring plays → scoringPlay null (no crash)", () => {
    const pt = computeLastChartPoint(hist({ win_prob_history: {}, history: [] }), null, null);
    expect(pt!.scoringPlay ?? null).toBeNull();
  });
});
