/**
 * #6600 — a featured hub's subtitle is read THROUGH the clock, asserted by
 * reading the Swift.
 *
 * On 2026-09-16, three days after Alexander Zverev won the title, Browse's first
 * card and the top row of a search for "us open" both read "US Open — Live
 * matches, results, title odds", with the app's own event rows printed directly
 * beneath them, every one stamped FINAL · Sep 13. The hub one tap away was
 * already honest ("No match is being played right now", "Settled · Alexander
 * Zverev won the title") and so was the payload, so the false claim lived
 * entirely in the phone's hand-maintained catalog.
 *
 * `FeaturedTournament` now stores `liveSubtitle` and `restingSubtitle` and picks
 * between them in `subtitle(asOf:)`.
 *
 * WHY THIS FILE EXISTS AND `FeaturedTournamentSubtitleTests` DOES NOT SUFFICE.
 * Those XCTest cases prove the function. They cannot prove the two view BODIES
 * call it, and the body is where this defect actually lived — the pre-fix render
 * sites were a bare `tournament.subtitle` inside `featuredGrid` and a bare
 * `hub.subtitle` inside `searchTournamentRow`, invisible to XCTest. A mutation
 * run confirms it: rewriting either call site to `.liveSubtitle` restores the
 * defect on the phone and leaves every Swift test green. The assertions below
 * are what kill that mutant, and they run in CI, which compiles no Swift.
 *
 * The rename is the other half of the guard and the stronger one — a call site
 * that still says `.subtitle` without parentheses no longer compiles. This scan
 * covers what the compiler cannot: a site that adopts the new name and renders
 * one arm of it unconditionally, which is the same lie under a new spelling.
 *
 * SCOPE. `IOS_ROOT` is the phone/iPad/Mac app. The watch app has no featured
 * catalog at all — `FeaturedTournaments.swift` is not a member of its target and
 * `grep` finds no `FeaturedTournament` under `BainLuckWatch Watch App/` — so
 * there is no second copy to reach, rather than one being excused.
 */

import { readFileSync, existsSync, readdirSync } from "fs";
import { join } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const CATALOG = join(IOS_ROOT, "Utilities/FeaturedTournaments.swift");

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

/**
 * A site rendering one arm of the pair directly instead of asking the clock.
 *
 * The declarations and the picker itself necessarily name both arms, so the
 * catalog file is the one place these are legitimate and is excluded by path
 * rather than by pattern — a pattern subtle enough to tell a declaration from a
 * use is a pattern subtle enough to miss a use.
 */
const UNCLOCKED_TELLS: Array<[string, RegExp]> = [
  ["renders .liveSubtitle directly instead of subtitle(asOf:)", /\.liveSubtitle\b/],
  ["renders .restingSubtitle directly instead of subtitle(asOf:)", /\.restingSubtitle\b/],
];

// A path typo would otherwise read as a clean pass — the unrunnable-check
// failure mode this whole file exists to stop.
describe("the scan can actually see the files it claims to check", () => {
  it("finds the catalog", () => {
    expect(existsSync(CATALOG)).toBe(true);
  });

  it("finds the two views that draw a featured hub", () => {
    for (const rel of ["Views/LeaguesView.swift", "Views/SearchView.swift"]) {
      expect(existsSync(join(IOS_ROOT, rel))).toBe(true);
    }
  });

  it("walks a real tree", () => {
    expect(swiftFiles(IOS_ROOT).length).toBeGreaterThan(50);
  });
});

describe("#6600 — nothing outside the catalog picks an arm for itself", () => {
  it("no view renders liveSubtitle or restingSubtitle without the clock", () => {
    const offences: string[] = [];

    for (const file of swiftFiles(IOS_ROOT)) {
      if (file === CATALOG) continue;
      const source = stripComments(readFileSync(file, "utf8"));
      for (const [why, pattern] of UNCLOCKED_TELLS) {
        if (pattern.test(source)) {
          offences.push(`${file.replace(IOS_ROOT, "")}: ${why}`);
        }
      }
    }

    expect(offences).toEqual([]);
  });

  it("both render sites do go through subtitle(asOf:)", () => {
    // The positive half. An empty offence list is also what a scan returns when
    // the featured card has been deleted, or renamed out from under it, or
    // moved to a file the walk does not reach — three ways to pass by drawing
    // nothing. This asserts the surface is still a surface.
    for (const rel of ["Views/LeaguesView.swift", "Views/SearchView.swift"]) {
      const source = stripComments(readFileSync(join(IOS_ROOT, rel), "utf8"));
      expect(source).toMatch(/\.subtitle\(/);
    }
  });
});

describe("#6600 — the shipped catalog cannot promise a live state it never dates", () => {
  // The Swift suite asserts this over the parsed catalog. Repeated here over the
  // source because CI compiles no Swift, so on a red-Swift day this is the only
  // thing standing between a new hub and the defect it just fixed.
  const source = stripComments(readFileSync(CATALOG, "utf8"));

  // Everything between `let featuredTournaments` and its closing bracket.
  const shipped = source.slice(source.indexOf("let featuredTournaments"));

  it("every entry declares both arms", () => {
    const live = shipped.match(/liveSubtitle:/g) ?? [];
    const resting = shipped.match(/restingSubtitle:/g) ?? [];
    expect(live.length).toBeGreaterThan(0);
    expect(resting.length).toBe(live.length);
  });

  it("no resting line claims a live state", () => {
    for (const [, value] of shipped.matchAll(/restingSubtitle:\s*"([^"]*)"/g)) {
      expect(value.toLowerCase()).not.toContain("live");
    }
  });

  it("an entry whose live line says \"live\" also says until when", () => {
    const entries = shipped.split("FeaturedTournament(").slice(1);
    for (const entry of entries) {
      const live = entry.match(/liveSubtitle:\s*"([^"]*)"/)?.[1] ?? "";
      if (!live.toLowerCase().includes("live")) continue;
      const through = entry.match(/liveThrough:\s*"([^"]*)"/)?.[1];
      expect(through).toBeDefined();
      // Parseable as an instant, not merely present.
      expect(Number.isNaN(Date.parse(through as string))).toBe(false);
    }
  });
});
