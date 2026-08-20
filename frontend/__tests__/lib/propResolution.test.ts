/**
 * Post-game THE DIVERGENCE — UX-P105 (#2011).
 *
 * THE ORACLE IS THE PRODUCTION PAYLOAD, AND IT IS A SECOND SIGNAL, NOT A
 * RESTATEMENT. Every claim below is checked one of two ways:
 *
 *   1. against `actual` vs `threshold` — the realised statistic, which resolves
 *      the over side INDEPENDENTLY of the `hit` the module reads; or
 *   2. against a number this file re-derives from the fixture rather than
 *      quotes.
 *
 * That discipline is not decoration. #2011's own scope section prescribes
 * "resolution is 1.0 for HIT and 0.0 for MISS", and measured against these two
 * production payloads that rule is WRONG on every Polymarket "Under" leg —
 * 9 of 57 typed rows (15.8%) across the 12 settled events surveyed. A test that
 * asserted the issue's rule would have agreed with the bug, which is exactly
 * how UX-P098's hand-written census agreed with the code it was checking.
 *
 * FIXTURES (captured from production 2026-08-19, `/api/events/{id}/game-markets`):
 *   15199902  Colorado @ Los Angeles D, completed. 55 rows, 41 reach the bar,
 *             39 typed. The rich one — and #2011's correct specimen.
 *   15194472  completed. 22 rows, 4 reach the bar, 4 typed, and TWO of them are
 *             the "Under" legs that break the issue's prescribed rule.
 */

import {
  PROP_OFF_SCRIPT_RESOLUTION,
  PROP_SURPRISE_RESOLUTION,
  selectDivergenceDetail,
  selectDivergenceRows,
} from "@/lib/propDivergence";
import {
  propOutcomeSide,
  readOverSideResolution,
  toOverSideGradeFields,
} from "@/lib/propResolution";
import { SETTLED_NO_GRADE_LABEL } from "@/lib/propGrade";
import type { PlayerPropRow } from "@/lib/playerPropsGrouping";

import dodgers from "../fixtures/eventPlayerProps.15199902.settled.json";
import braves from "../fixtures/eventPlayerProps.15194472.settled.json";

const DODGERS = dodgers as unknown as PlayerPropRow[];
const BRAVES = braves as unknown as PlayerPropRow[];

type RawRow = PlayerPropRow & {
  pregame_mark?: number | null;
  actual?: number | null;
};

/** Every raw row that clears the rail's own admission gate. */
function reachingTheBar(rows: readonly RawRow[]): RawRow[] {
  return rows.filter(
    (r) =>
      !!r.market_name &&
      Number.isFinite(r.threshold as number) &&
      Number.isFinite(r.over_probability as number) &&
      Number.isFinite(r.pregame_mark as number),
  );
}

/**
 * THE INDEPENDENT ORACLE. Did the OVER side resolve YES, judged only by the
 * realised statistic against the line — never by `hit`.
 *
 * Kalshi rungs are inclusive ("Freeman: 3+" is `actual >= 3`); Polymarket O/U
 * lines are strict against a half-point line (`actual > 0.5`). Both readings
 * are taken from the providers' own words, and the fixture's own thresholds are
 * half-integers where it matters, so the two agree in practice.
 */
function overResolvedFromActual(row: RawRow): boolean | null {
  const actual = row.actual;
  const threshold = row.threshold;
  if (actual == null || threshold == null) return null;
  const side = propOutcomeSide(row.outcome_name);
  if (side === "unreadable") return null;
  return side === "over" ? actual >= threshold : actual > threshold;
}

