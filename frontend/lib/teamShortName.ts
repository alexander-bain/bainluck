/**
 * UX-1065 (#2936) — the compact form of a TEAM's name.
 *
 * The site has always shortened a team to `name.split(" ").pop()`. That rule
 * encodes the AMERICAN naming convention, `<place> <nickname>`, where the last
 * word is the distinctive half: "Los Angeles Lakers" -> "Lakers" is right, and
 * this module keeps it.
 *
 * It is wrong whenever the last word is not a name at all — the ENGLISH club
 * convention `<place> <club-type>` ("Ipswich Town" -> "Town", "Austin FC" ->
 * "FC") and squad qualifiers ("Argentina W" -> "W", "Chaves B" -> "B"). Those
 * render a word that identifies nobody, and on 2026-09-04 the reported event
 * page printed "Town" three times against "Liverpool".
 *
 * Measured on production 2026-09-04 over all 4,701 DISTINCT multi-word team
 * names (exact, not a sample — the whole population, pulled in hash chunks):
 *
 *     trailing token <= 2 chars (FC 96, W 33, Jr 28, B 22, II 15, IF 13, ...)  326
 *     club-type word (State 33, City 26, United 24, Town 11, Rovers 6, ...)    126
 *     squad number / U21                                                        19
 *     ------------------------------------------------------------------------
 *     names that stop being shortened                              471  (10.0%)
 *
 * The remaining 90% keep `.pop()` unchanged. A sweep of every other trailing
 * token appearing on >= 9 distinct names returns only mascots (Eagles 26,
 * Bulldogs 22, Tigers 20, ...) and surnames (Silva 16, Garcia 10) — so the
 * club-word set below is complete against the current population, and that
 * sweep is how to re-check it when the population grows.
 *
 * NOTE the issue's own figure is 6,335 of 9,754 (65%). That counts table ROWS
 * rather than distinct names (43% of `teams` is duplicate name rows, #1204 /
 * #1946), and it counts every shared last word — which is mostly tennis
 * SURNAMES and college MASCOTS, where `.pop()` is the intended behaviour.
 * 10.0% of distinct names is the population where the output is not a name.
 *
 * FAILS SAFE BY CONSTRUCTION: every branch returns the team's abbreviation,
 * its last word, or its full name. It can never emit a string the team is not
 * called, and the only direction it moves is "less short, more correct".
 */

/**
 * Trailing words that are a club TYPE rather than a club's name. Each one is
 * in here because it was MEASURED as a trailing token on production, with its
 * count; nothing is included on the strength of sounding like a club word.
 * Deliberately absent: "Rangers" and "Kings", which are trailing MASCOTS in
 * North American leagues (Texas Rangers, LA Kings) as well as English club
 * words, so shortening them is right more often than it is wrong.
 */
const CLUB_TYPE_SUFFIXES: ReadonlySet<string> = new Set([
  "united", // 24
  "city", // 26
  "town", // 11
  "state", // 33
  "rovers", // 6
  "wanderers", // 5
  "albion", // 4
  "county", // 3
  "athletic", // 4  (note: "Athletics", the Oakland mascot, is NOT this word)
  "calcio", // 4
  "club", // 3
  "academy", // 2
  "sporting", // 1
]);

function alphanumeric(token: string): string {
  return token.replace(/[^A-Za-z0-9]/g, "");
}

