// #883 L2-53 (Alex ruling): a SETTLED futures hero shows the winner name + "Won"
// chip — NO big percentage (the last-traded price read as a bug). The live hero
// keeps its big blended number. Source-inspection guard: the giant number must be
// gated behind `!resolved`, and the resolved branch renders the chip, not a number.

import { readFileSync } from "fs";
import { join } from "path";

const src = readFileSync(
  join(__dirname, "../../components/FuturesHero.tsx"),
  "utf8",
);
const code = src
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/\/\/.*$/gm, "");

describe("FuturesHero resolved hero (#883 L2-53)", () => {
  test("the big number is gated behind !resolved (live only)", () => {
    expect(code).toMatch(/\{!resolved && pct != null &&/);
  });

  test("there is exactly one giant-number element, in the live block", () => {
    const matches = code.match(/text-\[56px\]/g) || [];
    expect(matches.length).toBe(1);
    // it lives after the !resolved guard
    const guardIdx = code.indexOf("!resolved && pct != null");
    const numIdx = code.indexOf("text-[56px]");
    expect(guardIdx).toBeGreaterThan(-1);
    expect(numIdx).toBeGreaterThan(guardIdx);
  });

  test("resolved branch renders the Won/Resolved chip", () => {
    expect(code).toMatch(/resolved &&/);
    expect(code).toContain('resolvedWon ? "Won" : "Resolved"');
  });

  test("the Yes/No live bar is also gated on !resolved", () => {
    expect(code).toMatch(/\{!resolved && pct != null && !isMultiOutcome &&/);
  });
});
