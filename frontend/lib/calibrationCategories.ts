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

import { LEAGUE_DISPLAY } from "@/lib/sportCategories";

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

// ## UX-P189 — why this no longer routes through `getLeagueDisplay`
//
// The previous implementation asked `getLeagueDisplay()` for a name and then
// title-cased the answer, "preserving short acronyms (NBA, UFL, NRL, AFL)" with
// the rule `w.length <= 4 && w === w.toUpperCase()`. That rule cannot work, and
// not because the threshold is wrong — because by the time it runs the
// information it needs is gone.
//
// `getLeagueDisplay` is a LEAGUE-key parser. For an unmapped key it (a) drops
// segment 0 as the sport prefix and (b) UPPERCASES every remaining segment. So
// the caller receives `OPEN`, `CUP`, `AND`, `OF`, `DEL` and `NCAAF` with no way
// to tell an acronym from an ordinary word it shouted a moment earlier. Any
// length threshold therefore mis-classifies in BOTH directions, necessarily:
// short English words stay shouted, long acronyms get de-capitalised. Measured
// on the live `/api/calibration` payload 2026-08-30, that produced
// `WTA Cincinnati OPEN` (the FIRST parked chip on the page), `FIFA World CUP`,
// `Spain COPA DEL REY`, `League OF Ireland`, and `Ncaaf` — whose correct label
// `NCAAF` was sitting in `LEAGUE_DISPLAY` and got de-capitalised on the way out.
//
// Worse, (a) fires on keys that are not `sport_league` at all. Calibration
// categories include plain two-word concepts, and dropping segment 0 turned
// `track_and_field` into `AND Field`, `ai_safety` into `Safety`, `horse_racing`
// into `Racing` and `figure_skating` into `Skating`. The old guard suite's own
// three "unknown key" examples rendered `POLO`, `Volleyball` and `NEW Sport` —
// and PASSED, because it asserted the label was not the raw key and that its
// first character was uppercase, never that it kept the words.
//
// So the label is now built from the raw key directly and never round-trips
// through the all-caps generator. Two consequences worth stating: a curated
// `LEAGUE_DISPLAY` name is returned VERBATIM (we do not re-case an opinion), and
// the sport prefix is dropped by MEMBERSHIP in a known-prefix set rather than by
// POSITION, so `horse_racing` keeps its horse.

/**
 * Sport prefixes that may be dropped from a compound key.
 *
 * Derived from the two maps that already enumerate our sports rather than
 * hand-listed, so a sport added to `LEAGUE_DISPLAY` becomes droppable without a
 * second edit here. Membership is the whole point: segment 0 of
 * `track_and_field` is not in this set, so it survives.
 */
const DROPPABLE_SPORT_PREFIXES: ReadonlySet<string> = new Set(
  [...Object.keys(LEAGUE_DISPLAY), ...Object.keys(SPORT_KEY_MAP)]
    .filter((k) => k.includes("_"))
    .map((k) => k.split("_")[0])
);

/**
 * Tokens printed in capitals.
 *
 * The sports half is derived from the all-caps words we already print in
 * curated `LEAGUE_DISPLAY` values — an acronym is a token we have already
 * decided to shout somewhere — so NFL, NCAAB, WNCAAB, ATP, WTA, US and T20 cost
 * nothing to maintain. The explicit half below is for tokens that appear only
 * inside payload KEYS and so have no curated value to be read out of.
 */
const CURATED_ACRONYMS: ReadonlySet<string> = new Set([
  ...Object.values(LEAGUE_DISPLAY)
    .flatMap((v) => v.split(/\s+/))
    .map((w) => w.replace(/[^A-Za-z0-9:]/g, ""))
    .filter((w) => w.length >= 2 && /[A-Z]/.test(w) && w === w.toUpperCase())
    .map((w) => w.toLowerCase()),
  // Present in category keys only: no curated value spells these out.
  // `fa` and `conmebol` are here because dropping the old all-caps round-trip
  // would otherwise have turned the wrong "FA CUP" into the equally wrong
  // "Fa Cup" — a governing body is an acronym whichever word follows it.
  "ai", "bmx", "conmebol", "dfb", "efl", "epl", "fa", "fcs", "fifa", "mls",
  "spl", "uefa", "usa",
]);

/**
 * Words that stay lowercase inside a title — unless they lead, where they are
 * capitalised like any other first word.
 *
 * `la` is deliberately ABSENT: `soccer_spain_la_liga` is "Spain La Liga", and
 * the old code's "Spain LA LIGA" is the failure this list must not invert into
 * "Spain la Liga".
 */
const TITLE_SMALL_WORDS: ReadonlySet<string> = new Set([
  "and", "da", "de", "del", "di", "du", "of", "the",
]);

function labelToken(token: string, isFirst: boolean): string {
  if (CURATED_ACRONYMS.has(token)) return token.toUpperCase();
  if (!isFirst && TITLE_SMALL_WORDS.has(token)) return token;
  return token.charAt(0).toUpperCase() + token.slice(1).toLowerCase();
}

/**
 * L2-103 Item 3b (Alex D5): a thin sub-league (e.g.
 * `icehockey_sweden_hockey_league`, ~730 outcomes) must NOT collapse to its
 * parent sport's display name ("Hockey"), because the parent sport is already
 * graded in the Category Breakdown above — that made a niche chip read as
 * "Hockey is still coming soon". Prefer the specific league label.
 *
 * **Never returns a lowercase or underscored key** — including for the bare
 * single-word categories (chess, crypto, commodities) the previous version
 * passed straight through. Those only looked fixed on the parked chips, which
 * carried a CSS `capitalize` class; in the By Category tabs and the breakdown
 * table, which do not, `crypto` reached the reader lowercase.
 */
export function nicheCatLabel(raw: string): string {
  // A curated name is an opinion. Return it verbatim — re-casing it is what
  // turned LEAGUE_DISPLAY's own "NCAAF" into "Ncaaf".
  const curated = LEAGUE_DISPLAY[raw];
  if (curated) return curated;

  const tokens = raw.split("_").filter(Boolean);
  if (tokens.length === 0) return raw;
  // Drop the sport prefix only when something is left to name the row with.
  const named =
    tokens.length > 1 && DROPPABLE_SPORT_PREFIXES.has(tokens[0])
      ? tokens.slice(1)
      : tokens;

  return named.map((t, i) => labelToken(t, i === 0)).join(" ");
}

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
