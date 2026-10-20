/**
 * #11296 — the forecast band under a finished game's actual result.
 *
 * Fixture: the producer's seeded shape (`select_pregame_projection`, A
 * f50f60d4a5): an NFL final whose sportsbooks' last pregame pair was
 * 25.4 / 22.4 from 6 books, read between 15:10Z and 16:58Z, before a 17:00Z
 * scheduled start. Every refusal below sits beside a positive control that
 * differs from it in the one field under test, so a refusal can only pass
 * because that field refused it.
 */

import {
  FINAL_FORECAST_LABEL,
  PREGAME_BASIS_CONSENSUS_SPREAD_TOTAL,
  finalForecastComparison,
  type FinalForecastComparisonInput,
  type PregameProjection,
} from "@/lib/finalForecastComparison";
import { cardProjectedFinal } from "@/lib/projectedFinalPair";

function projection(over: Partial<PregameProjection> = {}): PregameProjection {
  return {
    projected_home_score: 25.4,
    projected_away_score: 22.4,
    kind: "last_before_scheduled_start",
    earliest_captured_at: "2026-10-18T15:10:00+00:00",
    latest_captured_at: "2026-10-18T16:58:00+00:00",
    boundary: "scheduled_start",
    boundary_at: "2026-10-18T17:00:00+00:00",
    source: "sportsbooks",
    basis: "consensus_spread_total",
    bookmaker_count: 6,
    unit: "points",
    period: "full_game",
    ...over,
  };
}

function nfl(over: Partial<FinalForecastComparisonInput> = {}): FinalForecastComparisonInput {
  return {
    sportKey: "americanfootball_nfl",
    status: "completed",
    homeScore: 31,
    awayScore: 24,
    actualPeriod: "full_game",
    projection: projection(),
    ...over,
  };
}

function nba(over: Partial<FinalForecastComparisonInput> = {}): FinalForecastComparisonInput {
  return nfl({
    sportKey: "basketball_nba",
    homeScore: 112,
    awayScore: 118,
    projection: projection({ projected_home_score: 118.6, projected_away_score: 112.2 }),
    ...over,
  });
}

function soccer(over: Partial<FinalForecastComparisonInput> = {}): FinalForecastComparisonInput {
  return {
    sportKey: "soccer_epl",
    status: "completed",
    homeScore: 2,
    awayScore: 0,
    actualPeriod: "regulation",
    projection: projection({
      projected_home_score: 1.6,
      projected_away_score: 1.1,
      unit: "goals",
      period: "regulation",
    }),
    ...over,
  };
}

describe("admitted: the band, its label and its details", () => {
  it("an NFL final prints the rounded pregame pair under the scheduled-start label", () => {
    expect(finalForecastComparison(nfl())).toEqual({
      label: "Projection before scheduled start",
      forecast: { home: 25, away: 22 },
      details: {
        sourceLabel: "Sportsbooks",
        bookmakerCount: 6,
        earliestCapturedAt: "2026-10-18T15:10:00+00:00",
        latestCapturedAt: "2026-10-18T16:58:00+00:00",
        boundaryAt: "2026-10-18T17:00:00+00:00",
      },
    });
    expect(FINAL_FORECAST_LABEL).toBe("Projection before scheduled start");
  });

  it("the label says what the numbers are, not only when they were read (Design R1)", () => {
    // The band stands alone under a final: the old standalone "Before
    // scheduled start" named the boundary but never said the pair was a
    // forecast. The label must carry both, and the boundary must stay the
    // SCHEDULED start the producer reads before, never an observed one.
    const label = finalForecastComparison(nfl())!.label;
    expect(label).toMatch(/^Projection\b/);
    expect(label).toMatch(/\bbefore scheduled start$/);
    expect(label).not.toBe("Before scheduled start");
    expect(label).not.toMatch(/kick-?off|tip-?off|first pitch|actual/i);
    // Same label for every admitted sport: one band, one wording.
    expect(finalForecastComparison(nba())!.label).toBe(label);
  });

  it("an NBA final is admitted, rounded per side like the pre-game card", () => {
    expect(finalForecastComparison(nba())?.forecast).toEqual({ home: 119, away: 112 });
  });

  it("the rounding IS the card's: same input, same pair, same refusals", () => {
    const p = projection({ projected_home_score: 24.5, projected_away_score: 20.49 });
    expect(finalForecastComparison(nfl({ projection: p }))?.forecast).toEqual(
      cardProjectedFinal(p, "americanfootball_nfl"),
    );
    // A level NBA forecast is refused by the card (#8156), so it is refused here.
    const level = projection({ projected_home_score: 110.4, projected_away_score: 110.2 });
    expect(cardProjectedFinal(level, "basketball_nba")).toBeNull();
    expect(finalForecastComparison(nba({ projection: level }))).toBeNull();
  });

  it("carries no grading: no winner, hit/miss or colour field", () => {
    const result = finalForecastComparison(nfl());
    expect(Object.keys(result ?? {}).sort()).toEqual(["details", "forecast", "label"]);
    expect(Object.keys(result?.forecast ?? {}).sort()).toEqual(["away", "home"]);
    expect(Object.keys(result?.details ?? {}).sort()).toEqual([
      "bookmakerCount",
      "boundaryAt",
      "earliestCapturedAt",
      "latestCapturedAt",
      "sourceLabel",
    ]);
  });
});

