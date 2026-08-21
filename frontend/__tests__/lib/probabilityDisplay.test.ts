import fs from "fs";
import path from "path";
import {
  formatProbabilityPercent,
  BELOW_ONE_PERCENT,
  ABOVE_NINETY_NINE_PERCENT,
} from "@/lib/probabilityDisplay";
import { formatProbability } from "@/lib/api";

/**
 * UX-P046 (#1688) — a nonzero probability must never print as "0%".
 *
 * Production 2026-08-10, 100 unique Discover cards / 345 rendered outcome rows:
 * 17 rows were nonzero and printed "0%". One card printed "0%" on all eight of
 * its rows while its own headline named a 64% favourite.
 */
describe("formatProbabilityPercent", () => {
  test("the production specimen: every bridesmaids outcome stops printing 0%", () => {
    // The real wire values from GET /api/feed, market 12194657.
    const wire = [0.0035, 0.0005, 0.0005, 0.0005, 0.0005, 0.0005, 0.0005, 0.0005];
    // NOT `wire.map(formatProbabilityPercent)`. UX-P114 gave this function an
    // optional second argument, and the point-free form handed it the array
    // INDEX — these eight rows printed `<1%, 1%, 2%, 3%…` and this assertion is
    // what caught it. The parameter is an options OBJECT now, so the point-free
    // call is a type error rather than a wrong number, but the explicit arrow is
    // what makes the intent survive the next signature change.
    const printed = wire.map((p) => formatProbabilityPercent(p));
    expect(printed).toEqual(Array(8).fill(BELOW_ONE_PERCENT));
    expect(printed.filter((p) => p === "0%")).toHaveLength(0);
  });

  test("the second argument is an options object, not a positional number", () => {
    // The guard that keeps the trap above closed: an integer override only
    // applies when it arrives under its own key. Anything else — notably a bare
    // index — is ignored rather than printed.
    expect(formatProbabilityPercent(0.675, { rendered: 68 })).toBe("68%");
    expect(formatProbabilityPercent(0.675)).toBe("68%");
    // The boundary rule still wins over the override, because it is a claim
    // about the probability rather than about the arithmetic.
    expect(formatProbabilityPercent(0.996, { rendered: 100 })).toBe(">99%");
    expect(formatProbabilityPercent(0.004, { rendered: 0 })).toBe("<1%");
  });

  test("a value that is possible never prints as impossible", () => {
    expect(formatProbabilityPercent(0.0001)).toBe(BELOW_ONE_PERCENT);
    expect(formatProbabilityPercent(0.0005)).toBe(BELOW_ONE_PERCENT);
    expect(formatProbabilityPercent(0.004)).toBe(BELOW_ONE_PERCENT);
    // 0.005 rounds to 1% on its own merits — it is not in the band.
    expect(formatProbabilityPercent(0.005)).toBe("1%");
  });

  test("a value that is uncertain never prints as certain", () => {
    expect(formatProbabilityPercent(0.9999)).toBe(ABOVE_NINETY_NINE_PERCENT);
    expect(formatProbabilityPercent(0.996)).toBe(ABOVE_NINETY_NINE_PERCENT);
    expect(formatProbabilityPercent(0.994)).toBe("99%");
  });

  test("the true boundaries still print plainly — they ARE 0 and 100", () => {
    expect(formatProbabilityPercent(0)).toBe("0%");
    expect(formatProbabilityPercent(1)).toBe("100%");
  });

  /**
   * The other direction of gotcha #43: the fix must not restyle the 99% of rows
   * that were already correct. Everything outside the two bands is byte-identical
   * to the rounding it replaces.
   */
  test("every value outside the two bands is unchanged from plain rounding", () => {
    for (let i = 1; i <= 999; i++) {
      const p = i / 1000;
      const rounded = Math.round(p * 100);
      if (rounded <= 0 || rounded >= 100) continue;
      expect(formatProbabilityPercent(p)).toBe(`${rounded}%`);
    }
  });

  test("a non-finite value renders nothing rather than 'NaN%'", () => {
    expect(formatProbabilityPercent(Number.NaN)).toBe("—");
  });
});

describe("formatProbability (the shared helper) delegates", () => {
  test("absent data still prints the existing '-', not a percentage", () => {
    expect(formatProbability(null)).toBe("-");
    expect(formatProbability(undefined)).toBe("-");
  });

  test("it inherits the boundary rule instead of carrying its own rounding", () => {
    expect(formatProbability(0.0005)).toBe(BELOW_ONE_PERCENT);
    expect(formatProbability(0.9999)).toBe(ABOVE_NINETY_NINE_PERCENT);
    expect(formatProbability(0.42)).toBe("42%");
  });
});

/**
 * THE ANTI-DRIFT GUARD — this, not the extraction, is the deliverable.
 *
 * The defect existed because `Math.round(p * 100)` was written independently at
 * six call sites, so no single place could be fixed. Extracting one module only
 * helps if a SEVENTH copy cannot quietly appear. Third instance of the #1620
 * shape on this lane (after searchSuggestionDisplay and gameTimeLabel).
 */
describe("anti-drift: one home for the percentage boundary", () => {
  const repoFile = (rel: string) =>
    fs.readFileSync(path.join(__dirname, "..", "..", rel), "utf8");

  const TEXT_PERCENT_RENDERERS = [
    "components/discover/FuturesCard.tsx",
    "components/discover/ComparisonCard.tsx",
    "lib/api.ts",
  ];

  test("no card renders a TEXT percentage from its own rounding", () => {
    for (const rel of TEXT_PERCENT_RENDERERS) {
      const src = repoFile(rel);
      // A bar WIDTH may still round locally — a CSS length is a style value, not
      // a claim about the world — so a `width:` line is exempt and everything
      // else that interpolates a rounded percentage into a string is banned.
      const offenders = src
        .split("\n")
        .map((line, i) => ({ line: line.trim(), n: i + 1 }))
        .filter(({ line }) => /`\$\{Math\.round\([^`]*?\* 100\)\}%`/.test(line))
        .filter(({ line }) => !/\bwidth:/.test(line))
        .map(({ line, n }) => `${n}: ${line}`);
      expect({ file: rel, offenders }).toEqual({ file: rel, offenders: [] });
    }
  });

  test("the boundary strings live in exactly one module", () => {
    const roots = ["lib", "components"];
    const hits: string[] = [];
    const walk = (dir: string) => {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) walk(full);
        else if (/\.tsx?$/.test(entry.name)) {
          const src = fs.readFileSync(full, "utf8");
          if (src.includes('"<1%"') || src.includes("'<1%'")) hits.push(full);
        }
      }
    };
    for (const r of roots) walk(path.join(__dirname, "..", "..", r));
    expect(hits.map((h) => path.basename(h))).toEqual(["probabilityDisplay.ts"]);
  });
});
