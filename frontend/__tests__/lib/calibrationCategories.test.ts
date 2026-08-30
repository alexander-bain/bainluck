// UX-P075 item (e) — the category label can never be a raw payload key.
//
// The staged item was one word ("label casing: Table Tennis"). The measured
// defect was a MECHANISM: every call site was `DISPLAY_NAMES[c] || c`, whose
// fallback is the database identifier, so a category renders correctly until it
// grows past the page's 1,000-outcome floor without a map entry and then prints
// `table_tennis` at a reader. Nothing on our side changes when that fires.
//
// So this suite asserts the mechanism is gone, not just that one label is right.
// The named case is pinned first because Alex asked for it by name; the class
// assertion below it is the part that stops the next one.
//
// ---------------------------------------------------------------------------
// UX-P189, 2026-08-30 — WHAT THIS SUITE USED TO MISS, AND WHY THAT MATTERS MORE
// THAN THE LABELS IT NOW FIXES.
//
// The guarantee in the header above was not true, and this file was the reason
// it looked true. Two of its assertions were the problem:
//
//   * "an UNKNOWN multi-word key is prettified" tested `label !== raw`, no
//     underscore, and `label[0]` uppercase. Measured against the shipped code,
//     its own three examples returned `POLO`, `Volleyball` and `NEW Sport` —
//     the first word DROPPED and the rest shouted — and all three PASSED. A
//     label can satisfy "is not a raw key" while having lost half its words.
//
//   * "an unknown single-word key loses nothing" asserted
//     `categoryLabel("chess") === "chess"`, PINNING the raw lowercase key as
//     correct. On the parked chips a CSS `capitalize` class hid that; in the By
//     Category tabs and the breakdown table, which carry no such class, live
//     `crypto` (4,567 outcomes, published) reached the reader lowercase.
//
// Both are replaced below with assertions about the WORDS, not about the shape.
// The rule the old pair implied — a guard that can be satisfied by mangled
// output is a comment, not a branch.
// ---------------------------------------------------------------------------

import {
  DISPLAY_NAMES,
  categoryLabel,
  nicheCatLabel,
  normalizeCat,
} from "@/lib/calibrationCategories";
import { LEAGUE_DISPLAY } from "@/lib/sportCategories";

// The fifteen categories `/api/calibration` would render, measured on the LIVE
// payload 2026-08-14, after `normalizeCat` and after the page's 1,000-outcome
// floor, in the order the page sorts them.
//
// NOT read from `calibrationProdFixture`, and that is deliberate: that fixture
// pre-sums the category dimension away and says so in its own header — *"this
// fixture CANNOT prove anything about the per-category rollup"*. Grading a
// category test on it would have produced fifteen passes over a single row
// labelled `agg`, which is exactly the vacuous-guard shape this lane keeps
// finding. (It did, on the first run of this file.)
//
// A dated snapshot, not a live read. If the real category set drifts this list
// goes stale — but the class assertion below it ("an unknown key is prettified")
// holds for anything, so a stale list costs coverage of the named rows, never
// the guarantee.
const RENDERED_CATEGORIES_2026_08_14 = [
  "baseball", "basketball", "soccer", "tennis", "hockey",
  "economics", "weather", "esports", "golf", "table_tennis",
  "politics", "entertainment", "football", "motorsports", "mma",
] as const;

// UX-P189: every category key `/api/calibration` carried on 2026-08-30 —
// `by_category` (34, the published breakdown + tabs) and
// `small_sample_categories` (104, the "still accumulating" chips). Both lists
// are LABELLED surfaces, and the second is where the mangling lived, so a
// census limited to the published 34 would have graded none of it.
//
// Same dated-snapshot discipline as the list above: drift costs coverage of the
// named rows, never the properties, which are asserted over whatever is here.
const PUBLISHED_CATEGORIES_2026_08_30 = [
  "baseball", "soccer", "basketball", "tennis", "economics", "weather",
  "hockey", "basketball_ncaab", "esports", "baseball_mlb", "golf",
  "table_tennis", "politics", "baseball_ncaa", "entertainment",
  "basketball_nba", "football", "icehockey_nhl", "motorsports",
  "basketball_wncaab", "crypto", "basketball_wnba", "tech",
  "baseball_mlb_preseason", "mma", "cricket", "basketball_euroleague",
  "geopolitics", "aussierules_afl", "rugbyleague_nrl",
  "tennis_wta_canadian_open", "basketball_nba_summer_league",
  "tennis_atp_cincinnati_open", "tennis_atp_canadian_open",
] as const;

