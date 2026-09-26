// #3867, the second half of CERT-2224's required repair: a BOUNDED inline-display
// inventory guard over the event page's own component tree.
//
// WHY A CENSUS AND NOT A BAN. `Math.round(x * 100)` is not wrong — it is wrong for
// a PRINTED PROBABILITY, and right for a bar's width, a percentage-point delta and
// a `count / total` ratio, none of which are claims the rounding contract makes.
// Banning the expression outright would push those three into a worse spelling; so
// the guard pins the survivors instead, by file, with each one's reason on the
// record. A NEW site fails closed whichever kind it is, and the failure names the
// file, so the next reader classifies it deliberately rather than inheriting it.
//
// SCOPE IS #3867'S SCOPE — the event page and the components it renders. The other
// ~100 inline sites across the rest of the app are #3892 and are deliberately not
// pinned here: a baseline that spans the whole frontend is one nobody can move.

import { readFileSync, readdirSync, statSync } from "fs";
import { join } from "path";

const ROOTS = [
  "app/events/[id]/page.tsx",
  "components/SpecialEventMarkets.tsx",
  "components/event",
];

/**
 * Every inline site that MAY remain, and what it is.
 *
 * A number here is a promise that the file's remaining occurrences are all
 * non-probability-label uses. Routing one through the contract means DECREMENTING
 * this — the guard fails on a count that is too low as hard as on one too high, so
 * a stale baseline cannot quietly outlive the code (gotcha: a ratio guard that only
 * checks one direction decays).
 */
const PERMITTED: Record<string, { count: number; because: string }> = {
  "app/events/[id]/page.tsx": {
    count: 1,
    because:
      "`fraction_elapsed`, which is a clock ratio and not a probability. The " +
      "signed hero MOVE that used to sit beside it is gone: #5719 routed it " +
      "onto the difference of the two printed integers, which is #2951's rule " +
      "and needs no rounding of its own",
  },
  "components/event/EventLeaderboard.tsx": {
    count: 1,
    because: "bar width + the `rounds to 0%` dim test; the label is formatProbability",
  },
  "components/event/EventProps.tsx": {
    count: 1,
    because: "bar width only; the label is formatProbability",
  },
  "components/event/MatchupDuel.tsx": {
    count: 2,
    because:
      "split-bar width, in BOTH of its arms. #6238 gave the bar a second arm: " +
      "on a draw-priced sport the away side is withheld, so there is no pair to " +
      "take a share of and the home segment is its own probability rather than " +
      "`h / total` (renormalising a withheld pair paints a full-width bar). " +
      "Neither arm is a printed label — the numbers a reader sees still go " +
      "through formatProbability in TeamRow",
  },
  "components/event/MatchupsRail.tsx": {
    count: 1,
    because: "bar width only; the label is formatProbability",
  },
  "components/event/PropsSection.tsx": {
    count: 4,
    because:
      "one movement delta in points (the outcome card's), a fill width, a tick " +
      "POSITION and an outcome-bar width — the printed number goes through `pct()`, " +
      "which routes; #8754 routed THE DIVERGENCE's delta and unchanged test",
  },
  "components/event/TwoSidedTimeline.tsx": {
    count: 1,
    because: "split-bar width only",
  },
};

/** The files the repair routed. Each must still import the shared rule. */
const ROUTED = [
  "components/SpecialEventMarkets.tsx",
  "app/events/[id]/page.tsx",
  "components/event/SettledOutcomeHero.tsx",
  "components/event/PropsSection.tsx",
  "components/event/AdvancementPath.tsx",
  "components/event/LiveSparkline.tsx",
];

const INLINE = /Math\.round\([^;\n]*?\*\s*100\b/;

function walk(path: string): string[] {
  if (statSync(path).isFile()) return path.match(/\.tsx?$/) ? [path] : [];
  return readdirSync(path).flatMap((entry) => walk(join(path, entry)));
}

function inventory(): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const root of ROOTS) {
    for (const file of walk(root)) {
      const hits = readFileSync(file, "utf8")
        .split("\n")
        .filter((line) => INLINE.test(line)).length;
      if (hits > 0) counts[file] = hits;
    }
  }
  return counts;
}

describe("the event page's inline percent sites are pinned, not drifting", () => {
  const counts = inventory();

  test("the census is not vacuous", () => {
    // A regex that stopped matching would turn every assertion below into a pass.
    expect(Object.keys(counts).length).toBeGreaterThan(0);
    expect(INLINE.test("const w = Math.round(p * 100);")).toBe(true);
  });

  test("no file has a site that is not on the record", () => {
    const unknown = Object.keys(counts).filter((f) => !(f in PERMITTED));
    expect(unknown).toEqual([]);
  });

  test.each(Object.entries(PERMITTED))(
    "%s keeps exactly the sites it is permitted",
    (file, { count }) => {
      // Too MANY: a new inline site. Too FEW: one was routed and the baseline
      // was not moved with it, which is how a guard stops describing the code.
      expect(counts[file] ?? 0).toBe(count);
    },
  );

  test.each(ROUTED)("%s still routes through the shared rule", (file) => {
    // #5984 — THE SPELLING WIDENS, THE RULE DOES NOT. This asserted one import
    // path, which was the only way to reach the contract when #3867 wrote it.
    // `formatProbabilityPercent` is the other way, and it is STRICTER: it rounds
    // with `renderedPercent` and then applies the boundary rule on top, so a
    // 0.999 cannot print `100%`. `SpecialEventMarkets` moved to it, and the
    // narrow assertion would have read that as the file leaving the contract.
    // The chain is pinned in the test below so this cannot become an escape.
    const src = readFileSync(file, "utf8");
    const routes =
      src.includes('from "@/lib/renderedPercent"') ||
      src.includes('from "@/lib/probabilityDisplay"');
    expect(routes).toBe(true);
  });

  test("the indirect route is the contract's own, not a second copy of it", () => {
    // Without this, accepting `probabilityDisplay` above would be accepting a
    // file that could quietly grow its own `Math.round(p * 100)` and still
    // satisfy every assertion in this suite.
    const src = readFileSync("lib/probabilityDisplay.ts", "utf8");
    expect(src).toContain('from "./renderedPercent"');
    // COMMENT LINES ARE STRIPPED FIRST, and that is not a softening: this file
    // exists to explain `Math.round(p * 100)`, so it QUOTES the expression twice
    // in prose — once in the module docblock naming the original defect and once
    // beside the line that replaced it. A line-based scan that reads prose as
    // code would fail here forever and teach the next reader to delete the
    // assertion rather than fix it. The claim is about what the module EXECUTES.
    const code = src
      .split("\n")
      .filter((line) => !/^\s*(\/\/|\*|\/\*)/.test(line));
    expect(code.filter((line) => INLINE.test(line))).toEqual([]);
    // Non-vacuity: the stripper must not have eaten the whole file.
    expect(code.some((line) => line.includes("export function"))).toBe(true);
  });

  test("the filing surface has no inline site left at all", () => {
    // `SpecialEventMarkets` is the row Alex's issue named. It is absent from
    // PERMITTED on purpose: there is nothing left in it to permit.
    expect(counts["components/SpecialEventMarkets.tsx"]).toBeUndefined();
  });
});
