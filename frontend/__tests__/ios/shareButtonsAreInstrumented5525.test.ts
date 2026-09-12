/**
 * #5525 — a share button that records nothing.
 *
 * Every share affordance in the app is a declarative `ShareLink`, and `ShareLink`
 * exposes no completion or action callback. So the button a reader actually taps
 * had no writer at all: `discover_interactions` held THREE `action='share'` rows
 * ALL TIME when this shipped, every one of them `surface='web'`. The native zero
 * was read as "nobody shares from the phone". It was "nothing on the phone can
 * say that they did" — an instrumentation hole wearing a behaviour fact's
 * clothes, and every report quoting that zero inherited the error.
 *
 * ═══ WHY A SOURCE SCAN ═══
 *
 * CI COMPILES NO SWIFT. A tenth `ShareLink` added next month compiles, ships, and
 * is silent — there is no type error, no failing assertion, no red anything. The
 * Swift suite can only test the shape of the row once a tap arrives
 * (`ShareInstrumentationTests`); nothing in that target can notice a call site
 * that never calls. This file is the only thing standing between master and the
 * exact defect #5525 was filed for, recurring.
 *
 * ═══ WHY THE MENU SITES ARE LISTED, NOT FIXED ═══
 *
 * A `ShareLink` inside `.contextMenu { }` is rendered by UIKit as a `UIMenu`
 * element, outside the SwiftUI gesture system, so `.recordsShareOpened` is INERT
 * there — attaching it would be worse than leaving it off, because the call site
 * would then read as instrumented. Those four need the Button-and-sheet rewrite,
 * which trades a working share affordance for a row and is scoped separately.
 * They are enumerated here as an EXACT SET so the list cannot quietly grow: a new
 * uninstrumented site has to be added to this file on purpose, with a reason.
 */

import { readFileSync, existsSync, readdirSync } from "fs";
import { join, relative } from "path";

const APP_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const MODIFIER = ".recordsShareOpened";

/**
 * Share sites that CANNOT be gesture-instrumented because they render inside a
 * system menu. `file:count` — the count is asserted too, so a fifth menu item in
 * an already-listed file is a failure rather than an invisible addition.
 */
const MENU_SITES: Record<string, number> = {
  "Components/CardContextMenu.swift": 2,
  "Views/MyStuffView.swift": 2,
};

function swiftFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return swiftFiles(path);
    return entry.isFile() && entry.name.endsWith(".swift") ? [path] : [];
  });
}

/** Comments discuss `ShareLink` at length; only code counts as a call site. */
function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

/**
 * A `ShareLink` is instrumented when `.recordsShareOpened` appears in the
 * modifier chain attached to it. The chain can run to a dozen lines (a card's
 * share icon carries `.buttonStyle`, `.contextMenu` and a whole menu body), so
 * the window is generous and deliberately so: this guard exists to catch a site
 * with NO instrumentation anywhere near it, not to police modifier order.
 */
const WINDOW_LINES = 40;

type Site = { file: string; line: number; instrumented: boolean };

function shareSites(): Site[] {
  const sites: Site[] = [];
  for (const path of swiftFiles(APP_ROOT)) {
    const lines = stripComments(readFileSync(path, "utf8")).split("\n");
    lines.forEach((line, index) => {
      if (!/\bShareLink\s*\(/.test(line)) return;
      const window = lines.slice(index, index + WINDOW_LINES).join("\n");
      sites.push({
        file: relative(APP_ROOT, path).split("\\").join("/"),
        line: index + 1,
        instrumented: window.includes(MODIFIER),
      });
    });
  }
  return sites;
}

const present = existsSync(APP_ROOT);

(present ? describe : describe.skip)("every share button records that it was opened (#5525)", () => {
  const sites = shareSites();

  it("finds the share buttons at all — a scan that matches nothing passes vacuously", () => {
    expect(sites.length).toBeGreaterThanOrEqual(9);
  });

  it("has a `recordsShareOpened` modifier to look for", () => {
    const helper = join(APP_ROOT, "Utilities/ShareInstrumentation.swift");
    expect(existsSync(helper)).toBe(true);
    expect(readFileSync(helper, "utf8")).toContain("func recordsShareOpened");
  });

  it("instruments every share button that is not inside a system menu", () => {
    const uninstrumented = sites
      .filter((site) => !site.instrumented)
      .filter((site) => !(site.file in MENU_SITES))
      .map((site) => `${site.file}:${site.line}`);

    expect(uninstrumented).toEqual([]);
  });

  it("keeps the un-instrumentable menu sites an exact, unchanged set", () => {
    const counted: Record<string, number> = {};
    for (const site of sites) {
      if (!(site.file in MENU_SITES)) continue;
      counted[site.file] = (counted[site.file] ?? 0) + 1;
    }
    expect(counted).toEqual(MENU_SITES);
  });

  it("does not let a menu file quietly acquire a gesture that cannot fire there", () => {
    for (const file of Object.keys(MENU_SITES)) {
      const source = stripComments(readFileSync(join(APP_ROOT, file), "utf8"));
      expect(source).not.toContain(MODIFIER);
    }
  });

  it("spells every recorded source through the one enum, never a literal", () => {
    const owners = ["Views/DiscoverView.swift", "Views/EventDetailView.swift", "Views/FuturesDetailView.swift"];
    for (const file of owners) {
      const source = stripComments(readFileSync(join(APP_ROOT, file), "utf8"));
      const recordingBlocks = source.split(MODIFIER).slice(1);
      const hasShareCallback = /onShare:/.test(source) || recordingBlocks.length > 0;
      if (!hasShareCallback) continue;
      expect(source).toMatch(/ShareSurface\.|surface: \./);
    }
  });
});
