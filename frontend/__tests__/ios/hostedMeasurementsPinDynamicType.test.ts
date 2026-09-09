/**
 * #4207 — a test's verdict may not depend on the simulator's Dynamic Type setting.
 *
 * `UIHostingController` and `ImageRenderer` both inherit the PROCESS's content size
 * category, so a hosted measurement resolves `Font.caption` against whatever the
 * simulator happens to be set to. Measured on the same code, same machine, minutes
 * apart:
 *
 *     simulator content_size = large   →  1711 tests, 44 failures
 *     simulator content_size = a11y5   →  1711 tests, 46 failures
 *
 * The two extra were `ChampionshipRowLayoutTests` and `CalibrationCurveWidthTests`,
 * neither touched by the diff under test. That is worse than a flake: it accuses an
 * innocent diff in a module its author never opened, and it clears itself when they
 * look again. native/079 hit one; native/081 hit both, off a simulator left at a11y5
 * after photographing an accessibility frame — which this lane does daily.
 *
 * ═══ WHY A SOURCE SCAN ═══
 *
 * CI COMPILES NO SWIFT. The Swift suite passing at both settings (proven: 1698/44 at
 * `large` AND at a11y5, the same 44 being master's own `TeamShortNamePairTests` red)
 * is a fact about one laptop at one moment. Nothing but this file stands between a
 * seventeenth rendering site written the old way and master.
 *
 * ═══ WHAT THIS FILE DOES NOT CLAIM ═══
 *
 * That every test is hermetic. Locale, time zone and the device the destination names
 * are all still ambient. This closes the one that has now cost two lanes a debugging
 * detour, and it closes it as an EXACT SET so a new camera has to be added here on
 * purpose.
 */

import { readFileSync, existsSync, readdirSync } from "fs";
import { join } from "path";

const TESTS_ROOT = join(__dirname, "../../../ios/Bain Luck/BainLuckTests");
const HELPER = "HostedMeasurement.swift";

function swiftFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return swiftFiles(path);
    return entry.isFile() && entry.name.endsWith(".swift") ? [path] : [];
  });
}

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

/** The two ambient cameras. Neither takes a size unless it is handed one. */
const CAMERAS: Array<[string, RegExp]> = [
  ["UIHostingController", /UIHostingController\(rootView:/],
  ["ImageRenderer", /ImageRenderer\(content:/],
];

const present = existsSync(TESTS_ROOT) && existsSync(join(TESTS_ROOT, HELPER));
const d = present ? describe : describe.skip;

d("#4207 — a rendered measurement pins its own Dynamic Type", () => {
  const files = () => swiftFiles(TESTS_ROOT);

  it("the scan is looking at the real test target", () => {
    // A path typo would otherwise read as a clean pass — the failure mode a
    // source scan is most prone to, and the reason this assertion is first.
    const names = files().map((f) => f.slice(TESTS_ROOT.length + 1));
    expect(names.length).toBeGreaterThan(30);
    expect(names).toContain(HELPER);
    expect(names).toContain("ChampionshipRowLayoutTests.swift");
    expect(names).toContain("CalibrationCurveWidthTests.swift");
  });

  it.each(CAMERAS)("%s is constructed in one place only", (_name, pattern) => {
    const offenders = files()
      .filter((path) => pattern.test(stripComments(readFileSync(path, "utf8"))))
      .map((path) => path.slice(TESTS_ROOT.length + 1))
      .sort();

    // An EXACT set, not "at most a few". A seventeenth site is red, and so is
    // deleting the helper — either way somebody has made a decision on purpose.
    expect(offenders).toEqual([HELPER]);
  });

  it.each(CAMERAS)("the %s scan would have fired before the fix", (name, pattern) => {
    // Copied verbatim from origin/master 95b6b141, not written to match.
    const prefix: Record<string, string> = {
      UIHostingController: `        let host = UIHostingController(rootView: view.frame(width: width))`,
      ImageRenderer: `        let renderer = ImageRenderer(content: view)`,
    };
    expect([name, pattern.test(prefix[name])]).toEqual([name, true]);
  });

  describe("the helper", () => {
    const helper = () => readFileSync(join(TESTS_ROOT, HELPER), "utf8");

    it("pins the size on both cameras and defaults to the system default", () => {
      const source = stripComments(helper());
      expect(source).toContain("UIHostingController(rootView: view.environment(\\.dynamicTypeSize, size))");
      expect(source).toContain("ImageRenderer(content: view.environment(\\.dynamicTypeSize, size))");
      // `.large` IS the system default. A helper that defaulted to an
      // accessibility size would be hermetic and would measure the wrong thing.
      expect(source.match(/at size: DynamicTypeSize = \.large/g)).toHaveLength(2);
    });

    it("is REACHED — by every site that used to construct its own", () => {
      // #4134's lesson: a guard that proves a helper exists, while the tree still
      // does it the old way somewhere, is a guard on nothing. The counts are the
      // sites this ship converted; they may only ever grow.
      const callers = files()
        .filter((path) => !path.endsWith(HELPER))
        .map((path) => stripComments(readFileSync(path, "utf8")));
      const count = (needle: string) =>
        callers.reduce((n, src) => n + (src.split(needle).length - 1), 0);

      expect(count("hostForMeasurement(")).toBeGreaterThanOrEqual(10);
      expect(count("rendererForMeasurement(")).toBeGreaterThanOrEqual(16);
    });

    it("still lets a test ask for an accessibility size on purpose", () => {
      // The point is that the size is an ARGUMENT, not that it is always .large.
      // `GameSegmentTeamBadgeWidthTests` measures across sizes deliberately and
      // must keep being able to.
      const badges = stripComments(
        readFileSync(join(TESTS_ROOT, "GameSegmentTeamBadgeWidthTests.swift"), "utf8")
      );
      expect(badges).toContain("rendererForMeasurement(view, at: size)");
    });
  });
});
