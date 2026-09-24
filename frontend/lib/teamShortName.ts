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
 *
 * #4250 — the second block is the THREE-and-four-letter half of the same idea,
 * and it was missing because the `length <= 2` clause below reads like it
 * covers the club-initial case. It does not: "Sunderland AFC" is three letters
 * long, so the event hero printed the away side as **"AFC"** against a
 * full-length "Manchester City FC" (production, 2026-09-09, phone width). The
 * iPhone's `TeamShortName.swift` has caught `afc` since #3374; only the browser
 * was wrong, and the guard named for single-sourcing the two reads the Swift
 * alone. `teamDesignatorParityAcrossClients.test.ts` now compares the sets.
 *
 * Counts are distinct multi-word `events` team names, both sides, whole
 * population, measured 2026-09-09. Deliberately absent from this block:
 * "RFS" (2) — "FC RFS" and "FK RFS" are Riga Football School's own name, so
 * they must keep shortening — and "USA" (8), "EMEA", "NXT", "KOI", which name
 * somebody.
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
  // #4250, measured as TRAILING tokens the <= 2 rule is one letter too short for.
  "afc", // 68  Barrow AFC, Ashington AFC, Athlone Town AFC
  "wfc", // 8   Arsenal WFC, Manchester City WFC
  "sad", // 8   Portimonense SAD (the Spanish/Portuguese legal suffix)
  "lfc", // 2   Liverpool LFC
  "pfk", // 2   Neftçi PFK
  "nps", // 2   Volos NPS
  // #4250, carried over from the Swift's set so the two clients agree. These
  // are club initials that appear LEADING far more often than trailing
  // ("PSV Eindhoven"), so most have no measured trailing count here; they cost
  // nothing when they never fire and they keep the parity guard green.
  "cfc",
  "aik",
  "tsv",
  "vfb",
  "vfl",
  "bsc",
  "ssc",
  "psv",
  "gif",
  "bif",
  "fsv",
  "spvgg",
  "rkc",
  "nec",
  "atletico",
  "women",
  "res",
]);

function alphanumeric(token: string): string {
  return token.replace(/[^A-Za-z0-9]/g, "");
}

/**
 * Whitespace OR a dash of any kind, so "Paris Saint-Germain" and "Paris Saint
 * Germain" — both live on production the same afternoon — tokenise alike.
 *
 * Named because two things now share it: `teamCrestBadge`'s distinctive-token
 * count (#4466) and `handPickedKey` below (#4627). The iPhone's
 * `TeamShortName.tokenSeparators` is the same set, and the badge has been
 * spelling-independent since #4539 — the LABEL was not, which is the half of
 * #4627 nobody had named.
 */
const TOKEN_SEPARATORS = /[\s‐-―-]+/;

/**
 * Clubs whose compact label the rule cannot derive, decided by hand (#4627).
 *
 * Alex's ruling (option B, relayed by Fable-5 Sat 2026-09-12 6:14am PT): Paris
 * Saint-Germain is "PSG" — the crest letters, as an explicit entry, NOT a rule
 * change that would turn the Lakers into "LAL". "Germain" is a fragment and
 * "Lakers" is a name, and no test on the string alone tells them apart, so this
 * is a hand-kept list and it is meant to STAY SMALL. Per-club abbreviation data
 * (#3353) is the real answer and was deliberately deferred.
 *
 * Exported, like the key function below, so the guard can assert the two things
 * that are invisible from outside and would otherwise rot silently: that no two
 * clubs claim one label, and that every key is already in the normalised form
 * `handPickedKey` produces. A key written "Paris Saint-Germain" would be a DEAD
 * entry that every test calling only `teamShortName` would pass straight over.
 *
 * The iPhone's `TeamShortName.handPickedLabels` is the same table, and
 * `teamDesignatorParityAcrossClients.test.ts` reads both out of source rather
 * than transcribing either — a transcribed copy is the third implementation
 * that whole file exists to prevent.
 */
export const HAND_PICKED_LABELS: ReadonlyMap<string, string> = new Map([
  ["paris saint germain", "PSG"],
]);

/**
 * #5634 — nicknames that are TWO words, where the last word alone is not the
 * name. The last-word rule turned "Boston Red Sox" into "Sox" (which is also the
 * White Sox), "Alabama Crimson Tide" into "Tide", "Notre Dame Fighting Irish"
 * into "Irish", and Duke, Arizona State and the New Jersey Devils all into
 * "Devils". The hero printed "Sox · WON" on a finished Red Sox game
 * (`/events/15317515`, 2026-09-24).
 *
 * A list, not a rule, for the same reason as `HAND_PICKED_LABELS`: "Red Sox" is
 * one name and "Bay Rays" is the tail of a place plus a name, and nothing on the
 * string alone tells them apart. Unlike that table this one does not pick a label — it
 * only keeps the word the rule was dropping, so an entry can never make a label
 * less true than the full name.
 *
 * Every entry is a live name: all 41 were measured on production 2026-09-24
 * over 60 days of MLB, NHL, NBA, WNBA, NFL and NCAAF `events` (372 names), by
 * running this module's own `teamShortName` over them. Keys are the
 * `nicknameKey` form (letters and digits only, lower case), so "Ragin' Cajuns"
 * and "Ragin Cajuns" reach the same entry.
 */