const PARKED_CATEGORIES_2026_08_30 = [
  "tennis_wta_cincinnati_open", "mma_mixed_martial_arts", "chess",
  "lacrosse_ncaa", "icehockey_sweden_hockey_league", "americanfootball_cfl",
  "commodities", "americanfootball_nfl_preseason", "americanfootball_ufl",
  "lacrosse_pll", "soccer_usa_mls", "soccer_england_league1",
  "soccer_argentina_primera_division", "soccer_efl_champ",
  "soccer_england_league2", "soccer_spain_segunda_division", "rugby",
  "icehockey_sweden_allsvenskan", "soccer_brazil_serie_b",
  "soccer_brazil_campeonato", "soccer_italy_serie_b",
  "tennis_wta_monterrey_open", "lacrosse", "soccer_spain_la_liga",
  "soccer_germany_liga3", "tennis_atp_washington_open", "soccer_italy_serie_a",
  "soccer_china_superleague", "soccer_mexico_ligamx",
  "soccer_poland_ekstraklasa", "soccer_epl", "soccer_belgium_first_div",
  "soccer_japan_j_league", "legal", "soccer_germany_bundesliga",
  "soccer_germany_bundesliga2", "soccer_france_ligue_one",
  "soccer_turkey_super_league", "soccer_conmebol_copa_libertadores",
  "soccer_netherlands_eredivisie", "soccer_portugal_primeira_liga",
  "americanfootball_ncaaf_fcs", "tennis_wta_washington_open", "boxing",
  "soccer_sweden_superettan", "soccer_france_ligue_two",
  "soccer_chile_campeonato", "soccer_league_of_ireland", "basketball_nbl",
  "soccer_conmebol_copa_sudamericana", "soccer_greece_super_league",
  "soccer_norway_eliteserien", "soccer_fifa_world_cup",
  "soccer_sweden_allsvenskan", "soccer_switzerland_superleague", "energy",
  "soccer_finland_veikkausliiga", "soccer_russia_premier_league", "rodeo",
  "soccer_austria_bundesliga", "soccer_korea_kleague1", "soccer_spl",
  "soccer_denmark_superliga", "soccer_australia_aleague", "pickleball",
  "soccer_uefa_europa_conference_league", "soccer_uefa_champs_league",
  "cycling", "aussierules", "soccer_uefa_europa_league", "culture", "health",
  "olympics", "soccer_fa_cup", "soccer_uefa_champs_league_qualification",
  "soccer_uefa_champs_league_women", "skateboarding", "ai_safety",
  "americanfootball_ncaaf", "squash", "sailing", "sumo",
  "americanfootball_nfl", "soccer_fifa_world_cup_qualifiers_europe",
  "softball", "bmx", "climbing", "horse_racing", "wrestling", "auto_industry",
  "weightlifting", "bull_riding", "poker", "soccer_england_efl_cup", "xgames",
  "soccer_germany_dfb_pokal", "soccer_uefa_nations_league", "surfing", "darts",
  "soccer_italy_coppa_italia", "athletics", "figure_skating",
  "soccer_spain_copa_del_rey", "track_and_field",
] as const;

/** Every key the page labels, by either of its two labellers. */
const ALL_LABELLED_KEYS_2026_08_30 = [
  ...PUBLISHED_CATEGORIES_2026_08_30,
  ...PARKED_CATEGORIES_2026_08_30,
];

/**
 * The label a reader actually sees for a key, on both labelled surfaces: the
 * tabs and the breakdown table call `categoryLabel(normalizeCat(k))`, the parked
 * chips call `nicheCatLabel(k)` directly.
 *
 * ⚠️ This helper does NOT add discriminating power today, and saying so is the
 * point. Narrowing it to the first call alone was mutation-tested and left all
 * of this suite green, because `categoryLabel` FALLS THROUGH to `nicheCatLabel`
 * for anything the explicit map does not name — one labeller, reached two ways.
 * That fall-through is the load-bearing fact, so it is pinned as its own test
 * below rather than left as a claim in this comment. Both calls stay here so
 * that the day the fall-through is broken, these property tests are already
 * pointed at the surface that broke.
 */
function renderedLabels(key: string): string[] {
  return [categoryLabel(normalizeCat(key)), nicheCatLabel(key)];
}

