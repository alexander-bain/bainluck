/**
 * #3642 — an axis end names ITS OWN bound.
 *
 * `MarketMapRail.marginBounds` is asymmetric by construction on its declared
 * branch: `min` is driven by the away team's deepest rung and `max` by the home
 * team's, and a book does not quote both sides to the same depth. Both margin
 * call sites in `MarketMapView` nonetheless derived ONE
 * `axisEnd = formatThreshold(rangeMax)` and printed it on both ends.
 *
 * Photographed 2026-09-06, iPad Pro 11-inch against production, event 14780138
 * (Patriots at Seahawks) — `artifacts-native-042/ipad-nfl-14780138-top.png`:
 *
 *     NE by 23.5+          Tie          SEA by 23.5+
 *
 * a symmetric claim, with "Tie" drawn at 43% of the rail. From that event's own
 * `/api/events/14780138/game-markets`, Seattle is quoted out to `20.5` and New
 * England only to `15.0`; with football's declared `18` and the maps' `pad: 3`
 * the rail is `[-18.0, +23.5]`. The right label was right. The left named a
 * bound 5.5 points past New England's end of the rail.
 *
 * 🔴 WHY THE EXISTING TESTS COULD NOT SEE IT — and this is the same shape as
 * #3630. `MarketMapRailTests` pins `marginBounds` and `midAxisLabel`, and every
 * assertion was green: the BOUNDS were always computed correctly, and
 * `midAxisLabel`'s own doc comment records this very rail as `[-18.0, 23.5]`,
 * zero at 43.4%. The defect was never in the rule. It was two call sites that
 * took one number out of a two-number answer. So this guards the call sites,
 * and discovers them by shape rather than by an allowlist.
 *
 * It lives in jest because jest is a deploy gate here and the Swift test target
 * is not reachable from CI — the same reason `mapTitleSingleSource` does. The
 * arithmetic itself is pinned in `BainLuckTests/MarginAxisEndsTests.swift`.
 */

import { readFileSync, existsSync } from "fs";
import { join } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const MAP_VIEW = join(IOS_ROOT, "Components/MarketMapView.swift");
const RAIL = join(IOS_ROOT, "Utilities/MarketMapRail.swift");

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

function collapse(source: string): string {
  return stripComments(source).replace(/\s+/g, " ");
}

/** The text between `source[open]` (a `{`) and its matching `}`. */
function braceBody(source: string, open: number): string {
  let depth = 0;
  for (let i = open; i < source.length; i++) {
    if (source[i] === "{") depth++;
    else if (source[i] === "}" && --depth === 0) return source.slice(open + 1, i);
  }
  return source.slice(open + 1);
}

/**
 * Every `\(...)` expression inside a Swift interpolated string literal, with
 * the team-abbreviation term dropped — the two ends of an axis name different
 * teams on purpose, and that difference is not the one under test.
 */
function interpolations(literal: string): string[] {
  return [...literal.matchAll(/\\\(([^()]*(?:\([^()]*\)[^()]*)*)\)/g)]
    .map((m) => m[1].trim())
    .filter((expr) => !/^[ah]Abbr$/.test(expr));
}

/** Every `axisLeft:`/`axisRight:` pair passed to `mapCard`, in source order. */
function axisPairs(text: string): { left: string; right: string }[] {
  const lefts = [...text.matchAll(/\baxisLeft:\s*("(?:[^"\\]|\\.)*")/g)].map((m) => m[1]);
  const rights = [...text.matchAll(/\baxisRight:\s*("(?:[^"\\]|\\.)*")/g)].map((m) => m[1]);
  expect(lefts).toHaveLength(rights.length);
  return lefts.map((left, i) => ({ left, right: rights[i] }));
}

describe("#3642 — an axis end names its own bound", () => {
  it("finds the files it is guarding", () => {
    expect(existsSync(MAP_VIEW)).toBe(true);
    expect(existsSync(RAIL)).toBe(true);
  });

  /**
   * The regression itself, stated without naming any identifier: the two ends
   * of one axis may not be computed from the same expression. `axisEnd` was the
   * name this time; the rule has to survive the next name.
   */
  it("never labels both ends of one axis from a single value", () => {
    const pairs = axisPairs(collapse(readFileSync(MAP_VIEW, "utf8")));
    expect(pairs.length).toBeGreaterThan(0);

    const offenders = pairs
      .filter(({ left, right }) => {
        const l = interpolations(left);
        const r = interpolations(right);
        // A shared term is only a defect when it is the ONLY term each end has
        // to go on — that is the "one number, two ends" shape.
        return l.length > 0 && r.length > 0 && l.join("|") === r.join("|");
      })
      .map(({ left, right }) => `${left} / ${right}`);

    expect(offenders).toEqual([]);
  });

  /**
   * The positive half. Without it, deleting the axis labels entirely — or
   * inlining `abs(rangeMin)` at one site and forgetting the other — satisfies
   * the assertion above. Both margin cards, the full game and the halves, must
   * read the one selector.
   */
  it("routes both margin cards through the one selector", () => {
    const text = collapse(readFileSync(MAP_VIEW, "utf8"));
    const calls = text.match(/MarketMapRail\.marginAxisEnds\(/g) ?? [];
    expect(calls).toHaveLength(2);

    // …and every margin axis label is actually built from its result.
    const marginEnds = [...text.matchAll(/\baxis(?:Left|Right):\s*("(?:[^"\\]|\\.)*")/g)]
      .map((m) => m[1])
      .filter((literal) => / by \\\(/.test(literal));
    expect(marginEnds.length).toBe(4); // full game + halves, two ends each
    for (const literal of marginEnds) {
      expect(literal).toMatch(/axisEnds\.(left|right)/);
    }
  });

  /**
   * And the rule's own body, because CI cannot run the Swift target. Two
   * distinct mutants live here and the call-site checks above see neither:
   *
   * - `(max, max)` — reads one bound twice. Prints the photographed defect
   *   while every call site reads correct.
   * - `(max, min)` — reads both bounds and SWAPS them. Puts Seattle's `23.5`
   *   on New England's end and New England's `18` on Seattle's, which is the
   *   original bug plus a second one.
   *
   * So the ends are pinned positionally, not merely counted. `MarginAxisEndsTests`
   * pins the same two facts as arithmetic; this is the half of that CI can run.
   */
  it("derives each end from its own bound, in the right order", () => {
    const source = readFileSync(RAIL, "utf8");
    const at = source.indexOf("static func marginAxisEnds");
    expect(at).toBeGreaterThan(-1);
    const body = braceBody(source, source.indexOf("{", at));

    // Magnitudes, because the axis prints "NE by 18+" and the side carries the
    // sign — a signed low bound would render "NE by -18+".
    expect(body).toMatch(/left:\s*abs\(\s*\w+\.min\s*\)/);
    expect(body).toMatch(/right:\s*abs\(\s*\w+\.max\s*\)/);
  });
});
