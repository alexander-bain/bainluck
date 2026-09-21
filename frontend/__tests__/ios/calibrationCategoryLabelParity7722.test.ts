/**
 * #7722 — the Accuracy screen names a league the same way on both surfaces, or
 * CI says so.
 *
 * THE BUG. The Category Breakdown printed **"Aussierules Afl"** and
 * **"Rugbyleague Nrl"** in the app while web printed **AFL** and **NRL** from
 * the same payload — two database keys with their underscores swapped for
 * spaces, in a table whose entire job is looking trustworthy.
 *
 * It was not two missing labels. Web answers this class with BOTH halves —
 * `categoryLabel` reads `DISPLAY_NAMES[cat] || nicheCatLabel(cat)`, so an
 * uncurated key still reaches the LEAGUE-AWARE labeller — and
 * `calibrationCategories.ts` says why in its own header: the page has a
 * *scheduled* failure mode, and a map entry fixes today's instance while leaving
 * the mechanism. The app had the map and a bare title-caser, so it kept the
 * mechanism, and upstream growth fired it on two keys the same week.
 *
 * WHY THIS GUARD LIVES IN JEST. CI compiles no Swift (#4302, notice 10's iOS
 * clause), so `CalibrationPublishedCategoryLabelTests7722` — which owns the
 * BEHAVIOUR, over the measured published set — is reachable only from a macOS
 * runner. This reads the Swift SOURCE and pins the arrangement that behaviour
 * depends on, because a jest file is a deploy gate and a Swift file is not.
 *
 * WHAT IT IS FOR, beyond re-asserting the fix: the two surfaces must stay keyed
 * IDENTICALLY (#3557). A label curated on one surface and derived on the other
 * is a drift waiting for one of the two derivations to move, and the drift is
 * invisible until a reader has both screens open.
 *
 * EVERY EXTRACTOR HERE PINS A COUNT. A quote-matching scan that finds nothing
 * returns an empty result, and `expect([]).toEqual([])` is green — so a guard
 * built on extraction agrees with anything unless the extraction is itself
 * asserted to have happened.
 */

import { readFileSync } from "fs";
import { join } from "path";
import { categoryLabel, DISPLAY_NAMES } from "@/lib/calibrationCategories";
import { LEAGUE_DISPLAY } from "@/lib/sportCategories";

const REPO = join(__dirname, "../../..");
const IOS_VM = join(REPO, "ios/Bain Luck/Bain Luck/ViewModels/CalibrationViewModel.swift");
const IOS_NICHE = join(REPO, "ios/Bain Luck/Bain Luck/Utilities/NicheCategoryLabel.swift");
const IOS_SPORTS = join(REPO, "ios/Bain Luck/Bain Luck/Utilities/SportDisplayNames.swift");

/** The two keys, written once. Both surfaces must spell them the same bytes. */
const AFL = "aussierules_afl";
const NRL = "rugbyleague_nrl";

function read(file: string): string {
  try {
    return readFileSync(file, "utf8");
  } catch (err) {
    throw new Error(
      `#7722 category-label parity gate could not read ${file}: ${String(err)}. ` +
        `If the file moved, update this guard — do not delete the check.`,
    );
  }
}

/**
 * Both Swift files explain this bug in their PROSE using the very tokens the
 * scans below look for — `aussierules_afl`, `"AFL"`, `nicheCategoryLabel`,
 * `toTitleCaseAcronymSafe` — so a raw scan would read each header's explanation
 * as the code it describes. `///` doc comments and `//` line comments both.
 */
function stripSwiftComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "");
}

/**
 * The body of a named Swift collection literal.
 *
 * The closing bracket is found as the first line that holds nothing but `]`,
 * not as the first `"\n]"` — these maps live at two indentation levels
 * (`categoryDisplayNames` is a class member, `nicheLeagueNames` is a file-level
 * global) and a column-0 scan silently misses the indented one.
 */
function swiftLiteralBody(source: string, name: string): string {
  const at = source.indexOf(`let ${name}`);
  if (at === -1) throw new Error(`\`let ${name}\` not found — did it move or get renamed?`);
  const open = source.indexOf("[", source.indexOf("=", at));
  if (open === -1) throw new Error(`could not find the \`${name}\` literal's opening bracket`);
  const rest = source.slice(open);
  const end = rest.search(/\n[ \t]*\]/);
  if (end === -1) throw new Error(`could not bound the \`${name}\` literal`);
  return rest.slice(0, end);
}

/** `"key": "value"` pairs inside a named Swift dictionary literal. */
function swiftDict(source: string, name: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const m of swiftLiteralBody(source, name).matchAll(/"([^"]+)"\s*:\s*"([^"]*)"/g)) {
    out[m[1]] = m[2];
  }
  return out;
}

/** Bare quoted tokens inside a named Swift `Set<String>` literal. */
function swiftStringSet(source: string, name: string): string[] {
  return [...swiftLiteralBody(source, name).matchAll(/"([^"]+)"/g)].map((m) => m[1]);
}

const vm = stripSwiftComments(read(IOS_VM));
const niche = stripSwiftComments(read(IOS_NICHE));
const sports = stripSwiftComments(read(IOS_SPORTS));

