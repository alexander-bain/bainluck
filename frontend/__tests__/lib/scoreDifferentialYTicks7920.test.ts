// #7920 — the Score Differential y-axis ladder.
//
// MEASURED ON PRODUCTION, 2026-09-22, the probe at `artifacts/ux-1428/
// axis-tick-probe-7920.mjs` at 390px, reading every
// `.recharts-cartesian-axis-tick-value` with NO zero-area filter (so "absent"
// here is "no node", not "a node painting nothing"):
//
//   14780545  Rams–Giants   -26 -17  -8  +1 +10 +19    domainMax 26
//   14638444  Bills–Lions   -24 -16  -8   0  +8 +24    domainMax 24
//   14780544  Chiefs–Colts  -12  -8  -4   0  +4 +12    domainMax 12
//
// Six rungs on an axis handed seven. The first of those is the real defect and
// the other two are its mild form: on 14780545 the ladder never lands on zero,
// so the old generator appended zero next to `+1`, and recharts' overlap
// heuristic dropped one of the pair. On the other two the ladder is clean and
// the heuristic simply thinned a 22px gap.
//
// The cases below are the two production shapes, the arithmetic edges either
// side of them, and the ways the rule can be got wrong in the other direction —
// a ladder that reaches zero but is no longer symmetric, one that is symmetric
// but overshoots the domain, or one whose rungs crowd close enough that
// `interval={0}` on the `<YAxis>` would paint two labels on top of each other.

import {
  scoreDifferentialYStep,
  scoreDifferentialYTicks,
} from "@/lib/scoreDifferentialTicks";

/**
 * Every domain the chart can actually produce. `domainMax` is
 * `Math.max(2, Math.ceil(maxAbs / 2) * 2)` — always even, always at least 2.
 */
const EVERY_DOMAIN: number[] = [];
for (let dm = 2; dm <= 120; dm += 2) EVERY_DOMAIN.push(dm);

describe("#7920 the ladder is symmetric, lands on zero, and is evenly spaced", () => {
  it.each(EVERY_DOMAIN)("domainMax %i", (dm) => {
    const ticks = scoreDifferentialYTicks(dm);

    // Zero is the one label that means something on a differential axis.
    expect(ticks).toContain(0);

    // Symmetric about zero: the ladder read backwards is its own negation.
    // `+ 0` only to fold `-0` back to `0` — negating the zero rung yields `-0`,
    // which `toEqual` treats as a different value from the `0` in the ladder.
    expect(ticks).toEqual([...ticks].reverse().map((v) => -v + 0));

    // Spans exactly the domain — no rung outside the plot, no unlabelled end.
    expect(ticks[0]).toBe(-dm);
    expect(ticks[ticks.length - 1]).toBe(dm);

    // Evenly spaced. The old generator's zero was bolted on after the walk, so
    // it failed here even when it happened to contain zero.
    const gaps = ticks.slice(1).map((v, i) => v - ticks[i]);
    expect(new Set(gaps).size).toBe(1);

    // Strictly increasing, no duplicate rung.
    expect(new Set(ticks).size).toBe(ticks.length);
  });
});

describe("#7920 the ladder stays inside the density `interval={0}` needs", () => {
  it.each(EVERY_DOMAIN)("domainMax %i", (dm) => {
    const ticks = scoreDifferentialYTicks(dm);

    // At most 7 rungs: the step is at least a third of the domain, so at most
    // three per side. Seven at this plot height is ~22px apart against a 12px
    // label — the density the AFTER shot was read at.
    expect(ticks.length).toBeLessThanOrEqual(7);

    // At least 5, so the axis never collapses to just its endpoints and zero.
    // `domainMax` is even, so `domainMax / 2` is always an available divisor.
    if (dm >= 4) expect(ticks.length).toBeGreaterThanOrEqual(5);

    // THE PRECONDITION FOR `interval={0}`. The whole reason forcing every tick
    // to paint is safe is that no two rungs are close enough to collide. The
    // old ladder's tightest pair was 1 unit apart (`0` and `+1`, 2.9px); this
    // asserts the floor that replaced it. If this ever fails, `interval={0}`
    // in ScoreDifferentialChart must come out in the same change.
    const gaps = ticks.slice(1).map((v, i) => v - ticks[i]);
    expect(Math.min(...gaps)).toBeGreaterThanOrEqual(Math.ceil(dm / 3));
  });
});

describe("#7920 the production specimens", () => {
  // The defect, exactly as the probe read it.
  it("14780545 Rams–Giants: domainMax 26 no longer misses zero", () => {
    expect(scoreDifferentialYTicks(26)).toEqual([-26, -13, 0, 13, 26]);
    // What it was: [-26, -17, -8, 0, 1, 10, 19] — zero appended beside `+1`.
    expect(scoreDifferentialYTicks(26)).not.toContain(1);
  });

  // The two that were already clean must come through byte-identical: the fix
  // is scoped to the broken ladders and must not re-cut the good ones.
  it("14638444 Bills–Lions: domainMax 24 is unchanged", () => {
    expect(scoreDifferentialYTicks(24)).toEqual([-24, -16, -8, 0, 8, 16, 24]);
  });

  it("14780544 Chiefs–Colts: domainMax 12 is unchanged", () => {
    expect(scoreDifferentialYTicks(12)).toEqual([-12, -8, -4, 0, 4, 8, 12]);
  });

  it.each([
    [2, [-2, 0, 2]],
    [4, [-4, -2, 0, 2, 4]],
    [6, [-6, -4, -2, 0, 2, 4, 6]],
    [18, [-18, -12, -6, 0, 6, 12, 18]],
    [30, [-30, -20, -10, 0, 10, 20, 30]],
  ])("domainMax %i was already right and is preserved", (dm, expected) => {
    expect(scoreDifferentialYTicks(dm as number)).toEqual(expected);
  });

  // The ladders that were broken, pinned so a later reader can see the shape
  // that changed rather than infer it.
  it.each([
    [8, [-8, -4, 0, 4, 8]], // was [-8, -5, -2, 0, 1, 4, 7]
    [10, [-10, -5, 0, 5, 10]], // was [-10, -6, -2, 0, 2, 6, 10]
    [14, [-14, -7, 0, 7, 14]], // was [-14, -9, -4, 0, 1, 6, 11]
    [20, [-20, -10, 0, 10, 20]], // was [-20, -13, -6, 0, 1, 8, 15]
  ])("domainMax %i was broken and is repaired", (dm, expected) => {
    expect(scoreDifferentialYTicks(dm as number)).toEqual(expected);
  });
});

describe("#7920 the step divides the domain", () => {
  it.each(EVERY_DOMAIN)("domainMax %i", (dm) => {
    const step = scoreDifferentialYStep(dm);

    // Dividing the domain is what puts the ladder on zero. This is the property
    // the old `ceil(domainMax / 3)` lacked.
    expect(dm % step).toBe(0);

    // Still as close to thirds as a divisor allows — not just "any divisor".
    expect(step).toBeGreaterThanOrEqual(Math.max(2, Math.ceil(dm / 3)));

    // And it is the SMALLEST such divisor: nothing between the floor and the
    // chosen step divides the domain. Without this the function could return
    // `domainMax` every time and every assertion above would still pass.
    for (let s = Math.max(2, Math.ceil(dm / 3)); s < step; s++) {
      expect(dm % s).not.toBe(0);
    }
  });
});