describe("the over-axis mapping, checked against a signal it does not read", () => {
  it.each([
    ["15199902", DODGERS],
    ["15194472", BRAVES],
  ])(
    "%s: every typed row's mapped verdict agrees with actual-vs-threshold",
    (_id, rows) => {
      let checked = 0;
      for (const row of reachingTheBar(rows as RawRow[])) {
        if (row.hit == null) continue;
        const oracle = overResolvedFromActual(row);
        if (oracle == null) continue;
        const mapped = toOverSideGradeFields(row);
        expect(mapped).not.toBeNull();
        expect({ row: row.outcome_name, over: mapped?.hit }).toEqual({
          row: row.outcome_name,
          over: oracle,
        });
        checked += 1;
      }
      // NON-VACUITY: an empty loop passes every assertion inside it.
      expect(checked).toBeGreaterThan(0);
    },
  );

  it("places 100% of the fixtures' outcome labels, or refuses them by name", () => {
    const all = [...DODGERS, ...BRAVES] as RawRow[];
    const unreadable = all.filter(
      (r) => propOutcomeSide(r.outcome_name) === "unreadable",
    );
    // Measured on capture: 77 rows, every label placed. A future payload shape
    // that this parser cannot read must FAIL here rather than be guessed at.
    expect(all.length).toBeGreaterThan(50);
    expect(unreadable).toHaveLength(0);
  });

  it("refuses an unplaceable outcome instead of assuming a side", () => {
    expect(propOutcomeSide("Baltimore Orioles vs. Tampa Bay Rays")).toBe("unreadable");
    expect(propOutcomeSide("")).toBe("unreadable");
    expect(toOverSideGradeFields({ outcome_name: "???", hit: true })).toBeNull();
    // An all-unreadable question yields no resolution, not a coin flip.
    expect(readOverSideResolution([{ outcome_name: "???", hit: true }]).resolution).toBeNull();
  });
});

describe("#2011's prescribed rule, measured before it was implemented", () => {
  /**
   * The issue names this row as "the biggest upset in the game" and computes a
   * 91.5-point surprise from `hit: true`. The row's outcome is **"Under"**: the
   * under hit, so the OVER — which is what the 8.5% price and the bar are
   * quoted on — resolved NO. It is the LEAST surprising question on the page,
   * and the flat bar was telling the truth about it.
   */
  it("reads the Albies row as an 8.5-point non-event, not a 91.5-point upset", () => {
    const legs = (BRAVES as RawRow[]).filter((r) =>
      (r.market_name || "").startsWith("Ozzie Albies: Home Runs"),
    );
    // Both legs are present, and they type OPPOSITE `hit` values.
    expect(legs.map((r) => [r.outcome_name, r.hit])).toEqual([
      ["Under", true],
      ["Over", false],
    ]);
    // The independent oracle: 0 home runs against a 0.5 line — the over lost.
    expect(legs.map(overResolvedFromActual)).toEqual([false, false]);

    const { resolution } = readOverSideResolution(legs);
    expect(resolution).toBe(0);

    const detail = selectDivergenceDetail({ playerProps: BRAVES, status: "completed" });
    const albies = [...detail.offScript, ...detail.onScript, ...detail.ungraded].find(
      (r) => r.player === "Ozzie Albies",
    );
    expect(albies?.resolution).toBe(0);
    expect(albies?.surprise).toBeCloseTo(0.085, 6);
    // #2011-as-written would put it here. It must not be.
    expect(albies?.surprise).not.toBeCloseTo(0.915, 3);
    expect(albies?.surprising).toBe(false);
  });

  it("collapses the sibling leg by RECONCILING it, so ingest order cannot pick the verdict", () => {
    const legs = (BRAVES as RawRow[]).filter((r) =>
      (r.market_name || "").startsWith("Ozzie Albies: Home Runs"),
    );
    const forward = readOverSideResolution(legs).resolution;
    const reversed = readOverSideResolution([...legs].reverse()).resolution;
    expect(forward).toBe(reversed);
    expect(forward).toBe(0);
  });

  it("withholds when two legs disagree about the over side after mapping", () => {
    const contradictory = [
      { outcome_name: "Over", hit: true },
      { outcome_name: "Under", hit: true }, // maps to over=false
    ];
    const { grade, resolution } = readOverSideResolution(contradictory);
    expect(resolution).toBeNull();
    expect(grade.state).toBe("WITHHOLD");
    expect(grade.reason).toBe("conflicting_rung_verdicts");
  });
});

