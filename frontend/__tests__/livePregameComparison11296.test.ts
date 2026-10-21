/**
 * #11296 / #9483 — the live headline's retained pregame projection: the rule.
 *
 * Inputs are CONSTRUCTED controls in the producer's served shape (Authority's
 * `a333d40931` DTO contract: NFL 15328569, baseline 25.4 / 22.4 recorded
 * 16:30–16:50Z before a 17:00Z scheduled start; in-play 31.2 / 23.8 confirmed
 * from 20:25Z). They prove the admission rule only. They are not a real live
 * game carrying both objects, and they pay none of Design's real-input
 * before/current acceptance.
 */

import {
  FINAL_FORECAST_LABEL,
  FINAL_FORECAST_LABEL_90_MIN,
  finalForecastComparison,
  type PregameProjection,
} from "@/lib/finalForecastComparison";
import { livePregameComparison, type LivePregameComparisonInput } from "@/lib/livePregameComparison";
import type { LiveProjection } from "@/lib/projectedFinalPair";

const START = "2026-10-17T17:00:00+00:00";

const BASELINE: PregameProjection = {
  projected_home_score: 25.4,
  projected_away_score: 22.4,
  kind: "last_before_scheduled_start",
  earliest_captured_at: "2026-10-17T16:30:00+00:00",
  latest_captured_at: "2026-10-17T16:50:00+00:00",
  boundary: "scheduled_start",
  boundary_at: START,
  source: "sportsbooks",
  basis: "consensus_spread_total",
  bookmaker_count: 2,
  unit: "points",
  period: "full_game",
};

const CURRENT: LiveProjection = {
  projected_home_score: 31.2,
  projected_away_score: 23.8,
  kind: "in_play",
  boundary: "commence_time",
  boundary_at: START,
  earliest_confirmed_at: "2026-10-17T20:25:00+00:00",
  latest_captured_at: "2026-10-17T20:25:45+00:00",
  source: "sportsbooks",
  basis: "consensus_spread_total",
  bookmaker_count: 7,
  unit: "points",
  period: "full_game",
};

function input(patch: Partial<LivePregameComparisonInput> = {}): LivePregameComparisonInput {
  return {
    sportKey: "americanfootball_ncaaf",
    status: "live",
    isLive: true,
    commenceTime: START,
    odds: { projected_home_score: 31.2, projected_away_score: 23.8, live_projection: CURRENT },
    heroProjected: { home: 31, away: 24 },
    projection: BASELINE,
    ...patch,
  };
}

const withBaseline = (patch: Partial<PregameProjection>) =>
  input({ projection: { ...BASELINE, ...patch } as PregameProjection });
const withCurrent = (patch: Partial<LiveProjection>, hero = { home: 31, away: 24 }) =>
  input({
    odds: { live_projection: { ...CURRENT, ...patch } },
    heroProjected: hero,
  });

describe("admits a typed baseline beneath a typed current forecast", () => {
  it("NFL-shaped control: the baseline rounds as the card rounds, home first, with the final band's words", () => {
    expect(livePregameComparison(input())).toEqual({
      label: FINAL_FORECAST_LABEL,
      baseline: { home: 25, away: 22 },
      details: {
        sourceLabel: "Sportsbooks",
        bookmakerCount: 2,
        earliestCapturedAt: BASELINE.earliest_captured_at,
        latestCapturedAt: BASELINE.latest_captured_at,
        boundaryAt: START,
      },
    });
  });

  it("an unchanged line is legitimate: the same pair before and now is still shown", () => {
    const same = withBaseline({ projected_home_score: 31.2, projected_away_score: 23.8 });
    expect(livePregameComparison(same)?.baseline).toEqual({ home: 31, away: 24 });
  });

  it("orientation is keyed, never sorted: an away-favoured baseline stays away-favoured", () => {
    const r = livePregameComparison(withBaseline({ projected_home_score: 20.1, projected_away_score: 27.6 }));
    expect(r?.baseline).toEqual({ home: 20, away: 28 });
  });

  it("rounds each side on its own, half up, like the card", () => {
    const r = livePregameComparison(withBaseline({ projected_home_score: 24.5, projected_away_score: 21.49 }));
    expect(r?.baseline).toEqual({ home: 25, away: 21 });
  });

  it("a baseline below the score already on the board is history, not a refusal", () => {
    // Reachability belongs to the CURRENT forecast (the page gates it); the
    // pre-start reading is what it was.
    const r = livePregameComparison(withBaseline({ projected_home_score: 3.2, projected_away_score: 2.6 }));
    expect(r?.baseline).toEqual({ home: 3, away: 3 });
  });

  it("soccer: goals over 90 minutes on both objects, and the label says 90 min", () => {
    const r = livePregameComparison(
      input({
        sportKey: "soccer_epl",
        odds: { live_projection: { ...CURRENT, unit: "goals", period: "regulation", projected_home_score: 2.2, projected_away_score: 0.9 } },
        heroProjected: { home: 2, away: 1 },
        projection: { ...BASELINE, unit: "goals", period: "regulation", projected_home_score: 1.2, projected_away_score: 1.4 },
      }),
    );
    expect(r?.label).toBe(FINAL_FORECAST_LABEL_90_MIN);
    expect(r?.baseline).toEqual({ home: 1, away: 1 });
  });
});