describe("finished means completed OR closed (isFinishedStatus)", () => {
  it.each(["completed", "closed"])("%s is admitted", (status) => {
    expect(finalForecastComparison(nfl({ status }))?.forecast).toEqual({ home: 25, away: 22 });
    expect(finalForecastComparison(nba({ status }))?.forecast).toEqual({ home: 119, away: 112 });
  });

  it.each(["scheduled", "live", "suspended", "final", "", null, undefined])(
    "%p is refused",
    (status) => {
      expect(finalForecastComparison(nfl({ status }))).toBeNull();
      expect(finalForecastComparison(nba({ status }))).toBeNull();
    },
  );
});

describe("team order is keyed, never by value", () => {
  it("an away-favoured forecast keeps home first", () => {
    const p = projection({ projected_home_score: 20.6, projected_away_score: 27.2 });
    expect(finalForecastComparison(nfl({ projection: p }))?.forecast).toEqual({ home: 21, away: 27 });
  });

  it("swapping the served halves swaps the printed halves, and nothing else", () => {
    const a = finalForecastComparison(nfl())?.forecast;
    const b = finalForecastComparison(
      nfl({ projection: projection({ projected_home_score: 22.4, projected_away_score: 25.4 }) }),
    )?.forecast;
    expect(a).toEqual({ home: 25, away: 22 });
    expect(b).toEqual({ home: 22, away: 25 });
  });

  it("the actual score's order does not move the forecast", () => {
    expect(finalForecastComparison(nfl({ homeScore: 10, awayScore: 40 }))?.forecast).toEqual({
      home: 25,
      away: 22,
    });
  });
});

describe("sports whose sportsbook pair is not a final score are refused", () => {
  it.each([
    ["icehockey_nhl", "goals"],
    ["icehockey_ahl", "goals"],
    ["baseball_mlb", "points"],
    ["tennis_atp_shanghai", "points"],
    ["mma_mixed_martial_arts", "points"],
    ["boxing_boxing", "points"],
    [null, "points"],
    ["", "points"],
  ] as const)("%p (served unit %s) prints nothing", (sportKey, unit) => {
    expect(
      finalForecastComparison(
        nfl({ sportKey, homeScore: 4, awayScore: 3, projection: projection({ unit }) }),
      ),
    ).toBeNull();
  });

  it("control: the identical payload on an NFL key is admitted", () => {
    expect(finalForecastComparison(nfl({ homeScore: 4, awayScore: 3 }))).not.toBeNull();
  });
});

describe("no projection: the producer's refusal prints nothing", () => {
  it.each([
    "no_start",
    "start_not_from_schedule",
    "start_is_placeholder",
    "format_unsupported",
    "no_pregame_reading",
    "read_failed",
  ])("pregame_projection_unavailable=%s with no pregame_projection", (reason) => {
    const served: { pregame_projection?: PregameProjection; pregame_projection_unavailable?: string } = {
      pregame_projection_unavailable: reason,
    };
    expect(finalForecastComparison(nfl({ projection: served.pregame_projection }))).toBeNull();
  });

  it.each([null, undefined])("projection %p", (p) => {
    expect(finalForecastComparison(nfl({ projection: p }))).toBeNull();
  });
});

describe("kind: only last_before_scheduled_start, so a new kind never borrows the label", () => {
  it.each(["latest_before_play", "opening", "closing", ""])("kind %p is refused", (kind) => {
    const p = projection({ kind: kind as PregameProjection["kind"] });
    expect(finalForecastComparison(nfl({ projection: p }))).toBeNull();
    expect(finalForecastComparison(nba({ projection: { ...nba().projection!, kind: p.kind } }))).toBeNull();
  });

  it("control: the produced kind is admitted on the same payloads", () => {
    expect(finalForecastComparison(nfl())).not.toBeNull();
    expect(finalForecastComparison(nba())).not.toBeNull();
  });
});

describe("boundary and source must be the ones the label and details name", () => {
  it("a boundary other than scheduled_start is refused", () => {
    for (const boundary of ["observed_start", "market_close", ""]) {
      const p = projection({ boundary: boundary as PregameProjection["boundary"] });
      expect(finalForecastComparison(nfl({ projection: p }))).toBeNull();
    }
  });

  it("a source other than sportsbooks is refused (details would print 'Sportsbooks')", () => {
    for (const source of ["kalshi", "polymarket", ""]) {
      const p = projection({ source: source as PregameProjection["source"] });
      expect(finalForecastComparison(nfl({ projection: p }))).toBeNull();
    }
  });
});

