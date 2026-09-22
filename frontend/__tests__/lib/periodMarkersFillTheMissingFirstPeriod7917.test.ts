/**
 * #7917 — a period the transitions log structurally cannot report is filled
 * from a source that can, and nothing else moves.
 *
 * WHAT A READER SAW. On the notice-42 live walk of Giants @ Rams
 * (`/events/14780545`), on a page that was never reloaded, the win-prob chart
 * drew `Q1` at 00:40:50Z and had lost it by 01:01:00Z. The marker left the chart
 * under a reader who did nothing. Until 00:52:49Z the backend had observed no
 * transition, `period_markers` was empty, and the occurrence logs supplied `Q1`;
 * the instant the first transition landed, `period_markers` won the cascade
 * outright and every marker the occurrence logs had supplied was discarded.
 *
 * `period_markers` is a TRANSITIONS log: there is no observed transition *into*
 * the first period, so it can never hold it, and that is deliberate upstream
 * (#5140, "absent, never kickoff"). The consumer's bug is reading "this source
 * has at least one entry" as "this source is complete".
 *
 * ── WHY THE FIX IS A FILL AND NOT THE UNION THE ISSUE PROPOSED ───────────────
 *
 * Both of #7917's candidate repairs were measured and neither survived.
 *
 * A bare union keyed on the LABEL imports the end markers too. The fallback on
 * this very specimen holds `End of 1st Quarter` → `/Q1` at 00:51:52Z, one minute
 * from `Q2` at 00:52:49Z: two rules naming the same instant. It took `14780544`
 * from 5 markers to 9. Hence `periodIdentity` — `/Q1` is a statement about Q1,
 * not a period of its own. The `refuses the end marker` case below is that.
 *
 * Folding all four sources — the general form of the issue's diagnosis — adds a
 * rule labelled `Final` to 50 of 70 corpus events, in EVERY sport, because
 * ESPN's `period` field carries the game state at the end and
 * `normalizePeriodLabel`'s last line is `return s` (#7960). Hence
 * `FILLABLE_PERIOD_LABEL`, and the `Final` case below.
 *
 * The issue's candidate B ("never draw a boundary on the chart's own start")
 * expired before it could be built: it was premised on `applyCommenceTime`
 * pinning the first fallback boundary to kickoff, and #7901 deleted that. Every
 * `Q1` filled here stands at the first moment Q1 was OBSERVED — 1–18 minutes
 * after the nominal start across the corpus — which is why filling it is honest
 * now and would not have been when the issue was written.
 *
 * MEASURED, 70 completed events / 7 sports (`artifacts/ux-1433/reach.json`):
 * 20 charts change, all football, 19 gaining exactly `Q1`. MLB, NHL, WNBA,
 * soccer and MMA are untouched. Zero non-monotone sequences, zero label-packer
 * evictions (#7951).
 *
 * EVERY PAYLOAD BELOW IS REAL, taken from the banked corpus. The `win_prob`
 * fixtures are reduced to the first sighting of each distinct period string,
 * which is lossless for this function: `deriveBoundariesFromWinProb`'s whole
 * reduction is first-sighting-per-label.
 */

import { derivePeriodBoundaries } from "@/lib/periodMarkers";
import type { ESPNHistoryPoint, WinProbHistoryPoint } from "@/lib/types";

const NFL = "americanfootball_nfl";
const NCAAF = "americanfootball_ncaaf";
const MLB = "baseball_mlb";

/**
 * Typed to the real interfaces rather than cast: the probabilities are the
 * fields these points actually carry, and `derivePeriodBoundaries` reads none
 * of them — which is itself worth pinning, since a fill that depended on a
 * probability would be reading the series to decide what the clock said.
 */
const wp = (points: Array<[string, string]>): Record<string, WinProbHistoryPoint[]> => ({
  stat_model: points.map(([timestamp, period]) => ({
    timestamp,
    home_probability: 0.5,
    away_probability: 0.5,
    game_state: { period },
  })),
});

const espn = (points: Array<[string, string]>): ESPNHistoryPoint[] =>
  points.map(([timestamp, period]) => ({
    timestamp,
    period,
    home_probability: 0.5,
    away_probability: 0.5,
    home_score: 0,
    away_score: 0,
    game_clock: null,
  }));

