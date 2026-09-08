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
    count: 2,
    because:
      "a signed MOVE in percentage points (#3051 owns its wording), and " +
      "`fraction_elapsed`, which is a clock ratio and not a probability",
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
    count: 1,
    because: "split-bar width, and it is a `h / total` ratio, not a served probability",
  },
  "components/event/MatchupsRail.tsx": {
    count: 1,
    because: "bar width only; the label is formatProbability",
  },
  "components/event/PropsSection.tsx": {
    count: 5,
    because:
      "two movement deltas in points, a fill width, a tick POSITION and an " +
      "outcome-bar width — the printed number goes through `pct()`, which routes",
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
    expect(readFileSync(file, "utf8")).toContain(
      'from "@/lib/renderedPercent"',
    );
  });

  test("the filing surface has no inline site left at all", () => {
    // `SpecialEventMarkets` is the row Alex's issue named. It is absent from
    // PERMITTED on purpose: there is nothing left in it to permit.
    expect(counts["components/SpecialEventMarkets.tsx"]).toBeUndefined();
  });
});