export const TWO_WORD_NICKNAMES: ReadonlySet<string> = new Set([
  // MLB
  "red sox",
  "white sox",
  "blue jays",
  // NHL
  "maple leafs",
  "red wings",
  "blue jackets",
  "golden knights",
  // NBA
  "trail blazers",
  // NCAAF
  "black bears",
  "black knights",
  "blue devils",
  "blue hens",
  "blue raiders",
  "crimson tide",
  "delta devils",
  "demon deacons",
  "fighting camels",
  "fighting hawks",
  "fighting illini",
  "fighting irish",
  "golden bears",
  "golden eagles",
  "golden flashes",
  "golden gophers",
  "golden hurricane",
  "golden lions",
  "green wave",
  "horned frogs",
  "mean green",
  "nittany lions",
  "ragin cajuns",
  "rainbow warriors",
  "red raiders",
  "red wolves",
  "runnin bulldogs",
  "scarlet knights",
  "sun devils",
  "tar heels",
  "thundering herd",
  "wolf pack",
  "yellow jackets",
]);

/** One token as `TWO_WORD_NICKNAMES` keys it: letters and digits, lower case. */
function nicknameKey(token: string): string {
  return token.replace(/[^\p{L}\p{N}]/gu, "").toLowerCase();
}

/**
 * The last two words, as written, when together they are one nickname — else
 * null. Needs at least two words; a name that IS the nickname ("Red Sox")
 * returns itself.
 */
export function twoWordNickname(words: readonly string[]): string | null {
  if (words.length < 2) return null;
  const pair = words.slice(-2);
  const key = pair.map(nicknameKey).join(" ");
  return TWO_WORD_NICKNAMES.has(key) ? pair.join(" ") : null;
}

/**
 * The lookup key for `HAND_PICKED_LABELS`: one club, one key, however the row
 * spells it.
 *
 * Three normalisations, each paying for a spelling that is live on production
 * today. Measured over 60 days of `events` on 2026-09-12 by native/131, this
 * club alone has THREE — "Paris Saint-Germain FC" (14 events),
 * "Paris Saint-Germain" (9) and "Paris Saint Germain" (9) — rendering as three
 * different labels: the full name, "Saint-Germain" and "Germain".
 *
 *  1. Split on dashes as well as whitespace (`TOKEN_SEPARATORS`).
 *  2. Drop everything that is not a letter or a digit, so "1. FC …" and
 *     "Crimson (W)" key on their words rather than on their punctuation. This
 *     uses a UNICODE-aware class rather than `alphanumeric` above, deliberately:
 *     `alphanumeric` is ASCII and would key "1. FC Köln" as `1 fc kln` while the
 *     iPhone's `isLetter` keeps the ö. One club, one key, means one key ACROSS
 *     CLIENTS, so this half has to follow the Swift and not the neighbour.
 *  3. Strip trailing designators — but NEVER below two tokens. The floor is the
 *     whole of the rule: without it "Manchester United" keys as `manchester`,
 *     which is what "Manchester City" keys as too, and a future entry for either
 *     silently relabels the other. It also keeps "Arsenal W" off "Arsenal". A
 *     loop, not one step, because both suffixes of "Manchester United FC" are
 *     designators — and it stops at the floor.
 *
 * Every name in the population runs through this, so it may not be expensive to
 * be wrong in: a key that matches nothing costs one map miss and the last-word
 * rule decides exactly as it did before.
 */
