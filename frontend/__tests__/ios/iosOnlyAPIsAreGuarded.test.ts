/**
 * #5074 — the macOS app target stopped compiling, twice, and nobody noticed.
 *
 * The `Bain Luck` target builds for iOS AND macOS. CI compiles no Swift, and no
 * lane builds `-destination platform=macOS` as a matter of course, so a
 * UIKit-only API added to a shared view breaks the Mac app silently and stays
 * broken. Measured 2026-09-10 on `8403d1b5`:
 *
 *   - `OddsChartView.swift:1027`  `Color(.systemBackground)`        — 2026-09-05
 *   - `TournamentHubView.swift:47` `.navigationBarTitleDisplayMode` — 2026-09-08
 *
 * Five days and two days dark respectively, found only because #5057 fixes the
 * macOS menu bar and the fix could not be built to prove it.
 *
 * **THIS FILE IS A PARTIAL NET AND SAYS SO.** It cannot approximate Swift's
 * availability checking; it pins the ONE API whose idiom is uniform enough to
 * check exactly. The durable fix is compiling the macOS destination — in the
 * native lane's gate set now, in CI when a macOS runner is funded (D100). A
 * scan that looked comprehensive here would be worse than one that does not,
 * because it would be trusted in place of the build.
 */

import { readFileSync, existsSync, readdirSync } from "fs";
import { join } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");

function swiftFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return swiftFiles(path);
    return entry.isFile() && entry.name.endsWith(".swift") ? [path] : [];
  });
}

/**
 * `navigationBarTitleDisplayMode` is UIKit-only and is the most-used iOS-only
 * modifier in the target — 26 call sites across 26 files. The idiom is
 * completely uniform: the line before it is `#if os(iOS)`. That uniformity is
 * what makes an exact check possible with no false positives; measured
 * 2026-09-10, 25 of 26 sites already complied and the 26th was the build break.
 *
 * Line-precedence rather than block-nesting on purpose. Tracking `#if`/`#endif`
 * depth would let the check drift into approximating the preprocessor; the
 * house idiom is a one-line guard wrapping a one-line modifier, so that is
 * exactly what is asserted. A legitimate site written some other way should
 * change the idiom deliberately — and this test — rather than slip past.
 */
const IOS_ONLY_MODIFIER = /\.navigationBarTitleDisplayMode\s*\(/;
const IOS_GUARD = /^\s*#if\s+os\(iOS\)\s*$/;

function unguardedSites(source: string): number[] {
  const lines = source.split("\n");
  return lines
    .map((line, i) => ({ line, i }))
    .filter(({ line, i }) => IOS_ONLY_MODIFIER.test(line) && !IOS_GUARD.test(lines[i - 1] ?? ""))
    .map(({ i }) => i + 1);
}

const iosPresent = existsSync(IOS_ROOT);
const d = iosPresent ? describe : describe.skip;

d("iOS-only APIs in the shared app target are platform-guarded (#5074)", () => {
  it("every navigationBarTitleDisplayMode sits behind #if os(iOS)", () => {
    const offenders: string[] = [];
    let sites = 0;

    for (const path of swiftFiles(IOS_ROOT)) {
      const source = readFileSync(path, "utf8");
      sites += (source.match(new RegExp(IOS_ONLY_MODIFIER, "g")) ?? []).length;
      for (const line of unguardedSites(source)) {
        offenders.push(
          `${path.slice(IOS_ROOT.length + 1)}:${line} — unavailable in macOS; wrap in #if os(iOS)`
        );
      }
    }

    expect(offenders).toEqual([]);

    // An empty scan reads as a clean pass — the failure mode the sibling
    // period-label suite exists to stop. The modifier is in ~26 files; a floor
    // well under that catches a moved directory or a bad path without
    // tripping every time a view is deleted.
    expect(sites).toBeGreaterThan(15);
  });

  it("the check can actually fail", () => {
    // The exact shape that shipped, and the exact shape that fixes it.
    expect(unguardedSites(".navigationTitle(name)\n.navigationBarTitleDisplayMode(.inline)")).toEqual([2]);
    expect(
      unguardedSites("#if os(iOS)\n.navigationBarTitleDisplayMode(.inline)\n#endif")
    ).toEqual([]);
  });
});