describe("live only", () => {
  it.each([
    ["completed", true],
    ["closed", true],
    ["scheduled", true],
    ["suspended", true],
    ["in_progress", true],
    ["LIVE", true],
    [null, true],
    ["live", false],
  ])("status %p with isLive=%p prints no baseline", (status, isLive) => {
    expect(livePregameComparison(input({ status: status as string | null, isLive }))).toBeNull();
  });
});

describe("the current forecast must be the typed in-play pair, and the one on screen", () => {
  it("an untyped current pair (no live_projection: the page's ladders) gets no baseline", () => {
    expect(
      livePregameComparison(input({ odds: { projected_home_score: 31.2, projected_away_score: 23.8 } })),
    ).toBeNull();
  });

  it("a refused live_projection gets no baseline", () => {
    expect(livePregameComparison(withCurrent({ kind: "pregame" as LiveProjection["kind"] }))).toBeNull();
    expect(livePregameComparison(withCurrent({ earliest_confirmed_at: "2026-10-17T16:59:00+00:00" }))).toBeNull();
  });

  it("the page printing no current forecast gets no baseline", () => {
    expect(livePregameComparison(input({ heroProjected: null }))).toBeNull();
  });

  it("the page printing a different pair from the typed one gets no baseline", () => {
    expect(livePregameComparison(input({ heroProjected: { home: 30, away: 24 } }))).toBeNull();
    expect(livePregameComparison(input({ heroProjected: { home: 24, away: 31 } }))).toBeNull();
  });
});

describe("refusals of the baseline itself", () => {
  it("absent or not an object", () => {
    expect(livePregameComparison(input({ projection: null }))).toBeNull();
    expect(livePregameComparison(input({ projection: undefined }))).toBeNull();
  });

  it.each<[string, Partial<PregameProjection>]>([
    ["reserved kind latest_before_play", { kind: "latest_before_play" }],
    ["reserved kind opening", { kind: "opening" }],
    ["another boundary", { boundary: "commence_time" as PregameProjection["boundary"] }],
    ["another source", { source: "kalshi" as PregameProjection["source"] }],
    ["another basis", { basis: "ladder" as PregameProjection["basis"] }],
    ["wrong unit", { unit: "goals" }],
    ["wrong period", { period: "regulation" }],
    ["no sportsbooks", { bookmaker_count: 0 }],
    ["fractional count", { bookmaker_count: 1.5 }],
    ["unparseable time", { latest_captured_at: "yesterday" }],
    ["empty time", { earliest_captured_at: "" }],
    ["read at the boundary", { latest_captured_at: START }],
    ["read after the boundary", { latest_captured_at: "2026-10-17T17:05:00+00:00" }],
    ["earliest after latest", { earliest_captured_at: "2026-10-17T16:55:00+00:00" }],
    ["negative half", { projected_home_score: -1 }],
    ["non-finite half", { projected_away_score: Number.NaN }],
    ["a zero half", { projected_away_score: 0 }],
  ])("%s", (_name, patch) => {
    expect(livePregameComparison(withBaseline(patch))).toBeNull();
  });

  it("a no-tie sport's level baseline is refused, as the card refuses it", () => {
    const nba = input({
      sportKey: "basketball_nba",
      odds: { live_projection: { ...CURRENT, projected_home_score: 118.2, projected_away_score: 111.6 } },
      heroProjected: { home: 118, away: 112 },
      projection: { ...BASELINE, projected_home_score: 110.4, projected_away_score: 110.2 },
    });
    expect(livePregameComparison(nba)).toBeNull();
  });
});

