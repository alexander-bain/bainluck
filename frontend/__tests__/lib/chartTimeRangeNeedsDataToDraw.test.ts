// The two blank charts on a live US Open match, and the rule that stops them.
//
// LOOKED at production /events/15293847 (Jodar v Kokkinakis, LIVE) on
// 2026-09-01 22:18Z: Win Probability was a bare grid with one dot at the right
// edge, Score Differential was empty, and "Since Start" was the selected pill
// on a button OddsChart had itself disabled.
//
// The cause is not the win-prob blend — CERT-691 was already deployed on that
// match and Kalshi was in its legend. It is the SHARED time range. Both charts
// compute a `hasPostStartData` and fall back to "All" when "Since Start" would
// be empty, but the event page passes `externalTimeRange` and
// `timeRange = externalTimeRange ?? internalTimeRange`, so the parent wins and
// each child's fallback is dead code. The parent held a hardcoded "live".
//
// `commence_time` on that row is 16:00:00Z — an exact top of the hour from the
// Odds API's session-start default, not a reported first serve. The last
// sportsbook quote is 15:44Z, SIXTEEN MINUTES BEFORE it. Cut at 16:00 and the
// entire series is gone.
//
// Both arms below are verbatim production timestamps.

import {
  defaultChartTimeRange,
  maxPostStartSeriesPoints,
  computeSharedChartDomain,
} from "../../lib/eventKeyStats";
import type { EventHistoryResponse } from "../../lib/types";

// --- Arm A: the defect. 15293847, measured 2026-09-01 22:18Z. -------------
// 73 sportsbook points, the last at 15:44Z; commence_time 16:00Z. Exactly one
// post-start point exists in the whole payload per series: one score snapshot
// (17:04Z) and one Kalshi point (21:50Z).
const STAND_IN_START_COMMENCE = "2026-09-01T16:00:00+00:00";
const STAND_IN_START: EventHistoryResponse = {
  event_id: 15293847,
  commence_time: STAND_IN_START_COMMENCE,
  status: "live",
  history: [
    { timestamp: "2026-08-27T22:05:00+00:00" },
    { timestamp: "2026-08-31T13:20:00+00:00" },
    { timestamp: "2026-09-01T14:05:00+00:00" },
    { timestamp: "2026-09-01T15:12:00+00:00" },
    { timestamp: "2026-09-01T15:44:00+00:00" },
  ],
  score_history: [
    { timestamp: "2026-09-01T17:04:35.195527+00:00", home_score: 0, away_score: 0 },
  ],
  espn_history: [],
  win_prob_history: {
    kalshi: [{ timestamp: "2026-09-01T21:50:57.336768+00:00" }],
  },
} as unknown as EventHistoryResponse;

// --- Arm B: the control. 15297970 (Cerundolo v Gea), same sport, same page,
// same minute, LIVE, charts drawing correctly on screen. commence_time
// 20:16:04Z is a real staggered first serve and 116 odds points follow it.
const REPORTED_START_COMMENCE = "2026-09-01T20:16:04+00:00";
const REPORTED_START: EventHistoryResponse = {
  event_id: 15297970,
  commence_time: REPORTED_START_COMMENCE,
  status: "live",
  history: [
    { timestamp: "2026-08-30T22:22:00+00:00" },
    { timestamp: "2026-09-01T19:50:00+00:00" },
    { timestamp: "2026-09-01T20:17:00+00:00" },
    { timestamp: "2026-09-01T20:19:00+00:00" },
    { timestamp: "2026-09-01T21:40:00+00:00" },
    { timestamp: "2026-09-01T22:22:00+00:00" },
  ],
  score_history: [
    { timestamp: "2026-09-01T20:17:34.426050+00:00", home_score: 0, away_score: 0 },
    { timestamp: "2026-09-01T20:53:34.461089+00:00", home_score: 0, away_score: 1 },
    { timestamp: "2026-09-01T21:33:34.705793+00:00", home_score: 1, away_score: 1 },
  ],
  espn_history: [],
  win_prob_history: {},
} as unknown as EventHistoryResponse;

