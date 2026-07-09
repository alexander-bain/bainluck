// #999 L2-75: pure calibration math (extracted from the /calibration page).

import { ece, mce, monthYear } from "../../lib/calibrationMath";

describe("mce (equal-weighted)", () => {
  test("mean of |error| regardless of n", () => {
    // errors 2, 4 → mean 3.0; n is ignored.
    expect(mce([{ n: 10000, error: 2 }, { n: 3, error: 4 }])).toBeCloseTo(3.0);
  });
  test("uses absolute error", () => {
    expect(mce([{ n: 1, error: -6 }, { n: 1, error: 2 }])).toBeCloseTo(4.0);
  });
  test("empty → 0", () => {
    expect(mce([])).toBe(0);
  });
});

describe("ece (n-weighted)", () => {
  test("n-weighted mean of |error| — big bucket dominates", () => {
    // 10000*2 + 3*40 = 20120; /10003 ≈ 2.01 (a thin 40pp bucket barely moves it).
    expect(ece([{ n: 10000, error: 2 }, { n: 3, error: 40 }])).toBeCloseTo(2.01, 1);
  });
  test("differs from MCE when sizes are lopsided", () => {
    const buckets = [{ n: 10000, error: 1 }, { n: 2, error: 20 }];
    expect(ece(buckets)).toBeLessThan(mce(buckets)); // ECE stays honest; MCE over-reacts
  });
  test("empty / zero-n → 0", () => {
    expect(ece([])).toBe(0);
    expect(ece([{ n: 0, error: 5 }])).toBe(0);
  });
});

describe("monthYear", () => {
  test("formats ISO to Mon YYYY", () => {
    expect(monthYear("2026-07-09T00:00:00Z")).toMatch(/Jul 2026/);
  });
  test("echoes unparseable input", () => {
    expect(monthYear("not-a-date")).toBe("not-a-date");
  });
});
