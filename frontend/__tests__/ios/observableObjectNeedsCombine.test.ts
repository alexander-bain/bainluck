/**
 * CERT-782 — THE BUILD PROBE. An `ObservableObject` conformance in a file that
 * does not `import Combine` DOES NOT BUILD in this project.
 *
 * 🔴 WHAT HAPPENED, because it will happen again. latency/121 shipped
 * `ScreenTimingBox: ObservableObject` in a file importing only `Foundation` and
 * `SwiftUI`. Every target here sets
 * `SWIFT_UPCOMING_FEATURE_MEMBER_IMPORT_VISIBILITY = YES`, under which a
 * protocol is NOT visible through another module's re-export — SwiftUI re-exports
 * Combine, so `ObservableObject` resolves in a plain build and vanishes under
 * this feature:
 *
 *     ScreenTiming.swift:350:20: error: type 'ScreenTimingBox' does not conform
 *                                       to protocol 'ObservableObject'
 *
 * The author's gate had been `swiftc -typecheck` on the single file, which does
 * NOT apply the target's build settings — and the defect lived entirely in a
 * build setting. A file type-checking in isolation is a weaker claim than a
 * target building, and the weaker one was reported as if it covered the stronger.
 *
 * 🔴 WHY THIS GUARD IS IN JEST AND NOT IN XCTEST. `xcodebuild` is not reachable
 * from CI (no macOS runner, and Firebase's binary SPM artifacts are not
 * downloadable in the agent sandbox), so the Swift test target cannot fail a
 * merge. Jest can — `frontend-build` runs `npm run test:ci` and `deploy` depends
 * on it. A guard that cannot fail a build is documentation, not a gate.
 *
 * This does not replace building the app. It catches ONE build-breaking class,
 * cheaply, on every push, in the only place that can stop a merge.
 */

import { existsSync, readdirSync, readFileSync, statSync } from "fs";
import { join } from "path";

const REPO_ROOT = join(__dirname, "../../..");
const IOS_ROOT = join(REPO_ROOT, "ios");
const PBXPROJ = join(IOS_ROOT, "Bain Luck/Bain Luck.xcodeproj/project.pbxproj");

/**
 * Comments are stripped before scanning. Without this the guard reads
 * `/// Deliberately NOT an \`ObservableObject\`` as a conformance — which is a
 * real sentence in `ScreenTiming.swift`, put there by this very repair.
 */
function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/\/\/[^\n]*/g, " ");
}

/**
 * Every `class`/`extension` declaration head that names `ObservableObject` in
 * its conformance list. `[^{]*` crosses newlines in JS, so a conformance list
 * wrapped over several lines is still one head.
 */
const DECL = /(?:^|\n)\s*(?:@[\w.]+(?:\([^)]*\))?\s+)*(?:public\s+|internal\s+|private\s+|fileprivate\s+|open\s+)?(?:final\s+)?(?:class|extension)\s+\w+\s*:[^{]*\{/g;

interface Conformance {
  file: string;
  head: string;
}

function conformancesIn(relPath: string, source: string): Conformance[] {
  const clean = stripComments(source);
  const found: Conformance[] = [];
  for (const match of clean.matchAll(DECL)) {
    if (/[:,]\s*ObservableObject\b/.test(match[0])) {
      found.push({ file: relPath, head: match[0].trim().replace(/\s+/g, " ").slice(0, 120) });
    }
  }
  return found;
}

/** `import Combine` on its own line — not inside a comment, not a substring. */
function importsCombine(source: string): boolean {
  return /^[ \t]*import\s+Combine[ \t]*$/m.test(stripComments(source));
}

function swiftFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry === "build" || entry === "DerivedData" || entry.endsWith(".xcodeproj")) continue;
      out.push(...swiftFiles(full));
    } else if (entry.endsWith(".swift")) {
      out.push(full);
    }
  }
  return out;
}

describe("an ObservableObject conformance imports Combine (the build probe)", () => {
  // 🔴 A HARD FAILURE, never a skip. The whole point of this file is to catch a
  // build break; a guard that quietly passes because it was pointed at nothing
  // is the failure mode it exists to prevent.
  it("can see the iOS sources and the project file it reasons about", () => {
    expect(existsSync(IOS_ROOT)).toBe(true);
    expect(existsSync(PBXPROJ)).toBe(true);
  });

  it("the build setting that makes this rule real is still on", () => {
    // If MemberImportVisibility is ever turned OFF, this rule stops being a
    // build requirement and this guard becomes cargo cult. Better to go red and
    // be deleted deliberately than to keep passing for a reason that expired.
    const pbxproj = readFileSync(PBXPROJ, "utf8");
    expect(pbxproj).toContain("SWIFT_UPCOMING_FEATURE_MEMBER_IMPORT_VISIBILITY = YES");
    expect(pbxproj).not.toContain("SWIFT_UPCOMING_FEATURE_MEMBER_IMPORT_VISIBILITY = NO");
  });

  it("no Swift file conforms to ObservableObject without importing Combine", () => {
    const offenders: Conformance[] = [];
    let conformanceCount = 0;

    for (const path of swiftFiles(IOS_ROOT)) {
      const source = readFileSync(path, "utf8");
      const rel = path.slice(REPO_ROOT.length + 1);
      const conformances = conformancesIn(rel, source);
      conformanceCount += conformances.length;
      if (conformances.length > 0 && !importsCombine(source)) {
        offenders.push(...conformances);
      }
    }

    expect(offenders.map((o) => `${o.file}: ${o.head}`)).toEqual([]);

    // 🔴 THE VACUITY COMPANION. A regex that stops matching anything passes
    // this file silently and forever. The tree had 30 conformances when this
    // was written; a floor well under that survives ordinary churn but not a
    // broken parse.
    expect(conformanceCount).toBeGreaterThanOrEqual(20);
  });

  it("the detector actually detects — the arm that proves this file can go red", () => {
    // Without this, a typo in DECL would make every assertion above vacuous and
    // nothing would ever say so. Same shape as the real defect: SwiftUI only,
    // no Combine.
    const planted = [
      "import Foundation",
      "import SwiftUI",
      "",
      "@MainActor",
      "public final class ScreenTimingBox: ObservableObject {",
      "    public init() {}",
      "}",
    ].join("\n");

    expect(conformancesIn("planted.swift", planted)).toHaveLength(1);
    expect(importsCombine(planted)).toBe(false);

    // ...and the fix clears it, so the guard is not simply always-red.
    const repaired = planted.replace("import Foundation", "import Combine\nimport Foundation");
    expect(conformancesIn("repaired.swift", repaired)).toHaveLength(1);
    expect(importsCombine(repaired)).toBe(true);
  });

  it("a doc comment naming ObservableObject is not a conformance", () => {
    // `ScreenTiming.swift` documents why its box is deliberately NOT observable.
    // A guard that read prose as code would be red on the very repair that
    // fixed the defect — and would then be "fixed" by deleting the explanation.
    const commented = [
      "import SwiftUI",
      "",
      "/// Deliberately NOT an `ObservableObject`: nothing observes it.",
      "// class Legacy: ObservableObject {}",
      "@MainActor",
      "public final class ScreenTimingBox {",
      "    public init() {}",
      "}",
    ].join("\n");

    expect(conformancesIn("commented.swift", commented)).toEqual([]);
  });
});