/**
 * #3110 — a doubles PAIR is one competitor written as two surnames, and the
 * last-word rule silently deletes the first one: "Siniakova / Townsend" became
 * "Townsend", so the US Open women's doubles final read as a singles match
 * between two people who were not playing singles.
 *
 * The separator that means "and" is a SPACED slash, and that is the whole test.
 * Measured on production 2026-09-06 over every name carrying one — 252 distinct
 * sides across 30 days of events, 0 rows in `teams` — and all 252 are pairs;
 * none has three parts. Of those, 233 (92.5%) lose a player today; the other 19
 * survive only by accident, because their trailing token reduces to <= 2 chars
 * ("Arnaldi / Struff J-L" keeps both players because "J-L" is short, not
 * because anything here knows it is a pair).
 *
 * An UNSPACED slash is a different character in the data and is deliberately
 * not matched: it is part of one entity's own name. "Bodo/Glimt" (a club, event
 * 15296763), "Scranton/Wilkes-Barre RailRiders" and "W-B/Scranton Penguins"
 * (both in the UX-1065 corpus) must keep shortening exactly as they do — and
 * the pairs ESPN writes without spaces ("Krawietz/Puetz") already survive,
 * because a name with no whitespace has no last word to fall off.
 *
 * The pair is returned WHOLE rather than shortened side-by-side. Two reasons:
 * the sides are already surname-compact in every one of the 252 (the longest is
 * 41 characters), and returning the input keeps this module's stated invariant
 * literally true — every output is the last word or the full name, never a
 * string the competitor is not called.
 */
export function isDoublesPair(name: string): boolean {
  return / \/ /.test(name);
}

/**
 * Is this trailing word incapable of identifying the team on its own?
 *
 * The <= 2 character clause is a LENGTH test rather than a list, which is why
 * it needs no maintenance: "FC", "SC", "IF", "SK", "FK", "CF", "HC", "BK",
 * "AC", "W", "B", "II" are all caught without naming any of them. It also
 * catches a handful of genuine two-letter surnames ("Ann Li" -> keeps
 * "Ann Li"); that costs compactness and never correctness.
 */
export function isNonDistinctiveTrailingWord(token: string): boolean {
  const bare = alphanumeric(token);
  if (bare.length === 0) return true;
  if (bare.length <= 2) return true;
  if (CLUB_TYPE_SUFFIXES.has(bare.toLowerCase())) return true;
  // Squad markers: "U21", "U23", and bare reserve numbers.
  if (/^u\d{1,2}$/i.test(bare)) return true;
  if (/^\d+$/.test(bare)) return true;
  return false;
}

/**
 * The letters a crest square falls back to when no logo or flag exists.
 *
 * #2882's neighbour, found on the same LOOK. The card built this inline as
 * `name.split(" ").map(w => w.charAt(0)).join("").slice(0, 2)`, which counts a
 * spaced slash as a WORD: "Bondar / Kalinina" makes the initials "B", "/", "K"
 * and the two-character cap then cuts the pair in half, so every doubles crest
 * on `/sport/tennis/wta` read "B/", "S/", "H/", "P/" — a first initial and a
 * dangling separator, naming one player and half a punctuation mark. The event
 * hero two clicks away already drew "S/T" for the same fixture.
 *
 * A pair therefore gets ONE initial per side joined by the slash it arrived
 * with ("S/T"), capped at two sides because `isDoublesPair`'s own corpus has no
 * three-part name and a crest square has room for three glyphs, not five.
 * Everything else keeps the two-initial rule exactly: "Osaka" -> "O", "Boston
 * Celtics" -> "BC", "Bodo/Glimt" -> "B" (an UNSPACED slash is part of one
 * entity's name, so it is not a pair here either — same test as everywhere
 * else in this module).
 */
