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

  test("the giant hero numeral(s) live only in the live block", () => {
    // L2-161 Hero C introduced two 64px numeral renderings — the ambient-history
    // branch and the plain fallback — both inside the same !resolved gate.
    const guardIdx = code.indexOf("!resolved && pct != null");
    expect(guardIdx).toBeGreaterThan(-1);
    let idx = code.indexOf("text-[64px]");
    expect(idx).toBeGreaterThan(-1); // at least one giant numeral exists
    while (idx !== -1) {
      expect(idx).toBeGreaterThan(guardIdx); // every one is behind the guard
      idx = code.indexOf("text-[64px]", idx + 1);
    }
  });

  test("resolved branch renders the Won/Resolved chip", () => {
    expect(code).toMatch(/resolved &&/);
    expect(code).toContain('resolvedWon ? "Won" : "Resolved"');
  });

  test("the Yes/No live bar is also gated on !resolved", () => {
    expect(code).toMatch(/\{!resolved && pct != null && !isMultiOutcome &&/);
  });
});