describe("the named case — Alex, 2026-08-13", () => {
  test("table_tennis renders as Table Tennis", () => {
    expect(categoryLabel("table_tennis")).toBe("Table Tennis");
  });

  test("and it reaches the reader as a category key at all — the anchor", () => {
    // If `normalizeCat` ever folds table_tennis into something else, the label
    // above becomes dead code and this suite would keep passing while the page
    // showed something different. `table` is not a sport, so the whole key
    // survives normalisation and IS what the page labels.
    expect(normalizeCat("table_tennis")).toBe("table_tennis");
  });
});

describe("no category label is ever a raw payload key — the class", () => {
  test("the census carries categories to grade, and they survive normalisation", () => {
    // The anchor. Also proves the list is of RENDERED keys: a row that
    // `normalizeCat` folds elsewhere is never labelled, so listing it here would
    // grade a string the page does not show.
    expect(RENDERED_CATEGORIES_2026_08_14.length).toBe(15);
    for (const cat of RENDERED_CATEGORIES_2026_08_14) {
      expect(normalizeCat(cat)).toBe(cat);
    }
  });

  test("every category the page would render has a human label", () => {
    for (const cat of RENDERED_CATEGORIES_2026_08_14) {
      const label = categoryLabel(cat);
      expect(label).not.toBe(cat);
      expect(label).not.toMatch(/_/);
      expect(label).not.toBe("");
    }
  });

  test("the explicit map still wins over the generated label", () => {
    // Alex asked for "Table Tennis"; a generated label is not an opinion, and
    // the map is where opinions live.
    expect(DISPLAY_NAMES["table_tennis"]).toBe("Table Tennis");
    expect(categoryLabel("table_tennis")).toBe(DISPLAY_NAMES["table_tennis"]);
  });

  test("short all-caps acronyms survive the prettifier", () => {
    // Regression cover for `nicheCatLabel`'s acronym rule, which the fallback
    // now inherits: "MMA" must not become "Mma".
    expect(categoryLabel("mma")).toBe("MMA");
  });
});

// ---------------------------------------------------------------------------
// UX-P189 — the label keeps the WORDS, not merely the shape.
// ---------------------------------------------------------------------------

describe("UX-P189 — the label keeps every word of the key", () => {
  test("the census is the live one and covers both labelled surfaces", () => {
    // The anchor for everything below: if these shrink to nothing the property
    // tests all pass vacuously over an empty list.
    expect(PUBLISHED_CATEGORIES_2026_08_30.length).toBe(34);
    expect(PARKED_CATEGORIES_2026_08_30.length).toBe(104);
    expect(ALL_LABELLED_KEYS_2026_08_30.length).toBe(138);
  });

  test("a two-word concept keeps BOTH words — the `AND Field` class", () => {
    // Every one of these dropped its first word before UX-P189, because the
    // labeller handed the key to a LEAGUE-key parser that strips segment 0 as a
    // sport prefix. None of these keys is `sport_league`.
    expect(nicheCatLabel("track_and_field")).toBe("Track and Field");
    expect(nicheCatLabel("ai_safety")).toBe("AI Safety");
    expect(nicheCatLabel("horse_racing")).toBe("Horse Racing");
    expect(nicheCatLabel("figure_skating")).toBe("Figure Skating");
    expect(nicheCatLabel("auto_industry")).toBe("Auto Industry");
    expect(nicheCatLabel("bull_riding")).toBe("Bull Riding");
  });

  test("the OLD suite's own three unknown-key examples keep their words", () => {
    // These are verbatim the strings the previous "an UNKNOWN multi-word key is
    // prettified" test iterated over. It passed while they rendered `POLO`,
    // `Volleyball` and `NEW Sport`. Pinned by value so the regression cannot
    // return behind a property that tolerates it.
    expect(categoryLabel("water_polo")).toBe("Water Polo");
    expect(categoryLabel("beach_volleyball")).toBe("Beach Volleyball");
    expect(categoryLabel("some_new_sport")).toBe("Some New Sport");
  });

  test("no key in the live census silently loses a word", () => {
    // The class form of the two tests above, over the whole measured payload.
    //
    // Two exemptions, both principled: a key with a curated LEAGUE_DISPLAY name
    // is a deliberate RENAME (`icehockey_sweden_hockey_league` -> "SHL"), and a
    // key `normalizeCat` folds onto its parent sport is deliberately labelled
    // with the parent (`basketball_nba` -> "Basketball"). Everything else must
    // account for every segment of its key except a dropped sport prefix.
    const droppablePrefixes = new Set(
      [...Object.keys(LEAGUE_DISPLAY)]
        .filter(k => k.includes("_"))
        .map(k => k.split("_")[0])
    );
    const lost: string[] = [];
    for (const key of ALL_LABELLED_KEYS_2026_08_30) {
      if (LEAGUE_DISPLAY[key]) continue;
      if (normalizeCat(key) !== key) continue;
      const label = nicheCatLabel(key).toLowerCase();
      key.split("_").forEach((tok, i) => {
        if (i === 0 && droppablePrefixes.has(tok)) return;
        if (!label.includes(tok)) lost.push(`${key} -> "${nicheCatLabel(key)}" dropped "${tok}"`);
      });
    }
    expect(lost).toEqual([]);
  });

  test("the two labelled surfaces share ONE labeller", () => {
    // What makes `renderedLabels` honest, and the divergence this page is one
    // edit away from: the tabs/table go through `categoryLabel` and the chips
    // through `nicheCatLabel`, and they agree only because the former delegates
    // to the latter for every key the explicit map does not name. A second
    // prettifier added to either call site is the `clean_outcomes` four-copies
    // pattern arriving here, and it would show up as this test failing rather
    // than as one surface quietly drifting.
    for (const key of ALL_LABELLED_KEYS_2026_08_30) {
      if (DISPLAY_NAMES[key]) continue;
      expect(categoryLabel(key)).toBe(nicheCatLabel(key));
    }
  });

  test("a sport prefix is dropped by MEMBERSHIP, not by position", () => {
    // The distinction that makes the test above hold. `tennis` is a sport, so
    // it goes; `horse` sits in the same position and is not, so it stays. A
    // reimplementation that strips segment 0 unconditionally passes the first
    // of these and fails the second.
    expect(nicheCatLabel("tennis_wta_cincinnati_open")).toBe("WTA Cincinnati Open");
    expect(nicheCatLabel("horse_racing")).toBe("Horse Racing");
  });
});

