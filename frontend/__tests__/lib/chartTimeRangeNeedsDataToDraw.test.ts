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
import type { SharedChartDomain } from "../../lib/eventKeyStats";
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

// ---------------------------------------------------------------------------
// #3419 — the axis must describe the hours the match was PLAYED in.
//
// /events/15300276 (Jodar v Bu, US Open, FINAL) rendered two tick labels in
// DESCENDING order crowded into the left quarter of the plot: "11:00 PM
// 8:00 PM", over a match played the following afternoon. Two independent
// defects, both reproduced below against the verbatim production payload
// (559 Kalshi points, 2026-09-01T15:56Z → 2026-09-02T21:03Z, `history` empty,
// `completed_at` null, so the commence+duration estimate branch is the one
// that runs).
//
//   1. DOMAIN. commence_time is a ticker-derived midnight (00:00Z); + 180
//      tennis minutes = an end of 03:00Z, 12h56m BEFORE the first point.
//      "Since Start" cut to a 3h window containing no data; "All" came out
//      INVERTED (start 15:56Z, end 03:00Z), where fillMinuteGaps no-ops.
//   2. AXIS. Even with the domain right, the window spans 45h and the
//      categorical labels were "h:mm a", which repeats daily: 2,704 minutes
//      collapsed to 1,440 categories and the ticks resolved to
//      [1439,359,719,1079,1439,359,719,1079] — day two drawn on top of day one.
//
// Asserted structurally (no literal label strings): CI runs TZ=UTC but a
// developer's machine does not, and these properties hold in every timezone.
import {
  makeEnsurePoint,
  fillMinuteGaps,
  CATEGORY_LABEL_FORMAT,
} from "../../lib/chartTimeline";

const JODAR_COMMENCE = "2026-09-01T00:00:00+00:00"; // ticker midnight
const JODAR_FIRST = "2026-09-01T15:56:00+00:00";
const JODAR_LAST = "2026-09-02T21:03:00+00:00";

/** The 559-point Kalshi series, thinned to its shape: ends verbatim. */
function jodarPayload(): EventHistoryResponse {
  const pts: Array<{ timestamp: string }> = [];
  const startMs = new Date(JODAR_FIRST).getTime();
  const endMs = new Date(JODAR_LAST).getTime();
  for (let t = startMs; t < endMs; t += 15 * 60_000) {
    pts.push({ timestamp: new Date(t).toISOString() });
  }
  pts.push({ timestamp: JODAR_LAST });
  return {
    event_id: 15300276,
    commence_time: JODAR_COMMENCE,
    completed_at: null,
    status: "closed",
    history: [],
    score_history: [],
    espn_history: [],
    win_prob_history: { kalshi: pts },
  } as unknown as EventHistoryResponse;
}

/**
 * Rebuild the categorical XAxis exactly as OddsChart does — the SAME shared
 * primitives, not a re-derivation — and resolve each tick the way Recharts
 * does: to the FIRST category string equal to it.
 */
function resolveAxis(domain: SharedChartDomain, pts: Array<{ timestamp: string }>) {
  const map = new Map<string, { timestamp: string; time: string }>();
  const ensure = makeEnsurePoint<{ timestamp: string; time: string }>(
    map,
    () => ({}),
    domain.labelFormat,
  );
  for (const p of pts) ensure(p.timestamp);
  fillMinuteGaps(new Date(domain.start), new Date(domain.end), ensure);
  const categories = Array.from(map.values())
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
    .map((p) => p.time);
  return { categories, resolved: domain.ticks.map((t) => categories.indexOf(t)) };
}

