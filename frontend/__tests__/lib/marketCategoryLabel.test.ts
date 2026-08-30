/**
 * UX-P190 — a market's category chip reads as English, not as a payload key.
 *
 * `FuturesMarket.llm_sport_category` is a snake_case key. Seven call sites printed
 * it VERBATIM, so `/search?q=Kikawada` rendered "TABLE_TENNIS" (the search card
 * uppercases), the market page and its OpenGraph share image rendered
 * "table_tennis", and `/discover/stats` rendered "Table_tennis" (a CSS
 * `capitalize` that could not reach the underscore). 14,588 OPEN markets carry
 * an underscored key; 14,584 of them are `table_tennis`, the 5th largest
 * category at 103,674 markets.
 *
 * Two lessons from UX-P189 are load bearing in this file:
 *
 *  1. A guard that asserts a string's SHAPE passes on mangled words. UX-P189's
 *     predecessor checked "not a raw key / no underscore / starts uppercase" and
 *     its own examples returned "POLO" and "NEW Sport" — first word DROPPED —
 *     and passed. So this file pins the WORDS for every key it can, and the
 *     shape checks are a floor underneath that, never the whole assertion.
 *  2. The reader sees the label THROUGH the call site's CSS. A helper that
 *     returns "Table Tennis" still fails if the element uppercases or
 *     capitalizes it wrongly, so the census below applies each call site's real
 *     text-transform before asserting.
 */
import * as fs from "fs";
import * as path from "path";
import { getMarketCategoryLabel, getNameForCategory } from "@/lib/sportCategories";

const FRONTEND_ROOT = path.join(__dirname, "..", "..");

/**
 * Every `llm_sport_category` value present in production with its market count,
 * measured 2026-08-30 via admin db-query (75 keys). The counts are here so a
 * reader can see which rows matter; the assertions treat all 75 alike.
 */
const PROD_KEYS: Array<[string, number]> = [
  ["soccer", 232975], ["esports", 133938], ["baseball", 126909], ["tennis", 110001],
  ["table_tennis", 103674], ["basketball", 59260], ["economics", 27086], ["weather", 24009],
  ["football", 17411], ["politics", 13896], ["hockey", 10050], ["entertainment", 9929],
  ["cricket", 8733], ["golf", 7622], ["other", 6127], ["crypto", 4821], ["mma", 4342],
  ["tech", 3507], ["geopolitics", 2443], ["legal", 2014], ["energy", 1314],
  ["motorsports", 1206], ["rugby", 694], ["chess", 665], ["boxing", 602], ["lacrosse", 469],
  ["darts", 192], ["olympics", 183], ["rodeo", 140], ["aussierules", 138], ["health", 121],
  ["commodities", 75], ["culture", 69], ["pickleball", 68], ["softball", 56], ["cycling", 55],
  ["wrestling", 30], ["poker", 20], ["handball", 19], ["badminton", 12], ["sailing", 10],
  ["skateboarding", 10], ["horse_racing", 7], ["bmx", 6], ["surfing", 4], ["squash", 4],
  ["weightlifting", 4], ["mlb", 3], ["education", 3], ["eating_competition", 3],
  ["athletics", 3], ["real_estate", 2], ["combat_archery", 2], ["auto", 2],
  ["track_and_field", 2], ["transportation", 2], ["watchmaking", 2], ["ai_safety", 2],
  ["curling", 2], ["bull_riding", 1], ["space", 1], ["dance", 1], ["sumo", 1],
  ["dodgeball", 1], ["padel", 1], ["auto_industry", 1], ["word_games", 1],
  ["figure_skating", 1], ["retail", 1], ["extreme_sports", 1], ["climbing", 1],
  ["running", 1], ["adventure", 1], ["xgames", 1], ["business", 1],
];

/** The keys that carry an underscore — the population this ship is about. */
const UNDERSCORED = PROD_KEYS.map(([k]) => k).filter((k) => k.includes("_"));

// CSS text-transform, modelled. `uppercase` maps to toUpperCase; `capitalize`
// uppercases the FIRST letter of each word and — this is the part that made the
// old bug invisible — leaves the rest of the word, and any punctuation such as
// an underscore, exactly as it was.
const cssUppercase = (s: string) => s.toUpperCase();
const cssCapitalize = (s: string) =>
  s.replace(/(^|\s)(\S)/g, (_m, lead, ch) => lead + ch.toUpperCase());

describe("the production category-key corpus", () => {
  // Vacuity companion: every assertion below about underscores is worthless if
  // the corpus happens to hold none. Pin that it does, and that the corpus is
  // the size it was measured at.
  it("is the measured corpus and does contain underscored keys", () => {
    expect(PROD_KEYS).toHaveLength(75);
    expect(UNDERSCORED.length).toBeGreaterThanOrEqual(12);
    expect(UNDERSCORED).toContain("table_tennis");
  });

  it("models CSS capitalize as something that cannot reach an underscore", () => {
    // This is the mechanism of the shipped bug, pinned so the model above stays
    // honest. If this ever fails, the census's "before" column is fiction.
    expect(cssCapitalize("table_tennis")).toBe("Table_tennis");
    expect(cssUppercase("table_tennis")).toBe("TABLE_TENNIS");
  });
});