describe("the post-game rail ranks by surprise, not travel (#2011, Fable ruling (c))", () => {
  it("promotes the flat-bar upsets travel buries, on the issue's own event", () => {
    const detail = selectDivergenceDetail({ playerProps: DODGERS, status: "completed" });
    const ranked = [...detail.offScript, ...detail.onScript];

    // Re-derived from the fixture, not quoted: where these rows WOULD have sat
    // under the shipped travel ordering.
    const byTravel = [...ranked].sort(
      (a, b) => b.travel - a.travel || b.current - a.current || a.key.localeCompare(b.key),
    );
    const travelRank = (player: string) =>
      byTravel.findIndex((r) => r.player === player) + 1;
    const surpriseRank = (player: string) =>
      ranked.findIndex((r) => r.player === player) + 1;

    // Braxton Fulford: marked 92.5%, did not happen, price never moved.
    const fulford = ranked.find((r) => r.player === "Braxton Fulford");
    expect(fulford?.resolution).toBe(0);
    expect(fulford?.travel).toBeCloseTo(0, 6);
    expect(fulford?.surprise).toBeCloseTo(0.925, 6);
    expect(travelRank("Braxton Fulford")).toBeGreaterThan(10);
    expect(surpriseRank("Braxton Fulford")).toBeLessThanOrEqual(3);

    // Willi Castro: marked 17%, it HAPPENED, price never moved. Travel buried
    // it past rank 25; surprise puts it in the top five.
    const castro = ranked.find((r) => r.player === "Willi Castro");
    expect(castro?.resolution).toBe(1);
    expect(castro?.surprise).toBeCloseTo(0.83, 6);
    // Measured at 25 of 37 graded rows on capture. Asserted as a band, not the
    // exact index, because the travel tiebreak is by price and a re-capture
    // moves it — the claim is "buried", and 20 is well past the fold either way.
    expect(travelRank("Willi Castro")).toBeGreaterThanOrEqual(20);
    expect(surpriseRank("Willi Castro")).toBeLessThanOrEqual(5);
  });

  it("the rail's five are the five biggest surprises, and every one carries a verdict", () => {
    const rail = selectDivergenceRows({ playerProps: DODGERS, status: "completed" });
    expect(rail.rows).toHaveLength(5);
    for (const row of rail.rows) {
      expect(row.resolution).not.toBeNull();
      expect(row.surprise).not.toBeNull();
    }
    // Monotonically non-increasing surprise.
    const surprises = rail.rows.map((r) => r.surprise as number);
    expect([...surprises].sort((a, b) => b - a)).toEqual(surprises);
    // And the top row is a genuine upset, not the biggest price move.
    expect(surprises[0]).toBeGreaterThanOrEqual(PROP_SURPRISE_RESOLUTION);
  });

  it("in-game ordering is UNCHANGED — travel still ranks, and no row is resolved", () => {
    const live = selectDivergenceDetail({ playerProps: DODGERS, status: "live" });
    const rows = [...live.offScript, ...live.onScript];
    expect(live.ungraded).toHaveLength(0);
    for (const row of rows) {
      expect(row.resolution).toBeNull();
      expect(row.surprise).toBeNull();
      expect(row.grade).toBeNull();
    }
    const travels = rows.map((r) => r.travel);
    expect([...travels].sort((a, b) => b - a)).toEqual(travels);
  });
});

describe("the ungraded residual is a group, never a fabricated zero", () => {
  it("sorts every ungraded row after every graded one and gives it no surprise", () => {
    const detail = selectDivergenceDetail({ playerProps: DODGERS, status: "completed" });
    expect(detail.ungraded.length).toBeGreaterThan(0);
    for (const row of detail.ungraded) {
      expect(row.surprise).toBeNull();
      expect(row.resolution).toBeNull();
      expect(row.grade?.state).toBe("WITHHOLD");
      expect(row.surprising).toBe(false);
    }
    // They are not filed among the questions that went to script.
    for (const row of detail.onScript) expect(row.surprise).not.toBeNull();
    for (const row of detail.offScript) expect(row.surprise).not.toBeNull();

    // And the rail — which takes the top five overall — reaches them last.
    const rail = selectDivergenceRows({ playerProps: DODGERS, status: "completed" });
    expect(rail.rows.every((r) => r.surprise != null)).toBe(true);
  });

  it("the fixture really does contain ungraded settled rows (non-vacuity)", () => {
    const reach = reachingTheBar(DODGERS as RawRow[]);
    const ungradedRaw = reach.filter((r) => r.hit == null);
    expect(ungradedRaw.length).toBeGreaterThan(0);
    expect(SETTLED_NO_GRADE_LABEL).toBe("Resolved · grading unavailable");
  });
});