describe("the shared chart range needs enough post-start data to DRAW", () => {
  test("Arm A (15293847): a stand-in start leaves no series able to draw, so the page holds All", () => {
    // One score point and one Kalshi point ARE post-start. A has-any test goes
    // green here and the chart is still blank — which is why the rule counts.
    expect(maxPostStartSeriesPoints(STAND_IN_START, STAND_IN_START_COMMENCE)).toBe(1);
    expect(defaultChartTimeRange(STAND_IN_START, STAND_IN_START_COMMENCE)).toBe("all");
  });

  test("Arm B (15297970): a reported start has a drawable series, so the page holds Since Start", () => {
    expect(
      maxPostStartSeriesPoints(REPORTED_START, REPORTED_START_COMMENCE),
    ).toBeGreaterThanOrEqual(2);
    expect(defaultChartTimeRange(REPORTED_START, REPORTED_START_COMMENCE)).toBe("live");
  });

  // The consequence, not the predicate: with the range this function picks,
  // the window the charts actually render must CONTAIN points. This is the
  // assertion that fails if the range is right but the domain still clips.
  const pointsInsideDomain = (
    payload: EventHistoryResponse,
    commence: string,
    range: "all" | "live",
    status: string,
  ): number => {
    const domain = computeSharedChartDomain(payload, range, status, commence, "tennis_atp_us_open");
    if (!domain) return 0;
    const lo = new Date(domain.start).getTime();
    const hi = new Date(domain.end).getTime();
    return (payload.history ?? []).filter((p) => {
      const t = new Date(p.timestamp).getTime();
      return t >= lo && t <= hi;
    }).length;
  };

  test("Arm A: the chosen range yields a window with data in it", () => {
    const chosen = defaultChartTimeRange(STAND_IN_START, STAND_IN_START_COMMENCE);
    expect(
      pointsInsideDomain(STAND_IN_START, STAND_IN_START_COMMENCE, chosen, "live"),
    ).toBeGreaterThan(0);
  });

  test("Arm B: the control is green under the same assertion", () => {
    const chosen = defaultChartTimeRange(REPORTED_START, REPORTED_START_COMMENCE);
    expect(
      pointsInsideDomain(REPORTED_START, REPORTED_START_COMMENCE, chosen, "live"),
    ).toBeGreaterThan(0);
  });

  // Validates the DETECTOR: under the old hardcoded "live" the window is empty
  // for Arm A. Without this the two tests above would pass on a build that
  // never fixed anything.
  test("the old hardcoded \"live\" leaves Arm A's window with zero points", () => {
    expect(
      pointsInsideDomain(STAND_IN_START, STAND_IN_START_COMMENCE, "live", "live"),
    ).toBe(0);
    // ...and leaves the control untouched, so the detector is specific.
    expect(
      pointsInsideDomain(REPORTED_START, REPORTED_START_COMMENCE, "live", "live"),
    ).toBeGreaterThan(0);
  });
});

describe("the All-mode pre-game cap cannot clip the window empty", () => {
  // The cap trims "All" to 2h before commence_time once an event is in-game.
  // It is anchored on the same field that is wrong when a start was never
  // reported, so applied blind it can move the window past every point the
  // event has — turning "All" into the empty grid "Since Start" just was.
  const ALL_BEFORE_CAP_COMMENCE = "2026-09-02T00:00:00+00:00"; // ticker midnight stand-in
  const ALL_BEFORE_CAP: EventHistoryResponse = {
    event_id: 999,
    commence_time: ALL_BEFORE_CAP_COMMENCE,
    status: "live",
    history: [
      { timestamp: "2026-09-01T14:00:00+00:00" },
      { timestamp: "2026-09-01T15:00:00+00:00" },
      { timestamp: "2026-09-01T16:00:00+00:00" },
    ],
    score_history: [],
    espn_history: [],
    win_prob_history: {},
  } as unknown as EventHistoryResponse;

  test("every point predates the cap, so the cap does not apply", () => {
    const domain = computeSharedChartDomain(
      ALL_BEFORE_CAP,
      "all",
      "live",
      ALL_BEFORE_CAP_COMMENCE,
      "tennis_atp_us_open",
    );
    expect(domain).not.toBeNull();
    const lo = new Date(domain!.start).getTime();
    const hi = new Date(domain!.end).getTime();
    const inside = ALL_BEFORE_CAP.history!.filter((p) => {
      const t = new Date(p.timestamp).getTime();
      return t >= lo && t <= hi;
    });
    expect(inside).toHaveLength(3);
  });

  test("control: when data straddles the cap the cap still applies", () => {
    const commence = "2026-09-01T20:00:00+00:00"; // cap at 18:00
    const straddles = {
      ...ALL_BEFORE_CAP,
      commence_time: commence,
      history: [
        { timestamp: "2026-09-01T10:00:00+00:00" }, // dropped by the cap
        { timestamp: "2026-09-01T19:00:00+00:00" },
        { timestamp: "2026-09-01T20:30:00+00:00" },
      ],
    } as unknown as EventHistoryResponse;
    const domain = computeSharedChartDomain(
      straddles,
      "all",
      "live",
      commence,
      "tennis_atp_us_open",
    );
    expect(new Date(domain!.start).getTime()).toBe(
      new Date("2026-09-01T18:00:00+00:00").getTime(),
    );
  });
});
