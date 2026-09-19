/**
 * #7211 — the score does not stop being true when it stops changing.
 *
 * `score_history` is a change log, so a 0-1 game is TWO readings and the second
 * is stamped at the goal. Drawn `stepAfter` that is flat-then-step, which is
 * right; what it cannot draw is the stretch from the goal to the right edge,
 * because the series has no point there. Measured on production 2026-09-19
 * 12:26Z (Tottenham 0-1 Aston Villa, live, halftime): the orange actual line
 * was painted over plot columns 224-2222 while the green projection beside it
 * ran to 2459 — the line describing the score vanished for the last 10.6% of
 * the chart, starting at the exact moment the only goal was scored.
 *
 * This file pins the RULE. `carryScoreForwardIsWired7211.test.tsx` pins that
 * the chart actually calls it, which nothing here can see.
 */

import { carryForward } from "@/lib/chartTimeline";

type P = { timestamp: string; actualDiff: number | null; other?: number | null };
const pt = (timestamp: string, actualDiff: number | null): P => ({
  timestamp,
  actualDiff,
});

describe("#7211 carryForward", () => {
  test("THE SHIP — the last reading is carried to the end of the series", () => {
    // The specimen's shape: kick-off 0-0, a goal, then minutes with no reading.
    const points = [
      pt("11:30", 0),
      pt("11:31", null),
      pt("12:20", -1),
      pt("12:21", null),
      pt("12:26", null),
    ];
    const carried = carryForward(points, "actualDiff");

    expect(points.map((p) => p.actualDiff)).toEqual([0, 0, -1, -1, -1]);
    expect(carried).toBe(3);
    // The point that matters: the LAST point now carries the score.
    expect(points[points.length - 1].actualDiff).toBe(-1);
  });

  test("THE DEFECT, HELD STILL — without the carry the series ends at the goal", () => {
    // Same input, nothing applied. This is what production drew, and it is what
    // makes the assertion above a claim about behaviour rather than a
    // restatement of the helper's own loop.
    const points = [
      pt("11:30", 0),
      pt("11:31", null),
      pt("12:20", -1),
      pt("12:21", null),
      pt("12:26", null),
    ];
    const lastDrawn = points.reduce(
      (acc, p, i) => (typeof p.actualDiff === "number" ? i : acc),
      -1,
    );
    expect(lastDrawn).toBe(2);
    expect(points.length - 1 - lastDrawn).toBe(2); // the trailing gap, in categories
  });

  test("FORWARD ONLY — minutes before the first reading are never back-filled", () => {
    // The whole asymmetry. Back-filling would paint 0-0 across a pre-game
    // domain the chart knows nothing about: a fabricated number, not a carried
    // one. A mutant that drops the `last !== null` guard, or that runs the loop
    // in reverse, is killed here and nowhere else.
    const points = [
      pt("10:00", null),
      pt("10:01", null),
      pt("11:30", 0),
      pt("12:20", -1),
    ];
    carryForward(points, "actualDiff");
    expect(points.map((p) => p.actualDiff)).toEqual([null, null, 0, -1]);
  });

  test("a series that is null throughout stays null throughout", () => {
    const points = [pt("10:00", null), pt("10:01", null)];
    expect(carryForward(points, "actualDiff")).toBe(0);
    expect(points.every((p) => p.actualDiff === null)).toBe(true);
  });

  test("every change is carried, not just the last one", () => {
    // 0-0, then 1-0, then the equaliser: each reading owns the minutes after it
    // and none of them leaks backwards over the one before.
    const points = [
      pt("t0", 0),
      pt("t1", null),
      pt("t2", 1),
      pt("t3", null),
      pt("t4", null),
      pt("t5", 0),
      pt("t6", null),
    ];
    carryForward(points, "actualDiff");
    expect(points.map((p) => p.actualDiff)).toEqual([0, 0, 1, 1, 1, 0, 0]);
  });

  test("a real reading is never overwritten by the one before it", () => {
    // Guards the inverted branch: an implementation that assigns before testing
    // would flatten the series to its first value and still return a plausible
    // count.
    const points = [pt("t0", 2), pt("t1", -3)];
    carryForward(points, "actualDiff");
    expect(points.map((p) => p.actualDiff)).toEqual([2, -3]);
  });

  test("0 is a score, not an absence", () => {
    // `if (value)` instead of a typeof test treats a 0-0 draw as missing and
    // carries the previous scoreline straight over it.
    const points = [pt("t0", 1), pt("t1", 0), pt("t2", null)];
    carryForward(points, "actualDiff");
    expect(points.map((p) => p.actualDiff)).toEqual([1, 0, 0]);
  });

  test("NaN is not a reading", () => {
    const points = [pt("t0", 1), pt("t1", NaN), pt("t2", null)];
    carryForward(points, "actualDiff");
    expect(points.map((p) => p.actualDiff)).toEqual([1, 1, 1]);
  });

  test("idempotent — running it twice carries nothing the second time", () => {
    const points = [pt("t0", 0), pt("t1", null), pt("t2", null)];
    expect(carryForward(points, "actualDiff")).toBe(2);
    expect(carryForward(points, "actualDiff")).toBe(0);
  });

  test("it touches only the key it is given", () => {
    const points: P[] = [
      { timestamp: "t0", actualDiff: 1, other: 9 },
      { timestamp: "t1", actualDiff: null, other: null },
    ];
    carryForward(points, "actualDiff");
    expect(points[1].actualDiff).toBe(1);
    expect(points[1].other).toBeNull();
  });

  test("an empty series is a no-op, not a crash", () => {
    expect(carryForward([] as P[], "actualDiff")).toBe(0);
  });
});