describe("the two post-game constants are the measurement, and they are ordered", () => {
  it("the fold sits below the prose line, so a sentence is always above the fold", () => {
    expect(PROP_OFF_SCRIPT_RESOLUTION).toBeLessThan(PROP_SURPRISE_RESOLUTION);
    const detail = selectDivergenceDetail({ playerProps: DODGERS, status: "completed" });
    for (const row of detail.onScript) expect(row.sentence).toBeNull();
    for (const row of detail.offScript) {
      expect(row.surprise as number).toBeGreaterThanOrEqual(
        PROP_OFF_SCRIPT_RESOLUTION - 1e-9,
      );
      if (row.sentence) {
        expect(row.surprise as number).toBeGreaterThanOrEqual(
          PROP_SURPRISE_RESOLUTION - 1e-9,
        );
      }
    }
  });

  it("admits a row sitting EXACTLY on either line — both are written inclusive", () => {
    // Neither fixture contains a row on either boundary, so a `>=` -> `>`
    // mutation survives every payload-derived assertion above. Same class of
    // hole UX-P101 found on the travel thresholds; pinned the same way.
    const onFold: PlayerPropRow = {
      market_name: "Boundary Batter: Hits O/U 0.5",
      outcome_name: "Over",
      threshold: 0.5,
      over_probability: 0.8,
      pregame_mark: 0.8,
      hit: false,
    } as unknown as PlayerPropRow;
    const foldRow = selectDivergenceDetail({
      playerProps: [onFold],
      status: "completed",
    });
    // |0 - 0.8| = 0.8 clears the prose line.
    expect(foldRow.offScript[0].surprise).toBeCloseTo(0.8, 10);
    expect(foldRow.offScript[0].sentence).not.toBeNull();

    const exactlyOnFold: PlayerPropRow = {
      ...(onFold as object),
      pregame_mark: PROP_OFF_SCRIPT_RESOLUTION,
      over_probability: PROP_OFF_SCRIPT_RESOLUTION,
    } as unknown as PlayerPropRow;
    const d = selectDivergenceDetail({
      playerProps: [exactlyOnFold],
      status: "completed",
    });
    expect(d.offScript).toHaveLength(1);
    expect(d.onScript).toHaveLength(0);
    expect(d.offScript[0].sentence).toBeNull(); // 0.20 < 0.50, no escalation

    const exactlyOnProse: PlayerPropRow = {
      ...(onFold as object),
      pregame_mark: PROP_SURPRISE_RESOLUTION,
      over_probability: PROP_SURPRISE_RESOLUTION,
    } as unknown as PlayerPropRow;
    const p = selectDivergenceDetail({
      playerProps: [exactlyOnProse],
      status: "completed",
    });
    expect(p.offScript[0].surprising).toBe(true);
    expect(p.offScript[0].sentence).toContain("and it didn't");
  });
});

describe("the settled sentence states the OUTCOME, never the last traded price", () => {
  it("says what happened, and never 'finished at <price>'", () => {
    const rail = selectDivergenceRows({ playerProps: DODGERS, status: "completed" });
    const sentences = rail.rows.map((r) => r.sentence).filter(Boolean) as string[];
    expect(sentences.length).toBeGreaterThan(0);
    for (const s of sentences) {
      expect(s).not.toContain("finished at");
      expect(s).toContain("was marked");
      expect(s).toMatch(/and it (happened|didn't)\.$/);
    }
  });

  it("keeps the in-game sentence exactly as it was", () => {
    const live = selectDivergenceRows({ playerProps: DODGERS, status: "live" });
    const sentences = live.rows.map((r) => r.sentence).filter(Boolean) as string[];
    expect(sentences.length).toBeGreaterThan(0);
    for (const s of sentences) {
      expect(s).toContain("opened at");
      expect(s).toMatch(/it's \d+% now\.$/);
    }
  });
});
