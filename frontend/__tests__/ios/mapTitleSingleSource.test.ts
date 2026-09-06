/**
 * #3630 — a layout branch chooses LAYOUT, never WORDS.
 *
 * The iPad and Mac event page draws its market maps in two columns; the iPhone
 * stacks them. That branch (`MarketMapView.useColumns`) had also been choosing
 * the card's TITLE, pinned to the literals `"Full game margin map"` and
 * `"Full game total map"` — so every unit-aware title the phone gained from
 * #3509 and #3533 was invisible on the wider surfaces.
 *
 * Photographed 2026-09-06 on the same event, in the same minute, on two
 * simulators (`artifacts-native-041/BEFORE-ipad-swiatek-15305580-s600.png`
 * beside `artifacts-native-040/swiatek-15305580-s600.png`):
 *
 * | card   | iPhone            | iPad                    |
 * |--------|-------------------|-------------------------|
 * | margin | `Set margin map`  | `Full game margin map`  |
 * | totals | `Games map`       | `Full game total map`   |
 *
 * Zheng–Swiatek's rungs are `Set Handicap ±1.5`, so the iPad headed a map of
 * SETS with the word "game" — which in tennis is a real and *different* unit,
 * quoted on the same page (`Game Spread ±5.5`, `Match O/U 21.5` games).
 *
 * 🔴 WHY THE EXISTING TESTS COULD NOT SEE IT. `MarginQuotedUnitTests` and
 * `MarketQuotedUnitTests` pin `SportVocab.marginTitle(quotedBy:)` and
 * `.totalTitle(quotedBy:)` thoroughly, and every one of them was green. The
 * defect was never in the selector — it was a CALL SITE that did not call it.
 * So this guards the call sites, and it discovers them by shape rather than by
 * an allowlist, because an allowlist cannot catch the branch nobody thought to
 * add.
 *
 * It lives in jest because jest is a deploy gate here and the Swift test target
 * is not reachable from CI — the same reason `teamShortNameSingleSource` does.
 */

import { readFileSync, existsSync, readdirSync } from "fs";
import { join } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const MAP_VIEW = join(IOS_ROOT, "Components/MarketMapView.swift");

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

/** Newlines are not meaningful here and a ternary is routinely wrapped over
 *  three lines — which is exactly how the totals literal was written. */
function collapse(source: string): string {
  return stripComments(source).replace(/\s+/g, " ");
}

/**
 * The names in a file that stand for "this is a wide layout".
 *
 * `sizeClass` itself, plus any `Bool` computed from it or from `os(macOS)` —
 * `useColumns` is one such, and naming only `sizeClass` would miss it, which is
 * the whole point. Discovered per file so a new alias is covered on arrival.
 */
function layoutPredicates(source: string): string[] {
  const found = new Set<string>(["sizeClass"]);
  const decl = /\b(?:var|let)\s+(\w+)\s*:\s*Bool\s*\{/g;
  let m: RegExpExecArray | null;
  while ((m = decl.exec(source)) !== null) {
    // The body has to end at its OWN closing brace. A fixed-size window runs
    // past it into whatever follows, which reported `isLive` in
    // `EventDetailView` as a layout predicate on the first run — it is a
    // CONTENT predicate, and a sentence that changes with the clock is exactly
    // the thing this rule must not forbid.
    const body = braceBody(source, decl.lastIndex - 1);
    if (/sizeClass|os\(macOS\)|idiom|isPad\b|isMac\b/.test(body)) found.add(m[1]);
  }
  return [...found];
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

describe("#3630 — a layout branch may not choose the words", () => {
  it("finds the view it is guarding", () => {
    expect(existsSync(MAP_VIEW)).toBe(true);
  });

  /**
   * The specific regression: every title handed to `mapCard` is an expression,
   * never a literal. The full-match cards read `SportVocab`; the half cards
   * pass their own `label`. A quoted string here is a title that has stopped
   * asking what unit the rungs are quoted in.
   */
  it("never hands mapCard a hardcoded title", () => {
    const text = collapse(readFileSync(MAP_VIEW, "utf8"));
    const literals = [...text.matchAll(/\btitle:\s*("(?:[^"\\]|\\.)*")/g)].map((m) => m[1]);
    expect(literals).toEqual([]);
  });

  /**
   * And the positive half — the selectors are still actually consulted. Without
   * this, deleting both calls would "fix" the test above.
   */
  it("titles the full-match maps from the unit their rungs declare", () => {
    const text = collapse(readFileSync(MAP_VIEW, "utf8"));
    expect(text).toContain("title: vocab.marginTitle(quotedBy:");
    expect(text).toContain("title: vocab.totalTitle(quotedBy:");
  });

  /**
   * The class, across the whole target: no size-class branch anywhere picks
   * between two pieces of copy. Widths, paddings, column counts and whole
   * subtrees are what that branch is for; a sentence is not.
   */
  it("lets no size-class branch pick between two strings", () => {
    const offenders: string[] = [];
    for (const file of swiftFiles(IOS_ROOT)) {
      const text = collapse(readFileSync(file, "utf8"));
      for (const name of layoutPredicates(text)) {
        const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        const thenLiteral = new RegExp(`\\b${escaped}[^?"]{0,40}\\?\\s*"`);
        const elseLiteral = new RegExp(`\\b${escaped}[^?"]{0,40}\\?[^,"]{0,160}?:\\s*"`);
        if (thenLiteral.test(text) || elseLiteral.test(text)) {
          offenders.push(`${file.slice(IOS_ROOT.length + 1)} — via \`${name}\``);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