describe("UX-P189 — the label shouts acronyms and only acronyms", () => {
  test("an ordinary English word is never all-caps — the `OPEN`/`CUP` class", () => {
    expect(nicheCatLabel("tennis_wta_cincinnati_open")).toBe("WTA Cincinnati Open");
    expect(nicheCatLabel("soccer_fifa_world_cup")).toBe("FIFA World Cup");
    expect(nicheCatLabel("soccer_spain_copa_del_rey")).toBe("Spain Copa del Rey");
    expect(nicheCatLabel("soccer_league_of_ireland")).toBe("League of Ireland");
    expect(nicheCatLabel("soccer_spain_la_liga")).toBe("Spain La Liga");
    expect(nicheCatLabel("soccer_france_ligue_one")).toBe("France Ligue One");
    expect(nicheCatLabel("soccer_belgium_first_div")).toBe("Belgium First Div");
  });

  test("no label in the live census shouts a word that is not an acronym", () => {
    // The class form. These are the exact tokens the old `length <= 4 &&
    // isUpperCase` heuristic shouted, plus `POLO`/`NEW` from the old suite's own
    // examples. The heuristic could not do better: by the time it ran, the
    // league parser had already uppercased every word.
    const NEVER_SHOUTED = [
      "OPEN", "CUP", "AND", "OF", "DEL", "REY", "LIGA", "COPA", "ONE", "TWO",
      "DIV", "NEW", "POLO", "THE",
    ];
    const shouted: string[] = [];
    for (const key of ALL_LABELLED_KEYS_2026_08_30) {
      for (const label of renderedLabels(key)) {
        for (const word of label.split(/\s+/)) {
          if (NEVER_SHOUTED.includes(word)) shouted.push(`${key} -> "${label}"`);
        }
      }
    }
    expect(shouted).toEqual([]);
  });

  test("a curated LEAGUE_DISPLAY name is returned verbatim, not re-cased", () => {
    // `NCAAF` is six characters, so the old `length <= 4` acronym rule
    // de-capitalised the correct answer that was already sitting in the map and
    // rendered `Ncaaf`. Re-casing an opinion is how you lose it.
    expect(LEAGUE_DISPLAY["americanfootball_ncaaf"]).toBe("NCAAF");
    expect(nicheCatLabel("americanfootball_ncaaf")).toBe("NCAAF");
    expect(nicheCatLabel("americanfootball_ncaaf_fcs")).toBe("NCAAF FCS");
    for (const [key, curated] of Object.entries(LEAGUE_DISPLAY)) {
      expect(nicheCatLabel(key)).toBe(curated);
    }
  });
});

