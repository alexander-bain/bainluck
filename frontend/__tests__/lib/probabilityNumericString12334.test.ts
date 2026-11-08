/**
 * #12334 — a probability that arrives as a numeric STRING prints its percentage.
 *
 * The cached `/api/feed` served `top_outcomes[].probability` as text
 * (`"0.067500"`, a database `NUMERIC` stored as its string by the feed cache).
 * `probabilityParts` guarded with `Number.isFinite`, which is false for any
 * string, so the Discover hero printed `—` over a card whose own caption read
 * "7% chance": Grab (GRAB) earnings, the NASCAR Championship winner, and the
 * Washington Power and Middle East bundle rows. The backend now stores numbers;
 * this pins the client end, so one stray `Decimal` can never blank a card again.
 */

import {
  BELOW_ONE_PERCENT,
  ABOVE_NINETY_NINE_PERCENT,
  NO_READING,
  formatProbabilityPercent,
  probabilityParts,
} from "@/lib/probabilityDisplay";

/** The six strings the live feed served (the issue body's API excerpt). */
const SPECIMENS = ["0.105000", "0.067500", "0.460000", "0.345000", "0.235000", "0.320000"];

describe("#12334 · the mechanism", () => {
  test("CONTROL: a numeric string is not a finite number to JavaScript", () => {
    // The whole defect in one line: the old guard refused every string.
    expect(Number.isFinite("0.345000" as unknown as number)).toBe(false);
  });
});

describe("#12334 · a numeric string prints its percentage", () => {
  test("each specimen prints exactly what its number prints", () => {
    for (const text of SPECIMENS) {
      expect(probabilityParts(text)).toEqual(probabilityParts(Number(text)));
      expect(formatProbabilityPercent(text)).not.toBe(NO_READING);
    }
  });

  test("the cards from the issue print the numbers their captions give", () => {
    expect(formatProbabilityPercent("0.067500")).toBe("7%"); // Grab (GRAB): "7% chance"
    expect(formatProbabilityPercent("0.460000")).toBe("46%"); // NASCAR: "leads at 46%"
    // The Washington Power rows, with the card's served integer passed in.
    expect(formatProbabilityPercent("0.345000", { rendered: 35 })).toBe("35%");
    expect(formatProbabilityPercent("0.235000", { rendered: 24 })).toBe("24%");
  });

  test("the boundary rule still runs on the value", () => {
    expect(formatProbabilityPercent("0.004000")).toBe(BELOW_ONE_PERCENT);
    expect(formatProbabilityPercent("0.996000")).toBe(ABOVE_NINETY_NINE_PERCENT);
    expect(formatProbabilityPercent("0")).toBe("0%");
    expect(formatProbabilityPercent("1.000000")).toBe("100%");
  });
});

describe("#12334 · nothing that is not a number becomes one", () => {
  test("an empty or blank string is no reading, never 0%", () => {
    expect(formatProbabilityPercent("")).toBe(NO_READING);
    expect(formatProbabilityPercent("   ")).toBe(NO_READING);
  });

  test("words, hex and Infinity stay no reading", () => {
    for (const text of ["blend", "0x10", "Infinity", "NaN", "1/2", "0.3.4"]) {
      expect(formatProbabilityPercent(text)).toBe(NO_READING);
    }
  });

  test("a missing value still prints no reading", () => {
    // Callers type the wire as `number`, but the payload can hold null.
    expect(formatProbabilityPercent(null as unknown as number)).toBe(NO_READING);
    expect(formatProbabilityPercent(undefined as unknown as number)).toBe(NO_READING);
  });

  test("a number is unchanged", () => {
    expect(formatProbabilityPercent(0.0675)).toBe("7%");
    expect(formatProbabilityPercent(Number.NaN)).toBe(NO_READING);
  });
});