describe("getMarketCategoryLabel", () => {
  it("prefers the curated Sport.name when the market has a linked sport", () => {
    expect(getMarketCategoryLabel("MLB", "baseball")).toBe("MLB");
    expect(getMarketCategoryLabel("NFL", null)).toBe("NFL");
  });

  it("labels the category key when there is no linked sport", () => {
    // The shipped case: sport_name is null on all 14,584 open table-tennis
    // markets, so this branch is the one the reader actually gets.
    expect(getMarketCategoryLabel(null, "table_tennis")).toBe("Table Tennis");
    expect(getMarketCategoryLabel(undefined, "horse_racing")).toBe("Horse Racing");
    expect(getMarketCategoryLabel(null, "real_estate")).toBe("Real Estate");
    expect(getMarketCategoryLabel(null, "ai_safety")).toBe("AI Safety");
  });

  it("returns undefined when neither is present, so callers keep their own fallback word", () => {
    expect(getMarketCategoryLabel(null, null)).toBeUndefined();
    expect(getMarketCategoryLabel(undefined, undefined)).toBeUndefined();
    expect(getMarketCategoryLabel("", "")).toBeUndefined();
  });

  it("falls through to getNameForCategory rather than reimplementing it", () => {
    // Pins the delegation, not a comment about it. If the fall-through were
    // inlined or diverged, a curated rename would stop reaching this helper.
    for (const key of ["mma", "aussierules", "tech", "horse_racing"]) {
      expect(getMarketCategoryLabel(null, key)).toBe(getNameForCategory(key));
    }
  });
});

describe("every production key, rendered through each call site's CSS", () => {
  // The three text-transforms in play across the seven call sites. `none` covers
  // the market-page chip, the two Discover cards and /daily; `uppercase` is the
  // search/my-stuff/preferences card; `capitalize` is what /discover/stats and
  // the OG share image USED to apply and no longer do — it is kept in the
  // census as a regression check on re-adding it.
  const RENDERS: Array<[string, (s: string) => string]> = [
    ["none", (s) => s],
    ["uppercase", cssUppercase],
    ["capitalize", cssCapitalize],
  ];

  it.each(RENDERS)("never shows an underscore under text-transform: %s", (_name, transform) => {
    const offenders = PROD_KEYS
      .map(([key]) => [key, transform(getMarketCategoryLabel(null, key)!)] as const)
      .filter(([, rendered]) => rendered.includes("_"));
    expect(offenders).toEqual([]);
  });

  it("never renders a label that is still the raw lowercase key", () => {
    const offenders = PROD_KEYS
      .map(([key]) => [key, getMarketCategoryLabel(null, key)!] as const)
      .filter(([key, label]) => label === key);
    expect(offenders).toEqual([]);
  });

  it("never drops a word from a multi-word key", () => {
    // UX-P189's actual defect was a LOST first segment, which every shape check
    // it had still passed. Count words, per key, both directions.
    const offenders = UNDERSCORED.map((key) => {
      const label = getMarketCategoryLabel(null, key)!;
      return { key, label, keyWords: key.split("_").length, labelWords: label.split(/\s+/).length };
    }).filter((r) => r.labelWords !== r.keyWords);
    expect(offenders).toEqual([]);
  });

  it("spells out the underscored keys in the words a reader expects", () => {
    // The words themselves, not their shape. "Track And Field" is recorded as
    // the CURRENT output, not as an endorsement — toTitleCaseAcronymSafe
    // deliberately does not lowercase connectors, and changing that is a
    // separate, wider change (parked as UX-P190-1).
    // Keyed, not positional: an assertion that depends on corpus ORDER fails
    // for a reason that has nothing to do with the labels.
    const actual = Object.fromEntries(
      UNDERSCORED.map((k) => [k, getMarketCategoryLabel(null, k)]),
    );
    expect(actual).toEqual({
      table_tennis: "Table Tennis",
      horse_racing: "Horse Racing",
      eating_competition: "Eating Competition",
      real_estate: "Real Estate",
      track_and_field: "Track And Field",
      ai_safety: "AI Safety",
      combat_archery: "Combat Archery",
      bull_riding: "Bull Riding",
      auto_industry: "Auto Industry",
      word_games: "Word Games",
      figure_skating: "Figure Skating",
      extreme_sports: "Extreme Sports",
    });
  });

  it("keeps the curated names the site already shows elsewhere", () => {
    // The control. FeedCard and CombinedFeedCard already routed through
    // getNameForCategory, so these are the labels Discover has always printed;
    // a fix that renamed them would prove the helper had stopped honouring
    // SPORT_CATEGORIES.
    expect(getMarketCategoryLabel(null, "mma")).toBe("MMA");
    expect(getMarketCategoryLabel(null, "aussierules")).toBe("AFL");
    expect(getMarketCategoryLabel(null, "tech")).toBe("Tech & Science");
    expect(getMarketCategoryLabel(null, "soccer")).toBe("Soccer");
    expect(getMarketCategoryLabel(null, "other")).toBe("Other");
  });
});

describe("no call site open-codes the label again", () => {
  // Three of the seven sites held the SAME expression character for character.
  // That is how a formatter fix half-lands: someone copies the seventh copy.
  const SOURCE_GLOBS = ["app", "components"];

  function walk(dir: string, out: string[] = []): string[] {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "node_modules" || entry.name === "admin") continue;
        walk(full, out);
      } else if (/\.tsx?$/.test(entry.name)) {
        out.push(full);
      }
    }
    return out;
  }

  it("has no `sport_name || …llm_sport_category` left outside /admin", () => {
    const files = SOURCE_GLOBS.flatMap((g) => walk(path.join(FRONTEND_ROOT, g)));
    // Vacuity companion: prove the walk actually reached the tree it claims to.
    expect(files.length).toBeGreaterThan(100);

    const offenders: string[] = [];
    for (const file of files) {
      const src = fs.readFileSync(file, "utf8");
      src.split("\n").forEach((line, i) => {
        if (/sport_name\s*\|\|[^\n]*llm_sport_category/.test(line)) {
          offenders.push(`${path.relative(FRONTEND_ROOT, file)}:${i + 1}: ${line.trim()}`);
        }
      });
    }
    expect(offenders).toEqual([]);
  });
});
