/**
 * #1930 parity guard — ONE shared category-acronym list, not two copies.
 *
 * Authority: contracts/category-acronyms.json. Both platforms consume
 * generated mirrors of it (frontend/lib/categoryAcronyms.generated.ts via
 * `import`; ios/.../CategoryAcronyms.generated.swift merged into
 * `knownAcronyms` in TextFormatting.swift). This suite fails when a mirror
 * drifts from the authority or when the web caser stops shouting an
 * authority token — regenerate with:
 *   python3 scripts/generate_category_acronyms.py
 */

import { readFileSync } from "fs";
import { join } from "path";
import { toTitleCaseAcronymSafe } from "../lib/titleCase";
import { CATEGORY_ACRONYMS } from "../lib/categoryAcronyms.generated";

const ROOT = join(__dirname, "..", "..");
const AUTHORITY: string[] = JSON.parse(
  readFileSync(join(ROOT, "contracts", "category-acronyms.json"), "utf8"),
).acronyms;

function extractQuotedTokens(source: string): string[] {
  return [...source.matchAll(/"([^"]+)"/g)].map((m) => m[1]);
}

describe("#1930 shared category-acronym authority", () => {
  it("authority is sorted and duplicate-free", () => {
    expect([...AUTHORITY].sort()).toEqual(AUTHORITY);
    expect(new Set(AUTHORITY).size).toBe(AUTHORITY.length);
  });

  it("web mirror equals the authority exactly", () => {
    expect([...CATEGORY_ACRONYMS].sort()).toEqual(AUTHORITY);
  });

  it("native mirror equals the authority exactly", () => {
    const swift = readFileSync(
      join(
        ROOT,
        "ios",
        "Bain Luck",
        "Bain Luck",
        "Utilities",
        "CategoryAcronyms.generated.swift",
      ),
      "utf8",
    );
    expect(extractQuotedTokens(swift).sort()).toEqual(AUTHORITY);
  });

  it("native caser consumes the shared mirror instead of a forked list", () => {
    const textFormatting = readFileSync(
      join(
        ROOT,
        "ios",
        "Bain Luck",
        "Bain Luck",
        "Utilities",
        "TextFormatting.swift",
      ),
      "utf8",
    );
    expect(textFormatting).toContain("categoryAcronyms.union(");
  });

  it("web caser shouts every authority token from a bare slug", () => {
    for (const token of AUTHORITY) {
      expect(toTitleCaseAcronymSafe(token.toLowerCase())).toBe(token);
    }
  });
});
