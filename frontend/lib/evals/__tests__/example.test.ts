/**
 * #12102 — the worked example in "Where the numbers come from" is arithmetic,
 * not a claim: the betting site's odds and the prediction market's contract
 * mean the same chance, and that chance is the one the example shows.
 */

import {
  EXAMPLE_AMERICAN_ODDS,
  EXAMPLE_CONTRACT_CENTS,
  americanOddsText,
  americanToPercent,
} from "@/lib/evals/example";

describe("the worked example", () => {
  it("both sources say the same chance, so the example shows one number", () => {
    expect(americanToPercent(EXAMPLE_AMERICAN_ODDS)).toBe(EXAMPLE_CONTRACT_CENTS);
  });

  it("American odds convert both ways: a favourite below zero, an underdog above", () => {
    expect(americanToPercent(-150)).toBe(60);
    expect(americanToPercent(150)).toBe(40);
    expect(americanToPercent(-100)).toBe(50);
    expect(americanToPercent(100)).toBe(50);
  });

  it("refuses a number that is not American odds", () => {
    expect(() => americanToPercent(50)).toThrow();
    expect(() => americanToPercent(Number.NaN)).toThrow();
  });

  it("prints odds with a true minus sign", () => {
    expect(americanOddsText(-150)).toBe("−150");
    expect(americanOddsText(150)).toBe("+150");
  });
});