/** 14780545 Giants @ Rams, the specimen on the issue. Kickoff 00:15:00Z. */
const RAMS_COMMENCE = "2026-09-22T00:15:00+00:00";
const RAMS_MARKERS = [
  { timestamp: "2026-09-22T00:52:49.529937+00:00", period: "2nd Quarter" },
  { timestamp: "2026-09-22T01:44:49.687919+00:00", period: "Halftime" },
  { timestamp: "2026-09-22T01:56:49.683307+00:00", period: "3rd Quarter" },
  { timestamp: "2026-09-22T02:35:50.135950+00:00", period: "4th Quarter" },
];
const RAMS_WINPROB = wp([
  ["2026-09-22T00:17:49.668560+00:00", "15:00 - 1st Quarter"],
  ["2026-09-22T00:51:52.048687+00:00", "End of 1st Quarter"],
  ["2026-09-22T00:52:49.529937+00:00", "15:00 - 2nd Quarter"],
  ["2026-09-22T01:44:49.687919+00:00", "Halftime"],
  ["2026-09-22T01:56:49.683307+00:00", "14:54 - 3rd Quarter"],
  ["2026-09-22T02:34:49.652059+00:00", "End of 3rd Quarter"],
  ["2026-09-22T02:35:50.135950+00:00", "15:00 - 4th Quarter"],
]);
/** The same game's ESPN series, which carries `Final` as a period string. */
const RAMS_ESPN = espn([
  ["2026-09-22T00:17:49.668560+00:00", "15:00 - 1st Quarter"],
  ["2026-09-22T00:51:52.048687+00:00", "End of 1st Quarter"],
  ["2026-09-22T03:11:00+00:00", "Final"],
]);

/**
 * 15311740, NCAAF. The chart draws `Q2 Q4` today — the transitions log missed
 * Q1 AND Q3, so this is the general sparse-log case rather than the Q1 instance.
 */
const SPARSE_MARKERS = [
  { timestamp: "2026-09-20T03:19:21.284274+00:00", period: "2nd Quarter" },
  { timestamp: "2026-09-20T04:57:24.032211+00:00", period: "4th Quarter" },
];
const SPARSE_WINPROB = wp([
  ["2026-09-20T02:47:21.253472+00:00", "10:00 - 1st Quarter"],
  ["2026-09-20T03:19:21.284274+00:00", "14:56 - 2nd Quarter"],
  ["2026-09-20T04:23:24.018295+00:00", "15:00 - 3rd Quarter"],
  ["2026-09-20T04:57:24.032211+00:00", "14:05 - 4th Quarter"],
]);

/** 15316297, MLB. `period_markers` already names every half-inning. */
const MLB_MARKERS = [
  { timestamp: "2026-09-21T23:22:33.214999+00:00", period: "Top 1st" },
  { timestamp: "2026-09-21T23:37:33.243060+00:00", period: "End of 1st Inning" },
  { timestamp: "2026-09-21T23:39:33.980548+00:00", period: "Bottom 1st" },
  { timestamp: "2026-09-21T23:50:33.221080+00:00", period: "Top 2nd" },
  { timestamp: "2026-09-21T23:58:33.227080+00:00", period: "Bottom 2nd" },
];
const MLB_WINPROB = wp([
  ["2026-09-21T23:22:33.214999+00:00", "Top 1st"],
  ["2026-09-21T23:37:33.243060+00:00", "End of 1st Inning"],
  ["2026-09-21T23:39:33.980548+00:00", "Bottom 1st"],
  ["2026-09-21T23:50:33.221080+00:00", "Top 2nd"],
  ["2026-09-21T23:58:33.227080+00:00", "Bottom 2nd"],
]);