export function handPickedKey(name: string): string {
  const tokens = name
    .split(TOKEN_SEPARATORS)
    .map((token) => token.replace(/[^\p{L}\p{N}]/gu, ""))
    .filter(Boolean);
  while (tokens.length >= 3 && isNonDistinctiveTrailingWord(tokens[tokens.length - 1])) {
    tokens.pop();
  }
  return tokens.join(" ").toLowerCase();
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
 *
 * #4250 is the lesson that the clause stops one letter short of the club
 * initials it looks like it covers, which is why the set above now carries a
 * three-letter block and this file has a cross-client parity guard.
 */
export function isNonDistinctiveTrailingWord(token: string): boolean {
  const bare = alphanumeric(token);
  if (bare.length === 0) return true;
  if (bare.length <= 2) return true;
  if (CLUB_TYPE_SUFFIXES.has(bare.toLowerCase())) return true;
  // Squad markers: "U21", "U23", and bare reserve numbers.
  if (/^u\d{1,2}$/i.test(bare)) return true;
  if (/^\d+$/.test(bare)) return true;
  // #4250 — a roman numeral is a reserve side ("Ludogorets III") or a person's
  // generational suffix ("Kai Kamaka III"); 6 distinct names, and neither one
  // is called "III". "II" and "IV" already fall to the length clause.
  if (/^i{2,3}$/i.test(bare)) return true;
  return false;
}

/**
 * The sport keys whose competitor is a PERSON rather than a club.
 *
 * #4624 — the discriminator #4466 said was not in the string, and it is not:
 * "Paris Saint Germain" and "Eloy Mendez Alcantara" are both three
 * all-distinctive words, so no filter that keeps the club working can tell them
 * apart. The SPORT tells them apart, and both clients hold it already.
 *
 * Matched against the key's FIRST SEGMENT, never as a substring: every
 * production key is `<sport>_<tour-or-league>` (`tennis_atp_us_open`,
 * `mma_mixed_martial_arts`), so the segment is the sport. A `contains` would
 * answer for keys nobody listed, and England's Boxing Day fixtures are a
 * plausible `soccer_england_boxing_day_*` — under a substring matcher every
 * club in it would be badged as a person.
 *
 * `motorsport` is deliberately absent (0 of its 31 production names reach the
 * fork, so the entry would be unobservable) and `esports` is absent because
 * those competitors are organisations, which is the club case the fork exists
 * for. This is the iPhone's `individualSportPrefixes`
 * (`TeamShortName.swift`) and the two sets are compared out of source by
 * `__tests__/teamDesignatorParityAcrossClients.test.ts`.
 */
export const INDIVIDUAL_SPORT_PREFIXES: ReadonlySet<string> = new Set([
  "tennis",
  "golf",
  "mma",
  "boxing",
]);

/**
 * Does this sport key name a competition between PEOPLE?
 *
 * Null, undefined or empty answers `false`, so a caller that does not know its
 * sport keeps exactly the badge it paints today. The gate can only ever be
 * opened by a caller that positively knows.
 */
export function namesAPerson(sportKey: string | null | undefined): boolean {
  // The type test is not belt-and-braces, and a passing suite went red proving
  // it: `teamCrestBadge` gained a second parameter, and `names.map(teamCrestBadge)`
  // — point-free, legal, and in this repo — hands `map`'s INDEX in as the sport.
  // A number reached `.trim()` and threw, which would have been a blank card
  // rather than a wrong badge. Anything that is not a string means "the caller
  // did not tell me the sport", which is the shipped rule.
  if (typeof sportKey !== "string") return false;
  const key = sportKey.trim().toLowerCase();
  if (!key) return false;
  return INDIVIDUAL_SPORT_PREFIXES.has(key.split("_")[0]);
}

/**
 * #5634 — does this sport key name a football (soccer) competition, where a
 * club's last word is so often its CITY that the last-word rule cannot be used?
 *
 * "1. FC Union Berlin" became "Berlin" (so did Hertha, Croatia and Füchse),
 * "Bayern Munich" became "Munich" (so did 1860), "Real Salt Lake" became
 * "Lake". Measured 2026-09-24 over the first 1,000 distinct soccer names of 60
 * days of production `events`: the rule folds several clubs onto one word —
 * "Cali" ×5, "Juniors" ×4, "Central" ×4, "Boys" ×4, "Mineiro" ×3 — and those
 * are not all cities, so no place-name list can close it. English clubs where
 * the last word IS the name ("Wednesday", "Villa") lose only compactness.
 *
 * Same first-segment match and same fail-closed type test as `namesAPerson`:
 * a caller that does not pass the sport keeps exactly the shipped rule.
 */
export function keepsWholeClubName(sportKey: string | null | undefined): boolean {
  if (typeof sportKey !== "string") return false;
  const key = sportKey.trim().toLowerCase();
  if (!key) return false;
  return key.split("_")[0] === "soccer";
}

/**
 * #5634 — a football club's label: its own name with LEADING designators
 * dropped, never below two words. "1. FC Union Berlin" → "Union Berlin",
 * "CA Boca Juniors" → "Boca Juniors", "1. FC Köln" → "FC Köln" (the floor),
 * "AC Milan", "Real Salt Lake" and "2 de Mayo" (never onto a particle) unchanged.
 *
 * Only a token the LENGTH or digit clauses of `isNonDistinctiveTrailingWord`
 * catch is dropped ("1.", "FC", "CA", "AD", "05") — never a word from
 * `CLUB_TYPE_SUFFIXES`, which as a leading word is part of the name:
 * "Sporting Kansas City" is not "Kansas City", "Atletico Madrid" is not
 * "Madrid". The output is always a tail of the name, so it is a string the club
 * is called. The caller keeps it only when it is at most
 * `WHOLE_CLUB_NAME_MAX_WORDS` long.
 */
const WHOLE_CLUB_NAME_MAX_WORDS = 3;

function wholeClubName(full: string): string {
  const words = full.split(/\s+/);
  let start = 0;
  while (words.length - start > 2) {
    const bare = alphanumeric(words[start]);
    if (bare.length > 2 && !/^\d+$/.test(bare)) break;
    // "2 de Mayo" is not "de Mayo": a label never starts on a particle.
    if (/^\p{Ll}/u.test(words[start + 1])) break;
    start += 1;
  }
  return words.slice(start).join(" ");
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
 * #4466 — the crest badge for the LARGE tile (the 64px square on the Discover
 * duel cards). Three glyphs, as that tile has always drawn.
 *
 * THE DEFECT. `teamShortName(name).slice(0, 3)` painted PSG's tile **`GER`** on
 * production page one (2026-09-09 12:40 PT), and **`SAI`** an hour later on a
 * second LOOK — because the stored name is an INPUT and both spellings are
 * live:
 *
 *     "Paris Saint Germain"  -> last word "Germain"       -> "GER"
 *     "Paris Saint-Germain"  -> last word "Saint-Germain" -> "SAI"
 *
 * THE RULE, and why it is a fork rather than a replacement. The last-word rule
 * is *right* for the American `<place> <nickname>` convention and, thanks to
 * CLUB_TYPE_SUFFIXES above, for `<place> <club-type>` too — "Boston Celtics" is
 * "CEL", "Ipswich Town" is "IPS", "Altrincham FC" is "ALT". Where it has no
 * chance is a name whose DISTINCTIVE part is three or more words, because then
 * the trailing token is a fragment of a compound rather than a name anybody
 * uses. So: take initials only of the tokens that identify the club, and only
 * when there are three or more of them; anything else keeps the shipped
 * behaviour exactly. Hyphens split like spaces, which is what makes the two
 * PSG spellings agree.
 *
 * IT IS NOT A BARE WORD COUNT, AND THAT IS THE WHOLE DESIGN. A first version
 * of this function took initials of every token once the name had three parts.
 * Measured over the WHOLE production name population (19,675 distinct
 * multi-part `events` team names, 2026-09-09) that rule introduced 33 badges
 * that were not there before and that nobody may ship:
 *
 *     "Warrington Town FC"    -> W,T,F  -> "WTF"   (and 11 more `<W> Town FC`)
 *     "FC Akhmat Grozny"      -> F,A,G  -> "FAG"
 *     "FC Universitatea Cluj" -> F,U,C  -> "FUC"
 *     "Al Sadd SC"            -> A,S,S  -> "ASS"
 *
 * Every one of those is a club-type or article token — "FC", "SC", "Town",
 * "Al" — being counted as if it identified somebody. `isNonDistinctiveTrailing‐
 * Word` already knows exactly which tokens those are (it is what makes
 * `teamShortName` right on "Ipswich Town"), so this filters through it FIRST
 * and the whole class disappears structurally: "Warrington Town FC" keeps
 * "WAR", "FC Akhmat Grozny" keeps "GRO", "Al Sadd SC" keeps "SAD", while
 * "Paris Saint Germain" — three tokens that all identify the club — still
 * becomes "PSG".
 *
 * MEASURED, with these functions and not an approximation of them, over the
 * COMPLETE population of fixtures in a window (not a sample), counting the
 * fixtures whose two sides paint the SAME badge:
 *
 *                              ±24h (443 fixtures)   ±7d (3,261 fixtures)
 *     teamShortName().slice(0,3)        6                    35
 *     teamCrestInitials (2 glyphs)      6                    28
 *     this function                     2                    17
 *
 * Both windows are the COMPLETE set of fixtures whose two sides are multi-word,
 * reconciled against their own `COUNT(*)` and pulled in hash chunks because the
 * ±7d one exceeds the 1,000-row cap. No fixture that discriminates today stops
 * discriminating (BROKE = 0 on both), and 18 of the ±7d collisions are removed.
 *
 * `teamCrestInitials` is rejected because at two glyphs the Mets and the
 * Yankees are both "NY"; it barely improves on shipping. (A first pass at this
 * census approximated `teamShortName` in Python as a bare last-word rule and
 * reported numbers that inverted the answer — the proxy did not know about
 * CLUB_TYPE_SUFFIXES. Re-measured through the actual TypeScript. A second pass
 * sampled 1,000 rows ordered by `commence_time DESC`, which is not a window at
 * all but the furthest-FUTURE fixtures, and read a tie. Both wrong numbers were
 * on this comment before the population was taken exhaustively.)
 *
 * ACCEPTED COST: 21.4% of the 19,675 names change, all within the population
 * where the old value was a fragment. Some are plainly better ("New York Mets"
 * MET -> NYM, "Los Angeles Lakers" LAK -> LAL); some trade familiarity for
 * consistency ("Boston Red Sox" SOX -> BRS). Two pinned controls in
 * `teamShortNameUx1065.test.tsx` move with it and say why. Nothing gets SHORTER
 * than it is today (badges under three glyphs: 210 on master, 77 here; newly
 * shortened: 0) and no name newly paints an unshippable badge.
 *
 * A DOUBLES PAIR IS NOT TOUCHED. #3110 pinned this tile at three letters of the
 * first surname ("SIN", "HUN") and that decision is not #4466's to reopen — a
 * pair is not a compound name, it is two names.
 */
export function teamCrestBadge(
  name: string | null | undefined,
  sportKey?: string | null,
): string {
  const full = (name ?? "").trim();
  if (!full) return "";
  // #3110 pinned the doubles tile at three letters of the first surname, and
  // that decision is not this function's to reopen — so a pair keeps the
  // shipped expression untouched, including its edge cases.
  if (isDoublesPair(full)) return teamShortName(full).slice(0, 3).toUpperCase();
  // Hyphen splits like a space so that "Paris Saint-Germain" and "Paris Saint
  // Germain" — both live on production the same afternoon — agree.
  const distinctive = full
    .split(TOKEN_SEPARATORS)
    .filter(Boolean)
    .filter(token => !isNonDistinctiveTrailingWord(token));
  const shipped = teamShortName(full).slice(0, 3).toUpperCase();
  const initials = distinctive
    .map(word => word.charAt(0))
    .join("")
    .slice(0, 3)
    .toUpperCase();
  // #4624 — the fork is for CLUBS, so a person's sport closes it and the badge
  // is the rule that shipped before it: for a three-part name, their surname.
  // "Eloy Mendez Alcantara" is `ALC`, not `EMA`. `shortNameBadge` is the SAME
  // expression the fewer-than-three path already takes, so a person is badged
  // by the rule this module applies to every two-part name rather than by a
  // third one — and a surname that spells an unshippable badge keeps the
  // initials, which is the backstop below read the other way round.
  const person = distinctive.length >= 3 && namesAPerson(sportKey);
  const surname = person ? shortNameBadge(full, distinctive) : "";
  const candidate =
    distinctive.length < 3
      ? shortNameBadge(full, distinctive)
      : person && !UNSHIPPABLE_BADGES.has(surname)
        ? surname
        : initials;
  // Backstop for the residue the token filter cannot reach: a three-part PERSON
  // name is all-distinctive by construction ("Ana Sofia Sanchez" -> "ASS"), and
  // no filter that keeps "Paris Saint Germain" working can tell the two apart
  // from the string alone. The surname is the right badge for a person anyway,
  // so reverting to the shipped value is the correct answer, not just a censor.
  //
  // The test is "do not INTRODUCE one", not "never emit one": 43 names already
  // paint a badge in this set on master ("Shirak Gyumri" -> "SHI") by the
  // untouched last-word rule, and silently re-lettering those is a different
  // change on another lane's evidence. Filed separately as #4537.
  if (UNSHIPPABLE_BADGES.has(candidate) && !UNSHIPPABLE_BADGES.has(shipped)) {
    return shipped;
  }
  return candidate;
}

/**
 * The last-word badge — the shipped rule — with its own fragment case closed.
 *
 * `teamShortName` FAILS SAFE by returning the full name when it cannot find a
 * distinctive trailing word (see its header). That is right for a NAME slot and
 * wrong for a three-glyph badge, because slicing a multi-word string prints a
 * fragment with a space in it, which is the very thing #4466 is named after:
 *
 *     "AC Milan U20"          -> teamShortName gives it all back -> "AC "
 *     "1. FC Heidenheim 1846"                                    -> "1. "
 *     "Al Sadd SC"                                               -> "AL "
 *
 * Measured over the whole production population (19,675 distinct multi-part
 * `events` team names, 2026-09-09): 207 names paint a badge containing
 * whitespace, and all 207 already do so on master — this is a pre-existing
 * defect of the same class, not one this change introduces. The distinctive
 * tokens are already computed by the caller, so the fix is to use them:
 * "AC Milan U20" is "MIL", "1. FC Heidenheim 1846" is "HEI", "Al Sadd SC" is
 * "SAD", "APIA Leichhardt FC" is "AL".
 *
 * WHY TWO DISTINCTIVE TOKENS GIVE TWO INITIALS RATHER THAN THREE LETTERS OF THE
 * LAST ONE. The latter reads better on the specimens ("APIA Leichhardt FC" ->
 * "LEI" rather than "AL") and I wrote it that way first on exactly that basis.
 * Measured, it is worse on every axis that matters: ±7d collisions 15 -> 26,
 * five fixtures newly painting one badge on both sides ("Grenoble Foot 38" and
 * "Clermont Foot 63" are both "FOO"), and seven new unshippable badges
 * ("South Shields FC" -> "SHI", "San Diego FC" -> "DIE"). Initials keep the
 * discriminating token.
 *
 * This closes 182 of the 207. The 25 it does NOT close are all doubles pairs
 * ("An Lin / Yi Yang" -> "AN "), which take the #3110-pinned path above and are
 * that issue's decision rather than this one's. Filed as #4535.
 */
function shortNameBadge(full: string, distinctive: string[]): string {
  const sliced = teamShortName(full).trim().slice(0, 3);
  // The test is on the SLICE, not on the short name. `teamShortName` handing
  // back a multi-word string is only visible when the first word is shorter
  // than the badge — "AC Milan U20" cuts to "AC ", but "Abbey Hey FC" cuts to
  // "Abb", which is a clean prefix and stays exactly as it shipped. Testing the
  // short name instead re-lettered 963 names that were never broken.
  if (!/\s/.test(sliced)) return sliced.toUpperCase();
  if (distinctive.length === 1) return distinctive[0].slice(0, 3).toUpperCase();
  if (distinctive.length === 2) {
    return distinctive.map(word => word.charAt(0)).join("").toUpperCase();
  }
  // Nothing in the name identifies anybody ("3K FC"). Three glyphs of the name
  // itself still beats a slice that ends in a space.
  return alphanumeric(full).slice(0, 3).toUpperCase();
}

/**
 * Three-glyph strings that may never appear on a crest, whatever produces them.
 *
 * This is a BACKSTOP, not the fix: the structural cases are removed by
 * filtering non-distinctive tokens above, and this catches what is left when
 * three genuinely-distinctive words happen to spell something. Kept explicit
 * and short — a badge is three uppercase letters, so a substring matcher would
 * be all false positives.
 */
const UNSHIPPABLE_BADGES: ReadonlySet<string> = new Set([
  "ASS", "FAG", "FUC", "FUK", "CUM", "COC", "COK", "CNT", "KKK",
  "NIG", "SHT", "TIT", "TWA", "WTF", "JIZ", "PIS", "SEX", "HOE",
]);

/**
 * The crest badge for a surface that must not be able to paint a slur — the one
 * `/events/[id]`'s hero uses (#7270).
 *
 * ── WHY THIS EXISTS RATHER THAN A CALL TO `teamCrestBadge` ───────────────────
 *
 * The event hero carried its own INLINE copy of the initials rule and never
 * called this module at all, so `UNSHIPPABLE_BADGES` — which names "ASS" as its
 * reason to exist — was never consulted. Production, 390px, a live Big 12 game:
 * `/events/15311215` painted `ASS` for "Arizona State Sun Devils" (A·S·S·D cut
 * to three) with `KJ` opposite it.
 *
 * The obvious repair is to swap the inline copy for `teamCrestBadge`. MEASURED
 * OVER THE WHOLE POPULATION, THAT REPAIR IS A REGRESSION, and this function is
 * the reason the swap was not made. 30,340 distinct `events` team names
 * (exhaustive — paged past db-query's 1,000-row cap, not sampled), scored
 * through this module rather than a re-implementation of it:
 *
 *     rule                    unshippable   badges containing a space
 *     inline initials (live)           29                           0
 *     teamCrestBadge                   75                          26
 *     this function                     0                           0
 *
 * All 29 of the live ones carry no logo of either kind, so every one is on a
 * reader's screen when that page is opened. The 75 are not the same 29: the
 * swap fixes all 29 and introduces 73 reader-visible new ones, because
 * `teamCrestBadge` badges a short name by its LAST WORD — "Nigeria" becomes
 * `NIG`, "Detroit Pistons" `PIS`, "Fuchs" `FUC`, "Titans" `TIT`. A racial slur
 * across a national team's crest is not a fix for `ASS`. That residue is
 * `teamCrestBadge`'s own known, filed defect (#4537 — its header says the test
 * is "do not INTRODUCE one", not "never emit one"), and it is not this issue's
 * to reopen.
 *
 * ── THE RULE ─────────────────────────────────────────────────────────────────
 *
 * Take the first candidate that is clean, so the badge can only get better:
 * `teamCrestBadge` first (it is what every other surface draws — notice 35, one
 * card family), then the expression the hero ships today, then nothing. The
 * fallback is what makes this monotone: a name the helper would spoil keeps
 * exactly the badge it has on production right now, and no name anywhere gets a
 * worse one. Verified as an identity, not asserted — over those 30,340 names,
 * every badge this returns is either `teamCrestBadge`'s or today's.
 *
 * ── THE BLAST RADIUS, WHICH IS NOT 29 ───────────────────────────────────────
 *
 * Removing the slurs is the ship, but it is not most of what changes. The hero
 * was the only surface still lettering by raw initials, so adopting the shared
 * rule moves 28,240 of the 30,340 badges. Stated because "a p1 slur fix" and "a
 * 93% rewrite of one tile" deserve to be read as the same sentence:
 *
 *     22,177  gain glyphs — a one-token name showed ONE letter and now shows
 *             three ("Instituto" I -> INS, "Krka" K -> KRK)
 *      6,012  same length, different letters ("Al Nassr Club" ANC -> NAS)
 *         51  lose one glyph, all of one family ("Al Ahli Saudi Club" AAS -> AS)
 *
 * Dangling punctuation goes with it, which the raw split could never avoid:
 * "Wagner Seahawks (W)" WS( -> WAG, "Garcia Beitia / Giordano" GB/ -> GAR,
 * "FC Nantes - More Markets" FN- -> NMM. The 51 are the whole downside and they
 * stay legible; nothing becomes empty.
 *
 * A badge with a SPACE in it is rejected on the same test. `teamCrestBadge`
 * leaves a doubles pair to #3110's rule, which slices the raw string, so
 * "de Minaur / Peers" comes back as `"DE "` — a fragment, #4466's class. Those
 * 26 fall back and keep today's value; closing them properly is that pair rule's
 * job, not a call site's.
 *
 * WHY EMPTY RATHER THAN A CENSORED THIRD GUESS when both candidates are
 * unshippable: a crest tile with nothing in it is honest and the caller already
 * renders it (notice 34 — where a thing cannot be shown honestly, leave the
 * space empty rather than explaining it). Inventing a third lettering to dodge a
 * word would be a rule no other surface applies. On today's population this arm
 * is unreachable — 0 names of 30,340 reach it — and it is kept because it is the
 * only thing standing between a future name and the exact defect this fixes.
 */
export function shippableCrestBadge(
  name: string | null | undefined,
  sportKey?: string | null,
): string {
  const full = (name ?? "").trim();
  if (!full) return "";
  const shippable = (badge: string) =>
    badge !== "" && !UNSHIPPABLE_BADGES.has(badge) && !/\s/.test(badge);
  const preferred = teamCrestBadge(full, sportKey);
  if (shippable(preferred)) return preferred;
  // The expression the hero shipped inline before #7270: a first initial per
  // space-separated word, capped at three. Kept as the fallback rather than
  // deleted, because for the names `teamCrestBadge` spoils it is the value
  // already on production and it is clean.
  const initials = full
    .split(" ")
    .map(word => word.charAt(0))
    .join("")
    .slice(0, 3)
    .toUpperCase();
  return shippable(initials) ? initials : "";
}

/**
 * Onomastic particles: the little words that are part of a PERSON's surname
 * rather than a word in front of it. "Alex de Minaur" shortened to "Minaur"
 * named nobody (#7163) — the event hero printed it against Kasnikowski while
 * the payload served the name correctly.
 *
 * MEASURED, not assembled from particles that sound right, which is what the
 * issue asked for and what every entry in `CLUB_TYPE_SUFFIXES` above already
 * does. Sweep over every DISTINCT multi-word `events` team name, both sides,
 * whole population, 2026-09-19, grouping the token BEFORE the last one:
 *
 *     tennis  de 32 · van 13 · la 9 · der 4 · del 2 · von 2 · le 2 · da 1
 *     mma     de 10 · van 3 · dos 2
 *
 * and every one of those 80 names is a person: "Alex de Minaur",
 * "Van de Zandschulp", "von der Schulenburg", "Meyer auf der Heide",
 * "Santiago De la Fuente", "Huertas del Pino", "Junior dos Santos", "le Roux".
 *
 * THE RULE IS GATED ON THE SPORT, AND THAT IS THE WHOLE DESIGN. The same sweep
 * over the CLUB sports is what rejects the ungated form the issue proposed:
 *
 *     "Sport Lisboa e Benfica"  -> "Benfica" today, "e Benfica" ungated
 *     "Defensa y Justicia"      -> "Justicia"       "y Justicia"
 *     "Tigres de la UANL"       -> "UANL"           "la UANL"
 *     "Heart of Midlothian"     -> "Midlothian"     "of Midlothian"
 *     "Trinidad and Tobago"     -> "Tobago"         "and Tobago"
 *
 * Every one of those is correct today and wrong ungated, so a particle rule
 * that does not know whether it is looking at a person makes the site worse on
 * more names than it fixes. `namesAPerson` is the discriminator #4624 already
 * established for exactly this fork, and it can only ever be opened by a caller
 * that positively knows its sport — so every caller that does not keeps today's
 * output to the character.
 *
 * Deliberately absent: "e", "y", "of", "and", "the", "en", "in", "at", "nad",
 * "los" — conjunctions, prepositions and articles that are measured on CLUB
 * names and name nobody. The second block is not measured as a penultimate
 * token in a person sport today; each is an unambiguous particle in a language
 * the measured block already carries, they cost nothing when they never fire,
 * and they are what lets the walk below cross "auf der" and "van den".
 */
const NAME_PARTICLES: ReadonlySet<string> = new Set([
  "de", // 42  de Minaur, de Sousa
  "van", // 16  van Rooij, van Zijl
  "la", // 9   De la Fuente
  "der", // 4   von der Schulenburg
  "del", // 2   Huertas del Pino
  "von", // 2   von Deichmann
  "le", // 2   le Roux
  "dos", // 2   dos Santos
  "da", // 1   Dutra da Silva
  // Unmeasured as a penultimate token in a person sport; same languages.
  "auf", // German, and "Meyer auf der Heide" needs it to cross "der"
  "den", // Dutch, "van den Broek"
  "das", // Portuguese
  "do", // Portuguese
  "di", // Italian
  "della",
  "dello",
  "degli",
  "du", // French
  "las", // Spanish, "de las Casas"
  "ter", // Dutch, "ter Stegen"
  "ten", // Dutch, "ten Hag"
  "af", // Scandinavian
  "av",
  "zu", // German
  "el", // Arabic
  "bin",
  "abu",
]);

/**
 * Index of the first token of a particled surname, walking LEFT from the last
 * word for as long as the token in front is a particle.
 *
 * A loop rather than one step because the particles stack — "van de
 * Zandschulp", "von der Schulenburg", "Meyer auf der Heide" — and stopping at
 * one would hand back "de Zandschulp", which is the same defect one token
 * along. Matching is case-insensitive because the stored spelling varies on
 * production ("Van de Zandschulp", "Santiago De la Fuente"); the cost of that
 * is a first name like "Van Johnson" returning the whole name instead of
 * "Johnson", which is less short and still a string the person is called —
 * the only direction this module is allowed to move in.
 */
function particledSurnameStart(words: string[]): number {
  let start = words.length - 1;
  while (
    start > 0 &&
    NAME_PARTICLES.has(alphanumeric(words[start - 1]).toLowerCase())
  ) {
    start -= 1;
  }
  return start;
}

/**
 * One side's compact name. Prefer this only where the other side is genuinely
 * unavailable — `teamShortNames` below can additionally catch the case where
 * two teams shorten to the SAME word, which one side alone cannot see.
 *
 * `sportKey` is optional and opens the particle rule above; omitting it keeps
 * the shipped last-word behaviour exactly (#7163).
 */
export function teamShortName(
  name: string | null | undefined,
  abbreviation?: string | null,
  sportKey?: string | null,
): string {
  const full = (name ?? "").trim();
  if (!full) return "";
  // #3110: both halves of a doubles pair, or neither.
  if (isDoublesPair(full)) return full;
  // #4627 — a hand-picked label is FINAL, and it is read BEFORE the rule rather
  // than applied as a repair afterwards, so what a reader sees does not depend
  // on which of the club's three live spellings the row happens to carry.
  const picked = HAND_PICKED_LABELS.get(handPickedKey(full));
  if (picked) return picked;
  // #5634 — a football club is not its city: "Union Berlin", never "Berlin".
  // Up to THREE words only: a longer name is the formal one ("Sport Lisboa e
  // Benfica", "Futebol Clube do Porto", "Tigres de la UANL") and its last word
  // is the name people use, so it takes the rule below exactly as before.
  if (keepsWholeClubName(sportKey)) {
    const whole = wholeClubName(full);
    if (whole.split(/\s+/).length <= WHOLE_CLUB_NAME_MAX_WORDS) return whole;
  }
  const words = full.split(/\s+/);
  if (words.length < 2) return full;
  if (isNonDistinctiveTrailingWord(words[words.length - 1])) return full;
  // #5634 — "Red Sox", not "Sox". Clubs only: a person's name never reaches it.
  if (!namesAPerson(sportKey)) {
    const nickname = twoWordNickname(words);
    if (nickname) return nickname;
  }
  // #7163 — a person's surname carries its particles with it. Gated on the
  // sport, so a club can never reach this: see `NAME_PARTICLES` for the club
  // names the ungated form would have broken.
  if (namesAPerson(sportKey)) {
    const start = particledSurnameStart(words);
    if (start < words.length - 1) return words.slice(start).join(" ");
  }
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
  sportKey?: string | null,
): TeamShortNamePair {
  const homeFull = (home.name ?? "").trim();
  const awayFull = (away.name ?? "").trim();

  const homeShort = teamShortName(homeFull, null, sportKey);
  const awayShort = teamShortName(awayFull, null, sportKey);

  // Did the last-word rule have to give up on this side? (A single-word name
  // has nothing to shorten and has not "given up" — it is already compact.)
  //
  // #3110: a doubles pair is compact in the same way — "Siniakova / Townsend"
  // is two surnames and there is nothing left to drop — so it must not reach
  // for the abbreviation rescue and print the chip's own "S/T" a second time
  // underneath it. Unreachable on today's data (pairs have no `teams` row, so
  // no abbreviation exists to rescue with: 0 of 252 measured), and here so it
  // stays unreachable the day one does.
  //
  // #5634: a name that IS a two-word nickname ("Red Sox") is compact too.
  const gaveUp = (full: string, short: string) =>
    short === full &&
    full.split(/\s+/).length >= 2 &&
    !isDoublesPair(full) &&
    twoWordNickname(full.split(/\s+/)) === null;
  // #5634 — a football club's whole name is CHOSEN, not given up on, so the
  // rescue below is asked exactly as it was before that rule: from what the
  // last-word rule would have printed. Seattle Sounders FC v Real Salt Lake
  // keeps "SEA / RSL"; only the city-last labels move.
  const lastWordRule = (full: string, short: string) =>
    keepsWholeClubName(sportKey) ? teamShortName(full) : short;
  const homeGaveUp = gaveUp(homeFull, lastWordRule(homeFull, homeShort));
  const awayGaveUp = gaveUp(awayFull, lastWordRule(awayFull, awayShort));
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