describe("basis: only consensus_spread_total, the reading the card's rounding solves", () => {
  it.each(["model_fair_line", "moneyline", ""])("basis %p is refused", (basis) => {
    const p = projection({ basis: basis as PregameProjection["basis"] });
    expect(finalForecastComparison(nfl({ projection: p }))).toBeNull();
    expect(finalForecastComparison(nba({ projection: { ...nba().projection!, basis: p.basis } }))).toBeNull();
  });

  it("control: the produced basis is admitted on the same payloads", () => {
    expect(PREGAME_BASIS_CONSENSUS_SPREAD_TOTAL).toBe("consensus_spread_total");
    expect(projection().basis).toBe(PREGAME_BASIS_CONSENSUS_SPREAD_TOTAL);
    expect(finalForecastComparison(nfl())).not.toBeNull();
    expect(finalForecastComparison(nba())).not.toBeNull();
  });
});

describe("unit must match the sport's format", () => {
  it("NFL served in goals is refused; served in points is admitted", () => {
    expect(finalForecastComparison(nfl({ projection: projection({ unit: "goals" }) }))).toBeNull();
    expect(finalForecastComparison(nfl({ projection: projection({ unit: "points" }) }))).not.toBeNull();
  });

  it("soccer served in points is refused; served in goals is admitted", () => {
    const pts = { ...soccer().projection!, unit: "points" as const };
    expect(finalForecastComparison(soccer({ projection: pts }))).toBeNull();
    expect(finalForecastComparison(soccer())).not.toBeNull();
  });
});

describe("period: the actual score must cover what the forecast lines settle on", () => {
  it("soccer is withheld without regulation evidence: null, undefined or full_game", () => {
    for (const actualPeriod of [null, undefined, "full_game"] as const) {
      expect(finalForecastComparison(soccer({ actualPeriod }))).toBeNull();
    }
  });

  it("control: soccer WITH regulation evidence is admitted (the gate is the period, not the sport)", () => {
    expect(finalForecastComparison(soccer())?.forecast).toEqual({ home: 2, away: 1 });
  });

  it("a football or basketball final needs a stated full_game period", () => {
    for (const actualPeriod of [null, undefined, "regulation"] as const) {
      expect(finalForecastComparison(nfl({ actualPeriod }))).toBeNull();
      expect(finalForecastComparison(nba({ actualPeriod }))).toBeNull();
    }
    expect(finalForecastComparison(nfl({ actualPeriod: "full_game" }))).not.toBeNull();
  });

  it("an NFL forecast served as regulation is refused against a full_game final", () => {
    const p = projection({ period: "regulation" });
    expect(finalForecastComparison(nfl({ projection: p }))).toBeNull();
  });
});

describe("non-finite or negative values are refused", () => {
  it.each([NaN, Infinity, -Infinity, -0.5, null, "25.4"])("projected home %p", (v) => {
    const p = projection({ projected_home_score: v as number });
    expect(finalForecastComparison(nfl({ projection: p }))).toBeNull();
  });

  it.each([NaN, Infinity, -1, null])("projected away %p", (v) => {
    const p = projection({ projected_away_score: v as number });
    expect(finalForecastComparison(nfl({ projection: p }))).toBeNull();
  });

  it.each([NaN, Infinity, -1, null, undefined])("actual score %p (either side)", (v) => {
    expect(finalForecastComparison(nfl({ homeScore: v as number }))).toBeNull();
    expect(finalForecastComparison(nfl({ awayScore: v as number }))).toBeNull();
  });

  it("control: a 0–0 actual final is a finite score and is admitted", () => {
    expect(finalForecastComparison(soccer({ homeScore: 0, awayScore: 0 }))).not.toBeNull();
  });
});

describe("malformed stamps and counts are refused", () => {
  it.each([
    ["earliest after latest", { earliest_captured_at: "2026-10-18T16:59:00+00:00" }],
    ["latest at the boundary", { latest_captured_at: "2026-10-18T17:00:00+00:00" }],
    ["latest after the boundary", { latest_captured_at: "2026-10-18T20:25:00+00:00" }],
    ["unparseable earliest", { earliest_captured_at: "yesterday" }],
    ["empty boundary_at", { boundary_at: "" }],
    ["zero books", { bookmaker_count: 0 }],
    ["fractional books", { bookmaker_count: 1.5 }],
  ] as const)("%s", (_name, over) => {
    expect(finalForecastComparison(nfl({ projection: projection(over as Partial<PregameProjection>) }))).toBeNull();
  });

  it("control: one book, one stamp, just before the boundary, is admitted", () => {
    const p = projection({
      bookmaker_count: 1,
      earliest_captured_at: "2026-10-18T16:59:59+00:00",
      latest_captured_at: "2026-10-18T16:59:59+00:00",
    });
    expect(finalForecastComparison(nfl({ projection: p }))?.details.bookmakerCount).toBe(1);
  });
});
