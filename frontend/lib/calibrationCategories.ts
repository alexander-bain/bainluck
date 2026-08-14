// UX-P075 item (e) — the calibration page's category vocabulary.
//
// ## The measured defect, which is not a casing bug
//
// Alex, 2026-08-13, staged it as "label casing: Table Tennis". Measured on the
// live payload 2026-08-14, before building (ruling 030), it is worse than that:
// the page rendered the literal string `table_tennis`, underscore and all, in
// the By Category tabs and in the Category Breakdown table — sitting between
// "Golf" and "Politics" on the page whose entire job is looking trustworthy.
//
// 11,543 outcomes, the TENTH largest category, and the ONLY one of the fifteen
// rendered tabs that fell through to its raw payload key.
//
// ## Why it is extracted rather than patched in place
//
// Every call site was `DISPLAY_NAMES[c] || c`, and that fallback is the RAW KEY.
// So the defect is not "we forgot table tennis"; it is that the page has a
// SCHEDULED failure mode — a category renders correctly until the day it grows
// past the 1,000-outcome floor without a map entry, and then prints a database
// identifier at a reader. Nothing on our side changes when it fires; the trigger
// is upstream data growth.
//
// Adding one map entry fixes today's instance and leaves the mechanism. Routing
// the fallback through a prettifier makes the raw-key state unreachable, so the
// next category to cross the floor cannot reproduce it. Both are done — the map
// entry because Alex asked for a specific label and a generated one is not an
// opinion, the fallback because one label is not a class.
//
// Extracted here (ruling 005, extract-on-touch) because the page is a
// `"use client"` component behind SWR and a guard that cannot call the function
// is a guard that asserts against a copy of it.

import { getLeagueDisplay, LEAGUE_DISPLAY } from "@/lib/sportCategories";

/**
 * L2-103 Item 3b (Alex D5): a thin sub-league (e.g.
 * `icehockey_sweden_hockey_league`, ~730 outcomes) must NOT collapse to its
 * parent sport's display name ("Hockey"), because the parent sport is already
 * graded in the Category Breakdown above — that made a niche chip read as
 * "Hockey is still coming soon". Prefer the specific league label; only fall
 * back to a prettified raw key for bare single-word categories (chess,
 * commodities, health).
 */
export function nicheCatLabel(raw: string): string {
  if (raw.includes("_") || LEAGUE_DISPLAY[raw]) {
    // getLeagueDisplay returns proper-cased mapped names (SHL, NCAA Lacrosse)
    // and an ALL-CAPS generated fallback for unmapped keys — title-case the
    // latter while preserving short acronyms (NBA, UFL, NRL, AFL).
    return getLeagueDisplay(raw).replace(/\w\S*/g, (w) =>
      w.length <= 4 && w === w.toUpperCase()
        ? w
        : w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()
    );
  }
  return raw.replace(/_/g, " ");
}

export const SPORT_KEY_MAP: Record<string, string> = {
  basketball_nba: "basketball", basketball_ncaab: "basketball",
  basketball_wnba: "basketball", basketball_nbl: "basketball",
  basketball_wncaab: "basketball", basketball_euroleague: "basketball",
  americanfootball_nfl: "football", americanfootball_ncaaf: "football",
  baseball_mlb: "baseball", icehockey_nhl: "hockey",
  soccer_epl: "soccer", soccer_usa_mls: "soccer",
  soccer_uefa_champs_league: "soccer", soccer_spain_la_liga: "soccer",
  soccer_germany_bundesliga: "soccer", soccer_italy_serie_a: "soccer",
  soccer_france_ligue_one: "soccer", soccer_uefa_europa_league: "soccer",
  mma_mixed_martial_arts: "mma", golf_pga: "golf", golf_lpga: "golf",
  cricket_ipl: "cricket", cricket_test_match: "cricket",
};

export const DISPLAY_NAMES: Record<string, string> = {
  basketball: "Basketball", baseball: "Baseball", hockey: "Hockey",
  football: "Football", soccer: "Soccer", golf: "Golf", tennis: "Tennis",
  mma: "MMA", cricket: "Cricket", esports: "Esports", politics: "Politics",
  geopolitics: "Geopolitics", entertainment: "Entertainment",
  weather: "Weather", economics: "Economics", tech: "Tech",
  motorsports: "Motorsports",
  // UX-P075 item (e), Alex 2026-08-13.
  table_tennis: "Table Tennis",
};

/**
 * Fold a payload category onto the key the page groups and labels by.
 *
 * Unchanged by UX-P075 — moved verbatim. Note the shape of its fallback: a key
 * whose FIRST segment is not a known display name comes back WHOLE
 * (`table_tennis` stays `table_tennis`, because `table` is not a sport), which
 * is how the raw key reached the reader.
 */
export function normalizeCat(cat: string): string {
  if (SPORT_KEY_MAP[cat]) return SPORT_KEY_MAP[cat];
  const base = cat.split("_")[0];
  if (base === "americanfootball") return "football";
  if (base === "icehockey") return "hockey";
  return DISPLAY_NAMES[base] ? base : cat;
}

/**
 * A category's human label. **Never returns a raw payload key.**
 *
 * The explicit map governs where we have an opinion; `nicheCatLabel` — already
 * used for the small-sample chips in the same page, so this is reuse rather
 * than a second prettifier — covers everything else.
 */
export function categoryLabel(cat: string): string {
  return DISPLAY_NAMES[cat] || nicheCatLabel(cat);
}
