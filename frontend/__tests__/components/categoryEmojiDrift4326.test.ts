import fs from "fs";
import path from "path";

import { getCat } from "../../components/discover/constants";
import {
  CATEGORY_EMOJI,
  categoryEmoji,
  stripVariationSelectors,
} from "../../lib/categoryEmoji";
import { SPORT_CATEGORIES } from "../../lib/sportCategories";

/**
 * #4326 — one emoji per shelf, held at BOTH ENDS.
 *
 * Four maps used to answer this question independently and ten shelves got
 * different answers. Consolidating them is only half the fix: the other half is
 * a test that goes red when the fifth map appears, which is what
 * `test_the_docstring_catalog_did_not_drift_again` does for its own class.
 *
 * The trap this file is built around: two of the ten disagreements were
 * VARIATION SELECTOR differences (`🌤` vs `🌤️`, U+FE0F). A naive equality test
 * passes them through and a grep for one glyph does not find the other — which
 * is how they survived four surfaces and one issue write-up. Every comparison
 * below normalises first, and one test proves the normaliser can actually tell
 * the pair apart before normalising, so it cannot rot into a no-op.
 */

const REPO_ROOT = path.join(__dirname, "../../..");
const read = (p: string) => fs.readFileSync(path.join(REPO_ROOT, p), "utf8");

/** Every shelf key the app can be asked about. */
const ALL_KEYS = Object.keys(CATEGORY_EMOJI);

describe("#4326 category emoji — one map, and it stays one map", () => {
  test("the shared map is populated and every value is a real glyph", () => {
    // Guard the guard: an emptied map makes every agreement below vacuous.
    expect(ALL_KEYS.length).toBeGreaterThanOrEqual(55);
    for (const key of ALL_KEYS) {
      expect(CATEGORY_EMOJI[key]).toBeTruthy();
      expect(CATEGORY_EMOJI[key]).not.toBe("undefined");
    }
  });

  test("no shelf is stored with a variation selector", () => {
    // Store one form. `🌤` and `🌤️` are different strings that can paint
    // differently, and holding both is how the divergence came back twice.
    for (const key of ALL_KEYS) {
      expect(CATEGORY_EMOJI[key]).toBe(
        stripVariationSelectors(CATEGORY_EMOJI[key]),
      );
    }
  });

  test("the normaliser actually collapses the pair it exists for", () => {
    // Both directions. If `stripVariationSelectors` ever becomes the identity
    // function, every comparison in this file silently weakens — so prove it
    // still folds the real pair AND still distinguishes two real glyphs.
    expect(stripVariationSelectors("\u{1F324}️")).toBe("\u{1F324}");
    expect("\u{1F324}️").not.toBe("\u{1F324}");
    expect(stripVariationSelectors("🌤")).not.toBe(
      stripVariationSelectors("🌦"),
    );
  });

  test("Discover cards draw the shared icon for every shelf", () => {
    for (const key of ALL_KEYS) {
      expect(stripVariationSelectors(getCat(key).emoji)).toBe(
        stripVariationSelectors(CATEGORY_EMOJI[key]),
      );
    }
  });

  test("/categories draws the shared icon for every shelf it lists", () => {
    expect(SPORT_CATEGORIES.length).toBeGreaterThanOrEqual(30);
    for (const cat of SPORT_CATEGORIES) {
      expect(cat.emoji).toBeTruthy();
      expect(stripVariationSelectors(cat.emoji)).toBe(
        stripVariationSelectors(CATEGORY_EMOJI[cat.key]),
      );
    }
  });

  test("the ten shelves that disagreed now have one answer each", () => {
    // The census, as a table. These are the values a reader sees; changing one
    // is a product decision, so it fails here rather than drifting.
    const settled: Record<string, string> = {
      aussierules: "🏉",
      economics: "📈",
      health: "🏥",
      mma: "🥋",
      motorsports: "🏎",
      olympics: "🏅",
      other: "📋",
      politics: "🏛",
      tech: "💻",
      weather: "🌤",
    };
    for (const [key, emoji] of Object.entries(settled)) {
      expect(categoryEmoji(key)).toBe(emoji);
      expect(stripVariationSelectors(getCat(key).emoji)).toBe(emoji);
    }
  });

  test("no shelf shares a glyph with a DIFFERENT sport", () => {
    // Why `mma` is 🥋 and not Discover's 🥊, and why `aussierules` is 🏉 and not
    // /categories' 🏈. Repeats are allowed only inside a family — a league
    // sub-shelf may reuse its parent's ball.
    const FAMILIES: Record<string, string> = {
      nfl: "football",
      college_football: "football",
      nba: "basketball",
      college_basketball: "basketball",
      golf_pga: "golf",
      golf_liv: "golf",
      golf_lpga: "golf",
      golf_dp_world: "golf",
      // genuinely-similar racket and throwing sports, deliberately shared
      squash: "tennis",
      table_tennis: "pickleball",
      handball: "dodgeball",
      rugby: "aussierules",
      auto_industry: "auto",
    };
    const byEmoji = new Map<string, string[]>();
    for (const key of ALL_KEYS) {
      const root = FAMILIES[key] ?? key;
      const glyph = CATEGORY_EMOJI[key];
      const roots = byEmoji.get(glyph) ?? [];
      if (!roots.includes(root)) roots.push(root);
      byEmoji.set(glyph, roots);
    }
    for (const [glyph, roots] of byEmoji) {
      expect(`${glyph}: ${roots.join(",")}`).toBe(`${glyph}: ${roots[0]}`);
    }
  });

  test("no surface has grown a second emoji map", () => {
    // The both-ends half. Consolidation without this lasts until the next
    // component that needs an icon and writes its own object literal.
    const OWNERS = [
      "frontend/components/discover/constants.ts",
      "frontend/components/CategoryBrowser.tsx",
      "frontend/lib/sportCategories.ts",
    ];
    for (const file of OWNERS) {
      const source = read(file);
      expect(source).toMatch(/from "[@.]\/(lib\/)?categoryEmoji"/);
      // A shelf key mapped straight to a quoted emoji is a private map coming
      // back. Matches `weather: "🌤"` but not `emoji: CATEGORY_EMOJI["weather"]`.
      const privateEntries = source.match(
        /^\s{2,4}[a-z_]+:\s*"\p{Extended_Pictographic}/gmu,
      );
      expect(privateEntries ?? []).toEqual([]);
    }
  });

  test("iOS draws the same glyph for every shelf it names", () => {
    // CI compiles no Swift (standing notice 10), so this is a source scan — but
    // it is a scan for VALUES, not for the presence of a line, and it fails if
    // the Swift switch and the web map ever disagree.
    const IOS = [
      "ios/Bain Luck/Bain Luck/Components/DiscoverFuturesCard.swift",
      "ios/Bain Luck/Bain Luck/Views/FuturesDetailView.swift",
    ];
    let compared = 0;
    for (const file of IOS) {
      const source = read(file);
      const cases = [
        ...source.matchAll(/case "(\w+)": return "([^"]+)"/g),
      ];
      // If the switch is refactored the regex stops matching, and an empty scan
      // must not read as agreement.
      expect(cases.length).toBeGreaterThanOrEqual(8);
      for (const [, key, glyph] of cases) {
        expect(stripVariationSelectors(glyph)).toBe(
          stripVariationSelectors(CATEGORY_EMOJI[key]),
        );
        compared += 1;
      }
    }
    expect(compared).toBeGreaterThanOrEqual(16);
  });
});