describe("#3419 the settled chart's axis describes the hours it was played in", () => {
  test.each(["live", "all"] as const)(
    "%s: the domain covers the whole series and every tick lands, in order",
    (mode) => {
      const payload = jodarPayload();
      const pts = (payload as unknown as {
        win_prob_history: { kalshi: Array<{ timestamp: string }> };
      }).win_prob_history.kalshi;

      const domain = computeSharedChartDomain(
        payload, mode, "closed", JODAR_COMMENCE, "tennis_atp_us_open",
      );
      expect(domain).not.toBeNull();
      const lo = new Date(domain!.start).getTime();
      const hi = new Date(domain!.end).getTime();

      // 1. DOMAIN: not inverted, and it ends at or after the last real point.
      //    Before the fix "all" was inverted by 12h56m and "live" ended 18h
      //    before the series finished.
      expect(hi).toBeGreaterThan(lo);
      expect(hi).toBeGreaterThanOrEqual(new Date(JODAR_LAST).getTime());
      const drawable = pts.filter((p) => {
        const t = new Date(p.timestamp).getTime();
        return t >= lo && t <= hi;
      });
      expect(drawable).toHaveLength(pts.length);

      // 2. AXIS: unique categories, every tick on a real column, left to right.
      const { categories, resolved } = resolveAxis(domain!, pts);
      expect(new Set(categories).size).toBe(categories.length);
      expect(resolved).not.toContain(-1);
      for (let i = 1; i < resolved.length; i++) {
        expect(resolved[i]).toBeGreaterThan(resolved[i - 1]);
      }
      // The end label belongs at the right edge. It used to resolve to
      // category 307 of 1,748 — the left fifth of the plot.
      expect(resolved[resolved.length - 1]).toBe(categories.length - 1);
      expect(resolved[0]).toBe(0);
    },
  );

  test("the narrow 12-hour label really is inadequate here (the fix is not redundant)", () => {
    const payload = jodarPayload();
    const pts = (payload as unknown as {
      win_prob_history: { kalshi: Array<{ timestamp: string }> };
    }).win_prob_history.kalshi;
    const domain = computeSharedChartDomain(
      payload, "live", "closed", JODAR_COMMENCE, "tennis_atp_us_open",
    )!;
    // Same domain, but formatted the pre-fix way.
    const asNarrow = resolveAxis(
      { ...domain, labelFormat: CATEGORY_LABEL_FORMAT },
      pts,
    );
    expect(domain.labelFormat).not.toBe(CATEGORY_LABEL_FORMAT);
    // 45h of minutes cannot fit in 1,440 distinct 12-hour labels.
    expect(new Set(asNarrow.categories).size).toBeLessThan(
      asNarrow.categories.length,
    );
    const narrowAscending = asNarrow.resolved.every(
      (v, i) => i === 0 || v > asNarrow.resolved[i - 1],
    );
    expect(narrowAscending).toBe(false);
  });

  test("control: a same-day game keeps the narrow label and its full tick budget", () => {
    const commence = "2026-09-01T17:00:00+00:00";
    const pts: Array<{ timestamp: string }> = [];
    for (let i = 0; i <= 150; i += 5) {
      pts.push({
        timestamp: new Date(
          new Date(commence).getTime() + i * 60_000,
        ).toISOString(),
      });
    }
    const payload = {
      event_id: 1, commence_time: commence, completed_at: null, status: "closed",
      history: [], score_history: [], espn_history: [],
      win_prob_history: { kalshi: pts },
    } as unknown as EventHistoryResponse;

    const domain = computeSharedChartDomain(
      payload, "all", "closed", commence, "tennis_atp_us_open",
    )!;
    // Width is spent only where it buys uniqueness: a 2.5h window keeps the
    // 12-hour clock, so this fix costs nothing on the overwhelming majority
    // of charts.
    expect(domain.labelFormat).toBe(CATEGORY_LABEL_FORMAT);
    expect(domain.ticks.length).toBeGreaterThan(5);
    const { categories, resolved } = resolveAxis(domain, pts);
    expect(new Set(categories).size).toBe(categories.length);
    expect(resolved).not.toContain(-1);
    for (let i = 1; i < resolved.length; i++) {
      expect(resolved[i]).toBeGreaterThan(resolved[i - 1]);
    }
  });
});