export function teamCrestInitials(name: string | null | undefined): string {
  const full = (name ?? "").trim();
  if (!full) return "";
  if (isDoublesPair(full)) {
    return full
      .split(" / ")
      .slice(0, 2)
      .map(side => side.trim().charAt(0))
      .join("/")
      .toUpperCase();
  }
  return full
    .split(/\s+/)
    .map(word => word.charAt(0))
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

/**
 * One side's compact name. Prefer this only where the other side is genuinely
 * unavailable — `teamShortNames` below can additionally catch the case where
 * two teams shorten to the SAME word, which one side alone cannot see.
 */
export function teamShortName(
  name: string | null | undefined,
  abbreviation?: string | null,
): string {
  const full = (name ?? "").trim();
  if (!full) return "";
  // #3110: both halves of a doubles pair, or neither.
  if (isDoublesPair(full)) return full;
  const words = full.split(/\s+/);
  if (words.length < 2) return full;
  if (isNonDistinctiveTrailingWord(words[words.length - 1])) return full;
  return words[words.length - 1];
}

export interface TeamNameInput {
  name: string | null | undefined;
  abbreviation?: string | null;
}

export interface TeamShortNamePair {
  home: string;
  away: string;
}

/**
 * Both sides at once, which is what every display call site actually has.
 *
 * Deciding the pair together buys two things one-at-a-time cannot:
 *
 *  1. An abbreviation is used only when BOTH sides carry one, so the card can
 *     never read "IPS vs Liverpool". Measured on 120 live events: both sides
 *     carry one on 1, exactly one side on 7, neither on 112 — so this clause
 *     is real but rare, and it is NOT the half of this fix that ships today.
 *     (It is why the issue's "prefer team_data.abbreviation" cannot be the
 *     whole repair: on 93% of events there is no abbreviation to prefer.)
 *
 *  2. If the two sides shorten to the same word, both fall back to their full
 *     names — otherwise the card says "FC" beat "FC". Measured on the same 120
 *     events: 5 pairs collide, and all 5 are "FC vs FC", so today this clause
 *     is fully covered by the length test above and adds nothing on its own.
 *     It is kept as the structural backstop for the MASCOT case (60 teams end
 *     in "Bulldogs", 59 in "Eagles"), which the length test cannot see and
 *     which college fixtures will eventually produce.
 *
 * Asymmetry is allowed otherwise, and on purpose: "Bradford City" vs
 * "Sheffield Wednesday" must render as "Bradford City" vs "Wednesday",
 * because "Wednesday" IS that club's distinctive name. Forcing both sides to
 * the full name whenever either falls back would lose that.
 */
export function teamShortNames(
  home: TeamNameInput,
  away: TeamNameInput,
): TeamShortNamePair {
  const homeFull = (home.name ?? "").trim();
  const awayFull = (away.name ?? "").trim();

  const homeShort = teamShortName(homeFull);
  const awayShort = teamShortName(awayFull);

  // Did the last-word rule have to give up on this side? (A single-word name
  // has nothing to shorten and has not "given up" — it is already compact.)
  //
  // #3110: a doubles pair is compact in the same way — "Siniakova / Townsend"
  // is two surnames and there is nothing left to drop — so it must not reach
  // for the abbreviation rescue and print the chip's own "S/T" a second time
  // underneath it. Unreachable on today's data (pairs have no `teams` row, so
  // no abbreviation exists to rescue with: 0 of 252 measured), and here so it
  // stays unreachable the day one does.
  const gaveUp = (full: string, short: string) =>
    short === full && full.split(/\s+/).length >= 2 && !isDoublesPair(full);
  const homeGaveUp = gaveUp(homeFull, homeShort);
  const awayGaveUp = gaveUp(awayFull, awayShort);
  const collide =
    !!homeShort &&
    !!awayShort &&
    homeShort.toLowerCase() === awayShort.toLowerCase();

  // The abbreviation is a RESCUE, not a preference. Replaying the preference
  // form over 120 live events found it firing on exactly one card and making
  // it WORSE: Fremantle Dockers v Hawthorn Hawks went from "Dockers / Hawks"
  // to "FRE / HAW". Two good nicknames are better than two airport codes, so
  // abbreviations are reached for only when the last-word rule has already
  // failed — and then only if BOTH sides carry one, so the pair stays
  // symmetric and can never read "IPS vs Liverpool".
  if (homeGaveUp || awayGaveUp || collide) {
    const homeAbbrev = (home.abbreviation ?? "").trim();
    const awayAbbrev = (away.abbreviation ?? "").trim();
    if (homeAbbrev && awayAbbrev) {
      return { home: homeAbbrev, away: awayAbbrev };
    }
  }

  if (collide) {
    return { home: homeFull || homeShort, away: awayFull || awayShort };
  }

  return { home: homeShort, away: awayShort };
}