describe("UX-P189 — a single-word key is cased, not passed through", () => {
  test("the bare keys the old suite pinned as raw", () => {
    // `categoryLabel("chess") === "chess"` was an ASSERTION in this file. The
    // parked chips carried a CSS `capitalize` class that hid it there; the tabs
    // and the breakdown table do not, and that is where live `crypto` (4,567
    // outcomes, published in `by_category`) reached the reader lowercase.
    expect(DISPLAY_NAMES["chess"]).toBeUndefined();
    expect(DISPLAY_NAMES["crypto"]).toBeUndefined();
    expect(categoryLabel("chess")).toBe("Chess");
    expect(categoryLabel("crypto")).toBe("Crypto");
    expect(categoryLabel("commodities")).toBe("Commodities");
  });

  test("no label on either surface starts lowercase or keeps an underscore", () => {
    const bad: string[] = [];
    for (const key of ALL_LABELLED_KEYS_2026_08_30) {
      for (const label of renderedLabels(key)) {
        if (label === "") bad.push(`${key} -> empty`);
        if (label.includes("_")) bad.push(`${key} -> "${label}" kept an underscore`);
        if (label[0] !== label[0]?.toUpperCase()) bad.push(`${key} -> "${label}" starts lowercase`);
      }
    }
    expect(bad).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// UX-P189 — the render half: the parked chip must not re-case the label.
//
// Asserted at the source level, following the precedent set and reasoned out in
// `calibrationNonexclusiveBundleDisclosure.test.tsx` — this page is a large
// client component behind SWR and rendering it here would prove less and break
// more. The compensating control that stops an absence-assertion from staying
// green while the feature quietly disappears is `chipRegion()`, which throws if
// the chip is gone and pins the `catLabel(...)` binding INSIDE it, so "no
// capitalize class" can never be satisfied by "no chip".
// ---------------------------------------------------------------------------

describe("UX-P189 — the parked chip renders the label as the labeller cased it", () => {
  const fs = require("fs") as typeof import("fs");
  const path = require("path") as typeof import("path");
  const PAGE = path.join(__dirname, "..", "..", "app", "calibration", "page.tsx");
  const SOURCE: string = fs.readFileSync(PAGE, "utf8");
  const TESTID = "calibration-parked-category";

  /** The parked chip's JSX, from its test hook to the end of its element. */
  function chipRegion(): string {
    const start = SOURCE.indexOf(`data-testid="${TESTID}"`);
    if (start < 0) {
      throw new Error(
        `the parked-category chip is gone from the calibration page. It is the ` +
          `surface UX-P189 repaired (its first chip read "WTA Cincinnati OPEN"). ` +
          `Re-anchor this guard, do not delete it.`,
      );
    }
    const end = SOURCE.indexOf("</span>", SOURCE.indexOf("</span>", start) + 1);
    return SOURCE.slice(start, end);
  }

  test("the chip still exists and still renders a computed label", () => {
    // The anchor. Without it the assertion below passes on a deleted chip.
    const region = chipRegion();
    expect(region).toMatch(/catLabel\(c\.category\)/);
  });

  test("the chip does not apply CSS capitalize over the label", () => {
    // `text-transform: capitalize` uppercases the first letter of EVERY word, so
    // it would undo the small-word casing the labeller is now responsible for:
    // "Track and Field" -> "Track And Field", "Spain Copa del Rey" -> "Spain
    // Copa Del Rey". The class was only ever there to hide `nicheCatLabel`
    // returning bare keys like `chess` verbatim, which it no longer does.
    expect(chipRegion()).not.toMatch(/\bcapitalize\b/);
  });

  test("and the label it renders would be corrupted if it did", () => {
    // Proves the guard above is about a REAL interaction rather than a style
    // preference: these are live census keys whose correct label contains a
    // deliberately lowercase word.
    const cssCapitalize = (s: string) =>
      s.replace(/\b\w/g, (c) => c.toUpperCase());
    for (const key of ["track_and_field", "soccer_spain_copa_del_rey", "soccer_league_of_ireland"]) {
      expect(ALL_LABELLED_KEYS_2026_08_30).toContain(key);
      const label = nicheCatLabel(key);
      expect(cssCapitalize(label)).not.toBe(label);
    }
  });
});