describe("#7722 — web already names both leagues, and it is the reference", () => {
  it("renders AFL and NRL through the real label function", () => {
    expect(categoryLabel(AFL)).toBe("AFL");
    expect(categoryLabel(NRL)).toBe("NRL");
  });

  /**
   * Where the label comes from matters as much as what it is: neither key is in
   * `DISPLAY_NAMES`, so web reaches these strings through its FALLBACK. That is
   * the arrangement the app is being held to below — copying the two strings
   * into the app's map would match the output and not the mechanism.
   */
  it("reaches them through the fallback, not the curated page map", () => {
    expect(DISPLAY_NAMES[AFL]).toBeUndefined();
    expect(DISPLAY_NAMES[NRL]).toBeUndefined();
    expect(LEAGUE_DISPLAY[AFL]).toBe("AFL");
    expect(LEAGUE_DISPLAY[NRL]).toBe("NRL");
  });
});

describe("#7722 — the app's table falls through to the league-aware labeller", () => {
  /**
   * The ship, as an arrangement. `categoryDisplayNames[category] ??
   * nicheCategoryLabel(category)` is `DISPLAY_NAMES[cat] || nicheCatLabel(cat)`
   * in Swift. The `not.toMatch` is the load-bearing half: reverting the fallback
   * to the bare title-caser is exactly how both rows printed a raw key, and it
   * is a one-token edit.
   */
  it("pins categoryDisplayName's fallback to nicheCategoryLabel", () => {
    const body = vm.match(
      /static func categoryDisplayName\(_ category: String\) -> String \{([\s\S]*?)\n {4}\}/,
    );
    expect(body).not.toBeNull();
    const source = body![1];
    expect(source).toMatch(/categoryDisplayNames\[category\]\s*\?\?\s*nicheCategoryLabel\(category\)/);
    expect(source).not.toMatch(/toTitleCaseAcronymSafe/);
  });

  it("curates AFL in the app's league vocabulary, spelled as web spells it", () => {
    const names = swiftDict(niche, "nicheLeagueNames");
    expect(Object.keys(names).length).toBeGreaterThanOrEqual(5);
    expect(names[AFL]).toBe(LEAGUE_DISPLAY[AFL]);
  });

  /**
   * NRL is DERIVED rather than curated on this surface — the prefix drops
   * because `rugbyleague` is a known sport family, and `nrl` is shouted because
   * the chip acronym set carries it. Two tables a future edit could touch for
   * unrelated reasons, neither of them named "NRL", so both are pinned here or
   * the row silently becomes "Rugbyleague Nrl" again.
   */
  it("pins the two tables NRL is derived from", () => {
    const acronyms = swiftStringSet(niche, "nicheKeyAcronyms");
    expect(acronyms.length).toBeGreaterThanOrEqual(15);
    expect(acronyms).toContain("nrl");

    const families = swiftDict(sports, "sportFamilyDisplayNames");
    expect(Object.keys(families).length).toBeGreaterThanOrEqual(10);
    expect(families).toHaveProperty("rugbyleague");
  });

  /**
   * 🔴 #7532's trap, and the reason AFL is a curated entry rather than a token
   * added to the acronym set. `aussierules` is deliberately NOT a sport family
   * here: adding it would drop the prefix for calibration and change every
   * Discover badge and search row in the app at the same time. Adding the bare
   * `aussierules` / `rugbyleague` key to the calibration map would be worse —
   * `normalizedCategory` rolls a key up only when its base is in that map, so
   * the parent would re-group the buckets the table counts and collapse AFLW
   * onto AFL's label.
   */
  it("keeps the parent keys out of both maps", () => {
    expect(swiftDict(sports, "sportFamilyDisplayNames")).not.toHaveProperty("aussierules");
    const page = swiftDict(vm, "categoryDisplayNames");
    expect(Object.keys(page).length).toBeGreaterThanOrEqual(17);
    expect(page).not.toHaveProperty("aussierules");
    expect(page).not.toHaveProperty("rugbyleague");
  });
});

describe("#7722 — the surfaces are keyed identically (#3557)", () => {
  /**
   * The two keys are carried DIFFERENTLY on purpose, and the asymmetry is the
   * thing to record. AFL is curated on both surfaces, so its key must be spelled
   * with identical bytes in both files or one surface stops matching the
   * payload. NRL is curated on web and DERIVED in the app, so the key appears
   * nowhere in the Swift source at all — and asserting it did would be the
   * easiest possible way to write a check that passes for the wrong reason.
   */
  it("spells the curated key the same bytes on both sides, and derives the other", () => {
    expect(LEAGUE_DISPLAY).toHaveProperty(AFL);
    expect(swiftDict(niche, "nicheLeagueNames")).toHaveProperty(AFL);

    expect(LEAGUE_DISPLAY).toHaveProperty(NRL);
    expect(`${niche}${vm}${sports}`).not.toContain(NRL);
  });

  /**
   * `table_tennis` is the third published row whose label the app derived and
   * web curated. Same string on both surfaces today, which is exactly why it is
   * worth pinning: nothing would have reported the day one derivation moved.
   */
  it("agrees on table_tennis, which web curates and the app now does too", () => {
    expect(DISPLAY_NAMES["table_tennis"]).toBe("Table Tennis");
    expect(categoryLabel("table_tennis")).toBe("Table Tennis");
    expect(swiftDict(vm, "categoryDisplayNames")["table_tennis"]).toBe("Table Tennis");
  });
});