describe("#7917 — the first period is filled from a source that can report it", () => {
  it("gives Rams–Giants back the Q1 a reader watched vanish", () => {
    const drawn = derivePeriodBoundaries(
      undefined,
      RAMS_WINPROB,
      undefined,
      RAMS_MARKERS,
      NFL,
    );

    expect(drawn.map((b) => b.label)).toEqual(["Q1", "Q2", "HT", "Q3", "Q4"]);

    // Evidenced, not scheduled: the first moment Q1 was SEEN, 2m49s after the
    // nominal kickoff. #7901's invariant, which is what makes filling it honest.
    expect(drawn[0].timestamp).toBe("2026-09-22T00:17:49.668560+00:00");
    expect(drawn[0].timestamp).not.toBe(RAMS_COMMENCE);
  });

  it("is a change the reader can see: without the fill the chart opens on Q2", () => {
    // The BEFORE, on the same payload. Without this the assertions above could
    // be agreeing with behaviour that was already correct.
    const before = derivePeriodBoundaries(
      undefined,
      undefined,
      undefined,
      RAMS_MARKERS,
      NFL,
    );

    expect(before.map((b) => b.label)).toEqual(["Q2", "HT", "Q3", "Q4"]);
    expect(before.some((b) => b.label === "Q1")).toBe(false);
  });

  it("refuses the end marker that names a period the chart already has", () => {
    // The fallback really does hold `/Q1` — proven here rather than assumed, or
    // the assertion below would pass on a fixture that never carried it.
    const fallbackAlone = derivePeriodBoundaries(
      undefined,
      RAMS_WINPROB,
      undefined,
      undefined,
      NFL,
    );
    expect(fallbackAlone.map((b) => b.label)).toContain("/Q1");

    const drawn = derivePeriodBoundaries(
      undefined,
      RAMS_WINPROB,
      undefined,
      RAMS_MARKERS,
      NFL,
    );

    // `/Q1` at 00:51:52 and `Q2` at 00:52:49 are the same instant said twice.
    expect(drawn.map((b) => b.label)).not.toContain("/Q1");
    expect(drawn.map((b) => b.label)).not.toContain("/Q3");
    expect(drawn.filter((b) => b.label.startsWith("/"))).toHaveLength(0);
  });

  it("refuses `Final`, and fills the real period sitting beside it", () => {
    // Two arms on ONE payload: the ESPN series carries both `15:00 - 1st
    // Quarter` and `Final`. A fill that admitted everything would draw `Final`
    // on 50 of 70 corpus charts; one that admitted nothing would be inert. This
    // fails either way.
    const drawn = derivePeriodBoundaries(
      RAMS_ESPN,
      undefined,
      undefined,
      RAMS_MARKERS,
      NFL,
    );

    expect(drawn.map((b) => b.label)).toContain("Q1");
    expect(drawn.map((b) => b.label)).not.toContain("Final");
    expect(drawn.map((b) => b.label)).toEqual(["Q1", "Q2", "HT", "Q3", "Q4"]);
  });

  it("fills an interior hole too, not just the first period", () => {
    const drawn = derivePeriodBoundaries(
      undefined,
      SPARSE_WINPROB,
      undefined,
      SPARSE_MARKERS,
      NCAAF,
    );

    // Today this chart draws `Q2 Q4` and nothing else.
    expect(
      derivePeriodBoundaries(undefined, undefined, undefined, SPARSE_MARKERS, NCAAF).map(
        (b) => b.label,
      ),
    ).toEqual(["Q2", "Q4"]);

    expect(drawn.map((b) => b.label)).toEqual(["Q1", "Q2", "Q3", "Q4"]);
    // Filled markers land in period order, not merely somewhere on the plot: a
    // Q3 drawn after Q4 would be worse than the hole it fills.
    const times = drawn.map((b) => new Date(b.timestamp).getTime());
    expect(times).toEqual([...times].sort((a, b) => a - b));
    expect(drawn[2].timestamp).toBe("2026-09-20T04:23:24.018295+00:00");
  });

  it("leaves a chart whose markers are already complete exactly as it was", () => {
    const withFallback = derivePeriodBoundaries(
      undefined,
      MLB_WINPROB,
      undefined,
      MLB_MARKERS,
      MLB,
    );
    const markersOnly = derivePeriodBoundaries(
      undefined,
      undefined,
      undefined,
      MLB_MARKERS,
      MLB,
    );

    // This is the load-bearing line: consulting a second source changed nothing.
    expect(withFallback).toEqual(markersOnly);

    // 🪤 The bare `1` is NOT this ship and is not a filled marker — it is what
    // `normalizePeriodLabel("End of 1st Inning")` returns on master, and it is
    // present identically on both sides of the equality above. The `isEnd` strip
    // consumes "End of ", so `iMatch`'s `|end` arm (the one whose comment says
    // "Skip … 'End' to avoid chart clutter") never sees the string, and it falls
    // through to the plain-ordinal branch instead. Written out rather than
    // filtered away, so this pins the defect where a reader meets it: fix it and
    // this line fails, which is the point. Filed separately; measured at 6–9 such
    // rules on 10 of 10 corpus MLB charts.
    expect(withFallback.map((b) => b.label)).toEqual(["T1", "1", "B1", "T2", "B2"]);
  });

  it("never moves a marker the transitions log supplies", () => {
    // The two sources disagree about when Q2 began. `period_markers` wins:
    // this is a fill, not a merge, and a reader's existing markers do not shift
    // because a second source was consulted.
    const disagreeing = wp([
      ["2026-09-22T00:17:49.668560+00:00", "15:00 - 1st Quarter"],
      ["2026-09-22T00:40:00.000000+00:00", "15:00 - 2nd Quarter"],
    ]);

    const drawn = derivePeriodBoundaries(
      undefined,
      disagreeing,
      undefined,
      RAMS_MARKERS,
      NFL,
    );

    expect(drawn.find((b) => b.label === "Q2")!.timestamp).toBe(
      "2026-09-22T00:52:49.529937+00:00",
    );
    expect(drawn.filter((b) => b.label === "Q2")).toHaveLength(1);
  });

  it("changes nothing when there is no transitions log to fill", () => {
    // The pre-existing cascade still owns this path untouched.
    const drawn = derivePeriodBoundaries(undefined, RAMS_WINPROB, undefined, undefined, NFL);

    expect(drawn.map((b) => b.label)).toEqual([
      "Q1",
      "/Q1",
      "Q2",
      "HT",
      "Q3",
      "/Q3",
      "Q4",
    ]);
  });

  it("changes nothing when there is nothing to fill from", () => {
    const drawn = derivePeriodBoundaries(undefined, undefined, undefined, RAMS_MARKERS, NFL);

    expect(drawn.map((b) => b.label)).toEqual(["Q2", "HT", "Q3", "Q4"]);
  });
});
