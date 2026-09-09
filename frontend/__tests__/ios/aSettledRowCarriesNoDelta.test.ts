/**
 * #4108 — a row the app calls SETTLED does not also claim a 24h move.
 *
 * `ChampionshipStageBadges` drew "↑90.9%  ✓ clinched": a 90.9 percentage-POINT
 * delta on a stage the same row calls decided, with the probability itself never
 * printed (the clinched branch replaces it). Alex read the ↑90.9% as the
 * probability, which is the obvious reading of a lone percentage — and the true
 * statement was the stranger of the two.
 *
 * `LadderCardView` renders the same clinched concept and has suppressed its
 * delta since it shipped. Two components, one status, two answers — #4002's
 * shape. This guard is written for the AGREEMENT, not for the row that was
 * noticed: it fails if either side stops gating.
 *
 * 🔴 IN JEST BECAUSE CI COMPILES NO SWIFT (#4302). The behavioural proof is
 * `BainLuckTests/ChampionshipRowLayoutTests.swift`, which hosts the real badge
 * view and measures it — and which no pipeline runs.
 */

import { readFileSync } from "fs";
import { join } from "path";

import { swiftCode, swiftFunctionBody } from "../helpers/swiftSource";

const APP_ROOT = join(__dirname, "../../..", "ios/Bain Luck/Bain Luck");
const CHAMPIONSHIP = join(APP_ROOT, "Components/ChampionshipPathView.swift");
const LADDER = join(APP_ROOT, "Components/LadderCardView.swift");
const LAYOUT = join(APP_ROOT, "Utilities/ChampionshipRowLayout.swift");

const code = (path: string) => swiftCode(readFileSync(path, "utf8"));

function bodyOf(path: string, declaration: string): string {
  const found = swiftFunctionBody(code(path), declaration);
  if (found === null) {
    throw new Error(
      `\`${declaration}\` is gone from ${path}. This guard watches it; repoint the guard if it moved.`,
    );
  }
  return found;
}

describe("both components suppress the delta on a settled row", () => {
  it("ChampionshipStageBadges gates its trend badge on !isClinched", () => {
    const body = bodyOf(CHAMPIONSHIP, "struct ChampionshipStageBadges");
    // Pin the GUARD, not the mere presence of `isClinched` — the clinched branch
    // below references it too, so a scan for the identifier alone would pass on
    // the ungated view this issue is about.
    expect(body).toMatch(/if\s+!isClinched\s*,\s*\n\s*let trend = stage\.trend24h/);
    expect(body).toContain("ChampionshipRowLayout.showsTrendBadge(trend: trend)");
  });

  it("LadderCardView still gates its delta on !clinched", () => {
    // `header`, not `body` — the delta sits in the header row, and slicing the
    // outer `body` silently returns a scope that does not contain it (which is
    // how this assertion first passed a slice ending in `.opacity(...)`).
    const header = bodyOf(LADDER, "private var header: some View");
    expect(header).toContain("if let headlineDelta, !clinched && !eliminated");
  });
});

describe("the badge column follows the widest row, not the clinched one", () => {
  it("badgeWidth narrows only when EVERY row is clinched", () => {
    const fn = bodyOf(LAYOUT, "static func badgeWidth(for stages:");
    // A clinched row is now the NARROWER kind (53.5 pt vs 72+), so `contains`
    // would hand a mixed card a column its ordinary rows cannot fit — #3574
    // with the roles swapped.
    expect(fn).toContain("allSatisfy");
    expect(fn).not.toContain("stages.contains");
    expect(fn).toContain("allClinchedBadgeWidth");
  });

  it("the old any-clinched-widens constant is gone by name", () => {
    // Renamed rather than re-valued, so nothing can keep reading it expecting
    // the old meaning. `allClinchedBadgeWidth` is a different rule, not a
    // different number.
    const src = code(LAYOUT);
    expect(src).toContain("allClinchedBadgeWidth");
    expect(src).not.toMatch(/(?<!all)[Cc]linchedBadgeWidth\b/);
  });
});
