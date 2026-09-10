/**
 * #4031 / #3989: THE CONCEPT CARD'S FIELD QUALIFIER, PINNED ON BOTH CLIENTS.
 *
 * `ConceptCard.tsx`'s own comment says its grammar "mirrors the native concept
 * card's grammar (name · probability chip · movement · 'of N') so the two
 * surfaces print the same fact the same way". They diverged by one word for two
 * days: #3989 fixed web to render `field of 30`, and native kept the bare
 * `of 30` — which, read aloud after the probability chip, is "seventy-five
 * percent OF THIRTY", an arithmetic claim (22.5) rather than a field size.
 *
 * This file exists so the two halves cannot drift apart again by one noun.
 *
 * ── the trap this file had to be written around ──────────────────────────────
 *
 * Both source files discuss the defect in prose. `ConceptCard.tsx` carries
 * "#3989: the bare `of 30` read aloud as ..." in a JSX comment, and the Swift
 * card carries the same reasoning. A naive `source.includes("field of")` would
 * therefore pass on the COMMENT while the rendered string said something else —
 * a guard that cannot fail is worse than no guard, because it reports a pass.
 * So every assertion below runs against comment-stripped source.
 *
 * Native is asserted against SOURCE for the reason `periodLabelSingleSource.test.ts`
 * gives: jest is a deploy gate here and the Swift target is not reachable from it.
 * The behavioural half lives in `BainLuckTests/ConceptFieldQualifierTests.swift`,
 * which executes `NativeConceptDiscoverCard.fieldSizeLabel` over the same cases.
 */

import { readFileSync, existsSync } from "fs";
import { join } from "path";

const REPO_ROOT = join(__dirname, "../../..");

const NATIVE_CARD = join(
  REPO_ROOT,
  "ios/Bain Luck/Bain Luck/Components/DiscoverConceptCard.swift"
);
const WEB_CARD = join(REPO_ROOT, "frontend/components/discover/ConceptCard.tsx");

// A path typo must not read as a clean pass — an unrunnable check and a passing
// check are indistinguishable from the outside (gotcha #54's cousin).
for (const path of [NATIVE_CARD, WEB_CARD]) {
  if (!existsSync(path)) {
    throw new Error(`the guard cannot see its subject: ${path}`);
  }
}

/**
 * Remove block comments, line comments and JSX comment wrappers, so an assertion
 * about what the card PRINTS cannot be satisfied by what the card SAYS ABOUT
 * ITSELF. Deliberately crude: it over-strips string literals containing "//",
 * which neither of these two files has, and over-stripping can only make an
 * assertion harder to satisfy, never easier.
 */
function code(path: string): string {
  return readFileSync(path, "utf8")
    .replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, " ") // {/* jsx comment */}
    .replace(/\/\*[\s\S]*?\*\//g, " ") // /* block */
    .replace(/^\s*\/\/.*$/gm, " ") // // line
    .replace(/\s+/g, " ");
}

describe("#4031 — the concept card's field qualifier names the field", () => {
  it("the comment stripper actually strips (this file's own premise)", () => {
    // If this ever fails, every other assertion here is meaningless, so it is
    // asserted rather than assumed.
    const stripped = code(WEB_CARD);
    expect(stripped).not.toContain("read aloud as");
  });

  it("native prints the noun, not a bare 'of N'", () => {
    const swift = code(NATIVE_CARD);
    expect(swift).toContain('"field of \\(fieldSize)"');
    expect(swift).not.toMatch(/Text\(\s*"of \\\(/);
  });

  it("web prints the noun, not a bare 'of N'", () => {
    const tsx = code(WEB_CARD);
    expect(tsx).toMatch(/field of \{\s*leader\.field_size\s*\}/);
  });

  it("both clients keep the head-to-head guard at the same boundary", () => {
    // A two-way fight needs no qualifier. #4031's verification note names a live
    // UFC bout at field_size 2 that must keep printing nothing. If one client
    // moves this boundary and the other does not, the surfaces disagree again —
    // this time about WHETHER to speak rather than about the words.
    expect(code(NATIVE_CARD)).toMatch(/fieldSize\s*>\s*2/);
    expect(code(WEB_CARD)).toMatch(/leader\.field_size\s*>\s*2/);
  });

  it("native routes the qualifier through one testable helper", () => {
    // The string must be built somewhere `@testable import` can reach, or the
    // Swift half of this guard can only paraphrase the rule. `private func` on a
    // View is unreachable; `static func` is not.
    expect(code(NATIVE_CARD)).toMatch(
      /static func fieldSizeLabel\(\s*_ fieldSize: Int\?\s*\)\s*->\s*String\?/
    );
  });
});