describe("same unit, same period, same start", () => {
  it("soccer: a full-game baseline under a 90-minute current pair is refused", () => {
    const r = livePregameComparison(
      input({
        sportKey: "soccer_epl",
        odds: { live_projection: { ...CURRENT, unit: "goals", period: "regulation", projected_home_score: 2.2, projected_away_score: 0.9 } },
        heroProjected: { home: 2, away: 1 },
        projection: { ...BASELINE, unit: "goals", period: "full_game", projected_home_score: 1.2, projected_away_score: 1.4 },
      }),
    );
    expect(r).toBeNull();
  });

  it("soccer extra time: the producer withholds the current pair, so the 90-minute baseline is not shown", () => {
    const r = livePregameComparison(
      input({
        sportKey: "soccer_epl",
        odds: { projected_home_score: 2.2, projected_away_score: 1.9 },
        heroProjected: { home: 2, away: 2 },
        projection: { ...BASELINE, unit: "goals", period: "regulation", projected_home_score: 1.2, projected_away_score: 1.4 },
      }),
    );
    expect(r).toBeNull();
  });

  it("a baseline read before a different start is refused", () => {
    expect(
      livePregameComparison(
        withBaseline({
          boundary_at: "2026-10-17T18:00:00+00:00",
          latest_captured_at: "2026-10-17T17:30:00+00:00",
        }),
      ),
    ).toBeNull();
  });

  it("a current pair measured from a later start than the baseline's is refused", () => {
    // `admittedLiveProjection` admits a boundary at or after the row's start;
    // the two objects must still share one.
    expect(
      livePregameComparison(
        withCurrent({ boundary_at: "2026-10-17T17:10:00+00:00" }),
      ),
    ).toBeNull();
  });

  it("the same instant written two ways is the same start", () => {
    expect(livePregameComparison(withBaseline({ boundary_at: "2026-10-17T17:00:00Z" }))).not.toBeNull();
  });

  it.each(["icehockey_nhl", "baseball_mlb", "tennis_atp_paris", "mma_mixed_martial_arts", null])(
    "unsupported sport %p: nothing, whatever both objects say",
    (sportKey) => {
      expect(livePregameComparison(input({ sportKey }))).toBeNull();
    },
  );
});

describe("parity with the final band's field checks (no drift between phases)", () => {
  const finalOf = (projection: PregameProjection | null) =>
    finalForecastComparison({
      sportKey: "americanfootball_ncaaf",
      status: "completed",
      homeScore: 31,
      awayScore: 38,
      actualPeriod: "full_game",
      projection,
    });

  const cases: [string, Partial<PregameProjection>][] = [
    ["served", {}],
    ["away favoured", { projected_home_score: 20.1, projected_away_score: 27.6 }],
    ["level", { projected_home_score: 24.4, projected_away_score: 23.6 }],
    ["kind opening", { kind: "opening" }],
    ["boundary", { boundary: "commence_time" as PregameProjection["boundary"] }],
    ["source", { source: "kalshi" as PregameProjection["source"] }],
    ["basis", { basis: "ladder" as PregameProjection["basis"] }],
    ["unit", { unit: "goals" }],
    ["period", { period: "regulation" }],
    ["count 0", { bookmaker_count: 0 }],
    ["count 1.5", { bookmaker_count: 1.5 }],
    ["latest at boundary", { latest_captured_at: START }],
    ["earliest after latest", { earliest_captured_at: "2026-10-17T16:55:00+00:00" }],
    ["bad time", { boundary_at: "soon" }],
    ["negative", { projected_home_score: -0.5 }],
    ["zero", { projected_home_score: 0 }],
  ];

  it.each(cases)("%s: both phases admit the same baseline, rounded the same, or both refuse", (_n, patch) => {
    const p = { ...BASELINE, ...patch } as PregameProjection;
    const final = finalOf(p);
    // The live arm also needs the baseline's start to be the row's start; a
    // case that moves `boundary_at` moves the row with it.
    const start = patch.boundary_at ?? START;
    const live = livePregameComparison(
      input({
        projection: p,
        commenceTime: start,
        odds: { live_projection: { ...CURRENT, boundary_at: start } },
      }),
    );
    expect(live?.baseline ?? null).toEqual(final?.forecast ?? null);
    expect(live?.label ?? null).toEqual(final?.label ?? null);
    expect(live?.details ?? null).toEqual(final?.details ?? null);
  });
});
